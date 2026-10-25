"""Bounded output playback, with envelopes timed to PortAudio's DAC clock.

PCM/gain/RMS work and JSON reporting stay outside the real-time callback.
The callback only copies a prepared block and appends bounded telemetry.
"""
from collections import deque
from threading import Event, Thread
import time


def play_chunks(chunks, sample_rate, volume, report, playback):
    import numpy as np
    import sounddevice as sd

    frames = max(1, round(sample_rate * .02))
    blocks = deque()
    telemetry = deque(maxlen=128)
    finished, reporting_done = Event(), Event()
    ended = False
    callback_failed = False
    reporter_failed = False
    started = False

    def callback(outdata, count, timing, status):
        nonlocal callback_failed
        outdata.fill(0)
        if count != frames:
            callback_failed = True
            raise sd.CallbackAbort
        block = blocks.popleft() if blocks else None
        if block is not None:
            outdata[:, 0] = block[0]
        # PortAudio timestamps are in its stream clock, translated at callback
        # time into the process-shared monotonic clock used by the Qt controller.
        at = time.monotonic() + max(0., timing.outputBufferDacTime - timing.currentTime)
        telemetry.append((at, block[1] if block is not None else 0., block is not None,
                          block[2] if block is not None else 0.))
        if block is None and ended:
            raise sd.CallbackStop  # finished_callback runs after buffered audio drains.

    def send_levels():
        nonlocal reporter_failed
        announced = False
        try:
            while not reporting_done.is_set() or telemetry:
                if not telemetry:
                    reporting_done.wait(.005)
                    continue
                at, level, has_audio, rms = telemetry.popleft()
                if has_audio and not announced:
                    report('speaking')
                    announced = True
                playback(level, at, rms)
        except Exception:
            reporter_failed = True

    worker = Thread(target=send_levels, daemon=True)
    with sd.OutputStream(samplerate=sample_rate, blocksize=frames, channels=1,
                         dtype='float32', callback=callback,
                         finished_callback=finished.set) as output:
        # Context entry starts callbacks; empty generation gaps produce silence.
        worker.start()

        def enqueue(samples):
            nonlocal started
            # About half a second of PCM, regardless of how fast inference runs.
            while len(blocks) >= 25:
                if finished.is_set() or reporter_failed:
                    raise RuntimeError('Audio output stopped')
                time.sleep(.005)
            if finished.is_set() or reporter_failed:
                raise RuntimeError('Audio output stopped')
            rms = float(np.sqrt(np.mean(samples * samples)))
            level = min(1., max(0., (rms - .003) * 7.))
            blocks.append((samples, level, rms))
            started = True

        pending = np.empty(0, dtype=np.float32)
        try:
            for chunk in chunks:
                pcm = np.asarray(chunk, dtype=np.float32).reshape(-1)
                if not pcm.size:
                    continue
                pcm = np.clip(pcm * (volume / 100), -1, 1)
                if pending.size:
                    pcm = np.concatenate((pending, pcm))
                count = (len(pcm) // frames) * frames
                for offset in range(0, count, frames):
                    enqueue(pcm[offset:offset + frames].copy())
                pending = pcm[count:].copy()
            if pending.size:
                block = np.zeros(frames, dtype=np.float32)
                block[:len(pending)] = pending
                enqueue(block)
            ended = True
            if not started:
                raise RuntimeError('No audio was generated')
            deadline = time.monotonic() + 10
            while not finished.wait(.02):
                if time.monotonic() > deadline:
                    raise RuntimeError('Audio output did not drain')
            if callback_failed or reporter_failed:
                raise RuntimeError('Audio output failed')
        finally:
            ended = True
            output.abort() if not finished.is_set() else None
            reporting_done.set()
            worker.join(timeout=2)
    if reporter_failed:
        raise RuntimeError('Playback reporting failed')
