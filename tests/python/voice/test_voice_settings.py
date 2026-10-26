import io
import json
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np

from companion.voice.speech_process import PocketSpeaker, run
from companion.voice.settings import playback_sample_rate, validate_rate


class VoiceRateTests(unittest.TestCase):
    def test_varispeed_rate_and_invalid_values(self):
        self.assertEqual(playback_sample_rate(24000, 94), 22560)
        self.assertEqual(playback_sample_rate(24000), 24000)
        for value in (True, 79, 116, 0.94, "94", None):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_rate(value)

    def test_engine_sets_output_rate_and_keeps_chunk_order_and_gain(self):
        calls = []
        def playback(chunks, sample_rate, volume, report, levels):
            calls.append((sample_rate, volume, list(chunks)))
            report('speaking')
        class Chunk:
            def __init__(self, samples): self.samples = np.array(samples, dtype=np.float32)
            def detach(self): return self
            def cpu(self): return self
            def numpy(self): return self.samples
        class Model:
            sample_rate = 24000
            def generate_audio_stream(self, state, text):
                yield Chunk([0.2, -0.4])
                yield Chunk([0.8])
        speaker = PocketSpeaker()
        speaker.model, speaker.voices = Model(), {"jane": object()}
        statuses = []
        with patch.object(speaker, "prepare"), patch('companion.voice.playback.play_chunks', side_effect=playback):
            speaker.speak("A sample.", "jane", 50, statuses.append, rate=94)
        self.assertEqual(calls[0][:2], (22560, 50))
        np.testing.assert_allclose(np.concatenate(calls[0][2]).ravel(), [0.2, -0.4, 0.8])
        self.assertEqual(statuses, ["preparing", "speaking"])

    def test_protocol_passes_rate_defaults_old_commands_and_rejects_bad_rate(self):
        class Speaker:
            calls = []
            def speak(self, text, voice, volume, report, rate=100):
                self.calls.append(rate)
        speaker = Speaker()
        commands = [{"id": "1", "text": "One", "voice": "jane", "volume": 70, "rate": 94},
                    {"id": "2", "text": "Two", "voice": "jane", "volume": 70},
                    {"id": "3", "text": "Bad", "voice": "jane", "volume": 70, "rate": True}]
        output = io.StringIO()
        run(io.StringIO("\n".join(map(json.dumps, commands))), output, speaker)
        self.assertEqual(speaker.calls, [94, 100])
        events = [json.loads(line) for line in output.getvalue().splitlines()]
        self.assertEqual(events[-1]["type"], "error")
