"""A task never sits stuck: live progress, a watchdog for loops and silences, and steering mid-task."""

from dataclasses import replace
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from companion.tasks import runner
from companion.tasks.runner import ComputerTask
from tests.python.tasks.test_computer_tasks import SETTINGS, FakeRequest
from tests.qt_test_support import application


def tool(name, index, **values):
    return {"type": "assistant", "message": {"content": [{"type": "tool_use", "id": f"t{index}", "name": name,
                                                          "input": values}]}}


def done(index):
    return {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": f"t{index}"}]}}


class WatchdogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = application()

    def setUp(self):
        self.undo = tempfile.TemporaryDirectory()
        self.addCleanup(self.undo.cleanup)
        patcher = patch("companion.tasks.runner.UNDO_ROOT", Path(self.undo.name))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.task = ComputerTask("Tidy my notes", [], SETTINGS)
        self.addCleanup(self.task.folder.cleanup)
        self.sent, self.steps, self.live, self.finished = [], [], [], []
        self.task._write = self.sent.append
        self.task.step.connect(self.steps.append)
        self.task.activity.connect(self.live.append)
        self.task.finished.connect(lambda report, ok: self.finished.append((report, ok)))
        self.task.process.kill = lambda: None

    def messages(self):
        return [part["message"]["content"][0]["text"] for part in self.sent if part.get("type") == "user"]

    def interrupts(self):
        return [part for part in self.sent if part.get("type") == "control_request"]

    def test_the_run_streams_both_ways_with_the_chosen_task_effort(self):
        task = ComputerTask("Tidy", [], replace(SETTINGS, task_effort="high"))
        arguments = task.process.arguments()
        self.assertEqual(arguments[arguments.index("--input-format") + 1], "stream-json")
        self.assertIn("--include-partial-messages", arguments)
        self.assertEqual(arguments[arguments.index("--effort") + 1], "high")
        task.folder.cleanup()

    def test_the_same_step_three_times_is_steered_then_wrapped_up_then_stopped(self):
        for index in range(3):
            self.task._handle(tool("Read", index, file_path="C:/notes/a.md"))
            self.task._handle(done(index))
        self.assertEqual(len(self.interrupts()), 1)  # Interrupted, not killed.
        self.assertIn("Seemed stuck, so trying another way", self.steps)
        self.task._handle({"type": "result", "subtype": "error_during_execution", "result": ""})
        self.assertFalse(self.finished)  # The interrupted turn is not the end of the task.
        self.assertIn("same step three times", self.messages()[-1])
        self.assertIn("Read C:/notes/a.md", self.messages()[-1])
        for index in range(3, 6):
            self.task._handle(tool("Glob", index, pattern="*.md"))
        self.task._handle({"type": "result", "subtype": "success", "result": ""})
        self.assertIn("Stop working now", self.messages()[-1])
        self.assertFalse(self.finished)
        self.task.wrap_up_at = time.monotonic() - 1  # She never wrote the report.
        self.task._watch()
        self.assertEqual(len(self.finished), 1)
        report, ok = self.finished[0]
        self.assertFalse(ok)
        self.assertIn("I got stuck", report)
        saved = json.loads((self.task.journal.folder / "task.json").read_text(encoding="utf-8"))
        self.assertEqual(saved["stuck"], 2)
        self.assertTrue(any("Seemed stuck" in text for _, text in saved["steps"]))

    def test_waiting_and_looking_over_and_over_is_a_loop(self):
        for index in range(10):
            name = "mcp__jingliu__wait" if index % 2 else "mcp__jingliu__screenshot"
            self.task._handle(tool(name, index, **({"seconds": index} if index % 2 else {})))
        self.assertIn("waiting and looking at the screen", self.task.queued)

    def test_reading_one_file_again_and_again_is_noticed(self):
        for index in range(7):
            if index % 2:
                self.task._handle(tool("Grep", index, pattern=f"x{index}"))
            else:
                self.task._handle(tool("Read", index, file_path="C:/big.py", offset=index))
        self.assertIn("read C:/big.py four times", self.task.queued)

    def test_silence_and_a_hung_step_are_noticed_but_waiting_for_you_is_not(self):
        request = FakeRequest("PowerShell")
        request.answered = False
        self.task.pending = [request]
        self.task.last_event = time.monotonic() - runner.QUIET_SECONDS - 5
        self.task._watch()
        self.assertEqual(self.interrupts(), [])  # She is waiting for the person's Allow.
        request.answered = True
        self.task.last_event = time.monotonic() - runner.QUIET_SECONDS - 5
        self.task._watch()
        self.assertIn("nothing has happened", self.task.queued)
        task = ComputerTask("Build", [], SETTINGS)
        task._write = lambda payload: None
        task.running["t1"] = (time.monotonic() - runner.LONG_STEP_SECONDS - 1, "Run a command: npm run dev")
        task._watch()
        self.assertIn('"Run a command: npm run dev" has been running', task.queued)
        task.folder.cleanup()

    def test_what_you_say_reaches_her_or_declines_the_step_waiting_for_you(self):
        self.task.steer("use the venv python")
        self.assertEqual(len(self.interrupts()), 1)
        self.task._handle({"type": "result", "subtype": "error_during_execution", "result": ""})
        self.assertIn("The user says, while you work: use the venv python", self.messages()[-1])
        request = FakeRequest("PowerShell")
        request.answered = False
        original = request.answer

        def answer(allow, message=""):
            request.answered = True
            request.message = message
            original(allow, message)
        request.answer = answer
        self.task._approval(request)
        self.task.steer("skip the PDFs")
        self.assertEqual(request.answers, [False])
        self.assertIn("skip the PDFs", request.message)
        self.assertEqual(len(self.interrupts()), 1)  # Declining the step was enough.

    def test_live_progress_between_steps(self):
        self.task._handle({"type": "stream_event", "event": {"type": "content_block_start",
                                                            "content_block": {"type": "thinking"}}})
        self.task._handle({"type": "stream_event", "event": {"type": "content_block_start",
                                                            "content_block": {"type": "tool_use", "name": "Write"}}})
        self.task.last_live = 0
        self.task._handle({"type": "stream_event", "event": {"type": "content_block_delta", "delta": {
            "type": "input_json_delta", "partial_json": '{"file_path": "C:\\\\notes\\\\plan.md", "content": "a\\nb\\nc'}}})
        self.assertEqual(self.live[0], "Thinking…")
        self.assertEqual(self.live[-1], "Writing plan.md · 3 lines…")

    def test_a_finished_report_ends_the_task_and_keeps_its_steps(self):
        self.task._handle(tool("Glob", 1, pattern="*.md"))
        self.task._handle({"type": "result", "subtype": "success", "result": "Done, all tidy."})
        self.assertEqual(self.finished, [("Done, all tidy.", True)])
        saved = json.loads((self.task.journal.folder / "task.json").read_text(encoding="utf-8"))
        self.assertEqual(saved["steps"][-1][1], "Look for files: *.md")


if __name__ == "__main__":
    unittest.main()
