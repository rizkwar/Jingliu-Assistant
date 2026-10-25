"""Local speech engine. JSON commands on stdin, progress events on stdout.

Run separately so Stop can cancel even a model download or native inference call.
No OpenRouter key, conversation history, or Qt dependency is needed here.
"""

from concurrent.futures import Future
from contextlib import redirect_stdout
import json
import logging
import queue
import sys
import threading

from .voice_settings import VOICES, playback_sample_rate, validate_rate
from .reference_voice import inspect_reference, VoiceSetupError


class PocketSpeaker:
    def __init__(self):
        self.model = None
        self.voices = {}
        self.reference_keys = {}

    def prepare(self, voice, report):
        reference = None
        if voice not in VOICES:
            reference = inspect_reference(voice)
        import torch
        from pocket_tts import TTSModel
        if self.model is None:
            report("loading")
            torch.set_num_threads(2)
            self.model = TTSModel.load_model(language="english_2026-10")
        if reference is not None:
            if not getattr(self.model, "has_voice_cloning", False):
                raise VoiceSetupError(
                    "The loaded Pocket TTS model supports stock voices only. Reference voices need access to "
                    "kyutai/pocket-tts on Hugging Face. Review its model access terms, authenticate with HF_TOKEN "
                    "in .env or the Hugging Face CLI, then reload settings and restart the voice engine. "
                    "See docs/reference-voice.md. No stock voice was substituted."
                )
            if self.reference_keys.get(voice) != reference.fingerprint:
                report("preparing")
                for old in list(self.reference_keys):
                    if old != voice:
                        self.reference_keys.pop(old)
                        self.voices.pop(old, None)
                # The validator bounds duration; no external URL or serialized state is accepted.
                self.voices[voice] = self.model.get_state_for_audio_prompt(reference.path)
                self.reference_keys[voice] = reference.fingerprint
            return
        if voice not in self.voices:
            report("loading")
            self.voices[voice] = self.model.get_state_for_audio_prompt(voice)

    def speak(self, text, voice, volume, report, rate=100):
        from .audio_playback import play_chunks

        validate_rate(rate)
        self.prepare(voice, report)
        report("preparing")
        def chunks():
            for chunk in self.model.generate_audio_stream(self.voices[voice], text):
                yield chunk.detach().cpu().numpy()
        play_chunks(chunks(), playback_sample_rate(self.model.sample_rate, rate), volume,
                    report, getattr(report, 'playback', lambda *_: None))


class ChatterboxSpeaker:
    """The natural voice mode: Resemble AI's Chatterbox, cloned from the character's recording.

    Runs from its own environment (.cache/voice-lab). Settings match the calm, composed
    delivery chosen in listening tests: exaggeration 0.4, CFG weight 0.4.
    """

    EXAGGERATION = .4
    CFG_WEIGHT = .4
    def __init__(self):
        self.model = None
        self.reference_key = None
        # One worker renders phrases in order, so the next is ready while this one plays.
        # The phrase being spoken right now always goes first.
        self.lock = threading.Lock()
        self.wake = threading.Condition()
        self.pending = []   # (text, voice, future) not started yet
        self.rendered = {}  # text → Future of its audio
        self.thread = None

    def prepare(self, voice, report):
        with self.lock:
            self._prepare(voice, report)

    def _prepare(self, voice, report):
        if voice in VOICES:
            raise VoiceSetupError("Chatterbox speaks only in the character's own voice. Choose her reference "
                                  "recording in Settings, or switch the voice engine back to Pocket TTS.")
        reference = inspect_reference(voice)
        import torch
        from chatterbox.tts import ChatterboxTTS
        if self.model is None:
            report("loading")
            device = "cuda" if torch.cuda.is_available() else "cpu"
            self.model = ChatterboxTTS.from_pretrained(device=device)
            getattr(report, "info", lambda *_: None)(
                "Chatterbox is using the GPU." if device == "cuda" else
                "Chatterbox is running on the CPU, so she will start speaking slowly. "
                "Switch on the NVIDIA GPU and run Setup Chatterbox.cmd for real-time speech.")
        if self.reference_key != reference.fingerprint:
            report("preparing")
            self.model.prepare_conditionals(reference.path, exaggeration=self.EXAGGERATION)
            self.reference_key = reference.fingerprint
            # The first generation after loading is much slower (GPU warm-up); spend it here,
            # while she is still thinking, rather than on her first real phrase.
            self.model.generate("Mm.", exaggeration=self.EXAGGERATION, cfg_weight=self.CFG_WEIGHT)

    def _render(self, text, voice):
        with self.lock:
            self._prepare(voice, lambda *_: None)
            audio = self.model.generate(text, exaggeration=self.EXAGGERATION, cfg_weight=self.CFG_WEIGHT)
        return audio.squeeze(0).detach().cpu().numpy()

    def _loop(self):
        while True:
            with self.wake:
                while not self.pending:
                    self.wake.wait()
                text, voice, future = self.pending.pop(0)
            if not future.set_running_or_notify_cancel():
                continue
            try:
                future.set_result(self._render(text, voice))
            except BaseException as exc:  # Reported to whoever speaks the phrase.
                future.set_exception(exc)

    def _submit(self, text, voice, first=False):
        with self.wake:
            future = self.rendered.get(text)
            if future is None:
                future = self.rendered[text] = Future()
                self.pending.insert(0 if first else len(self.pending), (text, voice, future))
            elif first:
                for index, item in enumerate(self.pending):
                    if item[0] == text:
                        self.pending.insert(0, self.pending.pop(index))
                        break
            if self.thread is None:
                self.thread = threading.Thread(target=self._loop, name="chatterbox", daemon=True)
                self.thread.start()
            self.wake.notify()
        return future

    def ahead(self, text, voice):
        """A phrase that will be spoken soon: start rendering it now, after any earlier ones."""
        if text:
            self._submit(text, voice)

    def speak(self, text, voice, volume, report, rate=100):
        from .audio_playback import play_chunks

        validate_rate(rate)
        # Chatterbox renders a whole phrase at once. Phrases announced in advance are usually
        # finished by now; the next ones keep rendering while this one plays. Queue this one
        # first, before waiting on the model, so the worker cannot start a later phrase instead.
        future = self._submit(text, voice, first=True)
        self.prepare(voice, report)
        report("preparing")
        try:
            audio = future.result()
        finally:
            with self.wake:
                self.rendered.pop(text, None)
        play_chunks([audio], playback_sample_rate(self.model.sr, rate), volume,
                    report, getattr(report, 'playback', lambda *_: None))


ENGINES = {"pocket": PocketSpeaker, "chatterbox": ChatterboxSpeaker}


def run(input_stream=None, output_stream=None, speaker=None, engine="pocket"):
    input_stream = input_stream or sys.stdin
    output_stream = output_stream or sys.stdout
    speaker = speaker or ENGINES.get(engine, PocketSpeaker)()
    logging.basicConfig(level=logging.ERROR, stream=sys.stderr)
    writing = threading.Lock()

    def emit(job_id, kind, **values):
        with writing:
            output_stream.write(json.dumps({"id": job_id, "type": kind, **values}) + "\n")
            output_stream.flush()

    # Commands are read on their own thread: an "ahead" hint can arrive while a phrase plays.
    jobs = queue.Queue()

    def read():
        from .pipe_lines import lines
        for line in lines(input_stream):  # Never a blocking pipe read: see pipe_lines.
            try:
                command = json.loads(line)
            except ValueError:
                continue
            if isinstance(command, dict) and command.get("action") == "ahead":
                if hasattr(speaker, "ahead"):
                    try:
                        speaker.ahead(str(command.get("text", "")), command.get("voice", ""))
                    except Exception:
                        pass  # A hint never fails a job; the phrase is rendered when spoken instead.
                continue
            jobs.put(line)
        jobs.put(None)

    threading.Thread(target=read, daemon=True).start()
    for line in iter(jobs.get, None):
        job_id = ""
        try:
            command = json.loads(line)
            job_id = command["id"]
            # Third-party progress output must never corrupt the JSON protocol.
            with redirect_stdout(sys.stderr):
                report = lambda state: emit(job_id, "status", state=state)
                report.playback = lambda level, at: emit(job_id, "playback", level=level, at=at)
                report.info = lambda message: emit(job_id, "info", message=message)
                if command.get("action") == "prepare":
                    speaker.prepare(command["voice"], report)
                else:
                    speaker.speak(command["text"], command["voice"], command["volume"], report,
                                  rate=validate_rate(command.get("rate", 100)))
            emit(job_id, "done")
        except VoiceSetupError as exc:
            emit(job_id, "error", message=str(exc))
        except ImportError:
            emit(job_id, "error", message="Voice dependencies are missing. Run pip install -r requirements.txt.")
        except Exception:
            # Upstream errors can contain file paths or request data; display a stable message.
            emit(job_id, "error", message=(
                "Voice playback failed. Check your internet connection for the first model download "
                "and your Windows default speaker, then try Preview. Text chat still works."
            ))


if __name__ == "__main__":
    run(engine=sys.argv[sys.argv.index("--engine") + 1] if "--engine" in sys.argv else "pocket")

