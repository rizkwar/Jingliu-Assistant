import os
import sqlite3
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent
from PySide6.QtWidgets import QApplication, QMessageBox

from companion.library_ui import HistoryDialog, MemoryDialog
from companion.storage import Store
from companion.summary_ui import SummaryDialog
from qt_test_support import application


class LibraryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = application()

    def setUp(self):
        self.store = Store(":memory:")
        self.dialog = None

    def tearDown(self):
        if self.dialog is not None:
            self.dialog.close()
            self.dialog.deleteLater()
            self.app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.store.close()

    def chat(self):
        conversation = self.store.create_conversation()
        turn = self.store.start_turn(conversation, "Hello")
        self.store.save_turn(turn, "Hello.", "Hello.", "complete")
        return conversation

    def test_memory_editor_add_edit_delete_round_trip(self):
        self.dialog = MemoryDialog(self.store)
        self.dialog.editor.setPlainText("Prefer examples")
        self.dialog._save()
        memory_id = self.dialog.memory_id
        self.dialog.editor.setPlainText("Prefer Python examples")
        self.dialog.pinned.setChecked(False)
        self.dialog._save()
        self.assertEqual(self.store.memories()[0]["content"], "Prefer Python examples")
        self.assertEqual(self.store.memories()[0]["id"], memory_id)
        self.assertFalse(self.store.memories()[0]["pinned"])
        with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes):
            self.dialog._delete()
        self.assertEqual(self.store.memories(), [])
        self.assertEqual(self.dialog.items.count(), 0)

    def test_history_opens_selected_conversation_and_deletion_preserves_other_data(self):
        first = self.chat()
        second = self.chat()
        self.store.save_memory("Keep this memory")
        self.dialog = HistoryDialog(self.store)
        self.dialog._open()
        self.assertEqual(self.dialog.selected_id, second)
        with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes):
            self.dialog._delete()
        self.assertIsNone(self.store.conversation(second))
        self.assertIsNotNone(self.store.conversation(first))
        self.assertEqual(len(self.store.memories()), 1)

    def test_each_conversation_shows_when_a_glimpse_and_its_own_delete_button(self):
        older = self.store.create_conversation()
        turn = self.store.start_turn(older, "Remember the moon festival?")
        self.store.save_turn(turn, "I remember the lanterns.", "I remember the lanterns.", "complete")
        newer = self.chat()
        self.store.create_conversation()  # Never used: not listed.
        self.dialog = HistoryDialog(self.store)
        rows = [self.dialog.items.itemWidget(self.dialog.items.item(i)) for i in range(self.dialog.items.count())]
        self.assertEqual([row.conversation_id for row in rows], [newer, older])
        self.assertEqual(rows[1].full_preview, "I remember the lanterns.")
        self.assertIn("2 saved conversations", self.dialog.summary.text())
        with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.No):
            rows[1].delete.click()
        self.assertIsNotNone(self.store.conversation(older))  # Nothing happens without a yes.
        with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes):
            rows[1].delete.click()
        self.assertIsNone(self.store.conversation(older))
        self.assertEqual(self.dialog.items.count(), 1)

    def test_search_filters_titles_and_open_and_delete_follow_the_visible_selection(self):
        for title in ("Moon festival plans", "Python homework", "Moonlight sword practice"):
            conversation = self.chat()
            self.store.connection.execute("UPDATE conversations SET title=? WHERE id=?", (title, conversation))
        self.dialog = HistoryDialog(self.store)
        self.dialog.search.setText("moon")
        shown = [self.dialog.items.item(i) for i in range(3) if not self.dialog.items.item(i).isHidden()]
        self.assertEqual(len(shown), 2)
        self.dialog.search.setText("nothing like this")
        self.assertFalse(self.dialog.open_button.isEnabled())
        self.assertFalse(self.dialog.delete_button.isEnabled())
        self.assertIn("No conversation", self.dialog.empty.text())
        self.dialog._open()
        self.assertIsNone(self.dialog.selected_id)

    def test_a_conversation_can_be_renamed_in_place_and_keeps_its_name(self):
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QKeyEvent
        from PySide6.QtCore import QEvent as E
        conversation = self.chat()
        self.dialog = HistoryDialog(self.store)
        row = self.dialog.items.itemWidget(self.dialog.items.item(0))
        row.rename.click()
        self.assertTrue(row.editor.isVisibleTo(row))
        row.editor.setText("  Calculus   exam prep ")
        row.editor.returnPressed.emit()
        self.app.processEvents()
        self.assertEqual(self.store.conversation(conversation)["title"], "Calculus exam prep")
        row = self.dialog.items.itemWidget(self.dialog.items.item(0))
        self.assertEqual(row.full_title, "Calculus exam prep")
        # Esc leaves it as it was; an empty name is not saved.
        row.start_rename()
        row.editor.setText("Something else")
        self.app.sendEvent(row.editor, QKeyEvent(E.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier))
        self.assertFalse(row.editor.isVisibleTo(row))
        row.start_rename()
        row.editor.setText("   ")
        row.editor.returnPressed.emit()
        self.app.processEvents()
        self.assertEqual(self.store.conversation(conversation)["title"], "Calculus exam prep")
        # New messages never replace a name the person chose.
        turn = self.store.start_turn(conversation, "Another question")
        self.store.save_turn(turn, "Answer.", "Answer.", "complete")
        self.assertEqual(self.store.conversation(conversation)["title"], "Calculus exam prep")
        with self.assertRaises(ValueError):
            self.store.rename_conversation(conversation, "x" * 121)

    def test_dates_read_naturally(self):
        from datetime import date, datetime
        from companion.library_ui import when
        local = lambda *parts: datetime(*parts).astimezone().isoformat()
        today = date(2026, 10, 25)
        self.assertEqual(when(local(2026, 10, 25, 14, 32), today), "Today, 14:32")
        self.assertEqual(when(local(2026, 10, 24, 9, 5), today), "Yesterday, 09:05")
        self.assertEqual(when(local(2026, 10, 21, 9, 5), today), "Wednesday")
        self.assertEqual(when(local(2026, 3, 3, 9, 5), today), "3 Mar 2026")
        self.assertEqual(when("not a date", today), "")

    def test_summary_can_be_written_edited_and_cleared_without_network(self):
        conversation = self.store.create_conversation()
        self.dialog = SummaryDialog(self.store, conversation)
        self.assertFalse(self.dialog.generate.isEnabled())
        self.dialog.editor.setPlainText("We are building a desktop companion.")
        self.dialog._save()
        self.assertEqual(self.store.summary(conversation)["content"], "We are building a desktop companion.")
        self.dialog.editor.setPlainText("Use Python and local voice.")
        self.dialog._save()
        self.assertEqual(self.store.summary(conversation)["content"], "Use Python and local voice.")
        self.dialog._clear()
        self.assertIsNone(self.store.summary(conversation))
        self.assertEqual(self.dialog.through_id, 0)

    def test_invalid_summary_disables_save_and_generation_until_shortened(self):
        conversation = self.store.create_conversation()
        for _ in range(13):
            turn = self.store.start_turn(conversation, "Question")
            self.store.save_turn(turn, "Answer", "Answer", "complete")
        self.dialog = SummaryDialog(self.store, conversation)
        self.assertTrue(self.dialog.generate.isEnabled())
        self.dialog.editor.setPlainText("x" * 6001)
        self.assertFalse(self.dialog.save.isEnabled())
        self.assertFalse(self.dialog.generate.isEnabled())
        self.dialog.editor.setPlainText("Shorter notes")
        self.assertTrue(self.dialog.save.isEnabled())
        self.assertTrue(self.dialog.generate.isEnabled())

    def test_failed_summary_save_or_clear_keeps_previously_saved_notes(self):
        conversation = self.store.create_conversation()
        self.store.save_summary(conversation, "Original notes")
        self.dialog = SummaryDialog(self.store, conversation)
        self.dialog.editor.setPlainText("New draft")
        with patch.object(self.store, "save_summary", side_effect=sqlite3.OperationalError("disk full")):
            self.dialog._save()
        self.assertIn("Could not save", self.dialog.status.text())
        self.assertEqual(self.store.summary(conversation)["content"], "Original notes")
        self.assertEqual(self.dialog.editor.toPlainText(), "New draft")
        with patch.object(self.store, "clear_summary", side_effect=sqlite3.OperationalError("database locked")):
            self.dialog._clear()
        self.assertEqual(self.store.summary(conversation)["content"], "Original notes")
        self.assertEqual(self.dialog.editor.toPlainText(), "New draft")
