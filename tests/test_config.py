import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from companion.config import DEFAULT_MODEL, Settings, load_settings


class SettingsTests(unittest.TestCase):
    def test_key_is_not_in_settings_repr(self):
        self.assertNotIn("secret-key", repr(Settings("secret-key", DEFAULT_MODEL, "Jinger", "Hi")))
        self.assertNotIn("hf-secret", repr(Settings("key", DEFAULT_MODEL, "Jinger", "Hi", hf_token="hf-secret")))

    def test_reference_path_is_resolved_against_project_and_hf_token_is_separate(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {}, clear=True):
            root = Path(folder)
            (root / "character.md").write_text("You are {name}.", encoding="utf-8")
            (root / ".env").write_text("TTS_VOICE=reference\nTTS_REFERENCE=voices/reference.wav\nHF_TOKEN=hf-secret\n", encoding="utf-8")
            settings = load_settings(root)
            self.assertEqual(settings.tts_voice, "reference")
            self.assertEqual(settings.tts_reference, str((root / "voices" / "reference.wav").resolve()))
            self.assertEqual(settings.hf_token, "hf-secret")
            self.assertNotIn("hf-secret", settings.system_prompt)

    def test_webpage_anchor_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "without #providers"):
            Settings("key", DEFAULT_MODEL + "#providers", "Jinger", "Hi").validate_connection()

    def test_reload_reads_new_values_and_environment_takes_precedence(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {}, clear=True):
            root = Path(folder)
            (root / "character.md").write_text("You are {name}.", encoding="utf-8")
            (root / ".env").write_text("COMPANION_NAME=Jinger\nOPENROUTER_API_KEY=first\n", encoding="utf-8")
            self.assertEqual(load_settings(root).api_key, "first")
            (root / ".env").write_text("COMPANION_NAME=Luna\nOPENROUTER_API_KEY=second\n", encoding="utf-8")
            self.assertEqual(load_settings(root).system_prompt, "You are Luna.")
            os.environ["OPENROUTER_API_KEY"] = "from-shell"
            self.assertEqual(load_settings(root).api_key, "from-shell")

    def test_voice_settings_have_defaults_and_validate_volume(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {}, clear=True):
            root = Path(folder)
            (root / "character.md").write_text("You are {name}.", encoding="utf-8")
            settings = load_settings(root)
            self.assertEqual((settings.tts_voice, settings.tts_enabled, settings.tts_volume), ("alba", True, 70))
            (root / ".env").write_text("TTS_VOICE=anna\nTTS_ENABLED=false\nTTS_VOLUME=35\n", encoding="utf-8")
            settings = load_settings(root)
            self.assertEqual((settings.tts_voice, settings.tts_enabled, settings.tts_volume), ("anna", False, 35))
            os.environ["TTS_VOLUME"] = "101"
            with self.assertRaisesRegex(ValueError, "0 to 100"):
                load_settings(root)

    def test_transcription_settings_are_validated(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {}, clear=True):
            root = Path(folder)
            (root / "character.md").write_text("You are {name}.", encoding="utf-8")
            self.assertEqual(load_settings(root).stt_model, "base.en")
            (root / ".env").write_text("STT_MODEL=tiny.en\nSTT_AUTO_SEND=false\nSTT_MICROPHONE=3\n", encoding="utf-8")
            settings = load_settings(root)
            self.assertEqual((settings.stt_model, settings.stt_auto_send, settings.stt_microphone), ("tiny.en", False, "3"))
            os.environ["STT_MODEL"] = "unknown"
            with self.assertRaisesRegex(ValueError, "STT_MODEL"):
                load_settings(root)

    def test_voice_rate_defaults_and_rejects_out_of_range_values(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {}, clear=True):
            root = Path(folder)
            (root / "character.md").write_text("You are {name}.", encoding="utf-8")
            self.assertEqual(load_settings(root).tts_rate, 100)
            (root / ".env").write_text("TTS_RATE=94\n", encoding="utf-8")
            self.assertEqual(load_settings(root).tts_rate, 94)
            for rate in ("79", "116", "0.94", "calm"):
                os.environ["TTS_RATE"] = rate
                with self.assertRaisesRegex(ValueError, "TTS_RATE"):
                    load_settings(root)

