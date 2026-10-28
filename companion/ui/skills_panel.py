"""Settings → Tools → Skills: the skills she has, switched on or off, and adding more (see chat/skills.py)."""

from PySide6.QtCore import QThread, Qt, Signal
from PySide6.QtWidgets import (QCheckBox, QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QMenu, QPushButton,
                               QVBoxLayout, QWidget)

from ..chat import skills
from .theme import glyph_icon


class Installer(QThread):
    """Installs skills away from the window (a download can take a moment)."""
    done = Signal(list)
    failed = Signal(str)

    def __init__(self, source, parent=None):
        super().__init__(parent)
        self.source = source

    def run(self):
        try:
            self.done.emit(skills.install(self.source))
        except skills.SkillError as exc:
            self.failed.emit(str(exc))
        except Exception:  # A broken archive or a network problem: said plainly, never a crash.
            self.failed.emit("That skill could not be installed. Check the link and your connection.")


class SkillsPanel(QWidget):
    changed = Signal()
    installed = Signal(list)  # Names of skills just installed.

    def __init__(self, parent=None):
        super().__init__(parent)
        self.installer = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        hint = QLabel("Skills are packaged instructions she can use, as in Claude Code: a folder with a SKILL.md. "
                      "They work with your Claude subscription, in replies and in computer tasks. She can also install "
                      "one when you ask her to; she asks you first.")
        hint.setObjectName("rowHint")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        add = QHBoxLayout()
        add.setSpacing(6)
        self.source = QLineEdit()
        self.source.setPlaceholderText("GitHub link or owner/repo, e.g. https://github.com/owner/repo")
        self.source.returnPressed.connect(self.install_typed)
        add.addWidget(self.source, 1)
        self.install_button = QPushButton("Install")
        self.install_button.setObjectName("chip")
        self.install_button.clicked.connect(self.install_typed)
        add.addWidget(self.install_button)
        layout.addLayout(add)
        more = QHBoxLayout()
        folder = QPushButton("Add a folder…")
        folder.setObjectName("chip")
        folder.clicked.connect(self._add_folder)
        more.addWidget(folder)
        self.mine = QPushButton("From your Claude Code skills")
        self.mine.setObjectName("chip")
        self.mine_menu = QMenu(self)
        self.mine_menu.aboutToShow.connect(self._fill_mine)
        self.mine.setMenu(self.mine_menu)
        more.addWidget(self.mine)
        more.addStretch()
        layout.addLayout(more)
        self.status = QLabel()
        self.status.setObjectName("rowHint")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.rows = QVBoxLayout()
        self.rows.setSpacing(6)
        layout.addLayout(self.rows)
        self.refresh()

    def refresh(self):
        while self.rows.count():
            item = self.rows.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        found = skills.installed()
        if not found:
            empty = QLabel("No skills yet.")
            empty.setObjectName("rowHint")
            self.rows.addWidget(empty)
        for skill in found:
            self.rows.addWidget(self._row(skill))

    def _row(self, skill):
        row = QFrame()
        row.setObjectName("serverRow")
        line = QHBoxLayout(row)
        line.setContentsMargins(14, 10, 10, 10)
        text = QVBoxLayout()
        text.setSpacing(2)
        name = QLabel(skill["name"])
        name.setObjectName("rowTitle")
        text.addWidget(name)
        if skill["description"]:
            about = QLabel(skill["description"][:220] + ("…" if len(skill["description"]) > 220 else ""))
            about.setObjectName("rowHint")
            about.setWordWrap(True)
            text.addWidget(about)
        line.addLayout(text, 1)
        switch = QCheckBox()
        switch.setChecked(skill["enabled"])
        switch.setToolTip("On: she can use it")
        switch.toggled.connect(lambda on, name=skill["name"]: self._switch(name, on))
        line.addWidget(switch, 0, Qt.AlignmentFlag.AlignVCenter)
        remove = QPushButton()
        remove.setObjectName("rowAction")
        remove.setIcon(glyph_icon("delete", color="#f3a5b3"))
        remove.setToolTip("Remove this skill")
        remove.setCursor(Qt.CursorShape.PointingHandCursor)
        remove.clicked.connect(lambda _=False, name=skill["name"]: self._remove(name))
        line.addWidget(remove, 0, Qt.AlignmentFlag.AlignVCenter)
        return row

    def _switch(self, name, on):
        skills.set_enabled(name, on)
        self.changed.emit()

    def _remove(self, name):
        from .inline import ask
        ask(self, "Remove this skill?", f"{name} will be deleted from her skills.", "Remove",
            lambda: (skills.remove(name), self.refresh(), self.changed.emit()))

    def install_typed(self):
        if self.source.text().strip():
            self.install(self.source.text().strip())

    def install(self, source):
        """Installs from a GitHub link or a folder in the background; `installed` says which when done."""
        if self.installer is not None:
            return False
        self.status.setText("Installing…")
        self.install_button.setEnabled(False)
        installer = Installer(source, self)
        installer.done.connect(self._installed)
        installer.failed.connect(self._failed)
        installer.finished.connect(self._finished)
        self.installer = installer
        installer.start()
        return True

    def _installed(self, names):
        self.status.setText("Installed: " + ", ".join(names) + ".")
        self.source.clear()
        self.refresh()
        self.changed.emit()
        self.installed.emit(names)

    def _failed(self, message):
        self.status.setText(message)
        self.installed.emit([])

    def _finished(self):
        self.installer.deleteLater()
        self.installer = None
        self.install_button.setEnabled(True)

    def _add_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "A skill's folder (with a SKILL.md), or a folder of skills")
        if folder:
            self.install(folder)

    def _fill_mine(self):
        self.mine_menu.clear()
        found = skills.claude_code_skills()
        if not found:
            item = self.mine_menu.addAction("She has all of them already" if skills.installed() else "None found")
            item.setEnabled(False)
        for name, description, path in found:
            item = self.mine_menu.addAction(name)
            item.setToolTip(description)
            item.triggered.connect(lambda _=False, path=path: self.install(str(path)))
        self.mine_menu.setToolTipsVisible(True)
