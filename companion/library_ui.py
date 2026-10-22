"""Small native managers for saved conversations and explicit memories."""

import sqlite3

from PySide6.QtCore import Qt, Slot
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QHBoxLayout, QLabel, QListWidget,
    QListWidgetItem, QMessageBox, QPlainTextEdit, QPushButton, QVBoxLayout,
)


class HistoryDialog(QDialog):
    def __init__(self, store, parent=None):
        super().__init__(parent)
        self.store = store
        self.selected_id = None
        self.setWindowTitle("Saved conversations")
        self.resize(560, 440)
        layout = QVBoxLayout(self)
        description = QLabel("Open a conversation to continue it. New conversations keep older chats saved.")
        description.setWordWrap(True)
        layout.addWidget(description)
        self.items = QListWidget()
        self.items.itemDoubleClicked.connect(self._open)
        layout.addWidget(self.items)
        buttons = QHBoxLayout()
        delete = QPushButton("Delete selected")
        delete.clicked.connect(self._delete)
        buttons.addWidget(delete)
        buttons.addStretch()
        close = QPushButton("Close")
        close.clicked.connect(self.reject)
        buttons.addWidget(close)
        open_button = QPushButton("Open")
        open_button.clicked.connect(self._open)
        buttons.addWidget(open_button)
        layout.addLayout(buttons)
        self.refresh()

    def refresh(self):
        self.items.clear()
        for conversation in self.store.conversations():
            item = QListWidgetItem(f"{conversation['title']}\n{conversation['message_count']} saved messages")
            item.setData(Qt.ItemDataRole.UserRole, conversation["id"])
            self.items.addItem(item)
        if self.items.count():
            self.items.setCurrentRow(0)

    @Slot()
    def _open(self):
        item = self.items.currentItem()
        if item:
            self.selected_id = item.data(Qt.ItemDataRole.UserRole)
            self.accept()

    @Slot()
    def _delete(self):
        item = self.items.currentItem()
        if not item:
            return
        if QMessageBox.question(self, "Delete conversation", "Delete this conversation and its messages? Saved memories are managed separately.") != QMessageBox.StandardButton.Yes:
            return
        try:
            self.store.delete_conversation(item.data(Qt.ItemDataRole.UserRole))
            self.refresh()
        except sqlite3.Error:
            QMessageBox.warning(self, "Could not delete", "The database could not be updated. Please try again.")


class MemoryDialog(QDialog):
    def __init__(self, store, parent=None):
        super().__init__(parent)
        self.store = store
        self.memory_id = None
        name = parent.settings.name if parent is not None else "Companion"
        self.setWindowTitle(f"{name}'s memory")
        self.resize(620, 560)
        layout = QVBoxLayout(self)
        description = QLabel("Memories are saved only when you add them. Included memories are sent with online replies. Pinned memories are preferred; others are matched to your topic.")
        description.setWordWrap(True)
        layout.addWidget(description)
        self.items = QListWidget()
        self.items.currentItemChanged.connect(self._select)
        layout.addWidget(self.items, 1)
        self.editor = QPlainTextEdit()
        self.editor.setPlaceholderText("A preference or fact you want Mira to remember (up to 1,000 characters)")
        self.editor.setFixedHeight(100)
        layout.addWidget(self.editor)
        self.pinned = QCheckBox("Pin: prefer including this across topics")
        self.pinned.setChecked(True)
        layout.addWidget(self.pinned)
        hint = QLabel("Up to 6 memories and 3,000 characters are included per reply. Deleting a memory does not delete its original conversation.")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        buttons = QHBoxLayout()
        for label, callback in (("New", self._new), ("Save", self._save), ("Delete", self._delete)):
            button = QPushButton(label)
            button.clicked.connect(callback)
            buttons.addWidget(button)
        buttons.addStretch()
        close = QPushButton("Close")
        close.clicked.connect(self.accept)
        buttons.addWidget(close)
        layout.addLayout(buttons)
        self.refresh()

    def refresh(self):
        self.items.clear()
        for memory in self.store.memories():
            title = f"#{memory['id']} {'[pinned] ' if memory['pinned'] else ''}{memory['content']}"
            item = QListWidgetItem(title)
            item.setData(Qt.ItemDataRole.UserRole, memory)
            self.items.addItem(item)
        self._new()

    @Slot()
    def _new(self):
        self.items.setCurrentRow(-1)
        self.memory_id = None
        self.editor.clear()
        self.pinned.setChecked(True)
        self.editor.setFocus()

    def _select(self, current, previous):
        if current is not None:
            memory = current.data(Qt.ItemDataRole.UserRole)
            self.memory_id = memory["id"]
            self.editor.setPlainText(memory["content"])
            self.pinned.setChecked(bool(memory["pinned"]))

    @Slot()
    def _save(self):
        try:
            memory_id = self.store.save_memory(self.editor.toPlainText(), self.pinned.isChecked(), self.memory_id)
            self.refresh()
            for index in range(self.items.count()):
                if self.items.item(index).data(Qt.ItemDataRole.UserRole)["id"] == memory_id:
                    self.items.setCurrentRow(index)
                    break
        except (ValueError, sqlite3.Error) as exc:
            QMessageBox.warning(self, "Could not save memory", str(exc) if isinstance(exc, ValueError) else "The database could not be updated. Please try again.")

    @Slot()
    def _delete(self):
        if self.memory_id is None:
            return
        if QMessageBox.question(self, "Delete memory", "Delete this saved memory? Conversation messages are kept separately.") != QMessageBox.StandardButton.Yes:
            return
        try:
            self.store.delete_memory(self.memory_id)
            self.refresh()
        except sqlite3.Error:
            QMessageBox.warning(self, "Could not delete", "The database could not be updated. Please try again.")
