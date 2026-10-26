import re
import unittest
from pathlib import Path

from companion.avatar.cues import CUES, TEST_GROUPS, TESTS, CueFilter, PROMPT, strip_cues
from companion.chat.prompts import reply_prompt


def stream(text, size):
    cues, out = CueFilter(), []
    found = []
    for start in range(0, len(text), size):
        clean, items = cues.feed(text[start:start + size])
        out.append(clean)
        found += items
    out.append(cues.finish())
    return "".join(out), found


class CueFilterTests(unittest.TestCase):
    def test_cues_are_removed_at_any_chunk_boundary(self):
        reply = "[[blush]] You noticed that? I suppose [[smile]] I did wear it for you.[[nod]]"
        for size in (1, 2, 3, 5, 8, 64):
            with self.subTest(size=size):
                clean, cues = stream(reply, size)
                self.assertEqual(clean, "You noticed that? I suppose I did wear it for you.")
                self.assertEqual([name for _, name in cues], ["blush", "smile", "nod"])
                self.assertEqual(cues[1][0], clean.index("I did"))
                self.assertEqual(cues[2][0], len(clean))

    def test_text_that_only_looks_like_a_cue_is_kept(self):
        for text in ("matrix[[0]] = x", "[[unknown]] stays", "a [[ long bracketed thought that is not a cue ]]",
                     "list[[i]][[j]]", "ends with [", "ends with [["):
            with self.subTest(text=text):
                self.assertEqual(stream(text, 3)[0], text)
                self.assertEqual(stream(text, 3)[1], [])

    def test_case_and_spacing_are_tolerated(self):
        self.assertEqual(strip_cues("Hm. [[ Sigh ]] Fine."), "Hm. Fine.")

    def test_replies_cannot_trigger_tester_commands(self):
        self.assertEqual(strip_cues("[[test:sleep]] Hi"), "[[test:sleep]] Hi")

    def test_tester_covers_every_cue_and_life_command(self):
        life = (Path(__file__).resolve().parents[3] / "companion/avatar/web/avatar-life.js").read_text(encoding="utf-8")
        tests = life.split("  test(name){", 1)[1].split("  wake(kind", 1)[0]
        named = {name for _, items in TEST_GROUPS for _, name in items}
        self.assertTrue(set(CUES) - {"calm", "annoyed"} <= named, "every distinct cue can be tested")
        for command in TESTS:
            name = command[5:]
            # Working states share one route: test('work:<kind>') calls work(<kind>).
            self.assertIn("'work:'" if name.startswith("work:") else f"'{name}'", tests, command)

    def test_prompt_lists_every_cue_and_matches_the_avatar_vocabulary(self):
        life = Path(__file__).resolve().parents[3] / "companion/avatar/web/avatar-life.js"
        block = life.read_text(encoding="utf-8").split("export const CUES={", 1)[1].split("};", 1)[0]
        self.assertEqual(set(re.findall(r"(\w+):\{", block)), set(CUES))
        for cue in CUES:
            self.assertIn(cue, PROMPT)
        self.assertIn(PROMPT, reply_prompt("Profile", avatar_cues=True))
        self.assertNotIn("Avatar cues", reply_prompt("Profile"))


class PetStrokeTests(unittest.TestCase):
    def test_back_and_forth_strokes_count_but_a_pass_or_jitter_does_not(self):
        from companion.avatar.mesh import PetStrokes
        strokes, now = PetStrokes(), 0.
        for x in range(0, 200, 5):  # One sweep across the avatar.
            now += .01
            self.assertFalse(strokes.feed(x, 40, now))
        strokes.reset()
        for x in [50, 51, 50, 51, 50, 51, 50]:  # Hand tremor.
            now += .02
            self.assertFalse(strokes.feed(x, 40, now))
        strokes.reset()
        results = []
        for x in [60, 80, 100, 80, 60, 80, 100]:  # Stroking her head.
            now += .05
            results.append(strokes.feed(x, 40, now))
        self.assertTrue(results[-1])
        strokes.reset()
        for y in [30, 45, 30, 45]:  # Pats up and down count too.
            now += .05
            result = strokes.feed(100, y, now)
        self.assertTrue(result)
        self.assertFalse(strokes.feed(100, 45, now + 2), "old strokes expire")


class ActionCueTests(unittest.TestCase):
    def test_offer_and_task_carry_a_description_across_chunks(self):
        reply = ("Your desktop is crowded. [[offer: Move screenshots on the Desktop into Desktop/Screenshots, "
                 "named by date; leave other files.]] Shall I?")
        for size in (1, 4, 9, 64):
            with self.subTest(size=size):
                clean, cues = stream(reply, size)
                self.assertEqual(clean, "Your desktop is crowded. Shall I?")
                self.assertEqual(cues[0][1], "offer:Move screenshots on the Desktop into Desktop/Screenshots, "
                                             "named by date; leave other files.")
        self.assertEqual(stream("[[task]] On it.", 3)[1][0][1], "task")
        self.assertEqual(stream("[[smile: ignored]] Hi", 3)[1][0][1], "smile")

    def test_unfinished_or_odd_brackets_are_still_text(self):
        for text in ("a [[task: never closed", "a [[task: has [nested] brackets]] b", "[[offer:]] x"):
            with self.subTest(text=text):
                self.assertEqual(stream(text, 5)[0].replace("  ", " ").strip(),
                                 text.replace("  ", " ").strip() if "never" in text or "nested" in text else "x")

    def test_prompt_asks_for_confirmation_by_default(self):
        default = reply_prompt("Profile", computer_tasks=True)
        self.assertIn("Always offer first", default)
        self.assertNotIn("Always offer first", reply_prompt("Profile", computer_tasks=True, confirm_tasks=False))
        self.assertNotIn("[[offer", reply_prompt("Profile"))


class OfferAnswerTests(unittest.TestCase):
    def test_plain_answers_are_recognised_and_anything_more_is_left_to_her(self):
        from companion.ui.window import offer_answer
        for text in ("yes", "Yes.", "yeah go ahead", "Sure, do it please", "okay", "go for it", "sounds good",
                     "please do", "yep, thanks Jingliu"):
            self.assertEqual(offer_answer(text), "yes", text)
        for text in ("no", "Not now, thanks.", "nope", "never mind", "don't", "no thank you"):
            self.assertEqual(offer_answer(text), "no", text)
        for text in ("yes, but skip the PDFs", "no, put them on the desktop instead", "what would you name them?",
                     "do it tomorrow", "yes yes yes yes yes yes yes", ""):
            self.assertIsNone(offer_answer(text), text)


class LongActionCueTests(unittest.TestCase):
    def test_a_detailed_task_description_is_still_one_silent_cue(self):
        detail = "Find screenshot images on the Desktop and move them into Pictures, sorted by month. " * 10
        clean, cues = stream(f"Pictures it is. [[task: {detail.strip()}]] I'll tell you how it went.", 7)
        self.assertEqual(clean, "Pictures it is. I'll tell you how it went.")
        self.assertTrue(cues[0][1].startswith("task:Find screenshot images"))
        self.assertGreater(len(cues[0][1]), 800)


class StepKindTests(unittest.TestCase):
    def test_each_step_has_a_matching_working_look(self):
        from companion.tasks.runner import describe, step_kind
        self.assertEqual(step_kind(describe("Read", {"file_path": "a.txt"})), "read")
        self.assertEqual(step_kind(describe("WebSearch", {"query": "tea"})), "read")
        self.assertEqual(step_kind(describe("PowerShell", {"command": "dir"})), "command")
        self.assertEqual(step_kind(describe("Write", {"file_path": "a"})), "type")
        self.assertEqual(step_kind(describe("mcp__jingliu__type_text", {"text": "hi"})), "type")
        self.assertEqual(step_kind(describe("mcp__jingliu__click", {"x": 1, "y": 2})), "look")
        self.assertEqual(step_kind(describe("mcp__jingliu__screenshot", {})), "look")
        self.assertEqual(step_kind("Starting…"), "think")
