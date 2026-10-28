"""Computer tasks: Jingliu works on the person's PC through Claude Code, with approval for risky steps.

Conversation stays tool-free. When a task is requested, a separate Claude Code run gets real
tools (commands, files, web, and screen/mouse/keyboard through companion.tasks.tools). Reading
and looking are allowed; commands, file changes and input actions ask the person first.
"""

import json
import os
from pathlib import Path
import re
import secrets
import shutil
import string
import sys
import tempfile
import time

from PySide6.QtCore import QObject, QProcess, QProcessEnvironment, QTimer, Signal
from PySide6.QtNetwork import QHostAddress, QTcpServer

from ..core.config import PROJECT_ROOT

SERVER = "jingliu"
# Looking and reading need no approval; everything else reaches the approval hook.
FREE_TOOLS = ("Read", "Glob", "Grep", "WebSearch", "WebFetch", f"mcp__{SERVER}__screenshot", f"mcp__{SERVER}__wait")
TOOLS = "Bash,PowerShell,Read,Write,Edit,Glob,Grep,WebSearch,WebFetch"
INPUT_TOOLS = {f"mcp__{SERVER}__{name}" for name in ("click", "type_text", "press_keys", "scroll")}
MAX_TURNS = 80
UNDO_ROOT = PROJECT_ROOT / "data" / "task_undo"
TIME_LIMIT_MS = 20 * 60 * 1000
# The watchdog: a task is stuck when it repeats itself, goes quiet, or one step runs far too long.
QUIET_SECONDS = 4 * 60
LONG_STEP_SECONDS = 5 * 60
WRAP_UP_SECONDS = 2 * 60
LOOKING = {f"mcp__{SERVER}__screenshot", f"mcp__{SERVER}__wait"}

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
- Never get stuck waiting. Do not run commands that wait for input or never end in the foreground (servers,
  watchers, interactive prompts, `pause`); start apps with Start-Process; start a server in the background
  only when the task needs one, and stop it when done. Do not poll the screen or wait over and over: if
  something does not change after two or three checks, try another way or report it.
- Read economically. Search with Grep or Glob before opening files; read large files in parts (offset and
  limit); do not read a file again unless it changed; read independent files in parallel. Do not take a
  screenshot again unless something on screen should have changed.
- The app may tell you mid-task that you seem stuck, or pass on a message from the user. Follow it.

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
    if tool.startswith("mcp__") and not tool.startswith(f"mcp__{SERVER}__"):
        server, _, name = tool.removeprefix("mcp__").partition("__")
        return f"Use {name.replace('_', ' ')} from {server}"
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
    if tool.startswith("mcp__"):
        return "tools from " + tool.removeprefix("mcp__").partition("__")[0]
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
    activity = Signal(str)  # What she is doing right now, between steps ("Thinking…", "Writing notes.md · 40 lines")
    usage = Signal(dict)  # The tokens the task used: {model, input, output, cached}.
    limits = Signal(list)  # What is left of the plan, as reported while she works.

    def __init__(self, request, context, settings, parent=None, undo_root=None, servers=(), project=None, session=None):
        super().__init__(parent)
        self.request = request
        # The Claude Code session to run in ({id, resume}); a resumed one still has what her earlier task read.
        self.session, self.context_size, self.reported = session, 0, False
        self.model = settings.claude_model
        self.servers, self.project = list(servers), project
        from ..core.mcp import trusted_tools
        self.trusted = tuple(trusted_tools(self.servers))
        from .journal import Journal, cleanup
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
        # Watchdog state: what is running, what she has done, and how she is being steered.
        self.pending, self.running, self.calls, self.log = [], {}, [], []
        self.last_event = time.monotonic()
        self.building, self.last_live = None, 0.0
        self.steering, self.queued, self.stuck_count, self.wrap_up_at = False, None, 0, None
        self.watchdog = QTimer(self)
        self.watchdog.setInterval(5000)
        self.watchdog.timeout.connect(self._watch)
        self.step.connect(self._logged)
        self._prepare(context, settings)

    def _prepare(self, context, settings):
        work = Path(self.folder.name)
        python = Path(sys.executable)
        if python.name.lower() == "pythonw.exe":
            python = python.with_name("python.exe")
        server = {"command": str(python), "args": ["-u", "-m", "companion.tasks.tools"],
                  "env": {"PYTHONPATH": str(PROJECT_ROOT), "JINGLIU_APPROVAL_PORT": str(self.approvals.port),
                          "JINGLIU_APPROVAL_TOKEN": self.approvals.token, "PYTHONIOENCODING": "utf-8",
                          "JINGLIU_JOURNAL": str(self.journal.folder)}}
        from ..core.mcp import claude_config
        servers = {**claude_config(self.servers)["mcpServers"], SERVER: server}
        (work / "mcp.json").write_text(json.dumps({"mcpServers": servers}), encoding="utf-8")
        prompt = TASK_PROMPT.format(name=settings.name, home=Path.home(), profile=settings.system_prompt or settings.name)
        folder = Path(self.project["folder"]) if self.project and self.project.get("folder") else None
        if self.project:
            prompt += (f"\nThis task belongs to the user's project \"{self.project['name']}\"."
                       + (f" Its folder is {folder}; work there unless the task says otherwise." if folder else "")
                       + (f"\nProject instructions: {self.project['instructions']}" if self.project.get("instructions") else "")
                       + "\n")
        (work / "prompt.txt").write_text(prompt, encoding="utf-8")
        from ..chat.claude import DEFAULT_CLAUDE_MODEL
        from ..chat.effort import claude as claude_effort
        # stream-json both ways: the app can interrupt a stuck step and steer her with a message.
        session = self.session or {}
        keep = (["--resume", session["id"]] if session.get("resume") else ["--session-id", session["id"], "--name",
                f"{settings.name} task"]) if session.get("id") else ["--no-session-persistence"]
        arguments = ["-p", "--input-format", "stream-json", "--output-format", "stream-json", "--verbose",
                     "--include-partial-messages", *keep,
                     "--setting-sources", "", "--disable-slash-commands", "--strict-mcp-config",
                     "--mcp-config", str(work / "mcp.json"), "--permission-prompt-tool", f"mcp__{SERVER}__approve",
                     "--tools", TOOLS, "--allowedTools", *FREE_TOOLS, *self.trusted,
                     "--append-system-prompt-file", str(work / "prompt.txt"),
                     "--model", settings.claude_model or DEFAULT_CLAUDE_MODEL,
                     "--effort", claude_effort(getattr(settings, "task_effort", "medium")),
                     "--max-turns", str(MAX_TURNS), "--add-dir", *drives()]
        earlier = "\n".join(f"{m['role']}: {m['content']}" for m in context[-6:] if m.get("content"))
        self.prompt = (("Recent conversation, for context:\n" + earlier + "\n\n") if earlier else "") + \
            "The task to do now:\n" + self.request
        if session.get("resume"):
            # Her earlier task in this conversation is above: what she read and found is still in front of her.
            self.prompt = ("A new task in the same conversation. Your earlier task's work is above: reuse what you "
                           "already read and found instead of reading it again, and check only what may have changed "
                           "since (a file's modified time, or a quick Grep). Report on this new task only.\n\n"
                           + self.prompt)
        environment = QProcessEnvironment.systemEnvironment()
        for name in list(environment.keys()):
            # A configured API key would bill the API instead of the subscription.
            if name.endswith(("API_KEY", "AUTH_TOKEN")) or name.startswith("CLAUDE_CODE_") or name == "CLAUDECODE":
                environment.remove(name)
        self.process.setProcessEnvironment(environment)
        self.process.setWorkingDirectory(str(folder if folder and folder.is_dir() else Path.home()))
        self.process.setProgram(claude_executable() or "claude")
        self.process.setArguments(arguments)

    def start(self):
        if not claude_executable():
            self._finish("Claude Code isn't installed, so I can't work on your computer yet.", False)
            return
        self.step.emit("Starting…")
        self.process.start()
        self._send(self.prompt)
        self.limit.start()
        self.watchdog.start()

    def _send(self, text):
        self._write({"type": "user", "message": {"role": "user", "content": [{"type": "text", "text": text}]}})

    def _write(self, payload):
        if self.process.state() != QProcess.ProcessState.NotRunning:
            self.process.write((json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8"))

    def steer(self, message, by_person=True):
        """Interrupts what she is doing and gives her `message`; she carries on from there.
        A step waiting for approval is declined with the message instead, which reaches her the same way."""
        if self.done or not message.strip():
            return
        text = (f"The user says, while you work: {message.strip()}\nTake this into account and continue the task."
                if by_person else message)
        waiting = [request for request in self.pending if not request.answered]
        if waiting:
            for request in waiting:
                request.answer(False, "Not run. " + text)
            return
        self.steering, self.queued = True, text
        self._write({"type": "control_request", "request_id": "steer-" + secrets.token_hex(4),
                     "request": {"subtype": "interrupt"}})
        QTimer.singleShot(15000, self._release)  # If the interrupt has nothing to stop, send it anyway.

    def _release(self):
        if self.steering and self.queued and not self.done:
            self.steering, text, self.queued = False, self.queued, None
            self._send(text)

    def _logged(self, text):
        self.log.append([round(time.time(), 1), text[:300]])

    def _live(self, text, force=False):
        now = time.monotonic()
        if force or now - self.last_live > .4:
            self.last_live = now
            self.activity.emit(text)

    def _watch(self):
        """Every few seconds: is she stuck? Waiting for the person never counts."""
        if self.done:
            return
        now = time.monotonic()
        if any(not request.answered for request in self.pending):
            self.last_event = now
            return
        if self.wrap_up_at and now > self.wrap_up_at:
            self.stop("I got stuck and couldn't get past it, so I stopped. " + self._progress())
            return
        if self.steering:
            return
        long_steps = [summary for started, summary in self.running.values() if now - started > LONG_STEP_SECONDS]
        if long_steps:
            self._stuck(f"the step \"{long_steps[0]}\" has been running for over {LONG_STEP_SECONDS // 60} minutes")
        elif not self.running and now - self.last_event > QUIET_SECONDS:
            self._stuck(f"nothing has happened for {QUIET_SECONDS // 60} minutes")

    def _looping(self):
        """Why her last steps look like a loop, or an empty string."""
        if len(self.calls) >= 3 and len(set(self.calls[-3:])) == 1:
            return "you did the same step three times in a row: " + describe(*self._call(self.calls[-1]))
        recent = self.calls[-10:]
        if len(recent) == 10 and sum(name in LOOKING for name, _ in map(self._call, recent)) >= 8:
            return "you have been waiting and looking at the screen over and over"
        reads = [values.get("file_path") for name, values in map(self._call, self.calls) if name == "Read"]
        path = self._call(self.calls[-1])[1].get("file_path") if self.calls else None
        if path and reads.count(path) >= 4:
            return f"you have read {path} four times; use what you already read"
        return ""

    @staticmethod
    def _call(signature):
        name, values = signature
        return name, json.loads(values)

    def _stuck(self, reason):
        """First time: steer her to another way. Second: ask for her report. Then stop."""
        self.stuck_count += 1
        self.last_event = time.monotonic()
        self.running.clear()
        if self.stuck_count == 1:
            self.step.emit("Seemed stuck, so trying another way")
            self.steer(f"The app noticed you seem stuck: {reason}. Do not repeat that. Try a different approach; "
                       "if that part cannot be done, skip it and carry on with the rest of the task.", by_person=False)
        elif self.stuck_count == 2:
            self.step.emit("Still stuck, so wrapping up")
            self.wrap_up_at = time.monotonic() + WRAP_UP_SECONDS
            self.steer(f"You still seem stuck: {reason}. Stop working now. Reply with your report: what you "
                       "finished, what you could not do, and why.", by_person=False)

    def _progress(self):
        done = [text for _, text in self.log if text not in ("Starting…",)][-3:]
        return ("The last things I did: " + "; ".join(done) + ".") if done else ""

    def stop(self, report="You stopped the task, so I left things as they were at that moment."):
        if self.done:
            return
        self.process.kill()
        self._finish(report, False)

    def _approval(self, request):
        request.on_allow = self._record
        self.pending = [item for item in self.pending if not item.answered] + [request]
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
            self._handle(event)

    def _handle(self, event):
        """One stream-json event from her run."""
        self.last_event = time.monotonic()
        kind = event.get("type")
        if kind == "stream_event":
            self._partial(event.get("event") or {})
        elif kind == "assistant":
            for block in (event.get("message") or {}).get("content") or []:
                if block.get("type") != "tool_use":
                    continue
                # Only steps that need no approval are announced here; approved ones are
                # announced as they are allowed.
                name, values = block.get("name") or "", block.get("input") or {}
                self.running[block.get("id")] = (time.monotonic(), describe(name, values))
                self.calls.append((name, json.dumps(values, sort_keys=True, ensure_ascii=False)))
                if name in FREE_TOOLS or (self.trusted and name.startswith(self.trusted)):
                    self.step.emit(describe(name, values))
                loop = self._looping()
                if loop and not self.steering:
                    self._stuck(loop)
        elif kind == "user":
            content = (event.get("message") or {}).get("content")
            for block in content if isinstance(content, list) else []:
                if isinstance(block, dict) and block.get("type") == "tool_result":
                    self.running.pop(block.get("tool_use_id"), None)
        elif kind == "rate_limit_event":
            from ..chat.usage import claude_windows
            windows = claude_windows(event.get("rate_limit_info") or {})
            if windows:
                self.limits.emit(windows)
        elif kind == "result" and self.steering:
            # The interrupted turn ends here; she continues with the message.
            self.steering, text, self.queued = False, self.queued, None
            self.running.clear()
            if text:
                self._send(text)
        elif kind == "result":
            used = event.get("usage") or {}
            fresh = (used.get("input_tokens") or 0) + (used.get("cache_creation_input_tokens") or 0)
            counts = {"input": fresh, "output": used.get("output_tokens") or 0,
                      "cached": used.get("cache_read_input_tokens") or 0}
            if any(counts.values()):
                self.usage.emit({"model": self.model or "", **counts})
            # The last call's size is what a continuing session carries into the next task.
            last = (used.get("iterations") or [used])[-1]
            self.context_size = sum(last.get(name) or 0 for name in (
                "input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens", "output_tokens"))
            self.reported = True
            text = str(event.get("result") or "").strip()
            ok = not event.get("is_error") and event.get("subtype") == "success"
            if not text:
                text = ("I couldn't finish within the number of steps I'm allowed. Here is where I stopped."
                        if event.get("subtype") == "error_max_turns" else "I couldn't finish that task.")
            self._finish(text, ok)

    def _partial(self, inner):
        """Live progress between steps, from the reply as it streams."""
        kind = inner.get("type")
        block = inner.get("content_block") or {}
        if kind == "content_block_start":
            if block.get("type") == "thinking":
                self._live("Thinking…", force=True)
            elif block.get("type") == "text":
                self._live("Writing…", force=True)
            elif block.get("type") == "tool_use":
                self.building = {"name": block.get("name") or "", "json": ""}
                self._live(describe(self.building["name"], {}).replace(" the file ", " a file") + "…", force=True)
        elif kind == "content_block_delta" and self.building and (inner.get("delta") or {}).get("type") == "input_json_delta":
            self.building["json"] += inner["delta"].get("partial_json") or ""
            name, partial = self.building["name"], self.building["json"]
            path = re.search(r'"(?:file_path|path)"\s*:\s*"((?:[^"\\]|\\.)*)"', partial)
            where = Path(json.loads(f'"{path.group(1)}"')).name if path else ""
            if name in ("Write", "Edit") and where:
                body = re.split(r'"(?:content|new_string)"\s*:\s*"', partial, maxsplit=1)
                lines = len(re.findall(r'(?<!\\)(?:\\\\)*\\n', body[1])) + 1 if len(body) > 1 and body[1] else 0
                self._live(f"Writing {where}" + (f" · {lines} lines" if lines else "") + "…")
            elif name in ("Bash", "PowerShell"):
                self._live("Preparing a command…")
        elif kind == "content_block_stop":
            self.building = None

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
        self.watchdog.stop()
        if self.process.state() != QProcess.ProcessState.NotRunning:
            self.process.closeWriteChannel()  # Nothing more to say; anything she left running ends with her.
            QTimer.singleShot(3000, self.process.kill)
        try:
            # The steps and when they happened, to see later where a task got stuck.
            self.journal.describe_task(finished=time.time(), succeeded=bool(succeeded), report=report[:600],
                                       steps=self.log[-200:], stuck=self.stuck_count)
        except OSError:
            pass
        self.finished.emit(report, succeeded)
        QTimer.singleShot(0, self.folder.cleanup)
