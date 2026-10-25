"""Local speech detection and bounded utterance collection, independent of Qt."""

from collections import deque
import math
import time


SAMPLE_RATE = 16000


class SileroDetector:
    """Use the VAD bundled with the pinned Faster-Whisper package, on a rolling window."""

    def __init__(self):
        import numpy as np
        from faster_whisper.vad import VadOptions, get_speech_timestamps, get_vad_model

        get_vad_model()  # Load locally before opening the microphone.
        self._timestamps = get_speech_timestamps
        self._options = VadOptions(threshold=0.5, min_speech_duration_ms=64,
                                   min_silence_duration_ms=100, speech_pad_ms=0)
        self._tail = np.zeros(SAMPLE_RATE, dtype=np.float32)

    def __call__(self, audio):
        import numpy as np

        self._tail = np.concatenate((self._tail, audio))[-SAMPLE_RATE:]
        spans = self._timestamps(self._tail, self._options, sampling_rate=SAMPLE_RATE)
        return bool(spans and spans[-1]["end"] > len(self._tail) - len(audio))


class EchoGate:
    """While her voice plays from the speakers, speech counts as the person's only when the
    microphone is clearly louder than her own echo plus the room's noise would be. How strongly
    her voice reaches the microphone is learned while she speaks (speakers: strongly; headphones:
    barely), and the room's noise while she is silent."""

    QUIET = .004       # Her output RMS below this: she is between words.
    MARGIN = 2.0       # About +6 dB over a cautious estimate of her echo.
    WINDOW = .35       # Her loudest moment this recent covers timing differences and room echo.
    LEARN = 5          # Echo measurements needed before she can be interrupted at all.

    def __init__(self):
        self._played = deque()             # (time, her output RMS)
        self._ratios = deque(maxlen=60)    # (microphone RMS - noise) / her output RMS, while she plays.
        self.noise = .002                  # The room, as the microphone hears it while she is silent.

    def playing(self, rms, now=None):
        now = time.monotonic() if now is None else now
        self._played.append((now, float(rms)))
        while self._played and self._played[0][0] < now - 2:
            self._played.popleft()

    def recent(self, now=None):
        now = time.monotonic() if now is None else now
        return max((rms for at, rms in self._played if at >= now - self.WINDOW), default=0.)

    def allows(self, microphone_rms, now=None):
        """True when this block may be the person speaking."""
        played = self.recent(now)
        if played < self.QUIET:
            # She is silent: learn the room's noise (slowly up, quickly down) and detect normally.
            rate = .05 if microphone_rms > self.noise else .3
            self.noise += (microphone_rms - self.noise) * rate
            return True
        excess = max(0., microphone_rms - self.noise)
        ratio = excess / played
        known = len(self._ratios) >= self.LEARN
        # A cautious (high) estimate of her echo: the upper quarter of what she alone produced.
        coupling = sorted(self._ratios)[len(self._ratios) * 3 // 4] if known else None
        louder = known and excess > max(coupling * played * self.MARGIN, self.noise * 2)
        if played >= 3 * self.QUIET and not louder:
            self._ratios.append(ratio)  # Learn only from clear moments of her alone.
        return louder


class UtteranceBuffer:
    """Collect after sustained speech, end after a pause, and bound all retained audio."""

    def __init__(self, pause_ms=1200, max_seconds=30, idle_seconds=30, prefix_seconds=0.7):
        if type(pause_ms) is not int or not 600 <= pause_ms <= 2500:
            raise ValueError("Speech pause must be from 600 to 2,500 milliseconds.")
        self.pause_samples = pause_ms * SAMPLE_RATE // 1000
        self.max_samples = int(max_seconds * SAMPLE_RATE)
        self.idle_samples = int(idle_seconds * SAMPLE_RATE)
        self.prefix_samples = int(prefix_seconds * SAMPLE_RATE)
        self._prefix = deque()
        self._prefix_size = 0
        self._frames = []
        self._size = 0
        self._elapsed = 0
        self._onset = 0
        self._silence = 0
        self.started = False
        self.done = False
        self.timed_out = False

    def feed(self, audio, is_speech):
        import numpy as np

        if self.done:
            return
        audio = np.asarray(audio, dtype=np.float32).reshape(-1)
        if not len(audio) or not np.isfinite(audio).all():
            raise ValueError("Invalid speech detector audio.")
        self._elapsed += len(audio)
        if not self.started:
            self._prefix.append(audio.copy())
            self._prefix_size += len(audio)
            while self._prefix_size - len(self._prefix[0]) >= self.prefix_samples:
                self._prefix_size -= len(self._prefix.popleft())
            self._onset = self._onset + len(audio) if is_speech else 0
            if self._onset >= math.ceil(SAMPLE_RATE * 0.3):
                self.started = True
                self._frames = list(self._prefix)
                self._size = self._prefix_size
                self._prefix.clear()
            elif self._elapsed >= self.idle_samples:
                self.timed_out = self.done = True
        else:
            remaining = self.max_samples - self._size
            self._frames.append(audio[:remaining].copy())
            self._size += min(remaining, len(audio))
            self._silence = 0 if is_speech else self._silence + len(audio)
            self.done = self._silence >= self.pause_samples or self._size >= self.max_samples

    def audio(self):
        import numpy as np

        return np.concatenate(self._frames) if self._frames else np.empty(0, dtype=np.float32)

    def hold(self):
        """She is speaking: waiting for the person to talk is not idling."""
        self._elapsed = 0


class AutomaticCapture:
    """Keep the audio callback small; run resampling and VAD in the child process loop."""

    def __init__(self, device=None, pause_ms=1200, gate=None):
        from math import gcd
        import queue
        import numpy as np
        import sounddevice as sd
        from scipy.signal import resample_poly

        self.detector = SileroDetector()
        # With a gate (talking over her), less audio from before the onset: it holds her echo.
        self.gate = gate
        self.utterance = UtteranceBuffer(pause_ms, prefix_seconds=0.45 if gate is not None else 0.7)
        self.sample_rate = int(sd.query_devices(device, "input")["default_samplerate"])
        divisor = gcd(self.sample_rate, SAMPLE_RATE)
        self._resample = lambda audio: resample_poly(audio, SAMPLE_RATE // divisor, self.sample_rate // divisor).astype(np.float32)
        self._queue = queue.Queue(maxsize=25)
        self._level = 0
        self.overflowed = False

        def callback(indata, frames, timing, status):
            if status.input_overflow:
                self.overflowed = True
                raise sd.CallbackAbort
            try:
                self._queue.put_nowait(indata[:, 0].copy())
            except queue.Full:
                self.overflowed = True
                raise sd.CallbackAbort

        self.stream = sd.InputStream(device=device, samplerate=self.sample_rate,
                                     blocksize=self.sample_rate // 10, channels=1,
                                     dtype="float32", callback=callback)
        try:
            self.stream.start()
        except Exception:
            self.stream.close()
            raise

    def poll(self):
        import queue
        import numpy as np

        if self.overflowed:
            raise RuntimeError("Audio capture overflow")
        while not self.utterance.done:
            try:
                audio = self._queue.get_nowait()
            except queue.Empty:
                break
            self._level = min(100, int(float(np.max(np.abs(audio))) * 400))
            rms = float(np.sqrt(np.mean(audio * audio)))
            audio = self._resample(audio) if self.sample_rate != SAMPLE_RATE else audio
            speech = self.detector(audio)
            if self.gate is not None and not self.utterance.started:
                if self.gate.recent() >= EchoGate.QUIET:
                    self.utterance.hold()
                speech = speech and self.gate.allows(rms)
            self.utterance.feed(audio, speech)

    @property
    def full(self):
        return self.utterance.done

    @property
    def speaking(self):
        return self.utterance.started

    @property
    def timed_out(self):
        return self.utterance.timed_out

    def level(self):
        return self._level

    def close(self):
        self.stream.abort()
        self.stream.close()

    def finish(self):
        self.close()
        return self.utterance.audio(), SAMPLE_RATE
