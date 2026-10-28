"""Settings → Tools: MCP servers that give her more tools (notes, calendar, GitHub, a database…)."""
import asyncio
import shlex
import time

from PySide6.QtCore import QThread, Qt, Signal
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFrame, QHBoxLayout, QLabel,
                               QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPlainTextEdit, QPushButton,
                               QStackedWidget, QVBoxLayout, QWidget)

from ..core import mcp
from .inline import ask, tell
from .theme import ICONS

SCOPE_LABELS = (("Computer tasks only", "tasks"), ("Conversations and tasks", "everywhere"))


class ToolTest(QThread):
    """Starts a server once, asks for its tools, and stops it."""
    done = Signal(object, str)  # tools (list of (name, description)) or None, error text

    def __init__(self, server, parent=None):
        super().__init__(parent)
        self.server = server

    def run(self):
        try:
            self.done.emit(asyncio.run(mcp.list_tools(self.server)), "")
        except ValueError as exc:
            self.done.emit(None, str(exc))
        except Exception:  # A broken server must not take the app with it.
            self.done.emit(None, "The test failed unexpectedly. Check the server's settings.")


def _lines(mapping, separator):
    return "\n".join(f"{key}{separator}{value}" for key, value in mapping.items())


def _mapping(text, separator):
    values = {}
    for line in text.splitlines():
        if line.strip():
            key, found, value = line.partition(separator)
            if not found or not key.strip():
                raise ValueError(f"Write each line as NAME{separator}VALUE.")
            values[key.strip()] = value.strip()
    return values


class ServerDialog(QDialog):
    """Add or edit one server: by command or URL, or by pasting the JSON snippet from its instructions."""

    def __init__(self, server=None, others=(), parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit MCP server" if server else "Add an MCP server")
        self.others, self.result_server, self._test = list(others), None, None
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        intro = QLabel("Most servers' instructions show a JSON snippet. Paste it below and the fields fill in, "
                       "or fill them in yourself.")
        intro.setObjectName("rowHint")
        intro.setWordWrap(True)
        layout.addWidget(intro)
        self.paste = QPlainTextEdit()
        self.paste.setPlaceholderText('{"mcpServers": {"notes": {"command": "npx", "args": ["-y", "some-mcp-server"]}}}')
        self.paste.setMaximumHeight(70)
        layout.addWidget(self.paste)
        use = QPushButton("Fill in from the JSON")
        use.clicked.connect(self._from_json)
        layout.addWidget(use, 0, Qt.AlignmentFlag.AlignRight)

        def field(title, widget, hint=None):
            label = QLabel(title)
            label.setObjectName("rowTitle")
            layout.addWidget(label)
            layout.addWidget(widget)
            if hint:
                note = QLabel(hint)
                note.setObjectName("rowHint")
                note.setWordWrap(True)
                layout.addWidget(note)
            return label

        self.name = QLineEdit()
        self.name.setPlaceholderText("notes")
        field("Name", self.name, "Short, without spaces. Her tools appear as “name”.")
        self.transport = QComboBox()
        self.transport.addItem("Runs on this computer (a command)", "stdio")
        self.transport.addItem("On the web (a URL)", "http")
        field("Kind", self.transport)
        self.kinds = QStackedWidget()
        command_page = QWidget()
        command = QVBoxLayout(command_page)
        command.setContentsMargins(0, 0, 0, 0)
        self.command = QLineEdit()
        self.command.setPlaceholderText("npx -y @modelcontextprotocol/server-filesystem D:\\Notes")
        command.addWidget(QLabel("Command and arguments"))
        command.addWidget(self.command)
        self.env = QPlainTextEdit()
        self.env.setPlaceholderText("API_TOKEN=…   (one per line, optional)")
        self.env.setMaximumHeight(64)
        command.addWidget(QLabel("Environment variables"))
        command.addWidget(self.env)
        url_page = QWidget()
        web = QVBoxLayout(url_page)
        web.setContentsMargins(0, 0, 0, 0)
        self.url = QLineEdit()
        self.url.setPlaceholderText("https://example.com/mcp")
        web.addWidget(QLabel("URL"))
        web.addWidget(self.url)
        self.headers = QPlainTextEdit()
        self.headers.setPlaceholderText("Authorization: Bearer …   (one per line, optional)")
        self.headers.setMaximumHeight(64)
        web.addWidget(QLabel("Headers"))
        web.addWidget(self.headers)
        self.kinds.addWidget(command_page)
        self.kinds.addWidget(url_page)
        layout.addWidget(self.kinds)
        self.transport.currentIndexChanged.connect(self.kinds.setCurrentIndex)
        self.scope = QComboBox()
        for label, value in SCOPE_LABELS:
            self.scope.addItem(label, value)
        field("Where she can use it", self.scope,
              "In conversation its tools run without asking (Claude subscription only), so choose that for servers "
              "that only read, like notes or a calendar.")
        self.ask = QCheckBox("In computer tasks, ask me before each of its tools")
        self.ask.setChecked(True)
        layout.addWidget(self.ask)
        self.status = QLabel()
        self.status.setObjectName("rowHint")
        self.status.setWordWrap(True)
        self.status.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.status)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        self.test_button = buttons.addButton("Test", QDialogButtonBox.ButtonRole.ActionRole)
        self.test_button.clicked.connect(self._run_test)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        if server:
            self._show(server)

    def _show(self, server):
        self.name.setText(server.name)
        self.transport.setCurrentIndex(1 if server.transport == "http" else 0)
        self.command.setText(" ".join([server.command, *(f'"{arg}"' if " " in arg else arg for arg in server.args)]).strip())
        self.env.setPlainText(_lines(server.env, "="))
        self.url.setText(server.url)
        self.headers.setPlainText(_lines(server.headers, ": "))
        self.scope.setCurrentIndex(self.scope.findData(server.scope))
        self.ask.setChecked(server.ask)
        self._enabled = server.enabled

    def _from_json(self):
        try:
            servers = mcp.parse(self.paste.toPlainText())
        except ValueError as exc:
            self.status.setText(str(exc))
            return
        if not servers:
            self.status.setText("No server was found in that JSON.")
            return
        self._show(servers[0])
        self.status.setText("Filled in. Check the name, then Test or Save."
                            + (f" (The JSON had {len(servers)} servers; use Import for several.)" if len(servers) > 1 else ""))

    def server(self):
        transport = self.transport.currentData()
        parts = shlex.split(self.command.text(), posix=False) if transport == "stdio" else []
        parts = [part[1:-1] if len(part) > 1 and part[0] == part[-1] == '"' else part for part in parts]
        server = mcp.Server(name=self.name.text().strip(), transport=transport,
                            command=parts[0] if parts else "", args=parts[1:],
                            env=_mapping(self.env.toPlainText(), "=") if transport == "stdio" else {},
                            url=self.url.text().strip() if transport == "http" else "",
                            headers=_mapping(self.headers.toPlainText(), ":") if transport == "http" else {},
                            enabled=getattr(self, "_enabled", True), scope=self.scope.currentData(),
                            ask=self.ask.isChecked())
        return mcp.validate(server, self.others)

    def _run_test(self):
        try:
            server = self.server()
        except ValueError as exc:
            self.status.setText(str(exc))
            return
        self.test_button.setEnabled(False)
        self.status.setText("Starting the server and asking for its tools…")
        self._test = ToolTest(server, self)
        self._test.done.connect(self._tested)
        self._test.start()

    def _tested(self, tools, error):
        self.test_button.setEnabled(True)
        if tools is None:
            self.status.setText("Not working yet: " + error)
        elif not tools:
            self.status.setText("Connected, but the server offers no tools.")
        else:
            names = ", ".join(name for name, _ in tools[:12]) + (" …" if len(tools) > 12 else "")
            self.status.setText(f"Working: {len(tools)} tools ({names}).")

    def _save(self):
        try:
            self.result_server = self.server()
        except ValueError as exc:
            self.status.setText(str(exc))
            return
        self.accept()

    def done(self, result):
        if self._test is not None and self._test.isRunning():
            self._test.wait(35000)
        super().done(result)


class ImportDialog(QDialog):
    def __init__(self, candidates, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Import MCP servers")
        layout = QVBoxLayout(self)
        intro = QLabel("These servers are set up for Claude on this computer. Choose the ones she may use. "
                       "They start as computer-task tools that ask first; change that per server afterwards.")
        intro.setObjectName("rowHint")
        intro.setWordWrap(True)
        layout.addWidget(intro)
        self.list = QListWidget()
        for label, server in candidates:
            item = QListWidgetItem(f"{server.name}    ·  {label}  ·  {server.summary()[:70]}")
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked)
            item.setData(Qt.ItemDataRole.UserRole, server)
            self.list.addItem(item)
        layout.addWidget(self.list)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Import")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def chosen(self):
        return [self.list.item(row).data(Qt.ItemDataRole.UserRole) for row in range(self.list.count())
                if self.list.item(row).checkState() == Qt.CheckState.Checked]


class ServerRow(QFrame):
    changed = Signal()
    edit = Signal(object)
    remove = Signal(object)
    test = Signal(object)

    def __init__(self, server, status="", parent=None):
        super().__init__(parent)
        self.server = server
        self.setObjectName("serverRow")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 10, 10)
        layout.setSpacing(6)
        top = QHBoxLayout()
        glyph = QLabel(ICONS["tool"])
        glyph.setObjectName("memoryIcon")
        top.addWidget(glyph)
        name = QLabel(server.name)
        name.setObjectName("cardTitle")
        top.addWidget(name)
        kind = QLabel("web" if server.transport == "http" else "command")
        kind.setObjectName("historyBadge")
        top.addWidget(kind)
        top.addStretch()
        self.enabled = QCheckBox()
        self.enabled.setChecked(server.enabled)
        self.enabled.setToolTip("Use this server")
        self.enabled.toggled.connect(self._enabled)
        top.addWidget(self.enabled)
        layout.addLayout(top)
        summary = QLabel(server.summary())
        summary.setObjectName("taskSteps")
        summary.setWordWrap(True)
        layout.addWidget(summary)
        options = QHBoxLayout()
        self.scope = QComboBox()
        for label, value in SCOPE_LABELS:
            self.scope.addItem(label, value)
        self.scope.setCurrentIndex(self.scope.findData(server.scope))
        self.scope.currentIndexChanged.connect(self._scope)
        options.addWidget(self.scope)
        self.ask = QCheckBox("Ask first in tasks")
        self.ask.setChecked(server.ask)
        self.ask.toggled.connect(self._ask)
        options.addWidget(self.ask)
        options.addStretch()
        for text, signal in (("Test", self.test), ("Edit", self.edit), ("Remove", self.remove)):
            button = QPushButton(text)
            button.setObjectName("chip" if text != "Remove" else "danger")
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(lambda _=False, signal=signal: signal.emit(self.server))
            options.addWidget(button)
        layout.addLayout(options)
        self.status = QLabel(status)
        self.status.setObjectName("rowHint")
        self.status.setWordWrap(True)
        self.status.setVisible(bool(status))
        layout.addWidget(self.status)

    def _enabled(self, on):
        self.server.enabled = on
        self.changed.emit()

    def _scope(self, _index):
        self.server.scope = self.scope.currentData()
        self.changed.emit()

    def _ask(self, on):
        self.server.ask = on
        self.changed.emit()

    def show_status(self, text):
        self.status.setText(text)
        self.status.setVisible(bool(text))


class ToolsPanel(QWidget):
    """The server list in Settings. `present` shows a dialog as a page of the window and waits for it."""
    changed = Signal(list)

    def __init__(self, path=mcp.CONFIG, present=None, parent=None):
        super().__init__(parent)
        self.path, self.present = path, present or (lambda dialog: dialog.exec())
        self.statuses, self._tests = {}, []
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        intro = QLabel("MCP servers give her more tools: your notes, a calendar, GitHub, a database and more. "
                       "Computer tasks can use every enabled server. In conversation she can use servers set to "
                       "“Conversations and tasks” while replying, when replies come from your Claude subscription.")
        intro.setObjectName("rowHint")
        intro.setWordWrap(True)
        layout.addWidget(intro)
        buttons = QHBoxLayout()
        add = QPushButton("Add server…")
        add.setObjectName("primary")
        add.clicked.connect(self._add)
        imported = QPushButton("Import from Claude…")
        imported.setToolTip("Servers already set up for Claude Code or Claude Desktop on this computer")
        imported.clicked.connect(self._import)
        for button in (add, imported):
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            buttons.addWidget(button)
        buttons.addStretch()
        layout.addLayout(buttons)
        self.rows = QVBoxLayout()
        self.rows.setSpacing(10)
        layout.addLayout(self.rows)
        self.empty = QLabel("No servers yet.")
        self.empty.setObjectName("rowHint")
        layout.addWidget(self.empty)
        self.error = QLabel()
        self.error.setObjectName("error")
        self.error.setWordWrap(True)
        self.error.hide()
        layout.addWidget(self.error)
        try:
            self.servers = mcp.load(self.path)
        except ValueError as exc:
            self.servers = []
            self.error.setText(str(exc))
            self.error.show()
        self._render()

    def _render(self):
        while self.rows.count():
            widget = self.rows.takeAt(0).widget()
            if widget is not None:
                widget.deleteLater()
        for server in self.servers:
            row = ServerRow(server, self.statuses.get(server.name, ""))
            row.changed.connect(self._save)
            row.edit.connect(self._edit)
            row.remove.connect(self._remove)
            row.test.connect(self._test)
            self.rows.addWidget(row)
        self.empty.setVisible(not self.servers)

    def _save(self):
        try:
            mcp.save(self.servers, self.path)
            self.error.hide()
        except (OSError, ValueError) as exc:
            self.error.setText(f"Could not save the servers: {exc}")
            self.error.show()
        self.changed.emit(list(self.servers))

    def _add(self):
        dialog = ServerDialog(others=self.servers, parent=self)
        if self.present(dialog) and dialog.result_server:
            self.servers.append(dialog.result_server)
            self._save()
            self._render()
        dialog.deleteLater()

    def _edit(self, server):
        dialog = ServerDialog(server, [other for other in self.servers if other is not server], parent=self)
        if self.present(dialog) and dialog.result_server:
            self.servers[self.servers.index(server)] = dialog.result_server
            self.statuses.pop(server.name, None)
            self._save()
            self._render()
        dialog.deleteLater()

    def _remove(self, server):
        def remove():
            if server in self.servers:
                self.servers.remove(server)
                self._save()
                self._render()
        ask(self, "Remove server?", f"Remove “{server.name}”? She will no longer use its tools.", "Remove", remove)

    def _import(self):
        names = {server.name.lower() for server in self.servers}
        candidates = [(label, server) for label, server in mcp.import_candidates()
                      if server.name.lower() not in names and server.name.lower() not in mcp.RESERVED]
        if not candidates:
            tell(self, "Nothing to import", "No new MCP servers were found in Claude Code or "
                                    "Claude Desktop on this computer.", "info")
            return
        dialog = ImportDialog(candidates, self)
        if self.present(dialog):
            for server in dialog.chosen():
                try:
                    self.servers.append(mcp.validate(server, self.servers))
                except ValueError:
                    continue
            self._save()
            self._render()
        dialog.deleteLater()

    def _row(self, server):
        for index in range(self.rows.count()):
            row = self.rows.itemAt(index).widget()
            if isinstance(row, ServerRow) and row.server is server:
                return row
        return None

    def _test(self, server):
        row = self._row(server)
        if row:
            row.show_status("Testing…")
        test = ToolTest(server, self)
        self._tests.append(test)
        test.done.connect(lambda tools, error: self._tested(server, tools, error, test))
        test.start()

    def _tested(self, server, tools, error, test):
        if tools is None:
            text = "Not working: " + error
        else:
            names = ", ".join(name for name, _ in tools[:10]) + (" …" if len(tools) > 10 else "")
            text = f"Working · {len(tools)} tools · tested {time.strftime('%H:%M')}" + (f" · {names}" if names else "")
        self.statuses[server.name] = text
        row = self._row(server)
        if row:
            row.show_status(text)
        if test in self._tests:
            self._tests.remove(test)

    def shutdown(self):
        for test in list(self._tests):
            test.wait(35000)
