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
        first = self.store.create_conversation()
        second = self.store.create_conversation()
        self.store.save_memory("Keep this memory")
        self.dialog = HistoryDialog(self.store)
        self.dialog._open()
        self.assertEqual(self.dialog.selected_id, second)
        with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes):
            self.dialog._delete()
        self.assertIsNone(self.store.conversation(second))
        self.assertIsNotNone(self.store.conversation(first))
        self.assertEqual(len(self.store.memories()), 1)

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
