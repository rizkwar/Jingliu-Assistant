"""Usage: limits as each service reports them, tokens per reply, and the numbers the Usage page shows."""

from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from companion.chat import usage
from companion.chat.llm import stream_reply
from companion.core.storage import Store
from tests.python.chat.test_claude_backend import SETTINGS as CLAUDE, Process, delta, result
from tests.python.chat.test_codex_backend import SETTINGS as CODEX, Connection, event


class LimitTests(unittest.TestCase):
    def test_claude_windows_are_percent_left_in_a_fixed_order(self):
        windows = usage.claude_windows({"status": "allowed", "unifiedWindows": {
            "seven_day": {"utilization": 0.02, "resetsAt": 200, "status": "allowed"},
            "five_hour": {"utilization": 0.38, "resetsAt": 100, "status": "allowed"}}})
        self.assertEqual([w["label"] for w in windows], ["Session · 5 hours", "This week"])
        self.assertAlmostEqual(windows[0]["left"], 62.0)
        self.assertEqual(windows[0]["resets_at"], 100)
        self.assertFalse(windows[0]["blocked"])

    def test_a_rejected_claude_report_without_windows_still_says_the_limit_is_reached(self):
        windows = usage.claude_windows({"status": "rejected", "rateLimitType": "five_hour", "resetsAt": 100})
        self.assertEqual(windows[0]["left"], 0.0)
        self.assertTrue(windows[0]["blocked"])

    def test_codex_windows_are_named_by_their_length(self):
        windows = usage.codex_windows({"primary": {"usedPercent": 30, "windowDurationMins": 300, "resetsAt": 5},
                                       "secondary": {"usedPercent": 100, "windowDurationMins": 10080}})
        self.assertEqual([(w["label"], w["left"]) for w in windows], [("Session · 5 hours", 70.0), ("This week", 0.0)])
        self.assertTrue(windows[1]["blocked"])

    def test_openrouter_shows_the_balance_of_a_key_or_the_account(self):
        [key] = usage.openrouter_windows({"limit": 10, "limit_remaining": 4.2})
        self.assertEqual(key["detail"], "$4.20 left of $10.00")
        self.assertAlmostEqual(key["left"], 42.0)
        [account] = usage.openrouter_windows({"limit": None}, {"total_credits": 20, "total_usage": 15})
        self.assertAlmostEqual(account["left"], 25.0)
        self.assertEqual(usage.openrouter_windows({}, {}), [])

    def test_a_window_whose_reset_has_passed_is_full_again(self):
        moment = datetime(2026, 10, 28, 12)
        windows = [{"key": "a", "left": 3.0, "resets_at": moment.timestamp() - 1, "blocked": True},
                   {"key": "b", "left": 40.0, "resets_at": moment.timestamp() + 60}]
        now = usage.current(windows, moment)
        self.assertEqual((now[0]["left"], now[0]["blocked"]), (100.0, False))
        self.assertEqual(now[1]["left"], 40.0)
        self.assertEqual(usage.least_left(now)["key"], "b")

    def test_limits_are_kept_per_service_and_empty_reports_change_nothing(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "limits.json"
            usage.save_limits("claude", [{"key": "five_hour", "left": 50.0}], path)
            usage.save_limits("claude", [], path)
            usage.save_limits("codex", [{"key": "primary", "left": 10.0}], path)
            usage.save_limits("somewhere", [{"key": "x", "left": 1.0}], path)
            data = usage.load_limits(path)
            self.assertEqual(set(data), {"claude", "codex"})
            self.assertEqual(data["claude"]["windows"][0]["left"], 50.0)
            path.write_text("not json", encoding="utf-8")
            self.assertEqual(usage.load_limits(path), {})

    def test_reset_times_and_counts_read_naturally(self):
        moment = datetime(2026, 10, 28, 13, 26)
        self.assertEqual(usage.until(datetime(2026, 10, 28, 15, 40).timestamp(), moment), "resets 15:40 (in 2 h 14 min)")
        self.assertEqual(usage.until(datetime(2026, 10, 29, 8, 0).timestamp(), moment), "resets 08:00 (in 18 h 34 min)")
        self.assertEqual(usage.until(datetime(2026, 11, 2, 8, 0).timestamp(), moment), "resets Monday 08:00")
        self.assertEqual(usage.until(datetime(2026, 10, 30, 14, 0).timestamp(), moment), "resets Friday 14:00")
        self.assertEqual([usage.short(n) for n in (937, 48210, 21000, 1_250_000)], ["937", "48.2k", "21k", "1.2M"])
        self.assertEqual(usage.model_name("claude-opus-5-5"), "Opus")
        self.assertEqual(usage.model_name("openai/gpt-6"), "gpt-6")


class TokenTests(unittest.TestCase):
    def setUp(self):
        self.store = Store(":memory:")
        self.calculus = self.store.create_conversation()
        self.store.rename_conversation(self.calculus, "Calculus study")
        self.other = self.store.create_conversation()
        self.store.rename_conversation(self.other, "Random Stuff")

    def test_replies_are_counted_by_day_today_and_chat(self):
        self.store.record_usage(self.calculus, "claude", "claude-sonnet-5-5", 1000, 200, 300)
        self.store.record_usage(self.calculus, "claude", "claude-opus-5-5", 100, 50, 0)
        self.store.record_usage(self.other, "claude", "claude-sonnet-5-5", 400, 100, 0)
        self.store.record_usage(self.other, "claude", "claude-sonnet-5-5", 0, 0, 0)  # Nothing to keep.
        rows = self.store.usage_since(datetime.now(timezone.utc) - timedelta(days=1))
        self.assertEqual(len(rows), 3)
        self.assertNotIn("content", rows[0])  # Counts only, never the conversation's words.
        today = usage.today(rows)
        self.assertEqual((today["total"], today["replies"], today["output"]), (2150, 3, 350))
        days = usage.daily(rows)
        self.assertEqual(len(days), 14)
        self.assertEqual(days[-1][1], {"input": 1500, "output": 350, "cached": 300})
        self.assertEqual(days[0][1], {"input": 0, "output": 0, "cached": 0})
        chats = usage.by_conversation(rows)
        self.assertEqual([(c["title"], c["tokens"], c["model"]) for c in chats],
                         [("Calculus study", 1650, "Sonnet"), ("Random Stuff", 500, "Sonnet")])

    def test_a_deleted_chat_keeps_its_count_without_its_name(self):
        self.store.record_usage(self.other, "codex", "gpt-6", 10, 5, 0)
        self.store.delete_conversation(self.other)
        rows = self.store.usage_since(datetime.now(timezone.utc) - timedelta(days=1))
        self.assertEqual(usage.by_conversation(rows)[0]["title"], "A deleted chat")


class StreamReportTests(unittest.IsolatedAsyncioTestCase):
    async def test_claude_reports_its_windows_and_the_reply_tokens(self):
        lines = [{"type": "rate_limit_event", "rate_limit_info": {"status": "allowed", "unifiedWindows": {
                     "five_hour": {"utilization": 0.25, "resetsAt": 100, "status": "allowed"}}}},
                 delta("Hm."),
                 result(usage={"input_tokens": 2, "cache_creation_input_tokens": 1000, "cache_read_input_tokens": 500,
                               "output_tokens": 40})]
        process = Process(lines)

        async def fake_run(command, stdin_text=None, cwd=None):
            return process
        with patch("companion.chat.claude.run", fake_run), patch("companion.chat.claude.claude_executable", lambda: "claude"):
            parts = [part async for part in stream_reply(None, CLAUDE, [{"role": "user", "content": "Hi"}])]
        self.assertEqual(parts[0]["limits"][0]["left"], 75.0)
        self.assertEqual(parts[1], "Hm.")
        self.assertEqual(parts[2], {"usage": {"model": "sonnet", "input": 1002, "output": 40, "cached": 500}})

    async def test_codex_reports_its_windows_and_the_turn_tokens(self):
        connection = Connection([
            event("account/rateLimits/updated", rateLimits={"primary": {"usedPercent": 12, "windowDurationMins": 300}}),
            event("item/completed", item={"type": "agentMessage", "id": "answer", "text": "Answer."}),
            event("thread/tokenUsage/updated", turnId="t", tokenUsage={"total": {
                "inputTokens": 900, "cachedInputTokens": 600, "outputTokens": 30, "reasoningOutputTokens": 0,
                "totalTokens": 930}, "last": {}}),
            event("turn/completed", turn={"status": "completed"})])

        @asynccontextmanager
        async def fake_server():
            yield connection, "empty-workspace"
        with patch("companion.chat.codex.server", fake_server):
            parts = [part async for part in stream_reply(None, CODEX, [{"role": "user", "content": "Hi"}])]
        self.assertEqual(parts[0]["limits"][0]["left"], 88.0)
        self.assertEqual(parts[1], "Answer.")
        self.assertEqual(parts[2], {"usage": {"model": "chosen-model", "cached": 600, "input": 300, "output": 30}})


if __name__ == "__main__":
    unittest.main()
