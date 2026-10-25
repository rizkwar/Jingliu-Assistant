"""Small native managers for saved conversations and explicit memories."""

from datetime import datetime
import sqlite3
from .character import character_key

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMenu,
    QMessageBox, QPlainTextEdit, QPushButton, QSizePolicy, QVBoxLayout,
)

from .theme import icon_button


def when(timestamp, today=None):
    """"Today, 14:32", "Yesterday, 09:10", "Monday" or "3 Mar 2026", in local time."""
    try:
        moment = datetime.fromisoformat(timestamp).astimezone()
    except (TypeError, ValueError):
        return ""
    today = today or datetime.now().astimezone().date()
    days = (today - moment.date()).days
    if days <= 0:
        return f"Today, {moment:%H:%M}"
    if days == 1:
        return f"Yesterday, {moment:%H:%M}"
    if days < 7:
        return f"{moment:%A}"
    return f"{moment.day} {moment:%b %Y}"


class ConversationRow(QFrame):
    """One saved conversation: title, when, a glimpse of the last message, and a delete button."""
    delete_requested = Signal(str)

    def __init__(self, conversation, preview, current, parent=None):
        super().__init__(parent)
        self.setObjectName("historyRow")
        self.conversation_id = conversation["id"]
        self.full_title = conversation["title"] or "New conversation"
        row = QHBoxLayout(self)
        row.setContentsMargins(14, 10, 8, 10)
        row.setSpacing(10)
        text = QVBoxLayout()
        text.setSpacing(2)
        top = QHBoxLayout()
        top.setSpacing(8)
        self.title = QLabel(self.full_title)
        self.title.setObjectName("historyTitle")
        self.title.setTextFormat(Qt.TextFormat.PlainText)
        self.title.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        top.addWidget(self.title, 1)
        if current:
            badge = QLabel("Open now")
            badge.setObjectName("historyBadge")
            top.addWidget(badge)
        text.addLayout(top)
        count = conversation["message_count"]
        meta = QLabel(" · ".join(filter(None, (when(conversation["updated_at"]),
                                                 f"{count} message{'' if count == 1 else 's'}"))))
        meta.setObjectName("historyMeta")
        text.addWidget(meta)
        self.full_preview = ""
        self.glimpse = None
        if preview:
            self.full_preview = ("You: " if preview["role"] == "user" else "") + " ".join(preview["display"].split())[:200]
            self.glimpse = QLabel(self.full_preview)
            self.glimpse.setObjectName("historyPreview")
            self.glimpse.setTextFormat(Qt.TextFormat.PlainText)
            self.glimpse.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
            text.addWidget(self.glimpse)
        row.addLayout(text, 1)
        self.delete = icon_button("delete", "Delete this conversation", "historyDelete")
        self.delete.clicked.connect(lambda: self.delete_requested.emit(self.conversation_id))
        row.addWidget(self.delete, 0, Qt.AlignmentFlag.AlignVCenter)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Long titles and previews end in "…" instead of widening the list.
        for label, full in ((self.title, self.full_title), (self.glimpse, self.full_preview)):
            if label is not None:
                label.setText(label.fontMetrics().elidedText(full, Qt.TextElideMode.ElideRight, max(40, label.width())))


class HistoryDialog(QDialog):
    def __init__(self, store, parent=None):
        super().__init__(parent)
        self.store = store
        self.character = character_key(parent.settings.character_path) if parent is not None else None
        self.current_id = getattr(parent, "_conversation_id", None)
        self.selected_id = None
        self.setWindowTitle("Conversations")
        self.resize(600, 580)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 18)
        layout.setSpacing(10)
        self.summary = QLabel()
        self.summary.setObjectName("subtitle")
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search titles")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._filter)
        layout.addWidget(self.search)
        self.items = QListWidget()
        self.items.setObjectName("history")
        self.items.setSpacing(3)
        self.items.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        self.items.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.items.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.items.customContextMenuRequested.connect(self._menu)
        self.items.itemActivated.connect(self._open)
        self.items.currentItemChanged.connect(lambda *_: self._sync_buttons())
        layout.addWidget(self.items, 1)
        self.empty = QLabel()
        self.empty.setObjectName("hint")
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty.setWordWrap(True)
        layout.addWidget(self.empty, 1)
        hint = QLabel("Double-click or press Enter to open. Delete removes the selected conversation; "
                      "saved memories are kept.")
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        buttons = QHBoxLayout()
        self.delete_button = QPushButton("Delete")
        self.delete_button.setObjectName("danger")
        self.delete_button.clicked.connect(self._delete)
        buttons.addWidget(self.delete_button)
        buttons.addStretch()
        close = QPushButton("Close")
        close.clicked.connect(self.reject)
        buttons.addWidget(close)
        self.open_button = QPushButton("Open")
        self.open_button.setObjectName("primary")
        self.open_button.setDefault(True)
        self.open_button.clicked.connect(self._open)
        buttons.addWidget(self.open_button)
        layout.addLayout(buttons)
        QShortcut(QKeySequence(QKeySequence.StandardKey.Delete), self.items, self._delete)
        self.refresh()

    def refresh(self, keep=None):
        self.items.clear()
        # Empty chats (a New that was never used) are clutter, unless it is the one open now.
        conversations = [c for c in self.store.conversations(self.character)
                         if c["message_count"] or c["id"] == self.current_id]
        for conversation in conversations:
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, conversation["id"])
            item.setData(Qt.ItemDataRole.ToolTipRole, conversation["title"])
            row = ConversationRow(conversation, self.store.last_message(conversation["id"]),
                                  conversation["id"] == self.current_id)
            row.delete_requested.connect(self._delete_id)
            item.setSizeHint(row.sizeHint())
            self.items.addItem(item)
            self.items.setItemWidget(item, row)
        total = len(conversations)
        self.summary.setText(f"{total} saved conversation{'' if total == 1 else 's'} with this character. "
                             "Open one to carry on where you left off.")
        rows = [self.items.item(i) for i in range(self.items.count())]
        chosen = next((item for item in rows if item.data(Qt.ItemDataRole.UserRole) == keep), None)
        if chosen or rows:
            self.items.setCurrentItem(chosen or rows[0])
        self._filter(self.search.text())

    def _filter(self, text):
        words = text.lower().split()
        visible = []
        for index in range(self.items.count()):
            item = self.items.item(index)
            title = (item.data(Qt.ItemDataRole.ToolTipRole) or "").lower()
            item.setHidden(not all(word in title for word in words))
            if not item.isHidden():
                visible.append(item)
        current = self.items.currentItem()
        if visible and (current is None or current.isHidden()):
            self.items.setCurrentItem(visible[0])
        self.empty.setText("No conversation title matches that search." if words else
                           "No saved conversations yet. Say hello and this list starts filling up.")
        self.empty.setVisible(not visible)
        self.items.setVisible(bool(visible))
        self._sync_buttons()

    def _selected(self):
        item = self.items.currentItem()
        return item if item is not None and not item.isHidden() else None

    def _sync_buttons(self):
        usable = self._selected() is not None
        self.open_button.setEnabled(usable)
        self.delete_button.setEnabled(usable)

    def _menu(self, point):
        item = self.items.itemAt(point)
        if item is None:
            return
        self.items.setCurrentItem(item)
        menu = QMenu(self)
        menu.addAction("Open", self._open)
        menu.addAction("Delete", self._delete)
        menu.exec(self.items.viewport().mapToGlobal(point))

    @Slot()
    def _open(self, *_):
        item = self._selected()
        if item:
            self.selected_id = item.data(Qt.ItemDataRole.UserRole)
            self.accept()

    @Slot()
    def _delete(self):
        item = self._selected()
        if item:
            self._delete_id(item.data(Qt.ItemDataRole.UserRole))

    @Slot(str)
    def _delete_id(self, conversation_id):
        ids = [self.items.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.items.count())]
        index = ids.index(conversation_id) if conversation_id in ids else 0
        title = self.items.item(index).data(Qt.ItemDataRole.ToolTipRole) if ids else "this conversation"
        extra = (" It is the conversation open now, so a fresh one takes its place."
                 if conversation_id == self.current_id else "")
        if QMessageBox.question(self, "Delete conversation",
                                f"Delete “{title}” and all its messages? This cannot be undone.{extra} "
                                "Saved memories are kept.") != QMessageBox.StandardButton.Yes:
            return
        # The next conversation keeps the selection, so clearing out several is quick.
        following = (ids[index + 1:] + ids[:index])[:1]
        try:
            self.store.delete_conversation(conversation_id)
        except sqlite3.Error:
            QMessageBox.warning(self, "Could not delete", "The database could not be updated. Please try again.")
            return
        self.refresh(keep=following[0] if following else None)


class MemoryDialog(QDialog):
    def __init__(self, store, parent=None):
        super().__init__(parent)
        self.store = store
        self.memory_id = None
        name = parent.settings.name if parent is not None else "Companion"
        self.setWindowTitle(f"{name}'s memory")
        self.resize(620, 560)
        layout = QVBoxLayout(self)
        description = QLabel("Memories are shared across characters and saved only when you add them. Included memories are sent with online replies. Pinned memories are preferred; others are matched to your topic.")
        description.setWordWrap(True)
        layout.addWidget(description)
        self.items = QListWidget()
        self.items.currentItemChanged.connect(self._select)
        layout.addWidget(self.items, 1)
        self.editor = QPlainTextEdit()
        self.editor.setPlaceholderText("A preference or fact to remember across conversations (up to 1,000 characters)")
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


class ReminderDialog(QDialog):
    """Upcoming reminders she has set, with a way to remove any of them."""

    def __init__(self, store, parent=None):
        super().__init__(parent)
        from .reminders import describe
        self.store, self.describe = store, describe
        self.setWindowTitle("Reminders")
        self.resize(520, 420)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 18)
        layout.setSpacing(10)
        hint = QLabel("Ask her in your own words, such as “remind me at 7 to study” or “every weekday at 8, "
                      "remind me to stretch”. She tells you herself when one is due.")
        hint.setObjectName("subtitle")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.items = QListWidget()
        self.items.setObjectName("history")
        self.items.setSpacing(3)
        layout.addWidget(self.items, 1)
        self.empty = QLabel("No upcoming reminders.")
        self.empty.setObjectName("hint")
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.empty, 1)
        buttons = QHBoxLayout()
        buttons.addStretch()
        close = QPushButton("Close")
        close.setObjectName("primary")
        close.clicked.connect(self.accept)
        buttons.addWidget(close)
        layout.addLayout(buttons)
        self.refresh()

    def refresh(self):
        self.items.clear()
        upcoming = self.store.reminders()
        for reminder in upcoming:
            row = QFrame()
            row.setObjectName("historyRow")
            line = QHBoxLayout(row)
            line.setContentsMargins(14, 9, 8, 9)
            text = QVBoxLayout()
            text.setSpacing(2)
            title = QLabel(reminder["text"])
            title.setObjectName("historyTitle")
            title.setWordWrap(True)
            title.setTextFormat(Qt.TextFormat.PlainText)
            text.addWidget(title)
            when = QLabel(self.describe(reminder))
            when.setObjectName("historyMeta")
            text.addWidget(when)
            line.addLayout(text, 1)
            remove = icon_button("delete", "Remove this reminder", "historyDelete")
            remove.clicked.connect(lambda checked=False, reminder_id=reminder["id"]: self._remove(reminder_id))
            line.addWidget(remove, 0, Qt.AlignmentFlag.AlignVCenter)
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, reminder["id"])
            item.setSizeHint(row.sizeHint())
            self.items.addItem(item)
            self.items.setItemWidget(item, row)
        self.items.setVisible(bool(upcoming))
        self.empty.setVisible(not upcoming)

    def _remove(self, reminder_id):
        try:
            self.store.delete_reminder(reminder_id)
        except sqlite3.Error:
            QMessageBox.warning(self, "Could not remove", "The database could not be updated. Please try again.")
            return
        self.refresh()


class TasksDialog(QDialog):
    """Her computer tasks from the last week, each with Undo for the files it changed."""
    undo_requested = Signal(object)  # task_journal.Journal

    def __init__(self, root, parent=None):
        super().__init__(parent)
        self.root = root
        self.setWindowTitle("Recent tasks")
        self.resize(560, 460)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 18)
        layout.setSpacing(10)
        hint = QLabel("Tasks from the last 7 days that changed files. Undo puts back what she created, edited, moved "
                      "or deleted; you see exactly what before anything happens. You can also just ask her to undo it.")
        hint.setObjectName("subtitle")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.items = QListWidget()
        self.items.setObjectName("history")
        self.items.setSpacing(3)
        self.items.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        layout.addWidget(self.items, 1)
        self.empty = QLabel("No recent tasks with changes to undo.")
        self.empty.setObjectName("hint")
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.empty, 1)
        buttons = QHBoxLayout()
        buttons.addStretch()
        close = QPushButton("Close")
        close.setObjectName("primary")
        close.clicked.connect(self.accept)
        buttons.addWidget(close)
        layout.addLayout(buttons)
        self.refresh()

    def refresh(self):
        from .task_journal import recent
        self.items.clear()
        journals = recent(self.root)
        for journal in journals:
            details = journal.details
            row = QFrame()
            row.setObjectName("historyRow")
            line = QHBoxLayout(row)
            line.setContentsMargins(14, 10, 10, 10)
            text = QVBoxLayout()
            text.setSpacing(2)
            title = QLabel(details.get("request") or "A task")
            title.setObjectName("historyTitle")
            title.setWordWrap(True)
            title.setTextFormat(Qt.TextFormat.PlainText)
            text.addWidget(title)
            finished = datetime.fromtimestamp(details["finished"]).astimezone().isoformat()
            changes, _ = journal.plan()
            meta = QLabel(" · ".join(filter(None, (when(finished), "Undone" if journal.undone else ", ".join(changes)))))
            meta.setObjectName("historyMeta")
            meta.setWordWrap(True)
            text.addWidget(meta)
            line.addLayout(text, 1)
            if not journal.undone:
                undo = QPushButton("Undo")
                undo.setObjectName("taskUndo")
                undo.setCursor(Qt.CursorShape.PointingHandCursor)
                undo.clicked.connect(lambda checked=False, journal=journal: self.undo_requested.emit(journal))
                line.addWidget(undo, 0, Qt.AlignmentFlag.AlignVCenter)
            item = QListWidgetItem()
            item.setSizeHint(row.sizeHint())
            self.items.addItem(item)
            self.items.setItemWidget(item, row)
        self.items.setVisible(bool(journals))
        self.empty.setVisible(not journals)
