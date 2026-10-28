"""Effort: a fixed level or Auto, carried to every service, with background work kept light."""

from contextlib import asynccontextmanager
from dataclasses import replace
import json
import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import httpx
from PySide6.QtCore import QEvent, QObject, Signal

from companion.chat import effort
from companion.chat.claude import reply_command
from companion.chat.llm import ChatError, stream_reply
from companion.core.preferences import validate
from tests.python.chat.test_codex_backend import SETTINGS as CODEX, Connection, event
from tests.python.chat.test_llm import SETTINGS as OPENROUTER
from tests.qt_test_support import application


class ChoiceTests(unittest.TestCase):
    def test_auto_keeps_small_talk_light_and_thinks_for_real_work(self):
        self.assertEqual(effort.choose("hi, how was your day?"), "low")
        self.assertEqual(effort.choose("Good night, Jingliu"), "low")
        self.assertEqual(effort.choose("Can you explain why my SQL query returns duplicates?"), "medium")
        self.assertEqual(effort.choose("```python\nprint(1)\n```"), "medium")
        self.assertEqual(effort.choose("what is $\\frac{a}{b}$"), "medium")
        self.assertEqual(effort.choose("look at this", attachments=[{"kind": "pdf"}]), "medium")
        self.assertEqual(effort.choose("next one", study=True), "medium")
        self.assertEqual(effort.choose("Codeforces 2277C: 1 ≤ n ≤ 2·10^5, time limit 2 seconds"), "high")
        self.assertEqual(effort.choose("Think carefully about this proof"), "high")

    def test_a_fixed_level_is_kept_and_each_service_gets_its_own_word_for_it(self):
        self.assertEqual(effort.resolve("xhigh", "hi"), "xhigh")
        self.assertEqual(effort.resolve("auto", "hi"), "low")
        self.assertEqual(effort.resolve("nonsense", "explain this"), "medium")
        self.assertEqual([effort.claude(level) for level in ("low", "max", "auto")], ["low", "max", "low"])
        self.assertEqual(effort.codex("max"), "xhigh")
        self.assertEqual(effort.openrouter("low"), {"enabled": False, "exclude": True})
        self.assertEqual(effort.openrouter("xhigh"), {"effort": "high", "exclude": True})

    def test_saved_effort_is_checked(self):
        self.assertEqual(validate({"effort": "high", "task_effort": "max"}), {"effort": "high", "task_effort": "max"})
        for bad in ({"effort": "extreme"}, {"task_effort": "auto"}):
            with self.assertRaises(ValueError):
                validate(bad)


class ServiceTests(unittest.IsolatedAsyncioTestCase):
    def test_claude_gets_the_effort(self):
        with patch("companion.chat.claude.claude_executable", lambda: "claude"):
            command = reply_command("prompt.txt", "claude-sonnet-5-5", effort="high")
        self.assertEqual(command[command.index("--effort") + 1], "high")

    async def test_codex_gets_the_effort_and_answers_at_its_own_when_a_model_lacks_it(self):
        for refuse in (False, True):
            connection = Connection([event("item/completed", item={"type": "agentMessage", "id": "a", "text": "Hm."}),
                                     event("turn/completed", turn={"status": "completed"})])
            plain = connection.rpc

            async def rpc(method, params, plain=plain, refuse=refuse):
                if method == "turn/start" and refuse and "effort" in params:
                    raise ChatError("unsupported effort")
                return await plain(method, params)
            connection.rpc = rpc

            @asynccontextmanager
            async def fake_server(connection=connection):
                yield connection, "empty"
            with patch("companion.chat.codex.server", fake_server):
                parts = [p async for p in stream_reply(None, replace(CODEX, effort="max"), [{"role": "user", "content": "Hi"}])]
            turns = [params for method, params in connection.calls if method == "turn/start"]
            self.assertEqual(parts, ["Hm."])
            self.assertEqual(turns[-1].get("effort"), None if refuse else "xhigh")

    async def test_openrouter_reasons_only_above_low(self):
        seen = []

        def handler(request):
            seen.append(json.loads(request.content))
            return httpx.Response(200, text='data: {"choices":[{"delta":{"content":"Hi"},"finish_reason":"stop"}]}\n\n'
                                  "data: [DONE]\n\n", headers={"Content-Type": "text/event-stream"})
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            for level in ("low", "high"):
                _ = [p async for p in stream_reply(client, replace(OPENROUTER, effort=level), [{"role": "user", "content": "Hi"}])]
        self.assertEqual(seen[0]["reasoning"], {"enabled": False, "exclude": True})
        self.assertEqual(seen[1]["reasoning"], {"effort": "high", "exclude": True})


class FakeWorker(QObject):
    chunk = Signal(str, str)
    tool_used = Signal(str)
    usage = Signal(dict)
    limits = Signal(list)
    session = Signal(dict)
    finished = Signal()
    made = []

    def __init__(self, settings, messages, parent=None):
        super().__init__(parent)
        self.settings, self.messages, self.turn_id, self.error = settings, messages, "turn", ""
        FakeWorker.made.append(self)

    def start(self):
        pass

    def isRunning(self):
        return False

    def stop(self):
        pass


class WindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = application()

    def setUp(self):
        from companion.ui.window import CompanionWindow
        from tests.python.ui.test_ui import SETTINGS
        FakeWorker.made = []
        self.patch = patch("companion.ui.window.ReplyWorker", FakeWorker)
        self.patch.start()
        self.window = CompanionWindow(replace(SETTINGS, llm_provider="claude"))
        self.window.preferences.remember = lambda settings, fields: None

    def tearDown(self):
        self.patch.stop()
        self.window._worker = None
        self.window.close()
        self.window.deleteLater()
        self.app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.app.processEvents()

    def send(self, text):
        self.window._worker = None
        self.window.input.setPlainText(text)
        self.window._send()
        return FakeWorker.made[-1].settings.effort

    def test_auto_picks_per_message_and_says_so(self):
        self.assertEqual(self.window.effort_picker.text(), "Auto effort")
        self.assertEqual(self.send("hello there"), "low")
        self.assertEqual(self.send("Can you explain how a B-tree splits a node?"), "medium")
        self.assertIn("she chose Medium", self.window.effort_picker.toolTip())
        self.assertIn("medium effort", self.window.status.text())

    def test_a_chosen_level_applies_to_every_reply_and_the_settings_follow(self):
        self.window._choose_effort("effort", "high")
        self.assertEqual(self.window.effort_picker.text(), "High effort")
        self.assertEqual(self.window.reply_effort.currentData(), "high")
        self.assertEqual(self.send("hello there"), "high")
        self.window.task_effort.setCurrentIndex(self.window.task_effort.findData("xhigh"))
        self.assertEqual(self.window.settings.task_effort, "xhigh")
        self.window._fill_effort_menu()
        actions = self.window.effort_menu.actions()
        self.assertEqual([item.text() for item in actions if not item.isEnabled()], ["Replies", "Computer tasks"])
        checked = [item.text() for item in actions if item.isChecked()]
        self.assertEqual(checked, ["High", "Extra high"])  # One for replies, one for tasks.


if __name__ == "__main__":
    unittest.main()
