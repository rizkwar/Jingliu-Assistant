"""Computer tasks: Jingliu works on the person's PC through Claude Code, with approval for risky steps.

Conversation stays tool-free. When a task is requested, a separate Claude Code run gets real
tools (commands, files, web, and screen/mouse/keyboard through companion.task_tools). Reading
and looking are allowed; commands, file changes and input actions ask the person first.
"""

import json
import os
from pathlib import Path
import secrets
import shutil
import string
import sys
import tempfile
import time

from PySide6.QtCore import QObject, QProcess, QProcessEnvironment, QTimer, Signal
from PySide6.QtNetwork import QHostAddress, QTcpServer

from .config import PROJECT_ROOT

SERVER = "jingliu"
# Looking and reading need no approval; everything else reaches the approval hook.
FREE_TOOLS = ("Read", "Glob", "Grep", "WebSearch", "WebFetch", f"mcp__{SERVER}__screenshot", f"mcp__{SERVER}__wait")
TOOLS = "Bash,PowerShell,Read,Write,Edit,Glob,Grep,WebSearch,WebFetch"
INPUT_TOOLS = {f"mcp__{SERVER}__{name}" for name in ("click", "type_text", "press_keys", "scroll")}
MAX_TURNS = 80
UNDO_ROOT = PROJECT_ROOT / "data" / "task_undo"
TIME_LIMIT_MS = 20 * 60 * 1000

TASK_PROMPT = """You are {name}, the user's desktop companion, now carrying out a task they asked you to do
on their Windows computer. Their home folder is {home}. You may work anywhere on the computer.

How to work:
- Do exactly what was asked, sensibly and carefully. Prefer commands and file tools; use the screen,
  mouse and keyboard tools (take a screenshot first, then click by its pixel coordinates) when the
  task needs an app's window.
- The user cannot answer questions mid-task. If something is ambiguous, risky beyond the request
  (deleting many files, spending money, sending messages to others, changing system settings), or
  needs a password, stop and explain instead of guessing.
- Some steps need the user's approval. If a step is denied, do not retry it another way; finish what you
  can and say what was not done.
- The user can undo your task afterwards. To move, rename, copy or delete files and folders, or to create
  folders, always use the move_path, copy_path, delete_path and make_folder tools, and use Write or Edit for
  file contents: those changes can be reversed. Use commands only for what these tools cannot do.

When you finish, reply with a short report in {name}'s own voice (first person, composed, warm, no
stage directions or asterisks), two to four sentences: what you did, where to find the result, and
anything they should check. This report is shown and spoken to them.

Character profile for your voice:
{profile}
"""


def claude_executable():
    return shutil.which("claude.exe" if os.name == "nt" else "claude")


def drives():
    """Every fixed drive root, so file tools can reach the whole computer."""
    if os.name != "nt":
        return ["/"]
    return [f"{letter}:\\" for letter in string.ascii_uppercase if os.path.isdir(f"{letter}:\\")]


def describe(tool, values):
    """One line, in plain words, for the task card and the approval window."""
    values = values or {}
    path = values.get("file_path") or values.get("path") or values.get("pattern") or ""
    short = lambda text, limit=160: (text[:limit] + "…") if len(text) > limit else text
    name = tool.removeprefix(f"mcp__{SERVER}__")
    return {
        "Bash": lambda: f"Run a command: {short(str(values.get('command', '')))}",
        "PowerShell": lambda: f"Run a command: {short(str(values.get('command', '')))}",
        "Write": lambda: f"Write the file {path}",
        "Edit": lambda: f"Edit the file {path}",
        "Read": lambda: f"Read {path}",
        "Glob": lambda: f"Look for files: {path}",
        "Grep": lambda: f"Search in files for “{short(str(values.get('pattern', '')), 60)}”",
        "WebSearch": lambda: f"Search the web: {short(str(values.get('query', '')), 80)}",
        "WebFetch": lambda: f"Open the page {short(str(values.get('url', '')), 100)}",
        "screenshot": lambda: "Look at the screen",
        "click": lambda: f"{'Double-click' if values.get('count') == 2 else 'Right-click' if values.get('button') == 'right' else 'Click'} "
                         f"at ({values.get('x')}, {values.get('y')}) on the screen",
        "type_text": lambda: f"Type: {short(str(values.get('text', '')), 120)}",
        "press_keys": lambda: f"Press {values.get('keys', '')}",
        "scroll": lambda: f"Scroll {'up' if (values.get('amount') or 0) > 0 else 'down'} on the screen",
        "wait": lambda: "Wait a moment",
        **{tool: (lambda tool=tool: FILE_STEPS[tool](values)) for tool in FILE_STEPS},
    }.get(name, lambda: f"Use {name}")()


FILE_STEPS = {
    "move_path": lambda v: f"Move {v.get('source', '')} to {v.get('destination', '')}",
    "copy_path": lambda v: f"Copy {v.get('source', '')} to {v.get('destination', '')}",
    "delete_path": lambda v: f"Delete {v.get('path', '')}",
    "make_folder": lambda v: f"Create the folder {v.get('path', '')}",
}


def step_kind(summary):
    """How she looks while doing a step: reading, writing, running, using the screen or thinking."""
    for kind, starts in (("read", ("Read", "Look for files", "Search in files", "Search the web", "Open the page")),
                         ("command", ("Run a command", "Move ", "Copy ", "Delete ", "Create the folder")),
                         ("type", ("Write the file", "Edit the file", "Type", "Press")),
                         ("look", ("Click", "Double-click", "Right-click", "Scroll", "Look at the screen"))):
        if summary.startswith(starts):
            return kind
    return "think"


def approval_group(tool):
    """"Allow for this task" covers similar steps: all input actions, all commands, all file changes."""
    if tool in INPUT_TOOLS:
        return "mouse and keyboard"
    if tool in {"Bash", "PowerShell"}:
        return "commands"
    if tool in {"Write", "Edit"} or tool.removeprefix(f"mcp__{SERVER}__") in FILE_STEPS:
        return "file changes"
    return tool


class ApprovalServer(QObject):
    """Loopback-only: receives approval requests from task_tools and answers them."""
    requested = Signal(object)  # ApprovalRequest

    def __init__(self, parent=None):
        super().__init__(parent)
        self.token = secrets.token_urlsafe(24)
        self.server = QTcpServer(self)
        self.server.newConnection.connect(self._accept)
        if not self.server.listen(QHostAddress.SpecialAddress.LocalHost, 0):
            raise OSError("The approval channel could not start.")

    @property
    def port(self):
        return self.server.serverPort()

    def _accept(self):
        while self.server.hasPendingConnections():
            socket = self.server.nextPendingConnection()
            socket.setParent(self)
            buffer = bytearray()

            def read(socket=socket, buffer=buffer):
                buffer.extend(bytes(socket.readAll()))
                if b"\n" not in buffer:
                    if len(buffer) > 1_000_000:
                        socket.abort()
                    return
                try:
                    message = json.loads(bytes(buffer).split(b"\n", 1)[0])
                except ValueError:
                    socket.abort()
                    return
                if not isinstance(message, dict) or not secrets.compare_digest(str(message.get("token", "")), self.token):
                    socket.abort()  # Only this app's own tool server knows the token.
                    return
                request = message.get("request") or {}
                self.requested.emit(ApprovalRequest(socket, str(request.get("tool_name", "")), request.get("input") or {}))

            socket.readyRead.connect(read)
            socket.disconnected.connect(socket.deleteLater)


class ApprovalRequest:
    def __init__(self, socket, tool, values):
        self.socket, self.tool, self.values = socket, tool, values
        self.answered = False
        self.on_allow = None  # Records the step for undo just before it is allowed to run.

    @property
    def summary(self):
        return describe(self.tool, self.values)

    def answer(self, allow, message=""):
        if self.answered:
            return
        self.answered = True
        if allow and self.on_allow is not None:
            try:
                self.on_allow(self)
            except OSError as exc:
                # Without a copy of the original, the change could not be undone: refuse it.
                allow, message = False, f"The original could not be kept for undo ({exc}), so this was not done."
        from shiboken6 import isValid
        if not isValid(self.socket):
            return  # The task ended while the person was deciding.
        self.socket.write((json.dumps({"allow": bool(allow), "message": message}) + "\n").encode())
        self.socket.flush()


class ComputerTask(QObject):
    """One task run. Emits progress steps, approval requests, and a final report."""
    step = Signal(str)
    approval = Signal(object)
    finished = Signal(str, bool)  # report, succeeded

    def __init__(self, request, context, settings, parent=None, undo_root=None):
        super().__init__(parent)
        self.request = request
        from .task_journal import Journal, cleanup
        root = Path(undo_root or UNDO_ROOT)
        cleanup(root)
        self.journal = Journal(root / (time.strftime("%Y%m%d-%H%M%S") + "-" + secrets.token_hex(3)))
        self.journal.describe_task(request=request, started=time.time())
        self.allowed_groups = set()
        # Off in Settings: every step runs at once, still shown as it happens.
        self.ask = getattr(settings, "approve_steps", True)
        self.done = False
        self.folder = tempfile.TemporaryDirectory(prefix="jingliu-task-")
        self.approvals = ApprovalServer(self)
        self.approvals.requested.connect(self._approval)
        self.process = QProcess(self)
        self.buffer = bytearray()
        self.process.readyReadStandardOutput.connect(self._read)
        self.process.finished.connect(self._exited)
        self.process.errorOccurred.connect(self._failed_to_start)
        self.limit = QTimer(self)
        self.limit.setSingleShot(True)
        self.limit.setInterval(TIME_LIMIT_MS)
        self.limit.timeout.connect(lambda: self.stop("That task ran past twenty minutes, so I stopped it."))
        self._prepare(context, settings)

    def _prepare(self, context, settings):
        work = Path(self.folder.name)
        python = Path(sys.executable)
        if python.name.lower() == "pythonw.exe":
            python = python.with_name("python.exe")
        server = {"command": str(python), "args": ["-u", "-m", "companion.task_tools"],
                  "env": {"PYTHONPATH": str(PROJECT_ROOT), "JINGLIU_APPROVAL_PORT": str(self.approvals.port),
                          "JINGLIU_APPROVAL_TOKEN": self.approvals.token, "PYTHONIOENCODING": "utf-8",
                          "JINGLIU_JOURNAL": str(self.journal.folder)}}
        (work / "mcp.json").write_text(json.dumps({"mcpServers": {SERVER: server}}), encoding="utf-8")
        (work / "prompt.txt").write_text(TASK_PROMPT.format(
            name=settings.name, home=Path.home(), profile=settings.system_prompt or settings.name), encoding="utf-8")
        from .claude_backend import DEFAULT_CLAUDE_MODEL
        arguments = ["-p", "--output-format", "stream-json", "--verbose", "--no-session-persistence",
                     "--setting-sources", "", "--disable-slash-commands", "--strict-mcp-config",
                     "--mcp-config", str(work / "mcp.json"), "--permission-prompt-tool", f"mcp__{SERVER}__approve",
                     "--tools", TOOLS, "--allowedTools", *FREE_TOOLS, "--append-system-prompt-file", str(work / "prompt.txt"),
                     "--model", settings.claude_model or DEFAULT_CLAUDE_MODEL, "--effort", "medium",
                     "--max-turns", str(MAX_TURNS), "--add-dir", *drives()]
        earlier = "\n".join(f"{m['role']}: {m['content']}" for m in context[-6:] if m.get("content"))
        self.prompt = (("Recent conversation, for context:\n" + earlier + "\n\n") if earlier else "") + \
            "The task to do now:\n" + self.request
        environment = QProcessEnvironment.systemEnvironment()
        for name in list(environment.keys()):
            # A configured API key would bill the API instead of the subscription.
            if name.endswith(("API_KEY", "AUTH_TOKEN")) or name.startswith("CLAUDE_CODE_") or name == "CLAUDECODE":
                environment.remove(name)
        self.process.setProcessEnvironment(environment)
        self.process.setWorkingDirectory(str(Path.home()))
        self.process.setProgram(claude_executable() or "claude")
        self.process.setArguments(arguments)

    def start(self):
        if not claude_executable():
            self._finish("Claude Code isn't installed, so I can't work on your computer yet.", False)
            return
        self.step.emit("Starting…")
        self.process.start()
        self.process.write(self.prompt.encode("utf-8"))
        self.process.closeWriteChannel()
        self.limit.start()

    def stop(self, report="You stopped the task, so I left things as they were at that moment."):
        if self.done:
            return
        self.process.kill()
        self._finish(report, False)

    def _approval(self, request):
        request.on_allow = self._record
        group = approval_group(request.tool)
        if self.done:
            request.answer(False, "The task has ended.")
        elif not self.ask or group in self.allowed_groups:
            request.answer(True)
            self.step.emit(request.summary)
        else:
            self.approval.emit(request)

    def _record(self, request):
        """Before an allowed step runs: keep what undo needs, or note what it cannot reverse."""
        name = request.tool.removeprefix(f"mcp__{SERVER}__")
        if request.tool in {"Write", "Edit"}:
            self.journal.before_write(request.values.get("file_path", ""))
        elif request.tool in {"Bash", "PowerShell"}:
            self.journal.note("command", request.values.get("command", ""))
        elif request.tool in INPUT_TOOLS:
            self.journal.note("screen", name)

    def remember_approval(self, request):
        self.allowed_groups.add(approval_group(request.tool))

    def _read(self):
        self.buffer.extend(bytes(self.process.readAllStandardOutput()))
        while b"\n" in self.buffer:
            line, _, rest = bytes(self.buffer).partition(b"\n")
            self.buffer = bytearray(rest)
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if event.get("type") == "assistant":
                for block in (event.get("message") or {}).get("content") or []:
                    # Only steps that need no approval are announced here; approved ones are
                    # announced as they are allowed.
                    if block.get("type") == "tool_use" and (block.get("name") in FREE_TOOLS):
                        self.step.emit(describe(block.get("name", ""), block.get("input")))
            elif event.get("type") == "result":
                text = str(event.get("result") or "").strip()
                ok = not event.get("is_error") and event.get("subtype") == "success"
                if not text:
                    text = ("I couldn't finish within the number of steps I'm allowed. Here is where I stopped."
                            if event.get("subtype") == "error_max_turns" else "I couldn't finish that task.")
                self._finish(text, ok)

    def _exited(self, *_):
        self._read()
        if not self.done:
            self._finish("Something interrupted me before I could finish. Check your Claude sign-in and plan limits.", False)

    def _failed_to_start(self, error):
        if error == QProcess.ProcessError.FailedToStart:
            self._finish("I couldn't start Claude Code for this task.", False)

    def _finish(self, report, succeeded):
        if self.done:
            return
        self.done = True
        self.limit.stop()
        try:
            self.journal.describe_task(finished=time.time(), succeeded=bool(succeeded), report=report[:600])
        except OSError:
            pass
        self.finished.emit(report, succeeded)
        QTimer.singleShot(0, self.folder.cleanup)
