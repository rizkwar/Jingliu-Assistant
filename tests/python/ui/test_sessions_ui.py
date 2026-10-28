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
        self.commands, self.sent = [], []
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
        process = Process([delta("Hm."), result(usage={"input_tokens": 3, "cache_creation_input_tokens": 400,
                                                       "cache_read_input_tokens": 9000, "output_tokens": 20})])
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


if __name__ == "__main__":
    unittest.main()
