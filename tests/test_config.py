import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from companion.config import DEFAULT_MODEL, Settings, load_settings


class SettingsTests(unittest.TestCase):
    def test_key_is_not_in_settings_repr(self):
        self.assertNotIn("secret-key", repr(Settings("secret-key", DEFAULT_MODEL, "Mira", "Hi")))

    def test_webpage_anchor_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "without #providers"):
            Settings("key", DEFAULT_MODEL + "#providers", "Mira", "Hi").validate_connection()

    def test_reload_reads_new_values_and_environment_takes_precedence(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {}, clear=True):
            root = Path(folder)
            (root / "character.md").write_text("You are {name}.", encoding="utf-8")
            (root / ".env").write_text("COMPANION_NAME=Mira\nOPENROUTER_API_KEY=first\n", encoding="utf-8")
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

