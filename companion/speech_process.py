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


def run(input_stream=None, output_stream=None, speaker=None):
    input_stream = input_stream or sys.stdin
    output_stream = output_stream or sys.stdout
    speaker = speaker or PocketSpeaker()
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
    run()

