from dataclasses import replace
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtCore import QEvent

from companion.avatar_presets import AVATAR_MOTION_PRESETS
from companion.characters import CharacterLibrary
from companion.config import DEFAULT_MODEL, Settings
from companion.preferences import Preferences
from companion.ui import CompanionWindow
from qt_test_support import application


DEFAULTS = Settings('', DEFAULT_MODEL, 'Test character', 'Test personality', tts_enabled=False)


class AvatarPolishUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = application()

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        self.preferences = Preferences(self.root / 'preferences.json')
        self.window = self.make_window(DEFAULTS)

    def make_window(self, settings):
        return CompanionWindow(settings, preferences=self.preferences,
                               characters=CharacterLibrary(self.root))

    def close_window(self):
        self.window.request_quit()
        self.window.deleteLater()
        self.app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.app.processEvents()

    def tearDown(self):
        self.close_window()

    def values(self):
        return (self.window.avatar_motion.value(), self.window.avatar_gaze.value(),
                self.window.avatar_hair.value())

    def test_named_presets_apply_only_motion_gaze_and_hair(self):
        self.window.avatar_cursor_attention.setChecked(False)
        self.window.animate_avatar.setChecked(False)
        self.window.avatar_lip_sensitivity.setValue(170)
        before = self.window._current_preferences()
        with patch.object(self.window.speech, 'speak') as speech, \
             patch.object(self.window.microphone, 'start') as microphone:
            for name, expected in AVATAR_MOTION_PRESETS.items():
                self.window.avatar_preset.setCurrentText(name)
                self.assertEqual(self.values(), expected)
                self.assertEqual(self.window.avatar_preset.currentText(), name)
                current = self.window._current_preferences()
                self.assertEqual(replace(current, avatar_motion=before.avatar_motion,
                                         avatar_gaze=before.avatar_gaze, avatar_hair=before.avatar_hair), before)
            speech.assert_not_called()
            microphone.assert_not_called()

    def test_manual_values_derive_custom_then_restore_named_selection(self):
        self.assertEqual(self.window.avatar_preset.currentText(), 'Natural')
        for slider in (self.window.avatar_motion, self.window.avatar_gaze, self.window.avatar_hair):
            previous = slider.value()
            slider.setValue(previous - 1)
            self.assertEqual(self.window.avatar_preset.currentText(), 'Custom')
            slider.setValue(previous)
            self.assertEqual(self.window.avatar_preset.currentText(), 'Natural')
        self.window.avatar_preset.setCurrentText('Custom')
        self.assertEqual(self.window.avatar_preset.currentText(), 'Natural',
                         'Custom is derived from values, not independently stored')

    def test_loading_custom_values_does_not_overwrite_them_with_a_preset(self):
        settings = replace(DEFAULTS, avatar_motion=71, avatar_gaze=83, avatar_hair=38)
        self.window._apply_settings(settings)
        self.assertEqual(self.values(), (71, 83, 38))
        self.assertEqual(self.window.avatar_preset.currentText(), 'Custom')
        self.window._apply_settings(replace(settings, avatar_motion=45, avatar_gaze=55, avatar_hair=30))
        self.assertEqual(self.values(), AVATAR_MOTION_PRESETS['Calm'])
        self.assertEqual(self.window.avatar_preset.currentText(), 'Calm')

    def test_named_and_custom_defaults_round_trip_without_a_redundant_preset_field(self):
        for name, values in [('Lively', AVATAR_MOTION_PRESETS['Lively']), ('Custom', (67, 81, 39))]:
            for slider, value in zip((self.window.avatar_motion, self.window.avatar_gaze,
                                      self.window.avatar_hair), values):
                slider.setValue(value)
            self.window._save_preferences()
            document = json.loads(self.preferences.path.read_text(encoding='utf-8'))
            self.assertNotIn('avatar_preset', document['settings'])
            self.close_window()
            self.window = self.make_window(self.preferences.load(DEFAULTS))
            self.assertEqual(self.values(), values)
            self.assertEqual(self.window.avatar_preset.currentText(), name)

    def test_preview_controls_are_present_and_unavailable_without_a_visible_mesh(self):
        self.assertEqual(self.window.preview_avatar_motion.text(), 'Preview movement')
        self.assertFalse(self.window.preview_avatar_motion.isEnabled())
        self.assertTrue(self.window.avatar_preview_status.wordWrap())
        self.assertTrue(self.window.avatar_preview_status.text())
        self.assertIn('silent', self.window.preview_avatar_motion.toolTip())


if __name__ == '__main__':
    unittest.main()
