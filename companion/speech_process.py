"""Local speech engine. JSON commands on stdin, progress events on stdout.

Run separately so Stop can cancel even a model download or native inference call.
No OpenRouter key, conversation history, or Qt dependency is needed here.
"""

from contextlib import redirect_stdout
import json
import logging
import sys

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

    def prepare(self, voice, report):
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

    def speak(self, text, voice, volume, report, rate=100):
        from .audio_playback import play_chunks

        validate_rate(rate)
        self.prepare(voice, report)
        report("preparing")
        # Chatterbox renders a whole phrase at once; the app already sends one phrase at a time.
        audio = self.model.generate(text, exaggeration=self.EXAGGERATION, cfg_weight=self.CFG_WEIGHT)
        play_chunks([audio.squeeze(0).detach().cpu().numpy()], playback_sample_rate(self.model.sr, rate), volume,
                    report, getattr(report, 'playback', lambda *_: None))


ENGINES = {"pocket": PocketSpeaker, "chatterbox": ChatterboxSpeaker}


def run(input_stream=None, output_stream=None, speaker=None, engine="pocket"):
    input_stream = input_stream or sys.stdin
    output_stream = output_stream or sys.stdout
    speaker = speaker or ENGINES.get(engine, PocketSpeaker)()
    logging.basicConfig(level=logging.ERROR, stream=sys.stderr)

    def emit(job_id, kind, **values):
        output_stream.write(json.dumps({"id": job_id, "type": kind, **values}) + "\n")
        output_stream.flush()

    for line in input_stream:
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

