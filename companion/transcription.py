"""Local English speech recognition, with no UI or microphone dependency."""

from math import gcd

from .config import PROJECT_ROOT


class Transcriber:
    def __init__(self):
        self.models = {}

    def transcribe(self, audio, sample_rate, model_name="base.en", report=lambda state: None):
        import numpy as np
        from scipy.signal import resample_poly

        audio = np.asarray(audio, dtype=np.float32).flatten()
        if len(audio) < sample_rate * 0.3:
            return ""
        if not np.isfinite(audio).all():
            raise ValueError("Invalid microphone samples")
        if float(np.max(np.abs(audio))) < 0.001:
            return ""
        if sample_rate != 16000:
            divisor = gcd(int(sample_rate), 16000)
            audio = resample_poly(audio, 16000 // divisor, int(sample_rate) // divisor).astype(np.float32)
        if model_name not in self.models:
            report("loading")
            from faster_whisper import WhisperModel

            # One selected model in RAM; changing models releases the previous instance.
            self.models.clear()
            self.models[model_name] = WhisperModel(
                model_name, device="cpu", compute_type="int8", cpu_threads=2, num_workers=1,
                download_root=str(PROJECT_ROOT / ".cache" / "whisper"),
            )
        report("transcribing")
        segments, _ = self.models[model_name].transcribe(
            audio, language="en", beam_size=1, vad_filter=True,
            condition_on_previous_text=False, without_timestamps=True,
        )
        return " ".join(segment.text.strip() for segment in segments).strip()
