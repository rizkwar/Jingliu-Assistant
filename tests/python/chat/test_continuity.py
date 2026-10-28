import json
import unittest

from companion.chat.continuity import MAX_SOURCE_CHARS, recent_messages, split_turns, summary_batch


def turns(count, size=12):
    return [{"user_id": 2 * i + 1, "assistant_id": 2 * i + 2,
             "user": f"Q{i}:" + "x" * size, "assistant": f"A{i}:" + "y" * size} for i in range(count)]


class ContinuityTests(unittest.TestCase):
    def test_recent_pairs_and_summary_source_partition_the_conversation(self):
        source = turns(20)
        older, recent = split_turns(source)
        self.assertEqual((len(older), len(recent)), (8, 12))
        batch = summary_batch(source)
        data = json.loads(batch.source)
        self.assertEqual(batch.count, 8)
        self.assertEqual(batch.through_id, source[7]["assistant_id"])
        self.assertEqual(data["older_exchanges"][-1]["user"], source[7]["user"])
        # What a reply sends starts at a multiple of six turns, so its start stays put for six messages
        # and the service can reuse it from the cache: twelve to seventeen recent turns.
        self.assertEqual(recent_messages(source)[0]["content"], source[6]["user"])
        self.assertEqual([len(recent_messages(turns(count))) // 2 for count in range(17, 26)],
                         [17, 12, 13, 14, 15, 16, 17, 12, 13])
        self.assertNotIn(source[-1]["user"], batch.source)

    def test_large_recent_messages_leave_room_for_maximum_user_input(self):
        source = turns(12, 5000)
        messages = recent_messages(source)
        self.assertLessEqual(sum(len(message["content"]) for message in messages) + 16000, 48000)
        self.assertEqual(len(messages), 6)
        self.assertEqual(messages[0]["role"], "user")
        self.assertEqual(messages[-1]["role"], "assistant")
        self.assertEqual(len(split_turns(source)[0]), 9)

    def test_incremental_batches_advance_without_skipping_or_repeating_turns(self):
        source = turns(45, 2000)
        cursor, seen, previous = 0, [], "Original notes"
        while True:
            batch = summary_batch(source, previous, cursor)
            if not batch.count:
                break
            data = json.loads(batch.source)
            self.assertEqual(data["previous_summary"], previous)
            self.assertLessEqual(len(json.dumps(data["older_exchanges"], ensure_ascii=False)), MAX_SOURCE_CHARS)
            self.assertGreater(batch.through_id, cursor)
            seen.extend(item["user"] for item in data["older_exchanges"])
            cursor, previous = batch.through_id, "Updated notes"
        self.assertEqual(seen, [turn["user"] for turn in split_turns(source)[0]])

    def test_oversized_exchange_uses_marked_head_and_tail_excerpts(self):
        source = turns(13)
        source[0]["user"] = "Important start" + "\x00" * 40000 + "Important end"
        batch = summary_batch(source)
        item = json.loads(batch.source)["older_exchanges"][0]
        self.assertTrue(item["excerpted"])
        self.assertTrue(item["user"].startswith("Important start"))
        self.assertTrue(item["user"].endswith("Important end"))
        self.assertEqual(batch.excerpted, 1)
        self.assertEqual(batch.through_id, 2)
        self.assertLessEqual(len(json.dumps([item], ensure_ascii=False)), MAX_SOURCE_CHARS)

    def test_short_chat_has_no_old_source_but_can_include_manual_notes(self):
        batch = summary_batch(turns(5), "Manual notes")
        self.assertEqual(batch.count, 0)
        self.assertEqual(batch.through_id, 0)
        self.assertEqual(json.loads(batch.source)["previous_summary"], "Manual notes")
        with self.assertRaises(ValueError):
            summary_batch(turns(20), "x" * 6001)
