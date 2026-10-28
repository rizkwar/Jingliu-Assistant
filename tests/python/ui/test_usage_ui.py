"""The Usage item in the sidebar and its page of moons, tokens by day and chats."""

from datetime import datetime, timedelta, timezone
import os
import tempfile
import time
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent, QTimer
from PySide6.QtWidgets import QLabel, QPushButton

from companion.chat import usage
from companion.core.storage import Store
from companion.ui import theme
from companion.ui.usage import DayChart, UsageDialog, shadow_offset
from companion.ui.window import CompanionWindow
from tests.python.ui.test_ui import SETTINGS, FakeMicrophone, FakeSpeech
from tests.qt_test_support import application


class UsageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = application()

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.limits = Path(self.folder.name) / "limits.json"
        self.patch = patch.object(usage, "LIMITS_FILE", self.limits)
        self.patch.start()
        usage.save_limits("claude", usage.claude_windows({"unifiedWindows": {
            "five_hour": {"utilization": 0.38, "resetsAt": time.time() + 3600, "status": "allowed"},
            "seven_day": {"utilization": 0.19, "resetsAt": time.time() + 86400 * 3, "status": "allowed"}}}))
        self.store = Store(":memory:")
        self.chat = self.store.create_conversation("")
        self.store.rename_conversation(self.chat, "Calculus study")
        self.store.record_usage(self.chat, "claude", "claude-sonnet-5-5", 1200, 300, 500)
        self.window = CompanionWindow(replace(SETTINGS, llm_provider="claude"), speech=FakeSpeech(),
                                      microphone=FakeMicrophone(), store=self.store)
        self.window.resize(1200, 800)
        self.window.show()
        self.app.processEvents()

    def tearDown(self):
        self.window.close()
        self.window.deleteLater()
        self.app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.app.processEvents()
        self.patch.stop()
        self.folder.cleanup()
        theme.set_theme("moonlit")

    def note(self):
        return self.window.sidebar._notes[self.window.usage_button]

    def test_the_sidebar_shows_what_is_left_of_the_window_closest_to_running_out(self):
        self.assertEqual(self.note().text(), "62% left")
        self.assertFalse(self.note().property("warn"))
        self.assertIn("This week: 81% left", self.window.usage_button.toolTip())
        # A reply reports less left: the note follows at once, in amber below 20%.
        self.window._limits_reported("claude", [{"key": "five_hour", "label": "Session · 5 hours", "left": 12.0,
                                                 "resets_at": time.time() + 600}])
        self.assertEqual(self.note().text(), "12% left")
        self.assertTrue(self.note().property("warn"))
        # Another service has its own limits; with none known yet the note is empty.
        self.window.settings = replace(self.window.settings, llm_provider="codex")
        self.window._refresh_usage_note()
        self.assertFalse(self.note().isVisible())

    def test_tokens_of_a_reply_are_kept_for_its_chat(self):
        self.window._record_usage(self.chat, "claude", {"model": "claude-opus-5-5", "input": 10, "output": 5, "cached": 0})
        rows = self.store.usage_since(datetime.now(timezone.utc) - timedelta(days=1))
        self.assertEqual(len(rows), 2)

    def test_the_page_shows_moons_for_each_window_today_and_the_chats(self):
        dialog = UsageDialog(self.store, self.window.settings, parent=self.window)
        texts = [label.text() for label in dialog.findChildren(QLabel)]
        self.assertIn("62% left", texts)
        self.assertIn("81% left", texts)
        self.assertIn("2k tokens", texts)  # Today's moon.
        self.assertTrue(any(text.startswith("Claude subscription · Claude Sonnet 5.5") for text in texts))
        [chat] = [button for button in dialog.findChildren(QPushButton) if button.objectName() == "usageChat"]
        self.assertEqual(chat.text(), "Calculus study")
        self.assertEqual(dialog.chart.days[-1][1], {"input": 1200, "output": 300, "cached": 500})
        for key in theme.THEMES:  # Every theme paints it.
            theme.set_theme(key)
            dialog.resize(900, 700)
            self.assertFalse(dialog.grab().isNull())
        dialog.deleteLater()

    def test_choosing_a_chat_on_the_page_opens_it(self):
        other = self.store.create_conversation("")
        self.window._switch_conversation(other)

        def choose():
            buttons = [button for button in self.window.findChildren(QPushButton) if button.objectName() == "usageChat"]
            buttons[0].click()
        QTimer.singleShot(0, choose)
        self.window._open_usage()
        self.assertEqual(self.window._conversation_id, self.chat)

    def test_the_moon_is_lit_in_proportion_to_what_is_left(self):
        self.assertAlmostEqual(shadow_offset(100), 2.0, places=3)
        self.assertAlmostEqual(shadow_offset(0), 0.0, places=3)
        self.assertGreater(shadow_offset(62), shadow_offset(14))

    def test_chart_parts_stay_apart_in_every_theme(self):
        for key in theme.THEMES:
            theme.set_theme(key)
            colours = [rgb for _, rgb in DayChart.parts()]
            self.assertEqual(len(set(colours)), 3, key)


if __name__ == "__main__":
    unittest.main()
