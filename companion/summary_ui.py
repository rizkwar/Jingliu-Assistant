"""Inspectable conversation notes. Generation is owned by the main window."""

import sqlite3

from PySide6.QtCore import QTimer, Signal, Slot
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QVBoxLayout

from .continuity import MAX_SUMMARY_CHARS, summary_batch


class SummaryDialog(QDialog):
    generate_requested = Signal()
    cancel_requested = Signal()
    saved = Signal()

    def __init__(self, store, conversation_id, parent=None):
        super().__init__(parent)
        self.store = store
        self.conversation_id = conversation_id
        self._turns = store.context_turns(conversation_id)
        self.busy = False
        self._close_when_idle = False
        self._close_timer = QTimer(self)
        self._close_timer.setSingleShot(True)
        self._close_timer.timeout.connect(self.reject)
        saved = store.summary(conversation_id)
        self.through_id = saved["through_id"] if saved else 0
        self.setWindowTitle("Conversation context")
        self.resize(640, 580)
        self.setMinimumSize(540, 500)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 22, 22, 22)
        layout.setSpacing(12)
        explanation = QLabel(
            "Recent exchanges stay in context. Save notes here to carry older details into future replies "
            "in this conversation. Generate draft sends older exchanges and these notes to your configured model. "
            "Review the result before saving; summaries can miss details. Keep real developments and preferences "
            "separate from fictional scenes. The character profile is supplied separately with every reply. "
            "Your full transcript stays in History."
        )
        explanation.setWordWrap(True)
        layout.addWidget(explanation)
        self.coverage = QLabel()
        self.coverage.setObjectName("hint")
        self.coverage.setWordWrap(True)
        layout.addWidget(self.coverage)
        self.editor = QPlainTextEdit()
        self.editor.setPlaceholderText("Write your own conversation notes, or generate a draft from older exchanges…")
        self.editor.setPlainText(saved["content"] if saved else "")
        self.editor.textChanged.connect(self._count)
        layout.addWidget(self.editor, 1)
        self.count = QLabel()
        self.count.setObjectName("hint")
        layout.addWidget(self.count)
        self.status = QLabel("Saved notes accompany future replies, including when saved memory retrieval is off.")
        self.status.setWordWrap(True)
        self.status.setObjectName("hint")
        layout.addWidget(self.status)
        buttons = QHBoxLayout()
        self.generate = QPushButton("Generate draft")
        self.generate.clicked.connect(self.generate_requested)
        buttons.addWidget(self.generate)
        self.cancel = QPushButton("Cancel")
        self.cancel.clicked.connect(self.cancel_requested)
        self.cancel.setEnabled(False)
        buttons.addWidget(self.cancel)
        self.clear = QPushButton("Clear saved")
        self.clear.clicked.connect(self._clear)
        buttons.addWidget(self.clear)
        buttons.addStretch()
        self.save = QPushButton("Save")
        self.save.clicked.connect(self._save)
        buttons.addWidget(self.save)
        done = QPushButton("Done")
        done.clicked.connect(self.reject)
        buttons.addWidget(done)
        layout.addLayout(buttons)
        self.refresh_coverage()
        self._count()

    def batch(self):
        return summary_batch(self._turns, self.editor.toPlainText().strip(), self.through_id)

    def refresh_coverage(self):
        batch = self.batch()
        pending = batch.count + batch.remaining
        text = (
            f"Draft coverage: {pending} older {'exchange remains' if pending == 1 else 'exchanges remain'}. "
            f"The next draft covers {batch.count}; recent exchanges stay verbatim."
        )
        if batch.excerpted:
            text += " An oversized exchange will use excerpts; some source details are omitted."
        self.coverage.setText(text)
        self.generate.setEnabled(not self.busy and batch.count > 0)

    @Slot()
    def _count(self):
        length = len(self.editor.toPlainText().strip())
        self.count.setText(f"{length:,} / {MAX_SUMMARY_CHARS:,} characters")
        self.save.setEnabled(not self.busy and 0 < length <= MAX_SUMMARY_CHARS)
        self.generate.setEnabled(not self.busy and length <= MAX_SUMMARY_CHARS and self.generate.isEnabled())
        if not self.busy and length <= MAX_SUMMARY_CHARS:
            self.refresh_coverage()

    def set_busy(self, busy):
        self.busy = busy
        self.editor.setReadOnly(busy)
        self.generate.setEnabled(False)
        self.cancel.setEnabled(busy)
        self.clear.setEnabled(not busy)
        self.save.setEnabled(not busy)
        self._count()
        if busy:
            self.status.setText("Generating a draft… Cancel leaves your saved summary and current notes unchanged.")
        elif self._close_when_idle:
            self._close_timer.start(0)

    def draft_ready(self, text, through_id):
        self.through_id = through_id
        self.editor.setPlainText(text)
        self.refresh_coverage()
        self.status.setText("Draft ready. Review or edit it, then Save to use it in future replies.")

    @Slot()
    def _save(self):
        if self.busy:
            return
        try:
            self.store.save_summary(self.conversation_id, self.editor.toPlainText(), self.through_id)
        except (sqlite3.Error, ValueError) as exc:
            self.status.setText(str(exc) if isinstance(exc, ValueError) else "Could not save notes. Please try again.")
            return
        self.status.setText("Summary saved for this conversation. It will accompany the next reply.")
        self.saved.emit()

    @Slot()
    def _clear(self):
        if self.busy:
            return
        try:
            self.store.clear_summary(self.conversation_id)
        except sqlite3.Error:
            self.status.setText("Could not clear the saved summary. Please try again.")
            return
        self.through_id = 0
        self.editor.clear()
        self.refresh_coverage()
        self.status.setText("Saved summary cleared. Original messages and explicit memories are kept.")
        self.saved.emit()

    def reject(self):
        if self.busy:
            self._close_when_idle = True
            self.cancel_requested.emit()
        else:
            self._close_timer.stop()
            super().reject()

    def closeEvent(self, event):
        if self.busy:
            self.reject()
            event.ignore()
        else:
            super().closeEvent(event)
