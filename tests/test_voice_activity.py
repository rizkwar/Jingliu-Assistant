from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np

from companion.voice_activity import AutomaticCapture, SileroDetector, UtteranceBuffer


class UtteranceTests(unittest.TestCase):
    def feed(self, buffer, count, speech=False):
        for _ in range(count):
            buffer.feed(np.full(1600, 0.2 if speech else 0, dtype=np.float32), speech)

    def test_sustained_speech_keeps_preroll_and_finishes_after_pause(self):
        buffer = UtteranceBuffer()
        self.feed(buffer, 20)
        self.feed(buffer, 2, True)
        self.assertFalse(buffer.started)
        self.feed(buffer, 1, True)
        self.assertTrue(buffer.started)
        self.assertEqual(len(buffer.audio()), 11200)
        self.feed(buffer, 11)
        self.assertFalse(buffer.done)
        self.feed(buffer, 1)
        self.assertTrue(buffer.done)
        self.assertFalse(buffer.timed_out)

    def test_brief_speech_candidate_does_not_trigger_an_utterance(self):
        buffer = UtteranceBuffer(idle_seconds=2)
        self.feed(buffer, 2, True)
        self.feed(buffer, 18)
        self.assertTrue(buffer.timed_out)
        self.assertFalse(buffer.started)
        self.assertEqual(len(buffer.audio()), 0)

    def test_speech_after_a_short_pause_resets_endpoint_timer(self):
        buffer = UtteranceBuffer(pause_ms=800)
        self.feed(buffer, 5, True)
        self.feed(buffer, 7)
        self.feed(buffer, 2, True)
        self.feed(buffer, 7)
        self.assertFalse(buffer.done)
        self.feed(buffer, 1)
        self.assertTrue(buffer.done)

    def test_continuous_speech_is_bounded_to_thirty_seconds(self):
        buffer = UtteranceBuffer()
        self.feed(buffer, 500, True)
        self.assertTrue(buffer.done)
        self.assertEqual(len(buffer.audio()), 16000 * 30)
        self.assertFalse(buffer.timed_out)

    def test_invalid_audio_and_pause_are_rejected(self):
        for pause in [True, 0, 2501]:
            with self.assertRaises(ValueError):
                UtteranceBuffer(pause_ms=pause)
        with self.assertRaises(ValueError):
            UtteranceBuffer().feed(np.full(1600, np.nan), False)

    def test_bundled_detector_rejects_silence_without_downloading_a_model(self):
        detector = SileroDetector()
        for _ in range(3):
            self.assertFalse(detector(np.zeros(1600, dtype=np.float32)))


class AutomaticCaptureTests(unittest.TestCase):
    def fake_audio(self):
        class Abort(Exception):
            pass
        class Stream:
            def __init__(self, **options):
                self.options = options
                self.callback = options["callback"]
                self.closed = False
            def start(self):
                pass
            def abort(self):
                self.aborted = True
            def close(self):
                self.closed = True
        return SimpleNamespace(InputStream=Stream, CallbackAbort=Abort,
                               query_devices=lambda *args: {"default_samplerate": 48000})

    def test_native_rate_audio_is_resampled_and_closed_before_returning_utterance(self):
        audio = self.fake_audio()
        with patch.dict("sys.modules", {"sounddevice": audio}), patch("companion.voice_activity.SileroDetector", return_value=lambda block: True):
            capture = AutomaticCapture(device=0)
        for _ in range(3):
            capture.stream.callback(np.ones((4800, 1), dtype=np.float32) * 0.1, 4800, None, SimpleNamespace(input_overflow=False))
        capture.poll()
        samples, rate = capture.finish()
        self.assertEqual(capture.stream.options["device"], 0)
        self.assertEqual(rate, 16000)
        self.assertEqual(len(samples), 4800)
        self.assertTrue(capture.stream.closed)
        self.assertTrue(capture.stream.aborted)

    def test_capture_backlog_fails_instead_of_growing_without_bound(self):
        audio = self.fake_audio()
        with patch.dict("sys.modules", {"sounddevice": audio}), patch("companion.voice_activity.SileroDetector", return_value=lambda block: False):
            capture = AutomaticCapture()
        with self.assertRaises(audio.CallbackAbort):
            for _ in range(26):
                capture.stream.callback(np.zeros((4800, 1), dtype=np.float32), 4800, None, SimpleNamespace(input_overflow=False))
        self.assertTrue(capture.overflowed)
        with self.assertRaises(RuntimeError):
            capture.poll()
        capture.close()
