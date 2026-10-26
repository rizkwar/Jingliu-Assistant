"""Study subjects: spaced repetition, the exam countdown, her study cues, and the window's study tools."""

from dataclasses import replace
from datetime import date, timedelta
import os
import time
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent, Qt

from companion.chat import study
from companion.core.storage import Store
from companion.ui.flashcards import FlashcardReview
from companion.ui.window import CompanionWindow
from tests.python.ui.test_ui import SETTINGS, FakeMicrophone, FakeSpeech
from tests.qt_test_support import application

DAY = date(2026, 10, 26)


class ScheduleTests(unittest.TestCase):
    def test_cards_come_back_later_the_better_they_are_known(self):
        new = {"interval": 0, "ease": 2.5, "reviews": 0}
        self.assertEqual(study.schedule(new, "again", DAY)[:2], ("2026-10-26", 0))
        self.assertEqual(study.schedule(new, "good", DAY)[:2], ("2026-10-27", 1))
        self.assertEqual(study.schedule(new, "easy", DAY)[:2], ("2026-10-30", 4))
        known = {"interval": 3, "ease": 2.5, "reviews": 2}
        self.assertEqual(study.schedule(known, "good", DAY)[1], 8)        # 3 × 2.5, rounded
        self.assertEqual(study.schedule(known, "hard", DAY)[1], 4)
        self.assertTrue(study.schedule(known, "again", DAY)[3])           # A lapse on a known card
        self.assertGreaterEqual(study.schedule({"interval": 3, "ease": 1.3}, "again", DAY)[2], 1.3)

    def test_exam_countdown_reads_naturally(self):
        for offset, text in ((0, "Exam today"), (1, "Exam tomorrow"), (12, "Exam in 12 days"),
                             (-1, "Exam was 1 day ago"), (-3, "Exam was 3 days ago")):
            self.assertEqual(study.exam_text((DAY + timedelta(days=offset)).isoformat(), DAY), text)
        self.assertEqual(study.exam_text(""), "")

    def test_card_cues_need_a_question_and_an_answer(self):
        self.assertEqual(study.parse_card(" What is a limit? || The value approached. "),
                         ("What is a limit?", "The value approached."))
        for bad in ("No separator", "|| only an answer", "only a question ||"):
            self.assertIsNone(study.parse_card(bad))


class StudyStorageTests(unittest.TestCase):
    def setUp(self):
        self.store = Store(":memory:")
        self.addCleanup(self.store.close)
        self.subject = self.store.create_project("Statistika", "study")

    def test_subjects_are_separate_from_projects(self):
        self.store.create_project("Website")
        self.assertEqual([p["name"] for p in self.store.projects("study")], ["Statistika"])
        self.assertEqual([p["name"] for p in self.store.projects("project")], ["Website"])
        self.store.update_project(self.subject, exam_date="2026-11-07")
        self.assertEqual(self.store.project(self.subject)["exam_date"], "2026-11-07")
        with self.assertRaises(ValueError):
            self.store.update_project(self.subject, exam_date="next week")
        with self.assertRaises(ValueError):
            self.store.create_project("Odd", "hobby")

    def test_cards_events_and_progress(self):
        first = self.store.add_flashcard(self.subject, "Mean?", "The average.")
        self.store.add_flashcard(self.subject, "Median?", "The middle value.")
        with self.assertRaises(ValueError):
            self.store.add_flashcard(self.subject, " ", "x")
        self.store.schedule_flashcard(first, "2999-01-01", 30, 2.6)
        self.store.log_study(self.subject, "focus", 25)
        for right in (1, 1, 0):
            self.store.log_study(self.subject, "answer", right)
        progress = study.stats(self.store, self.subject)
        self.assertEqual((progress["cards"], progress["due"], progress["focus_week"], progress["right"], progress["answers"]),
                         (2, 1, 25, 2, 3))
        context = study.context(dict(self.store.project(self.subject), exam_date=""), [], progress)
        self.assertIn('study session for the user\'s subject "Statistika"', context)
        self.assertIn("[[card: question || answer]]", context)
        self.assertIn("2 of 3 recent quiz answers right", context)
        self.assertNotIn("this conversation belongs to the user's project", context)


class StudyWindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = application()

    def setUp(self):
        self.store = Store(":memory:")
        self.window = CompanionWindow(replace(SETTINGS, llm_provider="claude"), speech=FakeSpeech(),
                                      microphone=FakeMicrophone(), store=self.store)
        self.window.resize(1200, 800)
        self.window.show()
        self.app.processEvents()
        self.subject = self.window._new_project("study")
        self.window._new_chat_in_project(self.subject)

    def tearDown(self):
        self.window.close()
        self.window.deleteLater()
        self.app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.app.processEvents()

    def chips(self):
        row = self.window.type_row
        return [row.itemAt(index).widget().text() for index in range(row.count()) if row.itemAt(index).widget()]

    def cue(self, *cues):
        self.window._queue_cues([(0, cue) for cue in cues])
        self.window._apply_memory_actions()
        self.app.processEvents()

    def test_three_tabs_keep_the_kinds_apart(self):
        sidebar = self.window.sidebar
        self.assertEqual(sidebar.tab, "study")  # A study session shows the Study tab.
        self.assertEqual(sidebar.trees["study"].topLevelItem(0).text(0), "New subject")
        self.assertEqual(sidebar.trees["project"].topLevelItemCount(), 0)
        sidebar.tab_buttons["projects"].click()
        self.assertEqual(sidebar.tab, "projects")
        self.assertEqual(self.window.settings.sidebar_tab, "projects")  # Remembered.
        self.window._new_conversation()
        self.assertFalse(self.window.type_bar.isVisible())  # Everyday chats have no study tools.

    def test_study_sessions_have_their_tools(self):
        self.assertTrue(self.window.type_bar.isVisible())
        self.assertEqual(self.chips()[:4], ["Quiz me", "Make flashcards", "Explain simpler", "Summarize"])
        self.assertIn("Focus 25:00", self.chips())
        self.assertIn("tutor", self.window._project_context())

    def test_her_cards_scores_and_focus_cues(self):
        self.cue("card:Mean? || The average.", "card:Median? || The middle value.", "score:right", "score:wrong")
        self.assertEqual(len(self.store.flashcards(self.subject)), 2)
        self.assertIn("2 flashcards added to New subject", self.window.transcript.toPlainText())
        self.assertIn("Quiz 1/2", [w.text() for w in self.window.type_bar.findChildren(type(self.window.status))])
        self.assertIn("Review 2", self.chips())
        note = self.window.transcript._items[-1]
        note.undo.emit()
        self.assertEqual(self.store.flashcards(self.subject), [])
        self.cue("focus:40")
        self.assertEqual(self.window._focus["minutes"], 40)
        self.assertTrue(any(text.startswith("Focus 39:") or text.startswith("Focus 40:") for text in self.chips()))
        self.window._focus["ends"] = time.monotonic() - 1
        with patch.object(self.window, "_begin_reply") as begin:  # Never a real model in tests.
            self.window._focus_tick()
        self.assertIsNone(self.window._focus)
        self.assertEqual(study.stats(self.store, self.subject)["focus_week"], 40)
        line = begin.call_args.args[0]
        self.assertTrue(line.startswith(study.MARK))  # She is told the timer ended and speaks first.
        self.assertIn("40-minute focus session", line)

    def test_cues_outside_a_study_session_change_nothing(self):
        self.window._new_conversation()
        self.cue("card:Mean? || The average.", "score:right", "focus:25")
        self.assertEqual(self.store.flashcards(self.subject), [])
        self.assertIsNone(self.window._focus)

    def test_reviewing_flashcards(self):
        card = self.store.add_flashcard(self.subject, "Mean?", "The average.")
        review = FlashcardReview(self.store, self.subject)
        self.assertEqual(review.front.text(), "Mean?")
        self.assertFalse(review.back.isVisibleTo(review))
        review._reveal()
        self.assertIn("1 day", review.grade_buttons["good"].text())
        review._grade("good")
        self.assertEqual(self.store.flashcard(card)["interval"], 1)
        self.assertEqual(review.front.text(), "Done for now.")
        self.assertIn("Practise all 1", review.practise.text())
        review.deleteLater()


if __name__ == "__main__":
    unittest.main()
