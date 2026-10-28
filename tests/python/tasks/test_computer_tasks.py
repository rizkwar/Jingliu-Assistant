import json
import os
import socket
import subprocess
import sys
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent, QObject, Signal

from companion.tasks import runner as computer_tasks
from companion.tasks import tools as task_tools
from companion.tasks.runner import ApprovalServer, ComputerTask, FREE_TOOLS, approval_group, describe
from companion.core.config import DEFAULT_MODEL, Settings
from tests.qt_test_support import application

ROOT = Path(__file__).resolve().parents[3]
SETTINGS = Settings("test-key", DEFAULT_MODEL, "Jingliu", "Profile.", tts_enabled=False)


class ToolServerTests(unittest.TestCase):
    def test_approval_reply_shapes_follow_the_permission_hook(self):
        with patch.dict(os.environ, {"JINGLIU_APPROVAL_AUTO": "allow"}):
            reply = json.loads(task_tools.call("approve", {"tool_name": "Write", "input": {"file_path": "a"}})["content"][0]["text"])
        self.assertEqual(reply, {"behavior": "allow", "updatedInput": {"file_path": "a"}})
        with patch.dict(os.environ, {"JINGLIU_APPROVAL_AUTO": "deny"}):
            reply = json.loads(task_tools.call("approve", {"tool_name": "Bash", "input": {}})["content"][0]["text"])
        self.assertEqual(reply["behavior"], "deny")
        with patch.dict(os.environ, {}, clear=True):  # No window to ask: never allowed.
            reply = json.loads(task_tools.call("approve", {"tool_name": "Bash", "input": {}})["content"][0]["text"])
        self.assertEqual(reply["behavior"], "deny")

    def test_clicking_needs_a_screenshot_first(self):
        task_tools.state["factor"] = None
        result = task_tools.call("click", {"x": 1, "y": 1})
        self.assertTrue(result["isError"])

    def test_stdio_handshake_lists_tools(self):
        messages = [{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}},
                    {"jsonrpc": "2.0", "method": "notifications/initialized"},
                    {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
                    {"jsonrpc": "2.0", "id": 3, "method": "nope"}]
        output = subprocess.run([sys.executable, "-m", "companion.tasks.tools"], cwd=ROOT, capture_output=True, text=True,
                                input="".join(json.dumps(m) + "\n" for m in messages), timeout=60).stdout
        replies = [json.loads(line) for line in output.splitlines()]
        self.assertEqual([r["id"] for r in replies], [1, 2, 3])
        self.assertEqual(replies[0]["result"]["protocolVersion"], "2025-06-18")
        names = {tool["name"] for tool in replies[1]["result"]["tools"]}
        self.assertEqual(names, {"approve", "screenshot", "click", "type_text", "press_keys", "scroll", "wait",
                                 "move_path", "copy_path", "delete_path", "make_folder"})
        self.assertIn("error", replies[2])


class ApprovalChannelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = application()

    def pump_until(self, condition, timeout=5):
        end = time.monotonic() + timeout
        while not condition() and time.monotonic() < end:
            self.app.processEvents()
            time.sleep(.005)

    def test_only_the_token_holder_is_heard_and_gets_an_answer(self):
        server = ApprovalServer()
        requests, replies = [], []
        server.requested.connect(lambda request: (requests.append(request), request.answer(True)))

        def client(token):
            with socket.create_connection(("127.0.0.1", server.port), timeout=5) as connection:
                connection.sendall((json.dumps({"token": token, "request": {"tool_name": "Bash", "input": {"command": "dir"}}})
                                    + "\n").encode())
                try:
                    replies.append(connection.recv(1000))
                except OSError:
                    replies.append(b"")
        thread = threading.Thread(target=client, args=("wrong",)); thread.start()
        self.pump_until(lambda: not thread.is_alive()); thread.join()
        self.assertEqual(requests, [])
        self.assertEqual(replies, [b""])
        thread = threading.Thread(target=client, args=(server.token,)); thread.start()
        self.pump_until(lambda: not thread.is_alive()); thread.join()
        self.assertEqual(requests[0].summary, "Run a command: dir")
        self.assertEqual(json.loads(replies[1]), {"allow": True, "message": ""})
        # Tear down like a finished task does, not at a random garbage-collection moment.
        server.server.close()
        server.deleteLater()
        self.app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        requests[0].answer(False)  # Answering after the task ended is harmless.


class TaskRunTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = application()

    def setUp(self):
        import tempfile
        self.undo = tempfile.TemporaryDirectory()
        self.addCleanup(self.undo.cleanup)
        patcher = patch("companion.tasks.runner.UNDO_ROOT", Path(self.undo.name))
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_allowed_steps_are_recorded_for_undo_before_they_run(self):
        work = Path(self.undo.name) / "work"
        work.mkdir()
        (work / "notes.txt").write_text("original", encoding="utf-8")
        task = ComputerTask("Tidy", [], SETTINGS)
        self.assertIn(str(Path(self.undo.name)), str(task.journal.folder))  # Never the real data folder in tests.
        for tool, values in (("Edit", {"file_path": str(work / "notes.txt")}),
                             ("Write", {"file_path": str(work / "new.txt")}),
                             ("PowerShell", {"command": "Get-Date"}),
                             ("mcp__jingliu__click", {"x": 1, "y": 2})):
            request = FakeRequest(tool)
            request.values = values
            task._record(request)
        ops = [entry["op"] for entry in task.journal.entries()]
        self.assertEqual(ops, ["replace", "create", "note", "note"])
        (work / "notes.txt").write_text("changed by the task", encoding="utf-8")
        (work / "new.txt").write_text("made by the task", encoding="utf-8")
        lines, notes = task.journal.plan()
        self.assertTrue(any("restore 1 edited file" in line for line in lines))
        self.assertEqual(len(notes), 2)  # The command, and the clicks.
        done, problems = task.journal.undo()
        self.assertEqual(problems, [])
        self.assertEqual((work / "notes.txt").read_text(encoding="utf-8"), "original")
        self.assertFalse((work / "new.txt").exists())
        task.folder.cleanup()

    def test_tool_server_file_operations_are_undoable(self):
        work = Path(self.undo.name) / "files"
        (work / "Downloads").mkdir(parents=True)
        (work / "Downloads" / "a.png").write_text("a", encoding="utf-8")
        (work / "Downloads" / "old.zip").write_text("z", encoding="utf-8")
        journal = Path(self.undo.name) / "journal"
        with patch.dict(os.environ, {"JINGLIU_JOURNAL": str(journal)}):
            for name, arguments in (("make_folder", {"path": str(work / "Downloads" / "Pictures" / "2026")}),
                                    ("move_path", {"source": str(work / "Downloads" / "a.png"),
                                                   "destination": str(work / "Downloads" / "Pictures" / "2026")}),
                                    ("copy_path", {"source": str(work / "Downloads" / "Pictures"),
                                                   "destination": str(work / "Backup" / "Pictures")}),
                                    ("delete_path", {"path": str(work / "Downloads" / "old.zip")})):
                self.assertFalse(task_tools.call(name, arguments).get("isError"), name)
        self.assertTrue((work / "Downloads" / "Pictures" / "2026" / "a.png").exists())
        self.assertFalse((work / "Downloads" / "old.zip").exists())
        from companion.tasks.journal import Journal
        done, problems = Journal(journal).undo()
        self.assertEqual(problems, [])
        self.assertEqual(sorted(p.name for p in (work / "Downloads").iterdir()), ["a.png", "old.zip"])
        self.assertFalse((work / "Backup").exists())
        with patch.dict(os.environ, {"JINGLIU_JOURNAL": ""}):
            self.assertTrue(task_tools.call("delete_path", {"path": str(work)}).get("isError"))
        self.assertTrue(work.exists())

    def test_task_runs_isolated_with_approval_for_risky_steps(self):
        task = ComputerTask("Tidy my Downloads folder", [{"role": "user", "content": "Hi"}], SETTINGS)
        arguments = task.process.arguments()
        for flag in ("--strict-mcp-config", "--disable-slash-commands", "--no-session-persistence"):
            self.assertIn(flag, arguments)
        self.assertEqual(arguments[arguments.index("--setting-sources") + 1], "")
        self.assertEqual(arguments[arguments.index("--permission-prompt-tool") + 1], "mcp__jingliu__approve")
        self.assertNotIn("--safe-mode", arguments)  # It would drop the approval server.
        self.assertNotIn("--dangerously-skip-permissions", arguments)
        for risky in ("Bash", "PowerShell", "Write", "Edit", "mcp__jingliu__click", "mcp__jingliu__type_text"):
            self.assertNotIn(risky, FREE_TOOLS)
        environment = task.process.processEnvironment()
        self.assertFalse(any(name.endswith("API_KEY") for name in environment.keys()))
        self.assertIn("Tidy my Downloads folder", task.prompt)
        config = json.loads((Path(task.folder.name) / "mcp.json").read_text(encoding="utf-8"))
        self.assertEqual(config["mcpServers"]["jingliu"]["env"]["JINGLIU_APPROVAL_TOKEN"], task.approvals.token)
        task.folder.cleanup()

    def test_steps_can_run_without_asking_when_approval_is_off(self):
        from dataclasses import replace
        for ask in (True, False):
            task = ComputerTask("Open Notepad", [], replace(SETTINGS, approve_steps=ask))
            shown, steps, request = [], [], FakeRequest("mcp__jingliu__click")
            task.approval.connect(shown.append)
            task.step.connect(steps.append)
            task._approval(request)
            self.assertEqual(bool(shown), ask)
            self.assertEqual(request.answers, [] if ask else [True])
            self.assertEqual(steps, [] if ask else [request.summary])
            task.folder.cleanup()

    def test_steps_read_plainly_and_group_sensibly(self):
        self.assertEqual(describe("PowerShell", {"command": "Get-ChildItem"}), "Run a command: Get-ChildItem")
        self.assertEqual(describe("mcp__jingliu__click", {"x": 4, "y": 5, "count": 2}), "Double-click at (4, 5) on the screen")
        self.assertEqual(approval_group("mcp__jingliu__press_keys"), "mouse and keyboard")
        self.assertEqual(approval_group("Edit"), approval_group("Write"))


class FakeTask(QObject):
    step = Signal(str)
    approval = Signal(object)
    finished = Signal(str, bool)
    created = []

    def __init__(self, request, context, settings, parent=None, servers=(), project=None, session=None):
        super().__init__(parent)
        self.request, self.context, self.started, self.stopped, self.remembered = request, context, False, False, []
        self.servers, self.project = list(servers), project
        FakeTask.created.append(self)

    def start(self):
        self.started = True

    def stop(self, report="You stopped the task, so I left things as they were at that moment."):
        self.stopped = True
        self.finished.emit(report, False)

    def remember_approval(self, request):
        self.remembered.append(request.tool)


class FakeRequest:
    def __init__(self, tool):
        self.tool, self.values, self.answers = tool, {"command": "dir"}, []
        self.summary = describe(tool, self.values)

    def answer(self, allow, message=""):
        self.answers.append(allow)


class WindowTaskTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = application()

    def setUp(self):
        from companion.ui.window import CompanionWindow
        FakeTask.created = []
        self.patch = patch("companion.tasks.runner.ComputerTask", FakeTask)
        self.patch.start()
        import tempfile
        self.undo_folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.undo_folder.cleanup)
        undo_root = patch("companion.tasks.runner.UNDO_ROOT", Path(self.undo_folder.name))
        undo_root.start()
        self.addCleanup(undo_root.stop)
        self.window = CompanionWindow(SETTINGS)

    def tearDown(self):
        self.patch.stop()
        self.window.request_quit()
        self.window.deleteLater()
        self.app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.app.processEvents()

    def test_do_command_runs_a_task_and_its_report_is_saved_and_shown(self):
        self.window.input.setPlainText("/do tidy my Downloads folder")
        self.window._send()
        task = FakeTask.created[0]
        self.assertTrue(task.started)
        self.assertEqual(task.request, "tidy my Downloads folder")
        self.assertTrue(self.window.stop_button.isEnabled())
        task.step.emit("Look for files: Downloads/*")
        task.finished.emit("I sorted your Downloads into three folders.", True)
        text = self.window.transcript.toPlainText()
        self.assertIn("Look for files: Downloads/*", text)
        self.assertIn("I sorted your Downloads into three folders.", text)
        self.assertEqual(self.window.store.messages(self.window._conversation_id)[-1]["display"],
                         "I sorted your Downloads into three folders.")
        self.assertIsNone(self.window._task)

    def test_task_cue_carries_her_description_and_never_reaches_the_avatar(self):
        shown = []
        with patch.object(self.window.avatar, "cue", side_effect=shown.append):
            self.window._queue_cues([(0, "task:Create the folder Desktop/Trips"), (5, "smile")])
        self.assertEqual(self.window._task_request, "Create the folder Desktop/Trips")
        self.assertEqual(shown, ["smile"])

    def test_an_offer_waits_for_yes_and_then_starts_exactly_that_plan(self):
        self.window._show_offer("Sort Downloads into Images, Documents and Installers; leave other files.")
        card = self.window._offer_card
        self.assertTrue(card.open)
        self.assertEqual(FakeTask.created, [])  # Nothing happens before the person agrees.
        card.yes.click()
        self.assertFalse(card.open)
        self.assertEqual(FakeTask.created[0].request,
                         "Sort Downloads into Images, Documents and Installers; leave other files.")
        self.assertIn("Yes, do it.", self.window.transcript.toPlainText())
        FakeTask.created[0].finished.emit("Done: 42 files sorted.", True)
        self.assertEqual(self.window.store.messages(self.window._conversation_id)[-1]["display"], "Done: 42 files sorted.")

    def test_answering_in_words_closes_the_buttons_and_not_now_is_said_in_chat(self):
        self.window._show_offer("Rename the screenshots by date.")
        first = self.window._offer_card
        sent = []
        with patch.object(type(self.window), "_send", lambda window: sent.append(window.input.toPlainText())):
            first.no.click()
        self.assertEqual(sent, ["Not now, thank you."])
        self.assertFalse(first.open)
        self.window._show_offer("Rename the screenshots by date.")
        second = self.window._offer_card
        # A changed plan goes to her (stopped here before any network request).
        with patch.object(Settings, "validate_connection", side_effect=ValueError("offline test")),                 patch("companion.ui.window.QMessageBox.information"):
            self.window.input.setPlainText("yes, but only this month's")
            self.window._send()
        self.assertFalse(second.open)
        self.assertEqual(FakeTask.created, [])

    def test_a_spoken_or_typed_plain_yes_starts_the_offer_without_another_reply(self):
        self.window._show_offer("Open Notepad and type a shopping list: tea, mooncakes.")
        self.window.input.setPlainText("Yeah, go ahead please")  # What a transcript of "yeah go ahead please" sends.
        self.window._send()
        self.assertEqual(FakeTask.created[0].request, "Open Notepad and type a shopping list: tea, mooncakes.")
        self.assertIn("Yeah, go ahead please", self.window.transcript.toPlainText())
        self.assertIsNone(self.window._worker)  # No model reply was needed to start.

    def test_denied_steps_are_shown_and_stop_cancels_the_task(self):
        from companion.ui.approval import ApprovalDialog
        self.window._start_task("Rename my photos", None, "")
        task = FakeTask.created[0]
        request = FakeRequest("PowerShell")
        with patch.object(ApprovalDialog, "open", lambda dialog: dialog._choose("deny")):
            task.approval.emit(request)
        self.assertEqual(request.answers, [False])
        self.assertIn("Not allowed: Run a command: dir", self.window.transcript.toPlainText())
        request = FakeRequest("PowerShell")
        with patch.object(ApprovalDialog, "open", lambda dialog: dialog._choose("task")):
            task.approval.emit(request)
        self.assertEqual((request.answers, task.remembered), ([True], ["PowerShell"]))
        self.window._stop()
        self.assertTrue(task.stopped)
        self.assertIn("Stopped", self.window.transcript.toPlainText())

    def test_the_avatar_works_through_the_task_with_her(self):
        shown = []
        with patch.object(self.window.avatar, "work", side_effect=lambda state, text="": shown.append(state)):
            self.window._start_task("Sort my screenshots", None, "")
            task = FakeTask.created[0]
            task.step.emit("Look for files: Desktop/*.png")
            task.step.emit("Run a command: New-Item Screenshots")
            task.finished.emit("Sorted.", True)
        self.assertEqual(shown, ["start", "read", "command", "done"])

    def test_a_finished_task_can_be_undone_from_its_card_or_with_slash_undo(self):
        import tempfile
        from PySide6.QtWidgets import QMessageBox
        from companion.tasks.journal import Journal
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        work = Path(folder.name) / "Downloads"
        work.mkdir()
        (work / "a.png").write_text("a", encoding="utf-8")
        self.window.input.setPlainText("/do sort my downloads")
        self.window._send()
        task = FakeTask.created[0]
        task.journal = Journal(Path(folder.name) / "journal")
        task.journal.move(work / "a.png", task.journal.make_folder(work / "Pictures"))
        task.journal.note("command", "Get-ChildItem")
        task.finished.emit("Sorted.", True)
        card = self.window._task_card
        self.assertTrue(card.undo_button.isVisibleTo(card))
        asked = []
        with patch("companion.ui.inline.InlineBar.ask",
                   side_effect=lambda text, action, on_yes, *a, **k: (asked.append(text), on_yes())):
            card.undo_button.click()
        self.assertIn("move 1 item back", asked[0])
        self.assertIn("cannot reverse 1 command", asked[0])
        self.assertEqual([p.name for p in work.iterdir()], ["a.png"])  # Moved back, empty folder removed.
        self.assertEqual(card.status_text, "Undone")
        self.assertFalse(card.undo_button.isVisibleTo(card))
        self.assertIn("Undid the task", self.window.transcript.toPlainText())
        self.assertIn("[Task undone by the person]", self.window._messages[-1]["content"])
        self.window.input.setPlainText("/undo")
        self.window._send()
        self.assertIn("no recent task with changes to undo", self.window.transcript.toPlainText())

    def saved_task(self, request="Sort the screenshots"):
        """A finished task from an earlier session, as it is left on disk."""
        from companion.tasks.journal import Journal
        work = Path(self.undo_folder.name) / "work"
        work.mkdir(exist_ok=True)
        (work / "shot.png").write_text("x", encoding="utf-8")
        journal = Journal(Path(self.undo_folder.name) / "20261024-090000-abc123")
        journal.describe_task(request=request, started=1.0)
        journal.move(work / "shot.png", journal.make_folder(work / "Screenshots"))
        journal.describe_task(finished=__import__("time").time(), succeeded=True, report="Done.")
        return work, journal

    def test_after_a_restart_slash_undo_and_her_cue_find_the_saved_task(self):
        from PySide6.QtWidgets import QMessageBox
        work, journal = self.saved_task()
        asked = []
        with patch("companion.ui.inline.InlineBar.ask",
                   side_effect=lambda text, action, on_yes, *a, **k: (asked.append(text), on_yes())):
            self.window._queue_cues([(0, "undotask")])  # "Undo that" in conversation.
            self.window._apply_memory_actions()
            self.app.processEvents()
        self.assertIn("Task: Sort the screenshots", asked[0])
        self.assertTrue((work / "shot.png").exists())
        self.assertTrue(journal.undone)
        self.window.input.setPlainText("/undo")
        self.window._send()
        self.assertIn("no recent task with changes to undo", self.window.transcript.toPlainText())

    def test_recent_tasks_dialog_lists_and_undoes(self):
        from PySide6.QtWidgets import QMessageBox, QPushButton
        from companion.ui.library import TasksDialog
        work, journal = self.saved_task("Tidy the desktop")
        dialog = TasksDialog(Path(self.undo_folder.name), self.window)
        self.assertEqual(dialog.items.count(), 1)
        row = dialog.items.itemWidget(dialog.items.item(0))
        self.assertIn("move 1 item back", row.findChildren(type(dialog.empty))[1].text())
        dialog.undo_requested.connect(lambda j: self.window._undo_task(None, j) or dialog.refresh())
        with patch("companion.ui.inline.InlineBar.ask", side_effect=lambda text, action, on_yes, *a, **k: on_yes()):
            row.findChild(QPushButton).click()
        self.assertTrue((work / "shot.png").exists())
        self.assertEqual(dialog.items.count(), 1)  # Still listed, now marked Undone without a button.
        row = dialog.items.itemWidget(dialog.items.item(0))
        self.assertIsNone(row.findChild(QPushButton))
        dialog.deleteLater()

    def test_tasks_can_be_turned_off(self):
        self.window.computer_tasks.setChecked(False)
        self.window.input.setPlainText("/do something")
        self.window._send()
        self.assertEqual(FakeTask.created, [])
        self.assertIn("turned off", self.window.transcript.toPlainText())
