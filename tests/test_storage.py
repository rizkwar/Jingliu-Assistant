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
