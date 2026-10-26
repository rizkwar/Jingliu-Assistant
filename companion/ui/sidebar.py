"""The left sidebar: who she is, new chat, search, quick pages and the conversation list (pinned, then recent)."""
from datetime import datetime

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMenu,
                               QPushButton, QToolButton, QVBoxLayout, QWidget)

from .theme import glyph_icon, icon_button

RECENT_LIMIT = 40  # The full archive stays in History.


def _when(timestamp):
    try:
        moment = datetime.fromisoformat(timestamp).astimezone()
    except (TypeError, ValueError):
        return ""
    today = datetime.now().astimezone().date()
    days = (today - moment.date()).days
    return moment.strftime("%H:%M") if days == 0 else "Yesterday" if days == 1 else moment.strftime("%d %b")


class Sidebar(QFrame):
    open_conversation = Signal(str)
    pin_requested = Signal(str, bool)
    rename_requested = Signal(str)
    delete_requested = Signal(str)
    show_all = Signal()
    collapse = Signal()

    def __init__(self, name, seal, actions, parent=None):
        """`actions`: QActions for memories, reminders, tasks and settings, shared with the window's menu."""
        super().__init__(parent)
        self.setObjectName("sidebar")
        self.setFixedWidth(264)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 12, 10, 10)
        layout.setSpacing(2)

        header = QHBoxLayout()
        header.setContentsMargins(6, 0, 0, 6)
        header.setSpacing(6)
        self.title = QLabel(name)
        self.title.setObjectName("sideTitle")
        header.addWidget(self.title)
        self.seal = QLabel(seal)
        self.seal.setObjectName("seal")
        header.addWidget(self.seal)
        header.addStretch()
        self.search_button = icon_button("search", "Search conversations · Ctrl+K", name="sideIcon")
        self.search_button.clicked.connect(self.start_search)
        header.addWidget(self.search_button)
        self.collapse_button = icon_button("sidebar", "Hide the sidebar · Ctrl+B", name="sideIcon")
        self.collapse_button.clicked.connect(self.collapse)
        header.addWidget(self.collapse_button)
        layout.addLayout(header)

        self.new_chat = self._item("compose", "New chat", "A new conversation · the current one stays in your list · Ctrl+N")
        layout.addWidget(self.new_chat)
        for action in actions:
            button = QToolButton()
            button.setObjectName("sideItem")
            button.setDefaultAction(action)
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            button.setIconSize(QSize(24, 24))
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            layout.addWidget(button)

        self.search = QLineEdit()
        self.search.setObjectName("sideSearch")
        self.search.setPlaceholderText("Search conversations")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._filter)
        self.search.hide()
        layout.addSpacing(6)
        layout.addWidget(self.search)

        heading = QHBoxLayout()
        heading.setContentsMargins(8, 12, 4, 4)
        self.list_title = QLabel("Recents")
        self.list_title.setObjectName("sideSection")
        heading.addWidget(self.list_title)
        heading.addStretch()
        everything = QPushButton("All")
        everything.setObjectName("sideLink")
        everything.setToolTip("Every conversation, with search, previews and dates")
        everything.setCursor(Qt.CursorShape.PointingHandCursor)
        everything.clicked.connect(self.show_all)
        heading.addWidget(everything)
        layout.addLayout(heading)

        self.list = QListWidget()
        self.list.setObjectName("sideList")
        self.list.setFrameShape(QFrame.Shape.NoFrame)
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list.setIconSize(QSize(20, 20))
        self.list.setUniformItemSizes(True)
        self.list.setCursor(Qt.CursorShape.PointingHandCursor)
        self.list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self._menu)
        self.list.itemClicked.connect(self._clicked)
        layout.addWidget(self.list, 1)
        self._rows, self._current = [], None

        self.settings_slot = QVBoxLayout()
        self.settings_slot.setContentsMargins(0, 6, 0, 0)
        layout.addLayout(self.settings_slot)

    def _item(self, glyph, text, tooltip):
        button = QPushButton(text)
        button.setObjectName("sideNew")
        button.setIcon(glyph_icon(glyph))
        button.setIconSize(QSize(24, 24))
        button.setToolTip(tooltip)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        return button

    def add_bottom(self, action):
        button = QToolButton()
        button.setObjectName("sideItem")
        button.setDefaultAction(action)
        button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        button.setIconSize(QSize(24, 24))
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.settings_slot.addWidget(button)
        return button

    def set_identity(self, name, seal):
        self.title.setText(name)
        self.seal.setText(seal)

    def set_conversations(self, rows, current):
        """Rows from the store (newest first). Pinned ones come first, marked with a crescent."""
        self._rows = sorted(rows[:RECENT_LIMIT] + [row for row in rows[RECENT_LIMIT:] if row.get("pinned")],
                            key=lambda row: not row.get("pinned"))
        self._current = current
        self._filter(self.search.text())

    def _filter(self, text=""):
        words = text.casefold().split()
        self.list.clear()
        moon = glyph_icon("moon")
        for row in self._rows:
            title = row["title"]
            if words and not all(word in title.casefold() for word in words):
                continue
            item = QListWidgetItem(title)
            item.setSizeHint(QSize(0, 34))
            item.setData(Qt.ItemDataRole.UserRole, row["id"])
            item.setData(Qt.ItemDataRole.UserRole + 1, bool(row.get("pinned")))
            item.setToolTip(f"{title} · {_when(row.get('updated_at'))}" + (" · pinned" if row.get("pinned") else ""))
            if row.get("pinned"):
                item.setIcon(moon)
            self.list.addItem(item)
            if row["id"] == self._current:
                item.setSelected(True)
                self.list.setCurrentItem(item)
        self.list_title.setText("Results" if words else "Recents")

    def start_search(self):
        self.search.show()
        self.search.setFocus()
        self.search.selectAll()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape and self.search.isVisible():
            self.search.clear()
            self.search.hide()
            return
        super().keyPressEvent(event)

    def _clicked(self, item):
        self.open_conversation.emit(item.data(Qt.ItemDataRole.UserRole))

    def _menu(self, position):
        item = self.list.itemAt(position)
        if item is None:
            return
        conversation, pinned = item.data(Qt.ItemDataRole.UserRole), item.data(Qt.ItemDataRole.UserRole + 1)
        menu = QMenu(self)
        menu.addAction(glyph_icon("pin"), "Unpin" if pinned else "Pin to the top",
                       lambda: self.pin_requested.emit(conversation, not pinned))
        menu.addAction(glyph_icon("rename"), "Rename…", lambda: self.rename_requested.emit(conversation))
        menu.addSeparator()
        menu.addAction(glyph_icon("delete", color="#f3a5b3"), "Delete…", lambda: self.delete_requested.emit(conversation))
        menu.exec(self.list.viewport().mapToGlobal(position))
