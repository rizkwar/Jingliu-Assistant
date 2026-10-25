import sys
import time
from threading import Event, Thread
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np
from companion.audio_playback import play_chunks


class CallbackStop(Exception):
    pass


class CallbackAbort(Exception):
    pass


class AudioPlaybackTests(unittest.TestCase):
    def play(self, chunks, volume=50, sample_rate=1000):
        played, streams, events = [], [], []

        class Output:
            def __init__(self, **kwargs):
                streams.append(kwargs)
                self.options = kwargs
                self.stop = Event()

            def __enter__(self):
                def pump():
                    try:
                        while not self.stop.is_set():
                            out = np.empty((self.options['blocksize'], 1), dtype=np.float32)
                            now = time.monotonic()
                            try:
                                self.options['callback'](out, len(out), SimpleNamespace(
                                    currentTime=now, outputBufferDacTime=now + .04), None)
                            except CallbackStop:
                                played.append(out.copy())
                                break
                            played.append(out.copy())
                            time.sleep(.002)
                    finally:
                        self.options['finished_callback']()
                self.thread = Thread(target=pump)
                self.thread.start()
                return self

            def abort(self):
                self.stop.set()

            def __exit__(self, *args):
                self.abort()
                self.thread.join(2)

        device = SimpleNamespace(OutputStream=Output, CallbackStop=CallbackStop, CallbackAbort=CallbackAbort)
        with patch.dict(sys.modules, {'sounddevice': device}):
            play_chunks(chunks, sample_rate, volume, lambda state: events.append(('status', state)),
                        lambda level, at, rms=0.: events.append(("level", level, at, time.monotonic())))
        return played, streams, events

    def test_output_gain_clipping_chunk_order_and_final_padding(self):
        played, streams, events = self.play([np.full(13, .4), np.full(12, -.8), np.full(5, 3.)])
        blocks = [block.ravel() for block in played if np.any(block)]
        np.testing.assert_allclose(np.concatenate(blocks), [.2]*13 + [-.4]*12 + [1.]*5 + [0.]*10)
        self.assertEqual(streams[0]['samplerate'], 1000)
        self.assertEqual(streams[0]['blocksize'], 20)
        self.assertIn(('status', 'speaking'), events)
        levels = [event for event in events if event[0] == 'level']
        self.assertTrue(any(e[1] > 0 for e in levels))
        self.assertEqual(levels[-1][1], 0)
        self.assertTrue(all(e[2] - e[3] > 0 for e in levels))

    def test_generated_silence_and_muted_pcm_never_open_mouth(self):
        for chunks, volume in [([np.zeros(80)], 70), ([np.ones(80)], 0)]:
            _, _, events = self.play(chunks, volume)
            self.assertTrue(all(event[1] == 0 for event in events if event[0] == 'level'))

    def test_level_uses_post_volume_rms(self):
        _, _, events = self.play([np.full(40, .1)], volume=50)
        levels = [event[1] for event in events if event[0] == 'level' and event[1] > 0]
        self.assertTrue(levels)
        for level in levels:
            self.assertAlmostEqual(level, (.05 - .003) * 7, places=5)

    def test_generation_gap_reports_silence_and_empty_generation_fails(self):
        def chunks():
            yield np.ones(40)
            time.sleep(.04)
            yield np.ones(40)
        _, _, events = self.play(chunks())
        values = [e[1] for e in events if e[0] == 'level']
        first = next(i for i, value in enumerate(values) if value)
        self.assertIn(0, values[first + 1:-1])
        with self.assertRaises(RuntimeError):
            self.play([])

    def test_producer_failure_propagates_without_leaving_callback_thread(self):
        def chunks():
            yield np.ones(40)
            raise ValueError('fake generation failure')
        with self.assertRaises(ValueError):
            self.play(chunks())
