"""In the window: replies continue the conversation's session, and background work is light."""

from dataclasses import replace
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent

from companion.core.storage import Store
from companion.ui.window import CompanionWindow
from tests.python.chat.test_claude_backend import Process, delta, result
from tests.python.ui.test_ui import SETTINGS, FakeMicrophone, FakeSpeech
from tests.qt_test_support import application


class SessionWindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = application()

    def setUp(self):
        self.home = tempfile.TemporaryDirectory()
        self.addCleanup(self.home.cleanup)
        for patcher in (patch.dict(os.environ, {"CLAUDE_CONFIG_DIR": self.home.name}),
                        patch("companion.chat.claude.run", self.fake_run),
                        patch("companion.chat.claude.claude_executable", lambda: "claude")):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.commands, self.sent, self.before = [], [], []  # `before`: events ahead of her reply (reading files).
        self.store = Store(":memory:")
        self.window = CompanionWindow(replace(SETTINGS, llm_provider="claude", claude_model="claude-sonnet-5-5"),
                                      speech=FakeSpeech(), microphone=FakeMicrophone(), store=self.store)

    def tearDown(self):
        self.window.close()
        self.window.deleteLater()
        self.app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.app.processEvents()

    async def fake_run(self, command, stdin_text=None, cwd=None):
        self.commands.append(command)
        if "--session-id" in command:  # Claude Code keeps the new session's transcript.
            path = Path(self.home.name) / "projects" / "app" / f"{command[command.index('--session-id') + 1]}.jsonl"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("{}", encoding="utf-8")
        process = Process([*self.before, delta("Hm."), result(usage={
            "input_tokens": 3, "cache_creation_input_tokens": 400, "cache_read_input_tokens": 9000, "output_tokens": 20})])
        original = process.stdin.write
        process.stdin.write = lambda data: (self.sent.append(data), original(data))
        return process

    def send(self, text):
        self.window.input.setPlainText(text)
        self.window._send()
        deadline = time.monotonic() + 5
        while self.window._worker is not None and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(.005)
        self.assertIsNone(self.window._worker)
        return json.loads(self.sent[-1].decode())["message"]["content"][0]["text"]

    def test_the_second_reply_continues_the_session_with_only_the_new_message(self):
        first = self.send("Hello")
        self.assertIn("--session-id", self.commands[-1])
        self.assertTrue(first.startswith("<app_context>"))
        row = self.store.chat_session(self.window._conversation_id)
        self.assertEqual(row["size"], 9423)
        second = self.send("How are you today?")
        command = self.commands[-1]
        self.assertEqual(command[command.index("--resume") + 1], row["session_id"])
        self.assertNotIn("Hello", second)  # The session already has it.
        self.assertTrue(second.endswith("How are you today?"))
        self.assertEqual(self.store.chat_session(self.window._conversation_id)["turns"], 2)
        # Deleting the conversation ends the session and deletes its transcript.
        transcript = next((Path(self.home.name) / "projects").glob(f"*/{row['session_id']}.jsonl"))
        self.window._remove_conversation(self.window._conversation_id, True)
        self.assertFalse(transcript.exists())

    def test_reminders_out_of_view_and_summaries_use_haiku(self):
        self.assertEqual(self.window._light_model(), {"claude_model": "claude-haiku-5-5"})
        self.window.settings = replace(self.window.settings, llm_provider="codex")
        self.assertEqual(self.window._light_model(), {})

    def test_coding_mode_is_on_in_projects_and_can_be_chosen_for_any_chat(self):
        window = self.window
        self.assertFalse(window.coding_chip.isChecked())  # A plain chat.
        project = self.store.create_project("Carbon sense")
        in_project = self.store.create_conversation("")
        self.store.set_conversation_project(in_project, project)
        window._switch_conversation(in_project)
        self.assertTrue(window.coding_chip.isChecked())  # On by itself in a project.
        window.coding_chip.click()
        self.assertFalse(window._coding_on())  # Your choice wins and is kept.
        plain = self.store.create_conversation("")
        window._switch_conversation(plain)
        window.coding_chip.click()
        window._switch_conversation(in_project)
        window._switch_conversation(plain)
        self.assertTrue(window.coding_chip.isChecked())
        window.settings = replace(window.settings, llm_provider="codex")
        window._refresh_coding_chip()
        self.assertFalse(window.coding_chip.isEnabled())  # It needs Claude Code.
        self.assertFalse(window._coding_on())

    def test_in_coding_mode_she_reads_files_herself_and_the_note_gathers_them(self):
        self.store.set_coding(self.window._conversation_id, True)
        self.before = [{"type": "assistant", "message": {"content": [
            {"type": "tool_use", "name": "Read", "input": {"file_path": "C:/carbon/tracker/views.py"}},
            {"type": "tool_use", "name": "Grep", "input": {"pattern": "asset_version"}}]}}]
        self.send("Explain the tracker views")
        command = self.commands[-1]
        self.assertEqual(command[command.index("--tools") + 1], "Read,Grep,Glob")
        self.assertIn("--add-dir", command)
        self.assertIn("Looked at views.py, searched “asset_version”", self.window.transcript.toPlainText())
        plain = self.store.create_conversation("")
        self.window._switch_conversation(plain)
        self.before = []
        self.send("Hello")
        self.assertEqual(self.commands[-1][self.commands[-1].index("--tools") + 1], "")  # No tools in a plain chat.

    def test_a_long_session_is_compacted_into_the_notes(self):
        chat = self.window._conversation_id
        for index in range(20):  # Older exchanges, beyond what a reply sends.
            turn = self.store.start_turn(chat, f"Earlier question {index}")
            self.store.save_turn(turn, f"Earlier answer {index}", f"Earlier answer {index}", "complete")
        self.window._restore_conversation(chat)
        with patch("companion.chat.sessions.COMPACT_TOKENS", 5000):
            self.send("Where were we?")
            deadline = time.monotonic() + 5
            while (self.window._compactor is not None or self.store.summary(chat) is None) and time.monotonic() < deadline:
                self.app.processEvents()
                time.sleep(.005)
        self.assertEqual(self.store.summary(chat)["content"], "Hm.")  # Written on Haiku, as her notes.
        self.assertIn("--model", self.commands[-1])
        self.assertEqual(self.commands[-1][self.commands[-1].index("--model") + 1], "claude-haiku-5-5")
        self.assertIsNone(self.store.chat_session(chat))  # The next reply starts from the notes.
        self.assertIn("Compacted 9 older exchanges", self.window.transcript.toPlainText())  # 21 exchanges, 12 kept.

    def test_a_task_continues_the_chat_session_and_typing_while_she_works_steers_her(self):
        from tests.python.tasks.test_computer_tasks import FakeTask

        class SteeredTask(FakeTask):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.session, self.reported, self.context_size, self.heard = kwargs.get("session"), True, 30_000, []

            def steer(self, text):
                self.heard.append(text)
        FakeTask.created = []
        self.send("Hello")
        session = self.store.chat_session(self.window._conversation_id)["session_id"]
        with patch("companion.tasks.runner.ComputerTask", SteeredTask):
            self.window.input.setPlainText("/do tidy my notes")
            self.window._send()
            task = FakeTask.created[0]
            self.assertEqual((task.session["id"], task.session["resume"]), (session, True))  # One mind.
            self.window.input.setPlainText("use the PDF folder too")
            self.window._send()  # Typed while she works: it reaches her, not a separate reply.
            self.assertEqual(task.heard, ["use the PDF folder too"])
            task.finished.emit("Tidied your notes.", True)
        row = self.store.chat_session(self.window._conversation_id)
        self.assertEqual((row["session_id"], row["size"]), (session, 30_000))  # The session now holds the task.
        self.send("What did you do?")
        command = self.commands[-1]
        self.assertEqual(command[command.index("--resume") + 1], session)
        self.assertNotIn("Tidied your notes", json.loads(self.sent[-1].decode())["message"]["content"][0]["text"])


if __name__ == "__main__":
    unittest.main()
