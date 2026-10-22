"""Local speech engine. JSON commands on stdin, progress events on stdout.

Run separately so Stop can cancel even a model download or native inference call.
No API key, conversation history, or Qt dependency is needed here.
"""

from contextlib import redirect_stdout
import json
import logging
import sys


class PocketSpeaker:
    def __init__(self):
        self.model = None
        self.voices = {}

    def prepare(self, voice, report):
        import torch
        from pocket_tts import TTSModel

        if self.model is None:
            report("loading")
            torch.set_num_threads(2)
            self.model = TTSModel.load_model(language="english_2026-10")
        if voice not in self.voices:
            report("loading")
            self.voices[voice] = self.model.get_state_for_audio_prompt(voice)

    def speak(self, text, voice, volume, report):
        import numpy as np
        import sounddevice as sd

        self.prepare(voice, report)
        report("preparing")
        first = True
        with sd.OutputStream(samplerate=self.model.sample_rate, channels=1, dtype="float32") as output:
            for chunk in self.model.generate_audio_stream(self.voices[voice], text):
                pcm = chunk.detach().cpu().numpy().astype(np.float32).reshape(-1, 1)
                if not pcm.size:
                    continue
                if first:
                    report("speaking")
                    first = False
                output.write(np.clip(pcm * (volume / 100), -1, 1))
        if first:
            raise RuntimeError("No audio was generated")


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
                if command.get("action") == "prepare":
                    speaker.prepare(command["voice"], report)
                else:
                    speaker.speak(command["text"], command["voice"], command["volume"], report)
            emit(job_id, "done")
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

