"""The left sidebar: who she is, new chat, search, quick pages, and three tabs of conversations:
everyday chats, projects and study subjects."""
from datetime import datetime

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont
from PySide6.QtWidgets import (QButtonGroup, QFrame, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QListWidget,
                               QListWidgetItem, QMenu, QPushButton, QStackedWidget, QToolButton, QTreeWidget,
                               QTreeWidgetItem, QVBoxLayout, QWidget)

from .projects import project_icon
from .theme import DIM, glyph_icon, icon_button

RECENT_LIMIT = 60          # The full archive stays in History.
PROJECT_CHATS = 6          # Under an open project; its page lists them all.
ROW = 34
ID, PINNED, PROJECT, KIND = (Qt.ItemDataRole.UserRole + offset for offset in range(4))
TABS = ("chats", "projects", "study")
TAB_LABELS = {"chats": ("Chats", "compose"), "projects": ("Projects", "folder"), "study": ("Study", "study")}


def _moment(timestamp):
    try:
        return datetime.fromisoformat(timestamp).astimezone()
    except (TypeError, ValueError):
        return None


def _when(timestamp):
    moment = _moment(timestamp)
    if moment is None:
        return ""
    days = (datetime.now().astimezone().date() - moment.date()).days
    return moment.strftime("%H:%M") if days == 0 else "Yesterday" if days == 1 else moment.strftime("%d %b")


def _group(timestamp):
    moment = _moment(timestamp)
    days = (datetime.now().astimezone().date() - moment.date()).days if moment else 99
    return "Today" if days <= 0 else "Yesterday" if days == 1 else "Previous 7 days" if days < 7 else "Older"


class Sidebar(QFrame):
    open_conversation = Signal(str)
    pin_requested = Signal(str, bool)
    rename_requested = Signal(str)
    delete_requested = Signal(str)
    move_requested = Signal(str, str)      # conversation, project ('' = back to Chats, '+' = a new project)
    open_project = Signal(str)
    new_project = Signal(str)              # kind: "project" or "study"
    new_chat_in_project = Signal(str)
    review_cards = Signal(str)
    tab_changed = Signal(str)
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
            layout.addWidget(self._tool(action))

        self.search = QLineEdit()
        self.search.setObjectName("sideSearch")
        self.search.setPlaceholderText("Search all conversations")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._filter)
        self.search.hide()
        layout.addSpacing(6)
        layout.addWidget(self.search)

        self.stack = QStackedWidget()
        layout.addWidget(self.stack, 1)
        # Chats: everyday conversations, grouped by when they were last used.
        chats = QWidget()
        chats_layout = QVBoxLayout(chats)
        chats_layout.setContentsMargins(0, 0, 0, 0)
        chats_layout.setSpacing(2)
        heading = QHBoxLayout()
        heading.setContentsMargins(8, 10, 4, 2)
        self.list_title = QLabel("Chats")
        self.list_title.setObjectName("sideSection")
        heading.addWidget(self.list_title)
        heading.addStretch()
        everything = QPushButton("All")
        everything.setObjectName("sideLink")
        everything.setToolTip("Every conversation, with search, previews and dates")
        everything.setCursor(Qt.CursorShape.PointingHandCursor)
        everything.clicked.connect(self.show_all)
        heading.addWidget(everything)
        chats_layout.addLayout(heading)
        self.list = QListWidget()
        self.list.setObjectName("sideList")
        self.list.setFrameShape(QFrame.Shape.NoFrame)
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list.setIconSize(QSize(20, 20))
        self.list.setCursor(Qt.CursorShape.PointingHandCursor)
        self.list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self._list_menu)
        self.list.itemClicked.connect(self._list_clicked)
        chats_layout.addWidget(self.list, 1)
        self.stack.addWidget(chats)
        # Projects and Study: containers with their chats beneath them.
        self.trees, self.empty = {}, {}
        for kind, title, hint, action in (
                ("project", "Projects", "A project keeps chats, instructions, files and a folder together.", "New project"),
                ("study", "Study", "A subject for a course or exam: lessons with her, quizzes, flashcards and a "
                                   "focus timer.", "New subject")):
            page = QWidget()
            page_layout = QVBoxLayout(page)
            page_layout.setContentsMargins(0, 0, 0, 0)
            page_layout.setSpacing(2)
            heading = QHBoxLayout()
            heading.setContentsMargins(8, 10, 4, 2)
            label = QLabel(title)
            label.setObjectName("sideSection")
            heading.addWidget(label)
            heading.addStretch()
            add = icon_button("new", action, name="sideIcon")
            add.clicked.connect(lambda _=False, kind=kind: self.new_project.emit(kind))
            heading.addWidget(add)
            page_layout.addLayout(heading)
            tree = QTreeWidget()
            tree.setObjectName("sideTree")
            tree.setHeaderHidden(True)
            tree.setColumnCount(2)
            tree.header().setStretchLastSection(False)
            tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
            tree.header().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
            tree.setFrameShape(QFrame.Shape.NoFrame)
            tree.setIndentation(14)
            tree.setRootIsDecorated(False)
            tree.setIconSize(QSize(20, 20))
            tree.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            tree.setCursor(Qt.CursorShape.PointingHandCursor)
            tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            tree.customContextMenuRequested.connect(lambda position, tree=tree: self._tree_menu(tree, position))
            tree.itemClicked.connect(self._tree_clicked)
            page_layout.addWidget(tree, 1)
            empty = QWidget()
            empty_layout = QVBoxLayout(empty)
            empty_layout.setContentsMargins(8, 4, 8, 4)
            note = QLabel(hint)
            note.setObjectName("rowHint")
            note.setWordWrap(True)
            empty_layout.addWidget(note)
            start = QPushButton(action + "…")
            start.setObjectName("chip")
            start.setCursor(Qt.CursorShape.PointingHandCursor)
            start.clicked.connect(lambda _=False, kind=kind: self.new_project.emit(kind))
            empty_layout.addWidget(start, 0, Qt.AlignmentFlag.AlignLeft)
            empty_layout.addStretch()
            page_layout.addWidget(empty, 1)
            self.trees[kind], self.empty[kind] = tree, empty
            self.stack.addWidget(page)
        self.tree = self.trees["project"]

        # The tab bar sits just above Settings.
        bar = QFrame()
        bar.setObjectName("sideTabs")
        tabs = QHBoxLayout(bar)
        tabs.setContentsMargins(3, 3, 3, 3)
        tabs.setSpacing(2)
        self.tab_group = QButtonGroup(self)
        self.tab_buttons = {}
        for index, tab in enumerate(TABS):
            text, glyph = TAB_LABELS[tab]
            button = QToolButton()
            button.setObjectName("sideTab")
            button.setText(text)
            button.setIcon(glyph_icon(glyph))
            button.setIconSize(QSize(18, 18))
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setToolTip({"chats": "Everyday conversations", "projects": "Projects: chats with instructions, files "
                               "and a folder", "study": "Study: subjects with quizzes, flashcards and a focus timer"}[tab])
            self.tab_group.addButton(button, index)
            self.tab_buttons[tab] = button
            tabs.addWidget(button, 1)
        self.tab_group.idClicked.connect(lambda index: self.show_tab(TABS[index], user=True))
        layout.addSpacing(6)
        layout.addWidget(bar)

        self.settings_slot = QVBoxLayout()
        self.settings_slot.setContentsMargins(0, 4, 0, 0)
        layout.addLayout(self.settings_slot)
        self._rows, self._everything, self._projects, self._chats, self._extras = [], [], [], {}, {}
        self._current = self._current_project = self._page_project = None
        self._expanded = set()
        self.show_tab("chats")

    def _item(self, glyph, text, tooltip):
        button = QPushButton(text)
        button.setObjectName("sideNew")
        button.setIcon(glyph_icon(glyph))
        button.setIconSize(QSize(24, 24))
        button.setToolTip(tooltip)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        return button

    def _tool(self, action):
        button = QToolButton()
        button.setObjectName("sideItem")
        button.setDefaultAction(action)
        button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        button.setIconSize(QSize(24, 24))
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        return button

    def add_bottom(self, action):
        button = self._tool(action)
        self.settings_slot.addWidget(button)
        return button

    def set_identity(self, name, seal):
        self.title.setText(name)
        self.seal.setText(seal)

    @property
    def tab(self):
        return TABS[self.stack.currentIndex()]

    def show_tab(self, tab, user=False):
        if tab not in TABS:
            return
        self.stack.setCurrentIndex(TABS.index(tab))
        self.tab_buttons[tab].setChecked(True)
        if user:
            self.tab_changed.emit(tab)

    # Contents ----------------------------------------------------------------------------------

    def set_conversations(self, rows, current, projects=(), current_project="", page_project=None, extras=None):
        """`rows`: this character's conversations, newest first. `projects`: projects and subjects.
        `extras`: per subject, {"exam": "Exam in 12 days", "due": cards due}."""
        self._everything, self._projects, self._extras = list(rows), list(projects), dict(extras or {})
        self._chats = {}
        for row in rows:
            if row.get("project_id"):
                self._chats.setdefault(row["project_id"], []).append(row)
        known = {project["id"] for project in self._projects}
        loose = [row for row in rows if not row.get("project_id") or row["project_id"] not in known]
        self._rows = loose[:RECENT_LIMIT] + [row for row in loose[RECENT_LIMIT:] if row.get("pinned")]
        self._current, self._current_project, self._page_project = current, current_project, page_project
        if current_project:
            self._expanded.add(current_project)
        for kind in self.trees:
            self._fill_tree(kind)
        self._filter(self.search.text())

    def _fill_tree(self, kind):
        tree = self.trees[kind]
        tree.clear()
        projects = [project for project in self._projects if project.get("kind", "project") == kind]
        for project in projects:
            extra = self._extras.get(project["id"], {})
            item = QTreeWidgetItem([project["name"], self._badge(extra)])
            item.setIcon(0, project_icon(project["color"], glyph="study" if kind == "study" else "folder"))
            item.setData(0, ID, project["id"])
            item.setData(0, KIND, "project")
            item.setForeground(1, QBrush(QColor(DIM)))
            tips = [project.get("description") or project["name"]]
            tips += [text for text in (extra.get("exam"), f"{extra['due']} flashcards due" if extra.get("due") else "") if text]
            item.setToolTip(0, " · ".join(tips))
            item.setSizeHint(0, QSize(0, ROW))
            tree.addTopLevelItem(item)
            if kind == "study" and extra.get("due"):
                review = QTreeWidgetItem([f"Review flashcards", str(extra["due"])])
                review.setIcon(0, glyph_icon("cards"))
                review.setData(0, ID, project["id"])
                review.setData(0, KIND, "review")
                review.setForeground(1, QBrush(QColor(DIM)))
                review.setSizeHint(0, QSize(0, ROW - 4))
                item.addChild(review)
            chats = self._chats.get(project["id"], [])
            for row in chats[:PROJECT_CHATS]:
                child = QTreeWidgetItem([row["title"]])
                child.setData(0, ID, row["id"])
                child.setData(0, KIND, "chat")
                child.setData(0, PINNED, bool(row.get("pinned")))
                child.setData(0, PROJECT, project["id"])
                child.setToolTip(0, f"{row['title']} · {_when(row.get('updated_at'))}")
                child.setSizeHint(0, QSize(0, ROW - 4))
                item.addChild(child)
                child.setFirstColumnSpanned(True)  # One highlight across the row.
                if row["id"] == self._current:
                    tree.setCurrentItem(child)
            if len(chats) > PROJECT_CHATS:
                more = QTreeWidgetItem([f"All {len(chats)} {'sessions' if kind == 'study' else 'chats'}…"])
                more.setData(0, ID, project["id"])
                more.setData(0, KIND, "more")
                more.setSizeHint(0, QSize(0, ROW - 4))
                item.addChild(more)
                more.setFirstColumnSpanned(True)
            item.setExpanded(project["id"] in self._expanded)
            if project["id"] == self._page_project:
                tree.setCurrentItem(item)
        tree.setVisible(bool(projects))
        self.empty[kind].setVisible(not projects)

    @staticmethod
    def _badge(extra):
        exam = extra.get("exam", "")
        if exam.startswith("Exam in "):
            return exam.removeprefix("Exam in ").replace(" days", "d")
        return {"Exam today": "today", "Exam tomorrow": "1d"}.get(exam, "")

    def _filter(self, text=""):
        words = text.casefold().split()
        self.list.clear()
        if words:
            self.show_tab("chats")
            rows = [row for row in self._everything if all(word in row["title"].casefold() for word in words)]
        else:
            rows = sorted(self._rows, key=lambda row: not row.get("pinned"))
        names = {project["id"]: project["name"] for project in self._projects}
        moon, group = glyph_icon("moon"), None
        for row in rows:
            if not words:
                heading = "Pinned" if row.get("pinned") else _group(row.get("updated_at"))
                if heading != group:
                    group = heading
                    self._heading(heading)
            item = QListWidgetItem(row["title"])
            item.setSizeHint(QSize(0, ROW))
            item.setData(ID, row["id"])
            item.setData(PINNED, bool(row.get("pinned")))
            item.setData(PROJECT, row.get("project_id") or "")
            place = names.get(row.get("project_id"))
            item.setToolTip(f"{row['title']} · {_when(row.get('updated_at'))}" + (" · pinned" if row.get("pinned") else "")
                            + (f" · in {place}" if place else ""))
            if row.get("pinned"):
                item.setIcon(moon)
            self.list.addItem(item)
            if row["id"] == self._current:
                item.setSelected(True)
                self.list.setCurrentItem(item)
        self.list_title.setText("Results" if words else "Chats")

    def _heading(self, text):
        item = QListWidgetItem(text)
        item.setFlags(Qt.ItemFlag.NoItemFlags)
        item.setSizeHint(QSize(0, 26))
        font = QFont()
        font.setPixelSize(11)
        font.setBold(True)
        item.setFont(font)
        item.setForeground(QBrush(QColor(DIM)))
        self.list.addItem(item)

    # Interaction ----------------------------------------------------------------------------------

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

    def _list_clicked(self, item):
        if item.data(ID):
            self.open_conversation.emit(item.data(ID))

    def _tree_clicked(self, item, _column=0):
        kind, identifier = item.data(0, KIND), item.data(0, ID)
        if kind == "project":
            # A click opens it and shows its chats beneath it.
            self._expanded.add(identifier)
            item.setExpanded(True)
            self.open_project.emit(identifier)
        elif kind == "more":
            self.open_project.emit(identifier)
        elif kind == "review":
            self.review_cards.emit(identifier)
        else:
            self.open_conversation.emit(identifier)

    def _tree_menu(self, tree, position):
        item = tree.itemAt(position)
        if item is None:
            return
        kind, identifier = item.data(0, KIND), item.data(0, ID)
        if kind == "chat":
            self._chat_menu(identifier, item.data(0, PINNED), item.data(0, PROJECT), tree.viewport().mapToGlobal(position))
            return
        if kind != "project":
            return
        study = tree is self.trees["study"]
        menu = QMenu(self)
        menu.addAction(glyph_icon("open"), "Open subject" if study else "Open project",
                       lambda: self.open_project.emit(identifier))
        menu.addAction(glyph_icon("compose"), "New study session" if study else "New chat in this project",
                       lambda: self.new_chat_in_project.emit(identifier))
        if study:
            menu.addAction(glyph_icon("cards"), "Review flashcards", lambda: self.review_cards.emit(identifier))
        if item.isExpanded():
            menu.addAction("Collapse", lambda: (self._expanded.discard(identifier), item.setExpanded(False)))
        menu.exec(tree.viewport().mapToGlobal(position))

    def _list_menu(self, position):
        item = self.list.itemAt(position)
        if item is not None and item.data(ID):
            self._chat_menu(item.data(ID), item.data(PINNED), item.data(PROJECT), self.list.viewport().mapToGlobal(position))

    def _chat_menu(self, conversation, pinned, project, where):
        menu = QMenu(self)
        menu.addAction(glyph_icon("pin"), "Unpin" if pinned else "Pin to the top",
                       lambda: self.pin_requested.emit(conversation, not pinned))
        menu.addAction(glyph_icon("rename"), "Rename…", lambda: self.rename_requested.emit(conversation))
        for kind, title in (("project", "Move to project"), ("study", "Move to subject")):
            targets = [target for target in self._projects if target.get("kind", "project") == kind]
            move = menu.addMenu(glyph_icon("study" if kind == "study" else "folder"), title)
            for target in targets:
                action = move.addAction(project_icon(target["color"], glyph="study" if kind == "study" else "folder"),
                                        target["name"], lambda target=target["id"]: self.move_requested.emit(conversation, target))
                action.setEnabled(target["id"] != project)
            if targets:
                move.addSeparator()
            move.addAction(glyph_icon("new"), "New subject…" if kind == "study" else "New project…",
                           lambda kind=kind: self.move_requested.emit(conversation, "+" + kind))
        if project:
            menu.addAction("Back to Chats", lambda: self.move_requested.emit(conversation, ""))
        menu.addSeparator()
        menu.addAction(glyph_icon("delete", color="#f3a5b3"), "Delete…", lambda: self.delete_requested.emit(conversation))
        menu.exec(where)
