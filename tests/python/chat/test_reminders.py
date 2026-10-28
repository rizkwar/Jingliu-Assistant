from datetime import datetime, timedelta, timezone
import unittest
from unittest.mock import patch

from PySide6.QtCore import QEvent

from companion.chat import reminders
from companion.avatar.cues import CueFilter
from companion.core.config import DEFAULT_MODEL, Settings
from companion.chat.prompts import reply_prompt
from companion.core.storage import Store
from companion.ui.sidebar import UNREAD
from tests.qt_test_support import application

SETTINGS = Settings("test-key", DEFAULT_MODEL, "Jingliu", "Profile.", tts_enabled=False)
# A fixed local "now": Friday 23 October 2026, 18:30 in the computer's own time zone.
NOW = datetime(2026, 10, 23, 18, 30).astimezone()


class ReminderLogicTests(unittest.TestCase):
    def test_her_cue_is_read_as_local_time_and_stored_in_utc(self):
        due, text, repeat = reminders.parse("2026-10-23 19:00 | Study for the calculus exam", NOW)
        self.assertEqual(due.tzinfo, timezone.utc)
        self.assertEqual(due.astimezone(NOW.tzinfo).strftime("%H:%M"), "19:00")
        self.assertEqual((text, repeat), ("Study for the calculus exam", ""))
        self.assertEqual(reminders.parse("2026-10-23 18:59 | x | DAILY", NOW)[2], "daily")
        self.assertEqual(reminders.parse("2026-10-23 18:59 | x | hourly", NOW)[2], "")  # Unknown repeats are dropped.

    def test_impossible_reminders_are_refused(self):
        for payload in ("2026-10-23 17:00 | Too late", "tomorrow at seven | Study", "2026-10-23 19:00 |",
                        "2028-01-01 09:00 | Too far ahead"):
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                reminders.parse(payload, NOW)

    def test_a_past_time_with_a_repeat_starts_at_its_next_occurrence(self):
        due, _, _ = reminders.parse("2026-10-23 08:00 | Stretch | weekdays", NOW)
        self.assertEqual(due.astimezone(NOW.tzinfo).strftime("%a %H:%M"), "Mon 08:00")  # Not Saturday.

    def test_repeats_follow_the_calendar(self):
        friday = datetime(2026, 10, 23, 8, 0).astimezone()
        self.assertEqual(reminders.advance(friday, "daily").strftime("%a"), "Sat")
        self.assertEqual(reminders.advance(friday, "weekdays").strftime("%a"), "Mon")
        self.assertEqual(reminders.advance(friday, "weekly").day, 30)
        later = NOW + timedelta(days=3)
        following = reminders.following(friday.astimezone(timezone.utc), "daily", later)
        self.assertGreater(following, later)  # A long-closed app skips to the next one ahead.

    def test_times_read_naturally(self):
        at = lambda *parts: datetime(*parts).astimezone().astimezone(timezone.utc)
        self.assertEqual(reminders.when(at(2026, 10, 23, 19, 0), NOW), "Today, 19:00")
        self.assertEqual(reminders.when(at(2026, 10, 24, 8, 5), NOW), "Tomorrow, 08:05")
        self.assertEqual(reminders.when(at(2026, 10, 27, 9, 0), NOW), "Tuesday, 09:00")
        self.assertEqual(reminders.when(at(2026, 11, 3, 9, 0), NOW), "3 Nov, 09:00")
        self.assertEqual(reminders.describe({"due_at": at(2026, 10, 24, 8, 5).isoformat(), "repeat": "weekdays"}, NOW),
                         "Tomorrow, 08:05 · every weekday")

    def test_prompt_gives_her_the_time_and_what_is_scheduled(self):
        upcoming = [{"text": "Study", "due_at": datetime(2026, 10, 23, 19, 0).astimezone().isoformat(), "repeat": ""}]
        text = reminders.prompt(upcoming, NOW)
        self.assertIn("Friday 23 October 2026, 18:30", text)
        self.assertIn('"what": "Study"', text)
        self.assertIn("[[remind:", reply_prompt("Profile", reminders=text))
        self.assertNotIn("[[remind:", reply_prompt("Profile"))

    def test_cancel_words_match_loosely_but_not_wrongly(self):
        self.assertEqual(reminders.match("the stretching one", "Stretch your back"), 1.0)
        self.assertEqual(reminders.match("study reminder", "Study for the calculus exam"), 1.0)
        self.assertLess(reminders.match("dentist", "Study for the calculus exam"), .5)
        self.assertEqual(reminders.match("the one", "Anything"), 0.0)

    def test_cues_are_silent_and_carry_their_payload(self):
        cues = CueFilter()
        clean, found = cues.feed("Of course. [[remind: 2026-10-23 19:00 | Study | daily]] I will tell you. "
                                 "[[unremind: the stretching one]]")
        clean += cues.finish()
        self.assertEqual(clean.strip(), "Of course. I will tell you.")
        self.assertEqual([cue for _, cue in found],
                         ["remind:2026-10-23 19:00 | Study | daily", "unremind:the stretching one"])


class ReminderStorageTests(unittest.TestCase):
    def test_due_reminders_finish_or_move_on(self):
        store = Store(":memory:")
        self.addCleanup(store.close)
        now = datetime.now(timezone.utc)
        once = store.add_reminder("Once", now - timedelta(minutes=1))
        daily = store.add_reminder("Daily", now - timedelta(minutes=1), "daily")
        store.add_reminder("Later", now + timedelta(hours=2))
        self.assertEqual([r["text"] for r in store.due_reminders(now)], ["Once", "Daily"])
        store.finish_reminder(once)
        store.finish_reminder(daily, now + timedelta(days=1))
        self.assertEqual(store.due_reminders(now), [])
        self.assertEqual([r["text"] for r in store.reminders()], ["Later", "Daily"])
        store.delete_reminder(daily)
        self.assertEqual([r["text"] for r in store.reminders()], ["Later"])


class WindowReminderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = application()

    def setUp(self):
        from companion.ui.window import CompanionWindow
        self.window = CompanionWindow(SETTINGS)
        self.store = self.window.store

    def tearDown(self):
        self.window.request_quit()
        self.window.deleteLater()
        self.app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.app.processEvents()

    def test_setting_from_her_cue_shows_a_line_with_cancel(self):
        due = (reminders.now_local() + timedelta(hours=1)).strftime("%Y-%m-%d %H:%M")
        self.window._queue_cues([(0, f"remind:{due} | Take a break"), (2, "smile")])
        self.assertEqual(self.store.reminders(), [])  # Applied only when the reply finishes well.
        self.window._apply_memory_actions()
        self.assertEqual([r["text"] for r in self.store.reminders()], ["Take a break"])
        note = self.window.transcript._items[-1]
        self.assertIn("Reminder set: “Take a break”", note.plain())
        self.assertEqual(note.button.text(), "Cancel")
        note.button.click()
        self.assertEqual(self.store.reminders(), [])

    def test_cancelling_in_words_finds_the_reminder_and_can_be_undone(self):
        self.store.add_reminder("Stretch your back", datetime.now(timezone.utc) + timedelta(hours=3), "weekdays")
        self.window._cancel_reminder("the stretching back one")
        self.assertEqual(self.store.reminders(), [])
        self.window.transcript._items[-1].button.click()
        self.assertEqual([r["repeat"] for r in self.store.reminders()], ["weekdays"])
        self.window._cancel_reminder("dentist")
        self.assertIn("No reminder matched", self.window.transcript.toPlainText())

    def test_a_due_reminder_waits_until_she_is_free_then_she_delivers_it_in_her_session(self):
        self.store.add_reminder("Study", datetime.now(timezone.utc) - timedelta(minutes=1))
        started = []
        chat = self.window._conversation_id
        with patch.object(self.window, "_begin_reply") as begin, \
                patch.object(self.window, "_remind_out_of_view",
                             side_effect=lambda inbox, line, reminder: started.append((inbox, line)) or True):
            self.window._worker = object()  # Busy replying.
            self.window._check_reminders()
            self.assertEqual(started, [])
            self.window._worker = None
            self.window._check_reminders()
        begin.assert_not_called()  # Not in the chat you are in…
        self.assertEqual(len(started), 1)
        inbox, line = started[0]
        self.assertNotEqual(inbox, chat)  # …but in her Reminders session.
        self.assertEqual(self.store.conversation(inbox)["kind"], "reminders")
        self.assertTrue(line.startswith(reminders.MARK))
        self.assertIn("Study", line)
        self.assertEqual(self.store.reminders(), [])  # Delivered once.

    def test_with_her_session_open_she_reminds_you_there_as_she_writes(self):
        inbox = self.window._reminder_session()
        self.window._restore_conversation(inbox)
        self.store.add_reminder("Stretch", datetime.now(timezone.utc))
        with patch.object(self.window, "_begin_reply", return_value=True) as begin:
            self.window._check_reminders()
        self.assertTrue(begin.call_args.args[0].startswith(reminders.MARK))
        self.assertTrue(begin.call_args.kwargs["reminder"])

    def test_written_out_of_view_it_is_saved_there_marked_unread_and_your_chat_is_untouched(self):
        chat = self.window._conversation_id
        before = self.window.transcript.toPlainText()
        reminder = {"text": "Drink water", "due_at": datetime.now(timezone.utc).isoformat()}
        inbox = self.window._reminder_session()

        class Worker:
            turn_id, error = "t", ""
            stop_requested = __import__("threading").Event()

            def deleteLater(self):
                pass

        self.window._reminder_job = {"worker": Worker(), "inbox": inbox, "line": reminders.message(reminder),
                                     "reminder": reminder, "text": "", "cues": CueFilter()}
        self.window._reminder_chunk("t", "Water first. [[smile]] Then the next chapter.")
        self.window._reminder_finished()
        self.assertIsNone(self.window._reminder_job)
        self.assertEqual(self.window._conversation_id, chat)
        self.assertEqual(self.window.transcript.toPlainText(), before)
        saved = self.store.messages(inbox)
        self.assertTrue(saved[0]["display"].startswith(reminders.MARK))
        self.assertEqual(saved[1]["display"], "Water first. Then the next chapter.")
        self.assertEqual(self.store.conversation(inbox)["unread"], 1)
        # The sidebar shows her session above your chats, with what is new; opening it reads it.
        top = self.window.sidebar.list.item(0)
        self.assertEqual((top.text(), top.data(UNREAD)), ("Reminders from Jingliu", 1))
        self.assertEqual(self.window.sidebar._buttons_for(top), [])
        self.window._switch_conversation(inbox)
        self.assertEqual(self.store.conversation(inbox)["unread"], 0)
        text = self.window.transcript.toPlainText()
        self.assertIn("Reminder (", text)
        self.assertIn("Water first. Then the next chapter.", text)
        self.assertNotIn("You", text.split("Reminder (")[1].split("Water first")[0])  # A clock note, not your words.

    def test_long_missed_reminders_are_listed_not_delivered(self):
        self.store.add_reminder("Old one", datetime.now(timezone.utc) - timedelta(days=2))
        with patch.object(self.window, "_begin_reply") as begin:
            self.window._check_reminders()
        begin.assert_not_called()
        self.assertIn("Missed while the app was closed: “Old one”", self.window.transcript.toPlainText())

    def test_without_a_connection_the_reminder_is_still_left_in_her_session(self):
        self.store.add_reminder("Drink water", datetime.now(timezone.utc))
        with patch.object(Settings, "validate_connection", side_effect=ValueError("no model")):
            self.window._check_reminders()
        inbox = self.window._reminder_session()
        self.assertEqual(self.store.messages(inbox)[-1]["display"], "Reminder: Drink water")
        self.assertEqual(self.store.conversation(inbox)["unread"], 1)
        self.assertEqual(self.store.reminder_conversation(self.store.conversation(inbox)["character_key"]), inbox)

    def test_reminders_dialog_lists_and_removes(self):
        from companion.ui.library import ReminderDialog
        self.store.add_reminder("Call mum", datetime.now(timezone.utc) + timedelta(days=1))
        dialog = ReminderDialog(self.store, self.window)
        self.assertEqual(dialog.items.count(), 1)
        dialog._remove(self.store.reminders()[0]["id"])
        self.assertEqual(dialog.items.count(), 0)
        self.assertTrue(dialog.empty.isVisibleTo(dialog))
        dialog.deleteLater()


if __name__ == "__main__":
    unittest.main()
