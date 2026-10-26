from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np

from companion.voice.activity import AutomaticCapture, SileroDetector, UtteranceBuffer


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
        with patch.dict("sys.modules", {"sounddevice": audio}), patch("companion.voice.activity.SileroDetector", return_value=lambda block: True):
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
        with patch.dict("sys.modules", {"sounddevice": audio}), patch("companion.voice.activity.SileroDetector", return_value=lambda block: False):
            capture = AutomaticCapture()
        with self.assertRaises(audio.CallbackAbort):
            for _ in range(26):
                capture.stream.callback(np.zeros((4800, 1), dtype=np.float32), 4800, None, SimpleNamespace(input_overflow=False))
        self.assertTrue(capture.overflowed)
        with self.assertRaises(RuntimeError):
            capture.poll()
        capture.close()


class EchoGateTests(unittest.TestCase):
    """Talking over her: her echo alone never counts as the person; louder speech does."""

    def feed(self, gate, seconds, her, microphone, start=0.):
        results = []
        for step in range(int(seconds * 10)):
            now = start + step / 10
            gate.playing(her(now), now)
            results.append(gate.allows(microphone(now), now))
        return results

    def test_her_echo_alone_is_not_the_person_however_loud(self):
        from companion.voice.activity import EchoGate
        gate = EchoGate()
        her = lambda t: .03 + .02 * abs(((t * 3.7) % 2) - 1)  # She varies in loudness.
        allowed = self.feed(gate, 8, her, lambda t: .002 + .6 * her(t))  # Speakers: strong echo plus room noise.
        self.assertFalse(any(allowed))

    def test_the_person_speaking_up_over_her_is_heard(self):
        from companion.voice.activity import EchoGate
        gate = EchoGate()
        her = lambda t: .04
        self.feed(gate, 3, her, lambda t: .002 + .6 * her(t))
        allowed = self.feed(gate, 1, her, lambda t: .002 + .6 * her(t) + .06, start=3)
        self.assertTrue(all(allowed))

    def test_while_she_is_silent_detection_is_ordinary_and_the_room_is_learned(self):
        from companion.voice.activity import EchoGate
        gate = EchoGate()
        self.assertTrue(all(self.feed(gate, 4, lambda t: 0., lambda t: .006)))
        self.assertLess(abs(gate.noise - .006), .001)  # Rises slowly on purpose, so speech cannot pass as noise.

    def test_before_her_echo_is_known_she_cannot_be_interrupted(self):
        from companion.voice.activity import EchoGate
        gate = EchoGate()
        self.assertFalse(any(self.feed(gate, .3, lambda t: .04, lambda t: .5)))


class BargeCommandTests(unittest.TestCase):
    def test_listening_over_her_gives_the_capture_an_echo_gate_fed_by_her_levels(self):
        import io
        import json
        from companion.voice.microphone_process import run
        made = []

        class FakeCapture:
            def __init__(self, device, pause_ms, gate=None):
                self.gate, self.speaking, self.full, self.timed_out = gate, False, False, False
                made.append(self)
            def poll(self):
                pass
            def level(self):
                return 0
            def close(self):
                pass

        commands = [{"id": "a", "action": "start", "model": "base.en", "hands_free": True, "barge": True},
                    {"id": "", "action": "echo", "rms": .05},
                    {"id": "b", "action": "start", "model": "base.en", "hands_free": True}]
        run(io.StringIO("".join(json.dumps(c) + "\n" for c in commands)), io.StringIO(),
            transcriber=object(), automatic_factory=FakeCapture)
        self.assertIsNotNone(made[0].gate)
        self.assertGreaterEqual(made[0].gate.recent(), .05)  # Her level reached the gate.
        self.assertIsNone(made[1].gate)                      # An ordinary turn has no gate.
