from pathlib import Path
from contextlib import closing
import sqlite3
import tempfile
import unittest

from companion.storage import Store


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.store = Store(":memory:")
        self.conversation = self.store.create_conversation()

    def tearDown(self):
        self.store.close()

    def exchange(self, question="Hello", answer="Hi"):
        turn = self.store.start_turn(self.conversation, question)
        self.store.save_turn(turn, answer, answer, "complete")
        return turn

    def test_conversations_and_memories_survive_database_reopen(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "companion.sqlite3"
            store = Store(path)
            conversation = store.create_conversation()
            turn = store.start_turn(conversation, "Remember this conversation")
            store.save_turn(turn, "Saved response", "Saved response", "complete")
            memory_id = store.save_memory("Prefer examples first")
            store.close()
            reopened = Store(path)
            try:
                self.assertEqual(reopened.context(conversation)[1]["content"], "Saved response")
                self.assertEqual(reopened.memories()[0]["id"], memory_id)
                self.assertEqual(reopened.conversations()[0]["title"], "Remember this conversation")
            finally:
                reopened.close()

    def test_partial_checkpoint_is_recovered_as_interrupted_context(self):
        turn = self.store.start_turn(self.conversation, "Question")
        self.store.save_turn(turn, "Partial answer", "Partial answer", "pending")
        context = self.store.context(self.conversation)
        self.assertEqual(context[0]["content"], "Question")
        self.assertIn("app closed during", context[1]["content"])

    def test_unanswered_pending_and_failed_turns_are_not_in_context(self):
        self.store.start_turn(self.conversation, "Pending")
        turn = self.store.start_turn(self.conversation, "Failed")
        self.store.save_turn(turn, "", None, "error", "Provider unavailable")
        self.assertEqual(self.store.context(self.conversation), [])
        self.assertEqual(len(self.store.messages(self.conversation)), 4)

    def test_context_is_limited_to_twelve_answered_turns(self):
        for index in range(20):
            self.exchange(f"Question {index}", f"Answer {index}")
        context = self.store.context(self.conversation)
        self.assertEqual(len(context), 24)
        self.assertEqual(context[0]["content"], "Question 8")
        self.assertEqual(len(self.store.messages(self.conversation)), 40)

    def test_many_local_commands_do_not_hide_older_answered_turns(self):
        self.exchange("Actual question", "Actual answer")
        for _ in range(60):
            self.store.local_exchange(self.conversation, "/remember Fact", "Saved")
        self.assertEqual(self.store.context(self.conversation)[0]["content"], "Actual question")
        self.assertEqual(len(self.store.context_turns(self.conversation)), 1)

    def test_summary_is_bounded_scoped_and_deleted_with_its_conversation(self):
        turn = self.exchange()
        self.store.save_summary(self.conversation, " Useful notes ", turn[1])
        other = self.store.create_conversation()
        self.assertIsNone(self.store.summary(other))
        self.assertEqual(self.store.summary(self.conversation)["content"], "Useful notes")
        for content, cursor in [("", 0), ("x" * 6001, 0), ("Notes", turn[0]), ("Notes", -1)]:
            with self.subTest(content=content[:12], cursor=cursor), self.assertRaises(ValueError):
                self.store.save_summary(self.conversation, content, cursor)
        with self.assertRaises(ValueError):
            self.store.save_summary(other, "Wrong conversation", turn[1])
        self.store.clear_summary(self.conversation)
        self.assertIsNone(self.store.summary(self.conversation))
        self.assertEqual(len(self.store.messages(self.conversation)), 2)
        self.store.save_summary(self.conversation, "Notes")
        self.store.delete_conversation(self.conversation)
        self.assertEqual(self.store.connection.execute("SELECT COUNT(*) FROM conversation_summaries").fetchone()[0], 0)

    def test_version_one_database_migrates_without_losing_history_or_memories(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "companion.sqlite3"
            old = Store(path)
            conversation = old.create_conversation()
            turn = old.start_turn(conversation, "Keep the original question")
            old.save_turn(turn, "Keep the answer", "Keep the answer", "complete")
            old.save_memory("Keep this memory")
            old.connection.executescript("DROP TABLE conversation_summaries; PRAGMA user_version=1;")
            old.close()
            with closing(Store(path)) as migrated:
                self.assertEqual(migrated.context(conversation)[0]["content"], "Keep the original question")
                self.assertEqual(migrated.memories()[0]["content"], "Keep this memory")
                self.assertEqual(migrated.connection.execute("PRAGMA user_version").fetchone()[0], 5)
                migrated.save_summary(conversation, "Reviewed notes", turn[1])
            with closing(Store(path)) as reopened:
                self.assertEqual(reopened.summary(conversation)["through_id"], turn[1])

    def test_deleting_one_conversation_cascades_only_its_messages(self):
        self.exchange()
        other = self.store.create_conversation()
        turn = self.store.start_turn(other, "Other")
        self.store.save_turn(turn, "Still here", "Still here", "complete")
        self.store.save_memory("Independent memory")
        self.store.delete_conversation(self.conversation)
        self.assertEqual(self.store.messages(self.conversation), [])
        self.assertEqual(len(self.store.messages(other)), 2)
        self.assertEqual(len(self.store.memories()), 1)

    def test_local_memory_commands_are_archived_but_not_sent_as_chat_context(self):
        self.store.local_exchange(self.conversation, "/remember examples first", "Saved memory #1")
        self.exchange("Explain recursion", "A function can call itself")
        self.assertEqual(len(self.store.messages(self.conversation)), 4)
        self.assertEqual(len(self.store.context(self.conversation)), 2)
        self.assertNotIn("/remember", str(self.store.context(self.conversation)))

    def test_memory_edit_keeps_id_and_deduplicates_case_and_whitespace(self):
        memory_id = self.store.save_memory("Prefer examples first")
        self.assertEqual(self.store.save_memory(" prefer   EXAMPLES first "), memory_id)
        self.store.save_memory("Prefer short examples", False, memory_id)
        memory = self.store.memories()[0]
        self.assertEqual(memory["id"], memory_id)
        self.assertFalse(memory["pinned"])
        self.assertEqual(memory["content"], "Prefer short examples")

    def test_edit_cannot_overwrite_a_different_memory(self):
        one = self.store.save_memory("One")
        self.store.save_memory("Two")
        with self.assertRaisesRegex(ValueError, "already exists"):
            self.store.save_memory("Two", memory_id=one)
        self.assertEqual(len(self.store.memories()), 2)

    def test_retrieval_selects_pinned_and_topic_matches_with_a_budget(self):
        self.store.save_memory("Prefer intuition before formulas")
        relevant = self.store.save_memory("The counting project uses Python", False)
        unrelated = self.store.save_memory("The gardening project uses tomatoes", False)
        selected = self.store.relevant_memories("Explain Python counting", limit=2)
        ids = {item["id"] for item in selected}
        self.assertIn(relevant, ids)
        self.assertNotIn(unrelated, ids)
        self.assertEqual(len(selected), 2)
        bounded = self.store.relevant_memories("Python", max_chars=20)
        self.assertLessEqual(sum(len(item["content"]) for item in bounded), 20)

    def test_memory_delete_removes_retrieval_but_keeps_conversation(self):
        self.exchange("I like examples", "Understood")
        memory_id = self.store.save_memory("I like examples")
        self.assertTrue(self.store.delete_memory(memory_id))
        self.assertFalse(self.store.delete_memory(memory_id))
        self.assertEqual(self.store.relevant_memories("examples"), [])
        self.assertEqual(len(self.store.messages(self.conversation)), 2)

    def test_memory_length_is_validated_and_sql_text_is_data(self):
        for content in ("", "x" * 1001):
            with self.assertRaises(ValueError):
                self.store.save_memory(content)
        self.store.save_memory("'); DROP TABLE memories; --")
        self.assertEqual(len(self.store.memories()), 1)

    def test_future_schema_is_not_downgraded(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "future.sqlite3"
            with closing(sqlite3.connect(path)) as database:
                database.execute("PRAGMA user_version=99")
            with self.assertRaisesRegex(sqlite3.DatabaseError, "newer version"):
                Store(path)
            with closing(sqlite3.connect(path)) as database:
                self.assertEqual(database.execute("PRAGMA user_version").fetchone()[0], 99)

    def test_version_two_chats_are_claimed_once_and_character_archives_remain_separate(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "legacy.sqlite3"
            with closing(sqlite3.connect(path)) as database:
                database.executescript("""
                    CREATE TABLE conversations (id TEXT PRIMARY KEY, title TEXT NOT NULL,
                        created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
                    INSERT INTO conversations VALUES ('legacy', 'An old chat', 'a', 'a');
                    PRAGMA user_version=2;
                """)
            with closing(Store(path)) as store:
                store.claim_legacy_conversations("jingliu")
                second = store.create_conversation("luna")
                store.claim_legacy_conversations("luna")
                self.assertEqual([row["id"] for row in store.conversations("jingliu")], ["legacy"])
                self.assertEqual([row["id"] for row in store.conversations("luna")], [second])
                self.assertEqual(len(store.conversations()), 2)
                self.assertEqual(store.connection.execute("PRAGMA user_version").fetchone()[0], 5)
