"""Customize her: glasses over a Live2D model, saved with the model and sent to the avatar."""
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock

from companion.avatar.models import AvatarModels, accessories
from companion.core.preferences import Preferences
from companion.core.storage import Store
from companion.ui.window import CompanionWindow
from tests.python.avatar.test_avatar_models import fixture
from tests.python.ui.test_ui import SETTINGS, FakeMicrophone, FakeSpeech
from tests.qt_test_support import application


class AccessoryRulesTests(unittest.TestCase):
    def test_glasses_settings_are_checked_and_completed(self):
        self.assertEqual(accessories({}), {})
        self.assertEqual(accessories({"glasses": {"on": True}}),
                         {"glasses": {"on": True, "style": "teacher", "frame": "silver", "lens": "clear"}})
        for bad in ({"hat": {}}, {"glasses": {"on": "yes"}}, {"glasses": {"style": "monocle"}},
                    {"glasses": {"frame": "plaid"}}, {"glasses": {"on": True, "size": 3}}, []):
            with self.assertRaises(ValueError):
                accessories(bad)


class CustomizeWindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = application()

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.models = AvatarModels(self.root)
        self.profile = str(self.root / "character.toml")
        self.model = self.models.import_live2d(self.profile, fixture(self.root / "source"), "Rigged Jingliu")
        self.store = Store(":memory:")
        self.window = CompanionWindow(replace(SETTINGS, character_path=self.profile), speech=FakeSpeech(),
                                      microphone=FakeMicrophone(), store=self.store,
                                      preferences=Preferences(self.root / "preferences.json"), models=self.models)
        self.addCleanup(self.close_window)

    def close_window(self):
        self.window.avatar.shutdown()
        self.window._quitting = True
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()
        self.store.close()

    def test_glasses_are_saved_with_the_model_and_sent_to_her(self):
        self.window.avatar_model.setCurrentIndex(self.window.avatar_model.findData(self.model["id"]))
        self.assertFalse(self.window.glasses_row.isHidden())
        self.assertFalse(self.window.glasses_rows[0].isEnabled())  # Style waits until glasses are on.
        widget = MagicMock()
        self.window.avatar.widget = widget
        self.window.glasses.setChecked(True)
        self.window.glasses_frame.setCurrentIndex(self.window.glasses_frame.findData("gold"))
        saved = AvatarModels(self.root).selected(self.profile)["accessories"]
        self.assertEqual(saved, {"glasses": {"on": True, "style": "teacher", "frame": "gold", "lens": "clear"}})
        widget.set_accessories.assert_called_with(saved)
        self.assertTrue(self.window.glasses_rows[0].isEnabled())
        self.window.avatar.widget = None
        # Choosing the model again shows what she is wearing.
        self.window.avatar_model.setCurrentIndex(0)
        self.window.avatar_model.setCurrentIndex(self.window.avatar_model.findData(self.model["id"]))
        self.assertTrue(self.window.glasses.isChecked())
        self.assertEqual(self.window.glasses_frame.currentData(), "gold")

    def test_glasses_come_off_for_the_blindfold(self):
        blindfolded = self.models.import_live2d(self.profile, fixture(self.root / "source2"), "Blindfold rig",
                                                blindfold_parameter="Param100")
        self.window._refresh_avatar_models()
        self.window.avatar_model.setCurrentIndex(self.window.avatar_model.findData(blindfolded["id"]))
        widget = MagicMock()
        self.window.avatar.widget = widget
        self.window.glasses.setChecked(True)
        self.assertTrue(widget.set_accessories.call_args.args[0]["glasses"]["on"])
        self.window.avatar_blindfold.setChecked(True)
        self.assertFalse(widget.set_accessories.call_args.args[0]["glasses"]["on"])  # Not over a blindfold…
        self.assertTrue(AvatarModels(self.root).selected(self.profile)["accessories"]["glasses"]["on"])  # …still chosen.
        self.window.avatar_blindfold.setChecked(False)
        self.assertTrue(widget.set_accessories.call_args.args[0]["glasses"]["on"])  # Back on afterwards.
        self.window.avatar.widget = None

    def test_accessories_have_their_own_settings_tab(self):
        titles = [self.window.settings_tabs.nav.item(i).text() for i in range(self.window.settings_tabs.count())]
        self.assertEqual(titles, ["Companion", "Voice", "Avatar", "Accessories", "App", "Tools"])
        tab = self.window.settings_tabs.widget(titles.index("Accessories"))
        self.assertTrue(tab.isAncestorOf(self.window.glasses))

    def test_customizing_waits_for_a_live2d_model(self):
        self.window.avatar_model.setCurrentIndex(0)  # The AI portrait.
        self.assertTrue(self.window.glasses_row.isHidden())
        self.assertFalse(self.window.customize_note.isHidden())
        with self.assertRaises(ValueError):
            self.models.set_accessories(self.profile, "current", {"glasses": {"on": True}})


if __name__ == "__main__":
    unittest.main()
