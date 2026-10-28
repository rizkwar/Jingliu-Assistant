"""Themes: her moonlit palette recoloured, chosen in Settings and remembered."""
from dataclasses import replace
import os
from pathlib import Path
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent

from companion.core.preferences import Preferences
from companion.core.storage import Store
from companion.ui import theme
from companion.ui.window import CompanionWindow
from tests.python.ui.test_ui import SETTINGS, FakeMicrophone, FakeSpeech
from tests.qt_test_support import application


class ThemeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = application()

    def setUp(self):
        theme.set_font("segoe")  # Her original face, so the colours alone are compared.

    def tearDown(self):
        theme.set_theme("moonlit")
        theme.set_font("inter")

    def test_moonlit_is_untouched_and_others_recolour_everything(self):
        self.assertEqual(theme.style(), theme.STYLE)
        theme.set_theme("jade")
        jade = theme.style()
        self.assertNotIn("168, 212, 255", jade)               # Her icy blue became jade…
        self.assertIn(theme.CRIMSON, jade)                     # …while her crimson accent stays.
        self.assertEqual(jade.count("{"), theme.STYLE.count("{"))
        theme.set_theme("snow")
        light = theme.QColor(theme.tone(theme.NIGHT))
        self.assertGreater(light.lightness(), 230)             # Night becomes day…
        self.assertLess(theme.QColor(theme.tone(theme.FROST)).lightness(), 40)  # …and her silver text dark.
        self.assertTrue(theme.is_light())
        theme.set_theme("nonsense")
        self.assertEqual(theme.style(), theme.STYLE)

    def test_fonts_and_sizes(self):
        from PySide6.QtGui import QFontDatabase
        theme.set_font("inter", "large")
        sheet = theme.style()
        self.assertIn("Inter", QFontDatabase.families())          # Bundled, so it is there on every computer.
        self.assertNotIn("Segoe UI Variable Text", sheet)
        self.assertIn("font-family: 'Inter', 'Segoe UI'; font-weight: 600;", sheet)
        self.assertIn("font-size: 15.1px", sheet)                 # 14px, a size larger.
        theme.set_font("unknown", "huge")
        self.assertEqual(theme.font_family(), "Inter")


class ThemeSettingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = application()

    def tearDown(self):
        theme.set_theme("moonlit")
        theme.set_font("inter")

    def test_choosing_a_font_applies_and_remembers_it(self):
        folder = Path(tempfile.mkdtemp())
        preferences = Preferences(folder / "preferences.json")
        window = CompanionWindow(SETTINGS, speech=FakeSpeech(), microphone=FakeMicrophone(),
                                 store=Store(":memory:"), preferences=preferences)
        self.assertEqual(window.font_choice.currentData(), "inter")
        window.font_choice.setCurrentIndex(window.font_choice.findData("sitka"))
        window.font_size.setCurrentIndex(window.font_size.findData("larger"))
        self.assertIn("Sitka Text", window.styleSheet())
        saved = preferences.load(SETTINGS)
        self.assertEqual((saved.font, saved.font_size), ("sitka", "larger"))
        window._quitting = True
        window.close()
        window.deleteLater()
        self.app.sendPostedEvents(None, QEvent.Type.DeferredDelete)

    def test_choosing_a_theme_applies_and_remembers_it(self):
        folder = Path(tempfile.mkdtemp())
        preferences = Preferences(folder / "preferences.json")
        window = CompanionWindow(replace(SETTINGS, theme="violet"), speech=FakeSpeech(), microphone=FakeMicrophone(),
                                 store=Store(":memory:"), preferences=preferences)
        self.assertEqual(window.theme.currentData(), "violet")
        self.assertNotEqual(window.styleSheet(), theme.STYLE)
        window.theme.setCurrentIndex(window.theme.findData("snow"))
        self.assertEqual(window.styleSheet(), theme.style())
        self.assertTrue(theme.is_light())
        self.assertEqual(preferences.load(SETTINGS).theme, "snow")
        window.theme.setCurrentIndex(window.theme.findData("moonlit"))
        self.assertEqual(window.styleSheet(), theme.style())
        self.assertNotIn("rgba(16, 26, 46", theme.tone("x"))
        window._quitting = True
        window.close()
        window.deleteLater()
        self.app.sendPostedEvents(None, QEvent.Type.DeferredDelete)


if __name__ == "__main__":
    unittest.main()
