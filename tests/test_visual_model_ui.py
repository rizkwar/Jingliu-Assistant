from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from companion.avatar_models import AvatarModels
from companion.ui import CompanionWindow
from companion.storage import Store
from companion.preferences import Preferences
from qt_test_support import application
from test_avatar_models import fixture
from test_ui import FakeSpeech, FakeMicrophone, SETTINGS


class VisualModelUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = application()

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.models = AvatarModels(self.root)
        self.profile = str(self.root / 'character.toml')
        self.model = self.models.import_live2d(self.profile, fixture(self.root / 'source'),
                                              'Rigged Jingliu', blindfold_parameter='Param100')
        self.store = Store(':memory:')
        self.window = CompanionWindow(replace(SETTINGS, character_path=self.profile),
            speech=FakeSpeech(), microphone=FakeMicrophone(), store=self.store,
            preferences=Preferences(self.root / 'preferences.json'), models=self.models)
        self.addCleanup(self.close_window)

    def close_window(self):
        self.window.avatar.shutdown()
        self.window._quitting = True
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()
        self.store.close()

    def test_switching_visual_models_preserves_character_voice_and_conversation(self):
        before = self.window.settings
        conversation = self.window._conversation_id
        self.assertEqual(self.window.avatar_model.count(), 2)
        with patch.object(self.window.speech, 'speak') as speech, patch.object(self.window.microphone, 'start') as mic:
            self.window.avatar_model.setCurrentIndex(1)
            self.assertEqual(self.models.selected(self.profile)['id'], self.model['id'])
            self.assertEqual(self.window.settings, before)
            self.assertEqual(self.window._conversation_id, conversation)
            self.window.avatar_framing.setCurrentIndex(1)
            self.window.avatar_blindfold.setChecked(True)
            selected = AvatarModels(self.root).selected(self.profile)
            self.assertEqual(selected['framing'], 'full')
            self.assertEqual(selected['appearance'], {'Param100': 0})
            self.window.avatar_model.setCurrentIndex(0)
            self.assertEqual(self.models.selected(self.profile)['id'], 'current')
            self.assertFalse(self.window.avatar_framing.isEnabled())
            speech.assert_not_called()
            mic.assert_not_called()

    def test_model_options_and_selection_belong_to_the_active_character(self):
        self.window.avatar_model.setCurrentIndex(1)
        original = self.window.settings
        self.window.settings = replace(original, character_path=str(self.root / 'other.toml'))
        self.window._refresh_avatar_models()
        self.assertEqual(self.window.avatar_model.count(), 1)
        self.assertEqual(self.window.avatar_model.currentData(), 'current')
        self.window.settings = original
        self.window._refresh_avatar_models()
        self.assertEqual(self.window.avatar_model.currentData(), self.model['id'])
