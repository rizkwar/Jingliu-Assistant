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

from companion import computer_tasks, task_tools
from companion.computer_tasks import ApprovalServer, ComputerTask, FREE_TOOLS, approval_group, describe
from companion.config import DEFAULT_MODEL, Settings
from qt_test_support import application

ROOT = Path(__file__).resolve().parent.parent
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
        output = subprocess.run([sys.executable, "-m", "companion.task_tools"], cwd=ROOT, capture_output=True, text=True,
                                input="".join(json.dumps(m) + "\n" for m in messages), timeout=60).stdout
        replies = [json.loads(line) for line in output.splitlines()]
        self.assertEqual([r["id"] for r in replies], [1, 2, 3])
        self.assertEqual(replies[0]["result"]["protocolVersion"], "2025-06-18")
        names = {tool["name"] for tool in replies[1]["result"]["tools"]}
        self.assertEqual(names, {"approve", "screenshot", "click", "type_text", "press_keys", "scroll", "wait"})
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

    def __init__(self, request, context, settings, parent=None):
        super().__init__(parent)
        self.request, self.context, self.started, self.stopped, self.remembered = request, context, False, False, []
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
        from companion.ui import CompanionWindow
        FakeTask.created = []
        self.patch = patch("companion.computer_tasks.ComputerTask", FakeTask)
        self.patch.start()
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
        with patch.object(Settings, "validate_connection", side_effect=ValueError("offline test")),                 patch("companion.ui.QMessageBox.information"):
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
        from companion.approval_ui import ApprovalDialog
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

    def test_tasks_can_be_turned_off(self):
        self.window.computer_tasks.setChecked(False)
        self.window.input.setPlainText("/do something")
        self.window._send()
        self.assertEqual(FakeTask.created, [])
        self.assertIn("turned off", self.window.transcript.toPlainText())
