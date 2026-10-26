from datetime import datetime
import unittest
from unittest.mock import patch

from PySide6.QtCore import QEvent

from companion import check_ins
from companion.check_ins import CheckIns
from companion.config import DEFAULT_MODEL, Settings
from companion.prompts import reply_prompt
from qt_test_support import application

SETTINGS = Settings("test-key", DEFAULT_MODEL, "Jingliu", "Profile.", tts_enabled=False)


class CheckInRuleTests(unittest.TestCase):
    def test_she_greets_when_you_arrive_and_when_you_come_back_after_a_while(self):
        rules = CheckIns()
        self.assertIsNone(rules.greeting(datetime(2026, 10, 26, 8, 0), idle=600))     # Not at the computer yet.
        self.assertEqual(rules.greeting(datetime(2026, 10, 26, 8, 5), idle=3), "first")
        self.assertIsNone(rules.greeting(datetime(2026, 10, 26, 9, 0), idle=3))       # Already greeted today.
        self.assertIsNone(rules.greeting(datetime(2026, 10, 26, 13, 0), idle=3 * 3600))  # Away for a while...
        self.assertEqual(rules.greeting(datetime(2026, 10, 26, 13, 1), idle=2), "back")  # ...and back.
        self.assertIsNone(rules.greeting(datetime(2026, 10, 26, 13, 30), idle=2))
        # Working past midnight is still the same day; the next morning is a new one.
        self.assertIsNone(rules.greeting(datetime(2026, 10, 27, 1, 0), idle=2))
        self.assertEqual(rules.greeting(datetime(2026, 10, 27, 7, 0), idle=2), "first")

    def test_the_greeting_fits_the_time_of_day(self):
        cases = {6: "good morning", 14: "good afternoon", 19: "good evening", 23: "late at night", 2: "late at night"}
        for hour, words in cases.items():
            with self.subTest(hour=hour):
                self.assertIn(words, check_ins.greeting_label(datetime(2026, 10, 26, hour, 0), "first"))
        self.assertIn("welcome back", check_ins.greeting_label(datetime(2026, 10, 26, 19, 0), "back"))
        self.assertIn("evening", check_ins.greeting_message(datetime(2026, 10, 26, 19, 0), "back"))

    def test_a_rest_nudge_after_three_hours_without_a_break_then_not_again_for_three(self):
        rules = CheckIns()
        hour = 3600
        self.assertFalse(rules.long_session(0, idle=5))
        self.assertFalse(rules.long_session(2 * hour, idle=5))
        self.assertTrue(rules.long_session(3 * hour, idle=5))
        self.assertEqual(rules.hours(3 * hour), 3)
        self.assertFalse(rules.long_session(4 * hour, idle=5))     # Not again so soon.
        self.assertFalse(rules.long_session(5 * hour, idle=700))   # A real break resets the stretch.
        self.assertFalse(rules.long_session(5 * hour + 60, idle=5))  # Back at it (checked once a minute).
        self.assertFalse(rules.long_session(7 * hour, idle=5))     # Only two hours since the break.
        self.assertTrue(rules.long_session(8 * hour + 120, idle=5))

    def test_her_instructions_only_when_chosen(self):
        self.assertIn(check_ins.MARK, reply_prompt("Profile", check_ins=True))
        self.assertNotIn(check_ins.MARK, reply_prompt("Profile"))


class WindowCheckInTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = application()

    def setUp(self):
        from companion.ui import CompanionWindow
        self.window = CompanionWindow(SETTINGS)
        self.window.preferences.remember = lambda *args: None

    def tearDown(self):
        self.window.request_quit()
        self.window.deleteLater()
        self.app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.app.processEvents()

    def run_check(self, now, idle):
        started = []
        with patch("companion.reminders.now_local", return_value=now.astimezone()), \
                patch("companion.check_ins.idle_seconds", return_value=idle), \
                patch.object(self.window, "_begin_reply", side_effect=lambda *a, **k: started.append((a, k)) or True):
            self.window._check_in()
        return started

    def test_off_by_default(self):
        self.assertFalse(self.window.check_ins.isChecked())
        self.assertEqual(self.run_check(datetime(2026, 10, 26, 8, 0), 1), [])

    def test_when_on_she_greets_on_arrival_and_it_is_remembered(self):
        self.window.check_ins.setChecked(True)
        started = self.run_check(datetime(2026, 10, 26, 8, 0), 1)
        (line,), options = started[0]
        self.assertTrue(line.startswith(check_ins.MARK))
        self.assertEqual(options["note"], ("Check-in · good morning", "moon"))  # 08:00
        self.assertEqual(self.window.settings.check_in_greeted, "2026-10-26")
        self.assertEqual(self.run_check(datetime(2026, 10, 26, 9, 0), 1), [])

    def test_never_while_she_is_busy(self):
        self.window.check_ins.setChecked(True)
        self.window._worker = object()
        self.assertEqual(self.run_check(datetime(2026, 10, 26, 8, 0), 1), [])
        self.window._worker = None
        self.assertEqual(self.window._check_ins.greeted, "")  # Still to come once she is free.


if __name__ == "__main__":
    unittest.main()
