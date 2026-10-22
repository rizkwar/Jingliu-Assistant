from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from companion.config import DEFAULT_MODEL, Settings
from companion.preferences import Preferences


DEFAULTS = Settings("secret-key", DEFAULT_MODEL, "Mira", "Private character")


class PreferenceTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.path = Path(folder.name) / "data" / "preferences.json"
        self.preferences = Preferences(self.path)

    def test_restart_restores_only_nonsecret_preferences_over_new_env_defaults(self):
        self.assertEqual(self.preferences.load(DEFAULTS), DEFAULTS)
        self.preferences.save(replace(DEFAULTS, tts_voice="anna", tts_volume=0, tts_rate=94,
                                      memory_enabled=False, stt_microphone="0", close_to_tray=False))
        stored = self.path.read_text(encoding="utf-8")
        self.assertNotIn("secret-key", stored)
        self.assertNotIn("Private character", stored)
        self.assertNotIn("model", json.loads(stored)["settings"])
        changed_env = replace(DEFAULTS, api_key="new-key", system_prompt="New character", model="vendor/new")
        loaded = Preferences(self.path).load(changed_env)
        self.assertEqual((loaded.api_key, loaded.system_prompt, loaded.model), ("new-key", "New character", "vendor/new"))
        self.assertEqual((loaded.tts_voice, loaded.tts_volume, loaded.stt_microphone), ("anna", 0, "0"))
        self.assertEqual(loaded.tts_rate, 94)
        self.assertFalse(loaded.memory_enabled)
        self.assertFalse(loaded.close_to_tray)

    def test_invalid_values_and_future_format_are_rejected(self):
        self.path.parent.mkdir()
        for data in ["{bad", "[]", '{"version":2}', '{"version":1,"settings":null}',
                     '{"version":1,"settings":{"tts_volume":true}}',
                     '{"version":1,"settings":{"tts_volume":101}}',
                     '{"version":1,"settings":{"tts_rate":true}}',
                     '{"version":1,"settings":{"tts_rate":79}}',
                     '{"version":1,"settings":{"tts_voice":"missing"}}',
                     '{"version":1,"settings":{"stt_model":"missing"}}',
                     '{"version":1,"settings":{"stt_pause_ms":true}}',
                     '{"version":1,"settings":{"stt_pause_ms":2501}}',
                     '{"version":1,"settings":{"avatar_x":true,"avatar_y":0}}',
                     '{"version":1,"settings":{"avatar_x":20}}',
                     '{"version":1,"settings":{"avatar_x":1000001,"avatar_y":0}}']:
            with self.subTest(data=data):
                self.path.write_text(data, encoding="utf-8")
                with self.assertRaises(ValueError):
                    self.preferences.load(DEFAULTS)

    def test_unknown_fields_cannot_override_credentials(self):
        self.path.parent.mkdir()
        self.path.write_text(json.dumps({"version": 1, "settings": {"api_key": "injected", "tts_volume": 15}}))
        self.assertEqual(self.preferences.load(DEFAULTS).api_key, "secret-key")
        self.assertEqual(self.preferences.load(DEFAULTS).tts_volume, 15)

    def test_reference_choice_persists_without_hugging_face_credentials(self):
        path = str(self.path.parent / "reference.wav")
        self.preferences.save(replace(DEFAULTS, tts_voice="reference", tts_reference=path, hf_token="hf-secret"))
        self.assertNotIn("hf-secret", self.path.read_text())
        loaded = self.preferences.load(DEFAULTS)
        self.assertEqual((loaded.tts_voice, loaded.tts_reference), ("reference", path))

    def test_failed_atomic_replace_keeps_previous_defaults_and_cleans_temp_file(self):
        self.preferences.save(DEFAULTS)
        original = self.path.read_bytes()
        with patch("companion.preferences.os.replace", side_effect=PermissionError("busy")):
            with self.assertRaises(PermissionError):
                self.preferences.save(replace(DEFAULTS, tts_volume=20))
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual(list(self.path.parent.glob("*.tmp")), [])

    def test_avatar_preferences_round_trip_with_a_negative_monitor_position(self):
        self.preferences.save(replace(DEFAULTS, avatar_enabled=True, avatar_animated=False,
                                      avatar_x=-1100, avatar_y=200))
        loaded = Preferences(self.path).load(DEFAULTS)
        self.assertTrue(loaded.avatar_enabled)
        self.assertFalse(loaded.avatar_animated)
        self.assertEqual((loaded.avatar_x, loaded.avatar_y), (-1100, 200))
