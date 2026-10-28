"""The left sidebar: who she is, new chat, search, quick pages, and three tabs of conversations:
everyday chats (with her Reminders session on top), projects and study subjects."""
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QEvent, QSize, Qt, QUrl, Signal
from PySide6.QtGui import QBrush, QColor, QCursor, QDesktopServices, QFont, QIcon, QPixmap
from PySide6.QtWidgets import (QButtonGroup, QFrame, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QListWidget,
                               QListWidgetItem, QMenu, QPushButton, QStackedWidget, QToolButton, QTreeWidget,
                               QTreeWidgetItem, QVBoxLayout, QWidget)

from .projects import project_icon
from .theme import DIM, ICON_FONT, ICONS, badge_icon, glyph_icon, icon_button, repolish

RECENT_LIMIT = 60          # The full archive stays in History.
PROJECT_CHATS = 6          # Under an open project; its page lists them all.
ROW = 34
ID, PINNED, PROJECT, KIND, UNREAD = (Qt.ItemDataRole.UserRole + offset for offset in range(5))
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


class RowActions(QFrame):
    """Buttons over the row under the pointer (pin, new chat, ⋯), as ChatGPT and Codex show them.
    `buttons_for(item)` lists (glyph, tooltip, callback(item, button)) for a row, or nothing."""

    def __init__(self, view, buttons_for):
        super().__init__(view.viewport())
        self.setObjectName("rowActions")
        self.view, self.buttons_for, self.item = view, buttons_for, None
        self.row = QHBoxLayout(self)
        self.row.setContentsMargins(2, 0, 2, 0)
        self.row.setSpacing(0)
        view.viewport().setMouseTracking(True)
        view.viewport().installEventFilter(self)
        view.verticalScrollBar().valueChanged.connect(self.dismiss)
        self.hide()

    def eventFilter(self, watched, event):
        kind = event.type()
        if kind == QEvent.Type.MouseMove:
            self._hover(event.position().toPoint())
        elif kind == QEvent.Type.Leave and not self.underMouse():
            self.dismiss()
        return False

    def leaveEvent(self, event):
        super().leaveEvent(event)
        if not self.view.viewport().rect().contains(self.view.viewport().mapFromGlobal(QCursor.pos())):
            self.dismiss()

    def dismiss(self):
        self.item = None
        self.hide()

    def _hover(self, position):
        item = self.view.itemAt(position)
        buttons = self.buttons_for(item) if item is not None else []
        if not buttons:
            self.dismiss()
            return
        if item is not self.item:
            self.item = item
            while self.row.count():
                widget = self.row.takeAt(0).widget()
                if widget is not None:
                    widget.deleteLater()
            for glyph, tip, callback in buttons:
                button = QPushButton(ICONS[glyph])
                button.setObjectName("rowAction")
                button.setToolTip(tip)
                button.setCursor(Qt.CursorShape.PointingHandCursor)
                button.clicked.connect(lambda _=False, callback=callback, button=button: callback(item, button))
                self.row.addWidget(button)
            self.adjustSize()
        rect = self.view.visualItemRect(item)
        self.setFixedHeight(rect.height() - 6)
        self.move(self.view.viewport().width() - self.width() - 4, rect.top() + 3)
        self.show()
        self.raise_()


class Sidebar(QFrame):
    open_conversation = Signal(str)
    pin_requested = Signal(str, bool)
    rename_requested = Signal(str)
    delete_requested = Signal(str)
    move_requested = Signal(str, str)      # conversation, project ('' = back to Chats, '+' = a new project)
    open_project = Signal(str)
    new_project = Signal(str)              # kind: "project" or "study"
    new_chat_in_project = Signal(str)
    rename_project = Signal(str)
    delete_project = Signal(str)
    review_cards = Signal(str)
    tab_changed = Signal(str)
    show_all = Signal()
    collapse = Signal()

    def __init__(self, name, seal, actions, parent=None):
        """`actions`: QActions for memories, reminders, tasks and settings, shared with the window's menu."""
        super().__init__(parent)
        self.setObjectName("sidebar")
        self.setFixedWidth(264)
        self._glyph_font = QFont(ICON_FONT)
        self._glyph_font.setPixelSize(11)
        blank = QPixmap(20, 20)
        blank.fill(Qt.GlobalColor.transparent)
        self._indent = QIcon(blank)  # Sets a folder's chats in, under its name.
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
        self._tools, self._notes = {}, {}
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
        self.list.itemDoubleClicked.connect(lambda item: item.data(ID) and item.data(KIND) != "reminders" and self.rename_requested.emit(item.data(ID)))  # Double-click a chat to rename it.
        chats_layout.addWidget(self.list, 1)
        self.stack.addWidget(chats)
        # Projects and Study: containers with their chats beneath them.
        self.trees, self.empty = {}, {}
        for kind, title, hint, action in (
                ("project", "Projects", "A project keeps chats, instructions, files and a folder together.", "New project"),
                ("study", "Study", "A subject is a folder of study sessions she remembers together, with your "
                                   "materials, quizzes, flashcards and a focus timer.", "New subject")):
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
            # No indentation area: Qt paints it in its own highlight colour. Children are set in
            # by a blank icon instead, lined up under their folder's name.
            tree.setIndentation(0)
            tree.setRootIsDecorated(False)
            tree.setIconSize(QSize(20, 20))
            tree.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            tree.setCursor(Qt.CursorShape.PointingHandCursor)
            tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            tree.customContextMenuRequested.connect(lambda position, tree=tree: self._tree_menu(tree, position))
            tree.itemClicked.connect(self._tree_clicked)
            tree.itemDoubleClicked.connect(self._tree_renamed)
            tree.itemExpanded.connect(lambda item: self._folded(item, True))
            tree.itemCollapsed.connect(lambda item: self._folded(item, False))
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
        self.row_actions = [RowActions(self.list, self._buttons_for)]
        self.row_actions += [RowActions(tree, self._buttons_for) for tree in self.trees.values()]

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
        self._inbox = None
        self._working = None  # The chat where she is working on a task.
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
        self._tools[action] = button
        return button

    def set_note(self, action, text, warn=False):
        """A short note at the right of an item, such as how much of her plan is left beside Usage."""
        button = self._tools.get(action)
        if button is None:
            return
        note = self._notes.get(action)
        if note is None:
            row = QHBoxLayout(button)
            row.setContentsMargins(0, 0, 10, 0)
            row.addStretch()
            note = QLabel()
            note.setObjectName("sideNote")
            note.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            row.addWidget(note)
            self._notes[action] = note
        note.setText(text)
        note.setVisible(bool(text))
        repolish(note, warn=warn)

    def add_bottom(self, action):
        button = self._tool(action)
        self.settings_slot.addWidget(button)
        return button

    def set_working(self, conversation_id):
        """Marks the chat where she is working on a task, so it is easy to find while you are elsewhere."""
        self._working = conversation_id
        for kind in self.trees:
            self._fill_tree(kind)
        self._filter(self.search.text())

    def _mark_working(self, item, row, column=None):
        if row["id"] != self._working:
            return
        icon, tip = glyph_icon("tool", color="#e6c28c"), " · she is working on a task here"
        if column is None:
            item.setIcon(icon)
            item.setToolTip(item.toolTip() + tip)
        else:
            item.setIcon(column, icon)
            item.setToolTip(column, item.toolTip(column) + tip)

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
        `extras`: per subject, {"due": flashcards due}."""
        self._everything, self._projects, self._extras = list(rows), list(projects), dict(extras or {})
        # Her Reminders session sits above your chats, apart from them.
        self._inbox = next((row for row in rows if row.get("kind") == "reminders"), None)
        rows = [row for row in rows if row.get("kind") != "reminders"]
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
            count = len(self._chats.get(project["id"], []))
            item = QTreeWidgetItem([project["name"], ""])
            item.setData(0, ID, project["id"])
            item.setData(0, KIND, "project")
            item.setData(0, PROJECT, project)
            item.setFont(1, self._glyph_font)
            item.setForeground(1, QBrush(QColor(DIM)))
            tips = [project.get("description") or project["name"]]
            tips += [f"{count} {'session' if kind == 'study' else 'chat'}{'s' if count != 1 else ''}"] if count else []
            tips += [f"{extra['due']} flashcards due"] if extra.get("due") else []
            item.setToolTip(0, " · ".join(tips))
            item.setSizeHint(0, QSize(0, ROW))
            tree.addTopLevelItem(item)
            if kind == "study" and extra.get("due"):
                review = QTreeWidgetItem([f"Review flashcards · {extra['due']} due"])
                review.setIcon(0, glyph_icon("cards"))
                review.setData(0, ID, project["id"])
                review.setData(0, KIND, "review")
                review.setSizeHint(0, QSize(0, ROW - 4))
                item.addChild(review)
                review.setFirstColumnSpanned(True)
            chats = self._chats.get(project["id"], [])
            for row in chats[:PROJECT_CHATS]:
                child = QTreeWidgetItem([row["title"]])
                child.setIcon(0, self._indent)
                child.setData(0, ID, row["id"])
                child.setData(0, KIND, "chat")
                child.setData(0, PINNED, bool(row.get("pinned")))
                child.setData(0, PROJECT, project["id"])
                child.setToolTip(0, f"{row['title']} · {_when(row.get('updated_at'))}")
                self._mark_working(child, row, 0)
                child.setSizeHint(0, QSize(0, ROW - 4))
                item.addChild(child)
                child.setFirstColumnSpanned(True)  # One highlight across the row.
                if row["id"] == self._current:
                    tree.setCurrentItem(child)
            if len(chats) > PROJECT_CHATS:
                more = QTreeWidgetItem([f"All {len(chats)} {'sessions' if kind == 'study' else 'chats'}…"])
                more.setIcon(0, self._indent)
                more.setData(0, ID, project["id"])
                more.setData(0, KIND, "more")
                more.setSizeHint(0, QSize(0, ROW - 4))
                item.addChild(more)
                more.setFirstColumnSpanned(True)
            item.setExpanded(project["id"] in self._expanded)
            self._decorate(item)
            if project["id"] == self._page_project:
                tree.setCurrentItem(item)
        tree.setVisible(bool(projects))
        self.empty[kind].setVisible(not projects)

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
        if not words and self._inbox:
            self._inbox_item(self._inbox)
        for row in rows:
            if not words:
                heading = "Pinned" if row.get("pinned") else _group(row.get("updated_at"))
                if heading != group:
                    group = heading
                    self._heading(heading)
            if row.get("kind") == "reminders":
                self._inbox_item(row)
                continue
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
            self._mark_working(item, row)
            self.list.addItem(item)
            if row["id"] == self._current:
                item.setSelected(True)
                self.list.setCurrentItem(item)
        self.list_title.setText("Results" if words else "Chats")

    def _inbox_item(self, row):
        """Her Reminders session: a bell, and the number she has left you since you last looked."""
        unread = row.get("unread") or 0
        item = QListWidgetItem(row["title"])
        item.setSizeHint(QSize(0, ROW))
        item.setData(ID, row["id"])
        item.setData(KIND, "reminders")
        item.setData(UNREAD, unread)
        item.setIcon(badge_icon("bell", unread) if unread else glyph_icon("bell"))
        if unread:
            font = QFont()
            font.setBold(True)
            item.setFont(font)
        item.setToolTip("Where she reminds you and checks in, apart from your chats"
                        + (f" · {unread} new" if unread else f" · {_when(row.get('updated_at'))}"))
        self.list.addItem(item)
        if row["id"] == self._current:
            item.setSelected(True)
            self.list.setCurrentItem(item)

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

    def start_rename(self, identifier, text, commit, project=False):
        """Opens an editor over the row of this conversation (or project) where it is in the list. False if
        it is not in the sidebar."""
        from .inline import edit_in_place
        places = [] if project else [(self.list, "chats")]
        places += [(tree, "projects" if kind == "project" else "study") for kind, tree in self.trees.items()]
        for view, tab in places:
            items = ([view.item(i) for i in range(view.count())] if view is self.list else
                     [item for i in range(view.topLevelItemCount()) for item in
                      (view.topLevelItem(i), *(view.topLevelItem(i).child(j) for j in range(view.topLevelItem(i).childCount())))])
            for item in items:
                data = (lambda role: item.data(role)) if view is self.list else (lambda role: item.data(0, role))
                kind = data(KIND) or "chat"
                if data(ID) != identifier or (kind == "project") != project or kind in {"review", "more", "reminders"}:
                    continue
                self.show_tab(tab)
                if view is not self.list and item.parent():
                    item.parent().setExpanded(True)
                view.scrollToItem(item)
                for actions in self.row_actions:
                    actions.dismiss()
                edit_in_place(view, view.visualItemRect(item), text, commit)
                return True
        return False

    def _list_clicked(self, item):
        if item.data(ID):
            self.open_conversation.emit(item.data(ID))

    def _decorate(self, item):
        """A folder opens when its chats show; the chevron says it holds some, and which way it is folded."""
        project = item.data(0, PROJECT)
        study = project.get("kind") == "study"
        glyph = "study" if study else "folder_open" if item.isExpanded() else "folder"
        item.setIcon(0, project_icon(project["color"], glyph=glyph))
        item.setText(1, (ICONS["chevron"] if item.isExpanded() else ICONS["chevron_right"]) if item.childCount() else "")

    def _folded(self, item, expanded):
        if item.data(0, KIND) != "project":
            return
        (self._expanded.add if expanded else self._expanded.discard)(item.data(0, ID))
        self._decorate(item)

    def _buttons_for(self, item):
        """The hover buttons of a row: pin and ⋯ on a chat; new chat and ⋯ on a project or subject."""
        if isinstance(item, QListWidgetItem):
            if not item.data(ID) or item.data(KIND) == "reminders":
                return []  # A date heading, or her Reminders session, which stays where it is.
            return [("pin", "Unpin" if item.data(PINNED) else "Pin to the top",
                     lambda item, _button: self.pin_requested.emit(item.data(ID), not item.data(PINNED))),
                    ("more", "More", lambda item, button: self._chat_menu(
                        item.data(ID), item.data(PINNED), item.data(PROJECT), self._below(button)))]
        kind = item.data(0, KIND)
        if kind == "chat":
            return [("pin", "Unpin" if item.data(0, PINNED) else "Pin to the top",
                     lambda item, _button: self.pin_requested.emit(item.data(0, ID), not item.data(0, PINNED))),
                    ("more", "More", lambda item, button: self._chat_menu(
                        item.data(0, ID), item.data(0, PINNED), item.data(0, PROJECT), self._below(button)))]
        if kind == "project":
            study = item.data(0, PROJECT).get("kind") == "study"
            return [("compose", "New study session" if study else "New chat in this project",
                     lambda item, _button: self.new_chat_in_project.emit(item.data(0, ID))),
                    ("more", "More", lambda item, button: self._project_menu(item, self._below(button)))]
        return []

    @staticmethod
    def _below(button):
        return button.mapToGlobal(button.rect().bottomLeft())

    def _tree_clicked(self, item, column=0):
        kind, identifier = item.data(0, KIND), item.data(0, ID)
        if kind == "project" and column == 1 and item.childCount():
            item.setExpanded(not item.isExpanded())  # The chevron only folds.
        elif kind == "project":
            # A click opens it and shows its chats beneath it.
            item.setExpanded(True)
            self.open_project.emit(identifier)
        elif kind == "more":
            self.open_project.emit(identifier)
        elif kind == "review":
            self.review_cards.emit(identifier)
        else:
            self.open_conversation.emit(identifier)

    def _tree_renamed(self, item, _column=0):
        kind = item.data(0, KIND)
        if kind == "chat":
            self.rename_requested.emit(item.data(0, ID))
        elif kind == "project":
            self.rename_project.emit(item.data(0, ID))

    def _tree_menu(self, tree, position):
        item = tree.itemAt(position)
        if item is None:
            return
        kind, identifier = item.data(0, KIND), item.data(0, ID)
        if kind == "chat":
            self._chat_menu(identifier, item.data(0, PINNED), item.data(0, PROJECT), tree.viewport().mapToGlobal(position))
            return
        if kind == "project":
            self._project_menu(item, tree.viewport().mapToGlobal(position))

    def _project_menu(self, item, where):
        project, identifier = item.data(0, PROJECT), item.data(0, ID)
        study = project.get("kind") == "study"
        menu = QMenu(self)
        menu.addAction(glyph_icon("open"), "Open subject" if study else "Open project",
                       lambda: self.open_project.emit(identifier))
        menu.addAction(glyph_icon("compose"), "New study session" if study else "New chat in this project",
                       lambda: self.new_chat_in_project.emit(identifier))
        menu.addAction(glyph_icon("rename"), "Rename…", lambda: self.rename_project.emit(identifier))
        if study:
            menu.addAction(glyph_icon("cards"), "Review flashcards", lambda: self.review_cards.emit(identifier))
        if project.get("folder"):
            menu.addAction(glyph_icon("folder_open"), "Open in Explorer",
                           lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(project["folder"])))
            menu.actions()[-1].setEnabled(Path(project["folder"]).is_dir())
        if item.childCount():
            menu.addAction(glyph_icon("chevron"), "Collapse" if item.isExpanded() else "Expand",
                           lambda: item.setExpanded(not item.isExpanded()))
        menu.addSeparator()
        menu.addAction(glyph_icon("delete", color="#f3a5b3"), "Delete subject…" if study else "Delete project…",
                       lambda: self.delete_project.emit(identifier))
        menu.exec(where)

    def _list_menu(self, position):
        item = self.list.itemAt(position)
        if item is not None and item.data(ID) and item.data(KIND) != "reminders":
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
