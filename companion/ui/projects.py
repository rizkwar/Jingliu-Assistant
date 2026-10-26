"""A project's page: its name, the instructions she follows there, the files she knows, its folder and its chats."""
from datetime import datetime
from pathlib import Path
import sqlite3

from PySide6.QtCore import QSize, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (QBoxLayout, QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QListWidget,
                               QListWidgetItem, QMenu, QMessageBox, QPlainTextEdit, QPushButton, QScrollArea,
                               QVBoxLayout, QWidget)

from ..chat import projects as knowledge
from ..chat.attachments import FILE_FILTER, AttachmentError
from ..core.paths import resolve
from .theme import ICONS, glyph_icon, icon_button

COLORS = {"ice": "#7cc0ff", "frost": "#dfe9f7", "crimson": "#ff6b85", "amber": "#f2b45c", "jade": "#4fd1a5",
          "violet": "#a98bff"}
COLOR_NAMES = {"ice": "Glacial blue", "frost": "Frost", "crimson": "Crimson", "amber": "Lantern amber",
               "jade": "Jade", "violet": "Twilight violet"}
KIND_LABELS = {"image": "Image", "pdf": "PDF", "text": "Text"}
PROJECT_WORDS = {
    "name": "Project name", "description": "What is this project about? (optional)", "start": "New chat in {name}",
    "chats": "Conversations", "no_chats": "No conversations yet. Start one above; it stays in this project.",
    "chats_hint": "",
    "instructions": "Instructions",
    "instructions_hint": "She follows these in every conversation of this project. For example: “I'm a beginner, "
                         "use examples first” or “answer in Indonesian”.",
    "instructions_placeholder": "How should she help with this project?",
    "files": "Files", "files_hint": "Notes, documents and code she should know. Text and PDFs are read and kept in "
                                    "mind; you can also drop files here."}
STUDY_WORDS = {
    "name": "Subject name", "description": "What does this subject cover? e.g. “Chapters 1–5: probability”",
    "start": "New study session in {name}", "chats": "Sessions",
    "no_chats": "No sessions yet. Start one above: ask her to teach, quiz you, or make flashcards.",
    "chats_hint": "Every session here shares her memory of this subject: in a new one she remembers what you "
                  "covered before and picks up from there.",
    "instructions": "How she teaches you",
    "instructions_hint": "She tutors you in every session of this subject. For example: “explain in Indonesian”, "
                         "“I learn best from worked examples” or “be strict with my quiz answers”.",
    "instructions_placeholder": "How do you learn best?",
    "files": "Materials", "files_hint": "Lecture notes, slides, past papers. Text and PDFs are read, so she teaches "
                                        "and quizzes from them; you can also drop files here."}


def project_icon(color, size=32, glyph="folder"):
    """A project's folder (or a subject's cap) in its colour, for the sidebar, the page and menus."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    from PySide6.QtGui import QFont
    font = QFont("Segoe Fluent Icons")
    font.setPixelSize(int(size * 0.66))
    painter.setFont(font)
    painter.setPen(QColor(COLORS.get(color, COLORS["ice"])))
    painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, ICONS[glyph])
    painter.end()
    return QIcon(pixmap)


def _size(count):
    return f"{count / 1_000_000:.1f} MB" if count >= 1_000_000 else f"{max(1, count // 1000)} KB"


def _when(timestamp):
    try:
        moment = datetime.fromisoformat(timestamp).astimezone()
    except (TypeError, ValueError):
        return ""
    days = (datetime.now().astimezone().date() - moment.date()).days
    return moment.strftime("%H:%M") if days == 0 else "Yesterday" if days == 1 else moment.strftime("%d %b")


def _card(title, hint=None):
    card = QFrame()
    card.setObjectName("projectCard")
    layout = QVBoxLayout(card)
    layout.setContentsMargins(16, 13, 16, 14)
    layout.setSpacing(8)
    header = QHBoxLayout()
    label = QLabel(title)
    label.setObjectName("cardTitle")
    header.addWidget(label)
    header.addStretch()
    layout.addLayout(header)
    if hint:
        note = QLabel(hint)
        note.setObjectName("rowHint")
        note.setWordWrap(True)
        layout.addWidget(note)
    return card, layout, header


class ProjectPage(QWidget):
    back = Signal()
    open_conversation = Signal(str)
    new_chat = Signal(str)
    changed = Signal()        # Name, colour or chats: the sidebar should refresh.
    deleted = Signal(str, bool)  # project id, whether its chats were deleted too
    review_cards = Signal(str)

    def __init__(self, store, character, files_root=knowledge.PROJECT_ROOT_FOLDER, parent=None):
        super().__init__(parent)
        self.setObjectName("panel")
        self.store, self.character, self.files_root = store, character, files_root
        self.project_id = None
        self.setAcceptDrops(True)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        outer.addWidget(scroll)
        body = QWidget()
        body.setObjectName("panelBody")
        scroll.setWidget(body)
        layout = QVBoxLayout(body)
        layout.setContentsMargins(22, 14, 22, 18)
        layout.setSpacing(14)

        top = QHBoxLayout()
        top.setSpacing(10)
        self.back_button = icon_button("back", "Back to the conversation (Esc)")
        self.back_button.clicked.connect(self.back)
        top.addWidget(self.back_button, 0, Qt.AlignmentFlag.AlignTop)
        self.badge = QLabel()
        self.badge.setFixedSize(34, 34)
        top.addWidget(self.badge, 0, Qt.AlignmentFlag.AlignTop)
        names = QVBoxLayout()
        names.setSpacing(2)
        self.name = QLineEdit()
        self.name.setObjectName("projectName")
        self.name.setPlaceholderText("Project name")
        self.name.setMaxLength(80)
        self.name.editingFinished.connect(self._save_name)
        names.addWidget(self.name)
        self.description = QLineEdit()
        self.description.setObjectName("projectDescription")
        self.description.setPlaceholderText("What is this project about? (optional)")
        self.description.setMaxLength(300)
        self.description.editingFinished.connect(self._save_description)
        names.addWidget(self.description)
        top.addLayout(names, 1)
        self.more = icon_button("more", "Colour, delete")
        menu = QMenu(self)
        colours = menu.addMenu(glyph_icon("folder"), "Colour")
        for key, label in COLOR_NAMES.items():
            colours.addAction(project_icon(key), label, lambda key=key: self._set_color(key))
        menu.addSeparator()
        menu.addAction(glyph_icon("delete", color="#f3a5b3"), "Delete project…", self._delete)
        self.more.setMenu(menu)
        top.addWidget(self.more, 0, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(top)

        self.start = QPushButton()
        self.start.setObjectName("projectStart")
        self.start.setIcon(glyph_icon("compose"))
        self.start.setIconSize(QSize(20, 20))
        self.start.setCursor(Qt.CursorShape.PointingHandCursor)
        self.start.clicked.connect(lambda: self.project_id and self.new_chat.emit(self.project_id))
        layout.addWidget(self.start)

        self.columns = QBoxLayout(QBoxLayout.Direction.LeftToRight)
        self.columns.setSpacing(14)
        layout.addLayout(self.columns, 1)
        left, right = QVBoxLayout(), QVBoxLayout()
        left.setSpacing(14)
        right.setSpacing(14)
        self.columns.addLayout(left, 3)
        self.columns.addLayout(right, 2)

        # Study subjects only: flashcards, focus time and quiz results.
        self.progress_card, progress, _ = _card("Progress")
        self.progress = QLabel()
        self.progress.setObjectName("progressText")
        self.progress.setWordWrap(True)
        progress.addWidget(self.progress)
        self.review = QPushButton()
        self.review.setObjectName("primary")
        self.review.setIcon(glyph_icon("cards", color="#0a1424"))
        self.review.setCursor(Qt.CursorShape.PointingHandCursor)
        self.review.clicked.connect(lambda: self.project_id and self.review_cards.emit(self.project_id))
        progress.addWidget(self.review, 0, Qt.AlignmentFlag.AlignLeft)
        left.addWidget(self.progress_card)

        card, chats, self.chats_header = _card("Conversations")
        self.chats_title = card.findChild(QLabel, "cardTitle")
        self.chats_hint = QLabel()
        self.chats_hint.setObjectName("rowHint")
        self.chats_hint.setWordWrap(True)
        chats.addWidget(self.chats_hint)
        self.chats = QListWidget()
        self.chats.setObjectName("projectChats")
        self.chats.setFrameShape(QFrame.Shape.NoFrame)
        self.chats.setCursor(Qt.CursorShape.PointingHandCursor)
        self.chats.itemClicked.connect(lambda item: self.open_conversation.emit(item.data(Qt.ItemDataRole.UserRole)))
        self.chats.setMinimumHeight(220)
        chats.addWidget(self.chats, 1)
        self.no_chats = QLabel("No conversations yet. Start one above; it stays in this project.")
        self.no_chats.setObjectName("rowHint")
        self.no_chats.setWordWrap(True)
        chats.addWidget(self.no_chats)
        left.addWidget(card, 1)

        card, instructions, _ = _card("Instructions", "She follows these in every conversation of this project. "
                                      "For example: “I'm a beginner, use examples first” or “answer in Indonesian”.")
        self.instructions_title = card.findChild(QLabel, "cardTitle")
        self.instructions_hint = card.findChild(QLabel, "rowHint")
        self.instructions = QPlainTextEdit()
        self.instructions.setObjectName("projectInstructions")
        self.instructions.setPlaceholderText("How should she help with this project?")
        self.instructions.setMinimumHeight(120)
        self.instructions.textChanged.connect(lambda: self._instructions_timer.start())
        instructions.addWidget(self.instructions)
        self.saved = QLabel("")
        self.saved.setObjectName("rowHint")
        instructions.addWidget(self.saved)
        right.addWidget(card)
        self._instructions_timer = QTimer(self)
        self._instructions_timer.setSingleShot(True)
        self._instructions_timer.setInterval(700)
        self._instructions_timer.timeout.connect(self._save_instructions)

        card, files, header = _card("Files", "Notes, documents and code she should know. Text and PDFs are read "
                                    "and kept in mind; you can also drop files here.")
        self.files_title = card.findChild(QLabel, "cardTitle")
        self.files_hint = card.findChild(QLabel, "rowHint")
        self.refresh_all = QPushButton()
        self.refresh_all.setObjectName("chip")
        self.refresh_all.setToolTip("Bring in the newer versions of files that changed since they were added")
        self.refresh_all.setCursor(Qt.CursorShape.PointingHandCursor)
        self.refresh_all.clicked.connect(self._refresh_all)
        header.addWidget(self.refresh_all)
        add = QPushButton("Add files…")
        add.setObjectName("chip")
        add.setCursor(Qt.CursorShape.PointingHandCursor)
        add.clicked.connect(self._choose_files)
        header.addWidget(add)
        self.files = QListWidget()
        self.files.setObjectName("projectFiles")
        self.files.setFrameShape(QFrame.Shape.NoFrame)
        self.files.setMaximumHeight(200)
        files.addWidget(self.files)
        self.knowledge = QLabel()
        self.knowledge.setObjectName("rowHint")
        self.knowledge.setWordWrap(True)
        files.addWidget(self.knowledge)
        right.addWidget(card)

        card, folder, _ = _card("Folder", "Computer tasks in this project start in this folder.")
        self.folder_card = card
        self.folder = QLabel()
        self.folder.setObjectName("projectFolder")
        self.folder.setWordWrap(True)
        self.folder.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        folder.addWidget(self.folder)
        buttons = QHBoxLayout()
        self.choose_folder = QPushButton("Choose…")
        self.choose_folder.clicked.connect(self._choose_folder)
        self.open_folder = QPushButton("Open")
        self.open_folder.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(self._project()["folder"])))
        self.clear_folder = QPushButton("Clear")
        self.clear_folder.clicked.connect(lambda: self._update(folder=""))
        for button in (self.choose_folder, self.open_folder, self.clear_folder):
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            buttons.addWidget(button)
        buttons.addStretch()
        folder.addLayout(buttons)
        right.addWidget(card)
        right.addStretch()

    # Showing ---------------------------------------------------------------------------------

    def _project(self):
        return self.store.project(self.project_id) if self.project_id else None

    def show_project(self, project_id):
        self._save_instructions()  # Anything typed in the previous project is kept.
        self.project_id = project_id
        project = self._project()
        if not project:
            return
        self.name.setText(project["name"])
        self.description.setText(project["description"])
        self.instructions.blockSignals(True)
        self.instructions.setPlainText(project["instructions"])
        self.instructions.blockSignals(False)
        self.saved.setText("")
        self.refresh()

    def refresh(self):
        project = self._project()
        if not project:
            return
        study = project["kind"] == "study"
        words = STUDY_WORDS if study else PROJECT_WORDS
        self.badge.setPixmap(project_icon(project["color"], 34, "study" if study else "folder").pixmap(34, 34))
        self.name.setPlaceholderText(words["name"])
        self.description.setPlaceholderText(words["description"])
        self.start.setText(words["start"].format(name=project["name"]))
        self.instructions_title.setText(words["instructions"])
        self.instructions_hint.setText(words["instructions_hint"])
        self.instructions.setPlaceholderText(words["instructions_placeholder"])
        self.files_hint.setText(words["files_hint"])
        self.folder_card.setVisible(not study)
        self.progress_card.setVisible(study)
        if study:
            self._show_progress(project)
        rows = self.store.conversations(self.character(), project=project["id"])
        self.chats.clear()
        for row in rows:
            item = QListWidgetItem(f"{row['title']}    ·  {_when(row['updated_at'])}")
            item.setData(Qt.ItemDataRole.UserRole, row["id"])
            item.setSizeHint(QSize(0, 38))
            self.chats.addItem(item)
        self.chats_title.setText(f"{words['chats']} ({len(rows)})" if rows else words["chats"])
        self.no_chats.setText(words["no_chats"])
        self.chats_hint.setText(words["chats_hint"])
        self.chats_hint.setVisible(bool(words["chats_hint"]))
        self.no_chats.setVisible(not rows)
        files = self.store.project_files(project["id"])
        self.files.clear()
        for item in files:
            self._file_row(item)
        self.files_title.setText(f"{words['files']} ({len(files)})" if files else words["files"])
        stale = sum(knowledge.newer_at_source(item) for item in files)
        self.refresh_all.setText(f"Refresh all ({stale})")
        self.refresh_all.setVisible(stale > 1)
        self.files.setVisible(bool(files))
        readable, characters = knowledge.summary(files)
        self.knowledge.setText("" if not files else
                               f"She reads {readable} of {len(files)} files ({characters:,} characters"
                               + (f"; up to {knowledge.KNOWLEDGE_CHARS:,} are given to her each reply)."
                                  if characters > knowledge.KNOWLEDGE_CHARS else ")."))
        folder = project["folder"]
        self.folder.setText(folder or "No folder chosen. Tasks start in your home folder.")
        self.open_folder.setEnabled(bool(folder) and Path(folder).is_dir())
        self.clear_folder.setEnabled(bool(folder))

    def _show_progress(self, project):
        from ..chat import study
        progress = study.stats(self.store, project["id"])
        accuracy = (f"{progress['right']} of {progress['answers']} recent quiz answers right"
                    if progress["answers"] else "No quiz answers yet")
        self.progress.setText(f"{progress['cards']} flashcards · {progress['due']} due today\n"
                              f"{study.minutes_text(progress['focus_week'])} of focus this week "
                              f"({study.minutes_text(progress['focus_total'])} in total)\n{accuracy}")
        self.review.setText(f"Review flashcards ({progress['due']} due)" if progress["due"] else
                            "Browse flashcards" if progress["cards"] else "No flashcards yet")
        self.review.setEnabled(bool(progress["cards"]))

    def _file_row(self, item):
        row = QWidget()
        line = QHBoxLayout(row)
        line.setContentsMargins(4, 2, 0, 2)
        line.setSpacing(8)
        glyph = QLabel(ICONS["image" if item["kind"] == "image" else "document"])
        glyph.setObjectName("attachmentIcon")
        line.addWidget(glyph)
        name = QLabel(item["name"])
        name.setObjectName("attachmentName")
        name.setToolTip(str(resolve(item["path"])))
        line.addWidget(name, 1)
        meta = QLabel(f"{KIND_LABELS.get(item['kind'], 'File')} · {_size(item['size'])}")
        meta.setObjectName("rowHint")
        meta.setToolTip(f"This version added {_when(item['added_at'])}")
        line.addWidget(meta)
        if knowledge.newer_at_source(item):
            refresh = QPushButton("Refresh")
            refresh.setObjectName("chip")
            refresh.setToolTip(f"The original changed since it was added:\n{item['source']}")
            refresh.setCursor(Qt.CursorShape.PointingHandCursor)
            refresh.clicked.connect(lambda: self._replace_file(item, item["source"]))
            line.addWidget(refresh)
        more = QPushButton(ICONS["more"])
        more.setObjectName("remove")
        more.setToolTip("Open, replace or remove")
        more.setCursor(Qt.CursorShape.PointingHandCursor)
        menu = QMenu(more)
        menu.addAction(glyph_icon("open"), "Open", lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(resolve(item["path"])))))
        menu.addAction(glyph_icon("rename"), "Replace with a newer version…", lambda: self._choose_replacement(item))
        if item.get("source") and Path(item["source"]).exists():
            menu.addAction(glyph_icon("folder"), "Show the original",
                           lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(item["source"]).parent))))
        menu.addSeparator()
        menu.addAction(glyph_icon("delete", color="#f3a5b3"), "Remove", lambda: self._remove_file(item["id"]))
        more.clicked.connect(lambda: menu.exec(more.mapToGlobal(more.rect().bottomLeft())))
        line.addWidget(more)
        entry = QListWidgetItem()
        entry.setSizeHint(QSize(0, 34))
        self.files.addItem(entry)
        self.files.setItemWidget(entry, row)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        wide = self.width() >= 720
        self.columns.setDirection(QBoxLayout.Direction.LeftToRight if wide else QBoxLayout.Direction.TopToBottom)

    # Editing ---------------------------------------------------------------------------------

    def _update(self, **fields):
        try:
            self.store.update_project(self.project_id, **fields)
        except (ValueError, sqlite3.Error) as exc:
            QMessageBox.warning(self, "Could not save", str(exc) if isinstance(exc, ValueError)
                                else "The project could not be saved. Please try again.")
            return False
        self.refresh()
        self.changed.emit()
        return True

    def _save_name(self):
        project = self._project()
        if project and self.name.text().strip() and self.name.text().strip() != project["name"]:
            self._update(name=self.name.text())
        elif project:
            self.name.setText(project["name"])

    def _save_description(self):
        project = self._project()
        if project and self.description.text().strip() != project["description"]:
            self._update(description=self.description.text())

    def _save_instructions(self):
        self._instructions_timer.stop()
        project = self._project()
        if not project or self.instructions.toPlainText().strip("\n") == project["instructions"]:
            return
        try:
            self.store.update_project(self.project_id, instructions=self.instructions.toPlainText())
            self.saved.setText("Saved")
        except (ValueError, sqlite3.Error) as exc:
            self.saved.setText(str(exc) if isinstance(exc, ValueError) else "Could not save. Please try again.")

    def _set_color(self, color):
        self._update(color=color)

    def _choose_folder(self):
        project = self._project()
        folder = QFileDialog.getExistingDirectory(self, "Choose the project's folder", project["folder"] or str(Path.home()))
        if folder:
            self._update(folder=str(Path(folder)))

    def _choose_files(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "Add files to the project", str(Path.home()), FILE_FILTER)
        self.add_files(paths)

    def add_files(self, paths):
        if not paths or not self.project_id:
            return
        existing = len(self.store.project_files(self.project_id))
        problems = []
        for path in paths[:max(0, knowledge.MAX_FILES - existing)]:
            try:
                name, stored, kind, size = knowledge.store_file(path, self.project_id, self.files_root)
                self.store.add_project_file(self.project_id, name, stored, kind, size, *knowledge.origin(path))
            except AttachmentError as exc:
                problems.append(str(exc))
            except (OSError, sqlite3.Error):
                problems.append(f"{Path(path).name} could not be copied.")
        if len(paths) > knowledge.MAX_FILES - existing:
            problems.append(f"A project holds up to {knowledge.MAX_FILES} files.")
        self.refresh()
        self.changed.emit()
        if problems:
            QMessageBox.information(self, "Some files were not added", "\n".join(problems[:8]))

    def _choose_replacement(self, item):
        start = item.get("source") if item.get("source") and Path(item["source"]).exists() else str(Path.home())
        path, _ = QFileDialog.getOpenFileName(self, f"Replace {item['name']}", start, FILE_FILTER)
        if path:
            self._replace_file(item, path)

    def _replace_file(self, item, path, quiet=False):
        """A newer version of a material takes its place; the old copy is removed."""
        try:
            name, stored, kind, size = knowledge.store_file(path, self.project_id, self.files_root)
        except AttachmentError as exc:
            if not quiet:
                QMessageBox.information(self, "Could not update", str(exc))
            return False
        except OSError:
            if not quiet:
                QMessageBox.information(self, "Could not update", f"{Path(path).name} could not be copied.")
            return False
        try:
            before = self.store.update_project_file(item["id"], name, stored, kind, size, *knowledge.origin(path))
        except sqlite3.Error:
            knowledge.remove_stored([{"path": stored}], self.files_root)
            return False
        if before:
            knowledge.remove_stored([before], self.files_root)
        if not quiet:
            self.refresh()
            self.changed.emit()
        return True

    def _refresh_all(self):
        changed = [item for item in self.store.project_files(self.project_id) if knowledge.newer_at_source(item)]
        updated = sum(self._replace_file(item, item["source"], quiet=True) for item in changed)
        self.refresh()
        self.changed.emit()
        if updated < len(changed):
            QMessageBox.information(self, "Some files were not updated",
                                    f"{len(changed) - updated} of {len(changed)} could not be read again.")

    def _remove_file(self, file_id):
        try:
            item = self.store.remove_project_file(file_id)
        except sqlite3.Error:
            return
        if item:
            knowledge.remove_stored([item], self.files_root)
        self.refresh()
        self.changed.emit()

    def _delete(self):
        project = self._project()
        if not project:
            return
        box = QMessageBox(self)
        box.setWindowTitle("Delete project?")
        box.setText(f"Delete “{project['name']}”? Its instructions and files are removed.")
        keep = box.addButton("Delete, keep its chats", QMessageBox.ButtonRole.AcceptRole)
        everything = box.addButton("Delete with its chats", QMessageBox.ButtonRole.DestructiveRole)
        box.addButton(QMessageBox.StandardButton.Cancel)
        box.exec()
        if box.clickedButton() not in (keep, everything):
            return
        with_chats = box.clickedButton() is everything
        try:
            files = self.store.delete_project(project["id"], delete_conversations=with_chats)
        except sqlite3.Error:
            QMessageBox.warning(self, "Could not delete", "The project could not be deleted. Please try again.")
            return
        knowledge.remove_stored(files, self.files_root)
        knowledge.remove_folder(project["id"], self.files_root)
        self.project_id = None
        self.deleted.emit(project["id"], with_chats)

    # Dropping files on the page ----------------------------------------------------------------

    def dragEnterEvent(self, event):
        if self.project_id and any(url.isLocalFile() for url in event.mimeData().urls()):
            event.acceptProposedAction()

    def dropEvent(self, event):
        self.add_files([url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()])
        event.acceptProposedAction()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.back.emit()
            return
        super().keyPressEvent(event)
