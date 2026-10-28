"""Study subjects: shared memory across sessions, spaced repetition, her study cues and the study tools."""

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
        context = study.context(self.store.project(self.subject), [], progress)
        self.assertIn('study session for the user\'s subject "Statistika"', context)
        self.assertIn("[[card: question || answer]]", context)
        self.assertIn("2 of 3 recent quiz answers right", context)
        self.assertNotIn("this conversation belongs to the user's project", context)


class SubjectMemoryTests(unittest.TestCase):
    """A subject is a folder of sessions: in one, she remembers what was covered in the others."""

    def setUp(self):
        self.store = Store(":memory:")
        self.addCleanup(self.store.close)
        self.subject = self.store.project(self.store.create_project("Statistika", "study"))

    def session(self, title, user, reply, character="me"):
        conversation = self.store.create_conversation(character)
        self.store.rename_conversation(conversation, title)
        self.store.set_conversation_project(conversation, self.subject["id"])
        turn = self.store.start_turn(conversation, user)
        self.store.save_turn(turn, reply, reply, "complete")
        return conversation

    def test_a_new_session_remembers_the_earlier_ones(self):
        first = self.session("Mean and median", "What is the median?", "The middle value when sorted.")
        noted = self.session("Variance", "Explain variance", "The average squared distance from the mean.")
        self.store.save_summary(noted, "Covered variance and standard deviation; struggled with squaring.")
        current = self.session("Today", "Hello", "Welcome back.")
        memory = study.recall(self.store, self.subject, current, "me")
        self.assertIn("The middle value when sorted.", memory)          # Last exchanges of a session
        self.assertIn("struggled with squaring", memory)               # Saved notes when there are any
        self.assertNotIn("The average squared distance", memory)        # ...instead of its messages
        self.assertNotIn("Welcome back.", memory)                       # Not the session itself
        self.assertLess(memory.index("Variance"), memory.index("Mean and median"))  # Newest first
        self.assertIn(memory, study.context(self.subject, [], None, memory))
        self.assertEqual(study.recall(self.store, self.subject, first, "someone else"), "")  # Another character's

    def test_memory_stays_within_its_budget(self):
        for number in range(30):
            self.session(f"Session {number}", "Q" * 500, "A" * 600)
        memory = study.recall(self.store, self.subject, "", "me")
        self.assertLessEqual(len(memory), study.RECALL_CHARS + 1000)
        self.assertLessEqual(memory.count('"session"'), study.RECALL_SESSIONS)


class MaterialsFolderTests(unittest.TestCase):
    """A linked folder is read in place: she sees its index and only the passages a message needs."""

    def setUp(self):
        import tempfile
        from pathlib import Path
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.folder, self.cache = Path(temporary.name) / "Resources", Path(temporary.name) / "cache"
        (self.folder / "week 2").mkdir(parents=True)
        (self.folder / "normalisation.md").write_text(
            "Filler about the course schedule. " * 80 + "Third normal form (3NF) removes transitive functional "
            "dependencies: every non-key attribute depends on the key, the whole key and nothing but the key.",
            encoding="utf-8")
        (self.folder / "week 2" / "indexing.txt").write_text("A B-tree index speeds up lookups on a column.",
                                                             encoding="utf-8")
        (self.folder / "diagram.png").write_bytes(b"\x89PNG")
        (self.folder / ".hidden.txt").write_text("secret", encoding="utf-8")

    def test_index_and_only_the_related_passages(self):
        from companion.chat import materials
        text = materials.context(self.folder, "what is 3NF and transitive dependency?", self.cache)
        self.assertIn("- normalisation.md", text)
        self.assertIn("- week 2/indexing.txt", text)
        self.assertNotIn(".hidden", text)
        self.assertIn("nothing but the key", text)          # The passage the question needs…
        self.assertNotIn("B-tree", text)                     # …not the unrelated file.
        self.assertLess(len(text), 4000)                     # Far less than every file in full.
        self.assertIn("Not readable as text here (listed only): diagram.png", text)
        count, read, characters = materials.summary(self.folder, self.cache)
        self.assertEqual((count, read), (3, 2))              # Two of three files are text; the picture is listed.
        self.assertGreater(characters, 2700)

    def test_files_are_read_once_and_again_when_changed(self):
        from companion.chat import materials
        path = self.folder / "week 2" / "indexing.txt"
        materials.context(self.folder, "index", self.cache)
        self.assertTrue(materials.is_cached(path, self.cache))
        with patch.object(materials, "_extract", side_effect=AssertionError("read again")):
            self.assertIn("B-tree", materials.context(self.folder, "B-tree index", self.cache))
        path.write_text("A hash index answers equality lookups.", encoding="utf-8")
        os.utime(path, (time.time() + 5, time.time() + 5))
        self.assertIn("hash index", materials.context(self.folder, "hash index", self.cache))

    def test_word_and_powerpoint_files_are_read_without_extra_installs(self):
        import zipfile
        from companion.chat import materials
        with zipfile.ZipFile(self.folder / "slides.pptx", "w") as archive:
            archive.writestr("ppt/slides/slide1.xml", "<p:sld><a:t>Relational algebra</a:t></p:sld>")
            archive.writestr("ppt/slides/slide2.xml", "<p:sld><a:t>Selection sigma filters rows</a:t></p:sld>")
        with zipfile.ZipFile(self.folder / "notes.docx", "w") as archive:
            archive.writestr("word/document.xml", "<w:document><w:t>Projection pi keeps columns</w:t></w:document>")
        text = materials.context(self.folder, "selection sigma and projection pi", self.cache)
        self.assertIn("slides.pptx (2 slides)", text)
        self.assertIn('where="slide 2"', text)
        self.assertIn("Projection pi keeps columns", text)

    def test_a_subject_with_a_folder_gives_her_its_materials(self):
        subject = {"name": "Basdat", "description": "", "instructions": "", "folder": str(self.folder)}
        from companion.chat import materials
        with patch.object(materials, "CACHE", self.cache):
            text = study.context(subject, [], query="explain third normal form")
        self.assertIn("Materials folder:", text)
        self.assertIn("nothing but the key", text)


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

    def test_a_new_session_in_the_subject_remembers_the_last_one(self):
        turn = self.store.start_turn(self.window._conversation_id, "Teach me the mean")
        self.store.save_turn(turn, "The mean is the sum divided by the count.", "x", "complete")
        self.window._new_chat_in_project(self.subject)
        self.assertIn("The mean is the sum divided by the count.", self.window._project_context())

    def test_linking_a_materials_folder(self):
        import tempfile
        from pathlib import Path
        from companion.chat import materials
        folder = tempfile.mkdtemp()
        cache = patch.object(materials, "CACHE", Path(tempfile.mkdtemp()))
        cache.start()
        self.addCleanup(cache.stop)
        (Path(folder) / "er-diagrams.txt").write_text("An entity set is drawn as a rectangle.", encoding="utf-8")
        page = self.window.project_page
        self.window._open_project(self.subject)
        self.assertTrue(page.link_folder.isVisible())
        self.assertFalse(page.materials.isVisible())
        with patch("companion.ui.projects.QFileDialog.getExistingDirectory", return_value=folder), \
                patch.object(materials, "warm"):
            page.link_folder.click()
        self.assertEqual(self.store.project(self.subject)["folder"], str(Path(folder)))
        self.assertTrue(page.materials.isVisible())
        self.assertEqual(page.link_folder.text(), "Change folder…")
        self.window._new_chat_in_project(self.subject)
        self.assertIn("An entity set is drawn as a rectangle.", self.window._project_context("what is an entity set"))
        page_button = next(b for b in page.materials.findChildren(type(page.link_folder)) if b.text() == "Unlink")
        self.window._open_project(self.subject)
        page_button.click()
        self.assertEqual(self.store.project(self.subject)["folder"], "")
        self.assertTrue((Path(folder) / "er-diagrams.txt").exists())  # Unlinking deletes nothing.

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
