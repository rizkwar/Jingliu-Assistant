"""Sessions: a conversation continues its Claude Code session, so only what is new is processed."""

from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch

from companion.chat import sessions, usage
from companion.chat.claude import reply_command, resume_turn, user_turn
from companion.core.storage import Store


class SessionTests(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.TemporaryDirectory()
        self.addCleanup(self.home.cleanup)
        environment = patch.dict(os.environ, {"CLAUDE_CONFIG_DIR": self.home.name})
        environment.start()
        self.addCleanup(environment.stop)
        self.store = Store(":memory:")
        self.chat = self.store.create_conversation()

    def transcript(self, session_id, folder="C--data-claude-sessions"):
        path = Path(self.home.name) / "projects" / folder / f"{session_id}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}", encoding="utf-8")
        return path

    def turn(self, text, answer):
        turn = self.store.start_turn(self.chat, text)
        self.store.save_turn(turn, answer, answer, "complete")
        return turn

    def reply(self, text, answer, model="claude-sonnet-5-5", notes=None, size=5000):
        """One reply as the window runs it: plan, answer, record."""
        turns = self.store.context_turns(self.chat)
        session = sessions.plan(self.store, self.chat, turns, model, notes)
        turn = self.turn(text, answer)
        if not session["resume"]:
            self.transcript(session["id"])
        sessions.record(self.store, self.chat, session, model, notes, turn[1], size, first_user_id=turn[0])
        return session

    def test_a_conversation_continues_its_session_and_catches_up_on_what_it_missed(self):
        first = self.reply("Hello", "Hm. You came back.")
        self.assertFalse(first["resume"])
        second = self.reply("How are you?", "Well enough.")
        self.assertEqual((second["resume"], second["id"]), (True, first["id"]))
        self.assertEqual(second["since"], [])
        self.turn("/do tidy my notes", "[Task report] Tidied.")  # Not through the session.
        third = sessions.plan(self.store, self.chat, self.store.context_turns(self.chat), "claude-sonnet-5-5", None)
        self.assertTrue(third["resume"])
        self.assertEqual([m["content"] for m in third["since"]], ["/do tidy my notes", "[Task report] Tidied."])

    def test_it_starts_again_when_the_session_no_longer_matches(self):
        first = self.reply("Hello", "Hm.")
        turns = self.store.context_turns(self.chat)
        reasons = {
            "model": lambda row: sessions.stale(row, turns, "claude-opus-5-5", None),
            "notes": lambda row: sessions.stale(row, turns, "claude-sonnet-5-5", "New notes"),
            "full": lambda row: sessions.stale({**row, "size": sessions.ROTATE_TOKENS + 1}, turns, "claude-sonnet-5-5", None),
            "cold": lambda row: sessions.stale({**row, "size": 20_000}, turns, "claude-sonnet-5-5", None,
                                               moment=datetime.now(timezone.utc) + timedelta(hours=2)),
        }
        row = self.store.chat_session(self.chat)
        for reason, check in reasons.items():
            self.assertEqual(check(row), reason)
        small = {**row, "size": 3000}  # A small session is worth continuing even after the cache expired.
        self.assertEqual(sessions.stale(small, turns, "claude-sonnet-5-5", None,
                                        moment=datetime.now(timezone.utc) + timedelta(hours=2)), "")
        # An edited message: the session ends, transcript and all, and a new one begins.
        self.store.connection.execute("UPDATE messages SET context='Hello there' WHERE role='user'")
        path = sessions.transcripts(first["id"])[0]
        again = sessions.plan(self.store, self.chat, self.store.context_turns(self.chat), "claude-sonnet-5-5", None)
        self.assertFalse(again["resume"])
        self.assertNotEqual(again["id"], first["id"])
        self.assertFalse(path.exists())
        self.assertIsNone(self.store.chat_session(self.chat))

    def test_a_missing_transcript_means_a_new_session(self):
        first = self.reply("Hello", "Hm.")
        for path in sessions.transcripts(first["id"]):
            path.unlink()
        again = sessions.plan(self.store, self.chat, self.store.context_turns(self.chat), "claude-sonnet-5-5", None)
        self.assertFalse(again["resume"])

    def test_passages_already_sent_are_not_repeated(self):
        context = ('Materials folder: X\n\nPassages:\n<material file="a.pdf" where="page 2">\nB-trees\n</material>\n'
                   '<material file="b.pdf">\nHashing\n</material>')
        first, sent = sessions.dedupe(context, [])
        self.assertEqual(first, context)
        again, sent = sessions.dedupe(context.replace("Hashing", "Joins"), sent)
        self.assertNotIn("B-trees", again)
        self.assertIn("Joins", again)
        self.assertIn("1 related passage shown earlier", again)
        self.assertEqual(len(sent), 3)

    def test_claude_runs_in_the_conversation_session_and_sends_only_what_is_new(self):
        with patch("companion.chat.claude.claude_executable", lambda: "claude"):
            new = reply_command("p.txt", "m", session="11111111-1111-1111-1111-111111111111")
            resumed = reply_command("p.txt", "m", session="11111111-1111-1111-1111-111111111111", resume=True)
            none = reply_command("p.txt", "m")
        self.assertIn("--session-id", new)
        self.assertNotIn("--no-session-persistence", new)
        self.assertEqual(resumed[resumed.index("--resume") + 1], "11111111-1111-1111-1111-111111111111")
        self.assertIn("--no-session-persistence", none)
        history = [{"role": "user", "content": "Earlier"}, {"role": "assistant", "content": "Yes."},
                   {"role": "user", "content": "Now", "context": "<app_context>\nx\n</app_context>",
                    "since": [{"role": "user", "content": "/do tidy"}, {"role": "assistant", "content": "Tidied."}]}]
        full = json.loads(user_turn(history))["message"]["content"][0]["text"]
        short = json.loads(resume_turn(history))["message"]["content"][0]["text"]
        self.assertIn("Earlier", full)
        self.assertNotIn("Earlier", short)
        self.assertTrue(short.startswith("Messages since your last reply"))
        self.assertIn("/do tidy", short)
        self.assertTrue(short.endswith("<app_context>\nx\n</app_context>\n\nLatest user message:\nNow"))
        self.assertTrue(json.loads(resume_turn(history[-1:][:1] and [{**history[-1], "since": []}]))["message"][
            "content"][0]["text"].startswith("<app_context>"))

    def test_tasks_continue_the_last_task_session_in_the_same_folder_for_a_while(self):
        first = sessions.task_plan(self.store, self.chat, "C:/carbon", "claude-sonnet-5-5")
        self.assertFalse(first["resume"])
        self.transcript(first["id"], "C--carbon")
        sessions.record_task(self.store, self.chat, first, "C:/carbon", "claude-sonnet-5-5", 40_000)
        second = sessions.task_plan(self.store, self.chat, "C:/carbon", "claude-sonnet-5-5")
        self.assertEqual((second["resume"], second["id"], second["tasks"]), (True, first["id"], 1))
        elsewhere = sessions.task_plan(self.store, self.chat, "C:/other", "claude-sonnet-5-5")
        self.assertFalse(elsewhere["resume"])
        self.assertEqual(sessions.transcripts(first["id"]), [])  # A replaced task session is deleted.

    def test_cleanup_keeps_what_is_used_and_deleting_a_chat_ends_its_sessions(self):
        first = self.reply("Hello", "Hm.")
        own = re.sub(r"[^A-Za-z0-9]", "-", str(sessions.FOLDER.resolve()))  # How Claude Code names the folder.
        stray = Path(self.home.name) / "projects" / own / "22222222-2222-2222-2222-222222222222.jsonl"
        stray.parent.mkdir(parents=True, exist_ok=True)
        stray.write_text("{}", encoding="utf-8")
        kept = self.transcript(first["id"], stray.parent.name)
        task = sessions.task_plan(self.store, self.chat, "C:/carbon", "m")
        self.transcript(task["id"], "C--carbon")
        sessions.record_task(self.store, self.chat, task, "C:/carbon", "m", 100)
        self.store.connection.execute("UPDATE task_sessions SET updated_at=?",
                                      ((datetime.now(timezone.utc) - timedelta(hours=4)).isoformat(),))
        sessions.cleanup(self.store)
        self.assertFalse(stray.exists())  # Not any conversation's session.
        self.assertTrue(kept.exists())
        self.assertIsNone(self.store.task_session(self.chat))  # An old task session.
        sessions.forget(self.store, self.chat)
        self.assertFalse(kept.exists())
        self.assertIsNone(self.store.chat_session(self.chat))

    def test_cache_reuse_is_shown_as_a_share_of_what_was_read(self):
        self.store.record_usage(self.chat, "claude", "m", 1000, 100, 9000)
        rows = self.store.usage_since(datetime.now(timezone.utc) - timedelta(days=1))
        self.assertAlmostEqual(usage.reuse(rows), 90.0)
        self.assertIsNone(usage.reuse([]))


if __name__ == "__main__":
    unittest.main()
