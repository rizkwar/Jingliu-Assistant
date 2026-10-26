from array import array
import io
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import wave

from companion.voice.reference import inspect_reference, VoiceSetupError
from companion.voice.speech_process import PocketSpeaker, run


def write_reference(path, seconds=4, channels=1, value=1000):
    with wave.open(str(path), "wb") as output:
        output.setnchannels(channels)
        output.setsampwidth(2)
        output.setframerate(16000)
        output.writeframes(array("h", [value, -value] * int(8000 * seconds * channels)).tobytes())


class ReferenceTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.path = Path(folder.name) / "reference.wav"
        write_reference(self.path)

    def test_valid_reference_reports_metadata_and_content_changes_invalidate_fingerprint(self):
        first = inspect_reference(self.path)
        self.assertEqual((first.seconds, first.channels, first.sample_rate), (4, 1, 16000))
        self.assertEqual(first.path, self.path.resolve())
        write_reference(self.path, value=2000)
        self.assertNotEqual(first.fingerprint, inspect_reference(self.path).fingerprint)

    def test_invalid_duration_channels_and_silence_are_actionable(self):
        for kwargs in ({"seconds": 2}, {"seconds": 31}, {"channels": 3}, {"value": 0}):
            with self.subTest(kwargs=kwargs):
                write_reference(self.path, **kwargs)
                with self.assertRaises(VoiceSetupError):
                    inspect_reference(self.path)

    def test_missing_url_serialized_state_and_truncated_file_do_not_expose_paths(self):
        for source in ("", "https://example.com/secret.wav", self.path.with_suffix(".safetensors")):
            with self.subTest(source=str(source)), self.assertRaises(VoiceSetupError) as error:
                inspect_reference(source)
            self.assertNotIn("secret", str(error.exception))
        self.path.write_bytes(self.path.read_bytes()[:-100])
        with self.assertRaisesRegex(VoiceSetupError, "incomplete"):
            inspect_reference(self.path)

    def test_reference_is_passed_to_conditioner_and_state_is_reused_until_audio_changes(self):
        class Model:
            has_voice_cloning = True
            calls = []
            def get_state_for_audio_prompt(self, source):
                self.calls.append(source)
                return object()
        speaker = PocketSpeaker()
        speaker.model = Model()
        source = str(self.path)
        with patch.dict(sys.modules, {"torch": SimpleNamespace(), "pocket_tts": SimpleNamespace(TTSModel=object)}):
            speaker.prepare(source, lambda state: None)
            state = speaker.voices[source]
            speaker.prepare(source, lambda state: None)
            self.assertIs(speaker.voices[source], state)
            self.assertEqual(speaker.model.calls, [self.path.resolve()])
            write_reference(self.path, value=2000)
            speaker.prepare(source, lambda state: None)
            self.assertEqual(len(speaker.model.calls), 2)
            other = self.path.with_name("other.wav")
            write_reference(other)
            speaker.prepare(str(other), lambda state: None)
            self.assertNotIn(source, speaker.reference_keys)
            self.assertNotIn(source, speaker.voices)

    def test_stock_only_checkpoint_refuses_reference_without_silent_fallback(self):
        model = SimpleNamespace(has_voice_cloning=False, get_state_for_audio_prompt=lambda source: self.fail("Must not condition stock model"))
        speaker = PocketSpeaker()
        speaker.model = model
        with patch.dict(sys.modules, {"torch": SimpleNamespace(), "pocket_tts": SimpleNamespace(TTSModel=object)}):
            with self.assertRaisesRegex(VoiceSetupError, "stock voices only"):
                speaker.prepare(str(self.path), lambda state: None)
        self.assertEqual(speaker.voices, {})

    def test_setup_errors_survive_protocol_but_unexpected_details_are_redacted(self):
        class Speaker:
            def prepare(self, voice, report):
                raise VoiceSetupError("Choose a reference WAV in Settings.")
        output = io.StringIO()
        run(io.StringIO(json.dumps({"id": "1", "action": "prepare", "voice": "reference"})), output, Speaker())
        self.assertEqual(json.loads(output.getvalue())["message"], "Choose a reference WAV in Settings.")
        with patch.object(Speaker, "prepare", side_effect=RuntimeError("private-token")):
            output = io.StringIO()
            run(io.StringIO(json.dumps({"id": "2", "action": "prepare", "voice": "reference"})), output, Speaker())
            self.assertNotIn("private-token", output.getvalue())
