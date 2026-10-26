import unittest

from PySide6.QtCore import QEvent

from companion.avatar.cues import CueFilter
from companion.core.config import DEFAULT_MODEL, Settings
from companion.chat.prompts import reply_prompt
from tests.qt_test_support import application

SETTINGS = Settings("test-key", DEFAULT_MODEL, "Jingliu", "Profile.", tts_enabled=False)


def stream(text, size):
    cues, out, found = CueFilter(), [], []
    for start in range(0, len(text), size):
        clean, items = cues.feed(text[start:start + size])
        out.append(clean)
        found += items
    out.append(cues.finish())
    return "".join(out), [cue for _, cue in found]


class MemoryCueTests(unittest.TestCase):
    def test_remember_and_forget_are_silent_and_carry_the_fact(self):
        reply = "Noted. [[remember: Takes tea without sugar.]] I will not forget. [[forget: old exam date]]"
        for size in (1, 7, 64):
            with self.subTest(size=size):
                clean, cues = stream(reply, size)
                self.assertEqual(clean.strip(), "Noted. I will not forget.")
                self.assertEqual(cues, ["remember:Takes tea without sugar.", "forget:old exam date"])

    def test_prompt_lifts_the_no_saving_rule_and_follows_the_setting(self):
        on = reply_prompt("Profile", memory_cues=True)
        self.assertIn("[[remember:", on)
        self.assertIn("This replaces the earlier statement", on)
        self.assertIn("without being asked", on)
        off = reply_prompt("Profile", memory_cues=True, auto_memory=False)
        self.assertNotIn("without being asked", off)
        self.assertIn("Only save when the user asks", off)
        self.assertNotIn("[[remember:", reply_prompt("Profile"))


class WindowMemoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = application()

    def setUp(self):
        from companion.ui.window import CompanionWindow
        self.window = CompanionWindow(SETTINGS)
        self.store = self.window.store
        for memory in self.store.memories():
            self.store.delete_memory(memory["id"])

    def tearDown(self):
        self.window.request_quit()
        self.window.deleteLater()
        self.app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.app.processEvents()

    def contents(self):
        return [memory["content"] for memory in self.store.memories()]

    def test_a_remembered_fact_is_saved_shown_and_can_be_undone(self):
        self.window._queue_cues([(0, "remember:Takes tea without sugar."), (3, "smile")])
        self.assertEqual(self.contents(), [])  # Saved only once the reply finishes well.
        self.window._apply_memory_actions()
        self.assertEqual(self.contents(), ["Takes tea without sugar."])
        self.assertIn("Memory saved: “Takes tea without sugar.”", self.window.transcript.toPlainText())
        note = self.window.transcript._items[-1]
        note.button.click()
        self.assertEqual(self.contents(), [])
        self.assertIn("Not remembered", self.window.transcript.toPlainText())

    def test_saving_twice_says_already_remembered(self):
        self.store.save_memory("Takes tea without sugar.")
        self.window._remember("takes tea  without sugar.")
        self.assertEqual(len(self.contents()), 1)
        self.assertIn("Already remembered", self.window.transcript.toPlainText())

    def test_forget_removes_the_best_match_only_and_undo_restores_it(self):
        self.store.save_memory("Has a calculus exam on 3 November.", pinned=False)
        self.store.save_memory("Likes rainy evenings.")
        self.window._forget("calculus exam date")
        self.assertEqual(self.contents(), ["Likes rainy evenings."])
        self.window.transcript._items[-1].button.click()
        self.assertIn("Has a calculus exam on 3 November.", self.contents())
        self.window._forget("favourite colour")
        self.assertEqual(len(self.contents()), 2)
        self.assertIn("No saved memory matched", self.window.transcript.toPlainText())

    def test_the_setting_is_remembered(self):
        saved = []
        self.window.preferences.remember = lambda settings, keys: saved.append((settings.auto_memory, keys))
        self.window.auto_memory.setChecked(False)
        self.assertEqual(saved, [(False, ("auto_memory",))])
        self.assertFalse(self.window.settings.auto_memory)


if __name__ == "__main__":
    unittest.main()
