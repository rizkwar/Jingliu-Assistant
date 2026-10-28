"""The ChatGPT-like layout: a rounded conversation panel, a centred column, plain replies, and the Graphite theme."""

from dataclasses import replace
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent
from PySide6.QtGui import QColor

from companion.core.storage import Store
from companion.ui import theme
from companion.ui.chat_view import Bubble
from companion.ui.window import CompanionWindow
from tests.python.ui.test_ui import SETTINGS, FakeMicrophone, FakeSpeech
from tests.qt_test_support import application


class LookTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = application()

    def tearDown(self):
        theme.set_theme("moonlit")

    def test_graphite_is_chatgpt_grey_and_keeps_her_crimson(self):
        theme.set_theme("graphite")
        night = QColor(theme.tone(theme.NIGHT))
        self.assertLess(night.saturation(), 20)  # Neutral grey, not navy…
        self.assertGreater(night.lightness(), QColor(theme.NIGHT).lightness())  # …and lifted a little, like ChatGPT's dark.
        self.assertEqual(theme.tone(theme.CRIMSON), theme.CRIMSON)  # Her accent stays.
        self.assertIn("graphite", theme.THEMES)

    def test_a_one_line_message_of_yours_is_a_pill(self):
        import re
        from companion.ui.chat_view import Bubble
        radius = int(re.search(r"QFrame#user \{ [^}]*border-radius: (\d+)px", theme.style()).group(1))
        bubble = Bubble("user", "You")
        bubble.setStyleSheet(theme.style())
        bubble.set_text("i mean the demo turns out to be fine")
        bubble.adjustSize()
        # Qt draws no rounding at all when the radius is more than half the height.
        self.assertLessEqual(radius, bubble.sizeHint().height() / 2)

    def test_the_conversation_is_a_rounded_panel_in_a_centred_column_and_replies_are_plain(self):
        window = CompanionWindow(replace(SETTINGS, message_style="plain", openrouter_model="nvidia/a-very-long-model-name-x"),
                                 speech=FakeSpeech(), microphone=FakeMicrophone(), store=Store(":memory:"))
        try:
            self.assertEqual(window.centralWidget().objectName(), "shell")
            panels = window.findChildren(theme.NightSky)
            self.assertTrue(panels and panels[0].panel)
            self.assertLessEqual(window.pages.maximumWidth(), 820)
            window.transcript.add_message("user", "You", "Hello")
            reply = window.transcript.add_message("assistant", "Jingliu", "Hm. You came back.")
            self.assertTrue(reply.name.isHidden())  # No name above a plain reply, as in ChatGPT.
            window.transcript.set_plain(False)
            self.assertFalse(reply.name.isHidden())  # A bubble keeps it.
            self.assertTrue(window.model_picker.text().endswith("…"))
            self.assertLessEqual(len(window.model_picker.text()), 18)
        finally:
            window.close()
            window.deleteLater()
            self.app.sendPostedEvents(None, QEvent.Type.DeferredDelete)


if __name__ == "__main__":
    unittest.main()
