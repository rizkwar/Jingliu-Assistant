import tempfile
import time
import os
import unittest
from pathlib import Path

from companion.task_journal import Journal, cleanup


class JournalTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        self.work = self.root / "work"
        self.work.mkdir()
        self.journal = Journal(self.root / "journal")

    def test_only_the_first_original_of_a_file_is_kept(self):
        target = self.work / "notes.txt"
        target.write_text("v1", encoding="utf-8")
        self.journal.before_write(target)
        target.write_text("v2", encoding="utf-8")
        self.journal.before_write(target)  # A second edit in the same task.
        target.write_text("v3", encoding="utf-8")
        self.journal.undo()
        self.assertEqual(target.read_text(encoding="utf-8"), "v1")

    def test_changes_made_since_the_task_are_respected(self):
        (self.work / "a.txt").write_text("a", encoding="utf-8")
        (self.work / "b.txt").write_text("b", encoding="utf-8")
        self.journal.move(self.work / "a.txt", self.work / "moved.txt")
        self.journal.delete(self.work / "b.txt")
        folder = self.journal.make_folder(self.work / "New")
        (self.work / "a.txt").write_text("a new file the person made", encoding="utf-8")
        (self.work / "b.txt").write_text("another", encoding="utf-8")
        (folder / "theirs.txt").write_text("keep", encoding="utf-8")
        done, problems = self.journal.undo()
        self.assertEqual(len(problems), 3)
        self.assertEqual((self.work / "a.txt").read_text(encoding="utf-8"), "a new file the person made")
        self.assertTrue((folder / "theirs.txt").exists())
        self.assertTrue((self.work / "moved.txt").exists())

    def test_moving_onto_an_existing_name_is_refused(self):
        (self.work / "a.txt").write_text("a", encoding="utf-8")
        (self.work / "b.txt").write_text("b", encoding="utf-8")
        with self.assertRaises(FileExistsError):
            self.journal.move(self.work / "a.txt", self.work / "b.txt")
        self.assertEqual(self.journal.undoable(), [])

    def test_removed_new_files_are_set_aside_not_destroyed(self):
        target = self.work / "draft.txt"
        self.journal.before_write(target)
        target.write_text("draft", encoding="utf-8")
        self.journal.undo()
        self.assertFalse(target.exists())
        kept = list((self.journal.files / "removed-by-undo").iterdir())
        self.assertEqual([p.read_text(encoding="utf-8") for p in kept], ["draft"])
        self.assertTrue(self.journal.undone)

    def test_old_journals_are_cleaned_up_after_a_week(self):
        old, recent = self.root / "undo" / "old", self.root / "undo" / "recent"
        old.mkdir(parents=True)
        recent.mkdir()
        week_ago = time.time() - 8 * 86400
        os.utime(old, (week_ago, week_ago))
        cleanup(self.root / "undo")
        self.assertFalse(old.exists())
        self.assertTrue(recent.exists())


if __name__ == "__main__":
    unittest.main()
