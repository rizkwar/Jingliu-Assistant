import io
import json
import os
import time
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent, QProcess
from PySide6.QtWidgets import QApplication

from companion.speech import SpeechController
from companion.speech_process import run
from companion.speech_text import SpeechSegmenter, spoken_text
from qt_test_support import application


class SpokenTextTests(unittest.TestCase):
    def test_stage_directions_are_silent_but_meaningful_emphasis_and_asides_survive(self):
        text = "*smiles faintly* You have my attention. _blushes_ [sighs] (chuckles softly) Keep **this** and *that* (for now)."
        self.assertEqual(spoken_text(text), "You have my attention. Keep this and that (for now).")
        self.assertEqual(spoken_text("That makes me smile. Use x * y and snake_case."), "That makes me smile. Use x * y and snake_case.")

    def test_interrupted_action_is_not_read_on_replay(self):
        for action in ("*smiles while considering", "_blushes", "[sighs and looks", "(chuckles softly"):
            with self.subTest(action=action):
                self.assertEqual(spoken_text("All right. " + action), "All right.")

    def test_omits_code_and_urls_but_keeps_link_labels_and_inline_names(self):
        text = "## Try this\nUse `count()` and [the docs](https://example.com).\n```python\nsecret()\n```\n**Done.**"
        self.assertEqual(spoken_text(text), "Try this Use count() and the docs. Done.")

    def test_unclosed_fence_is_not_read_aloud(self):
        self.assertEqual(spoken_text("Explanation.\n```python\nprint(1)"), "Explanation.")

    def test_code_only_reply_is_silent(self):
        self.assertEqual(spoken_text("```python\nprint(1)\n```"), "")

    def test_long_reply_gets_a_bounded_spoken_preview(self):
        text = spoken_text("A long explanation. " * 200)
        self.assertLess(len(text), 2400)
        self.assertTrue(text.endswith("You can read the rest in the conversation."))


class SegmentationTests(unittest.TestCase):
    def phrases(self, chunks):
        segmenter = SpeechSegmenter()
        phrases = []
        for chunk in chunks:
            phrases.extend(segmenter.feed(chunk))
        phrases.extend(segmenter.finish())
        return phrases

    def test_first_sentence_is_ready_before_end_of_response(self):
        segmenter = SpeechSegmenter()
        self.assertEqual(segmenter.feed("One sentence."), [])
        self.assertEqual(segmenter.feed(" Still writing"), ["One sentence."])
        self.assertEqual(segmenter.finish(), ["Still writing"])
        self.assertEqual(segmenter.finish(), [])

    def test_action_directions_split_at_every_character_never_leak_into_audio(self):
        text = "*smiles. A very long pause.* You have my attention. _blushes faintly_ [sighs] (chuckles. Quietly.) Continue."
        expected = ["You have my attention.", "Continue."]
        self.assertEqual(self.phrases([text]), expected)
        for width in (1, 2, 3, 7, 23):
            with self.subTest(width=width):
                self.assertEqual(self.phrases([text[i:i + width] for i in range(0, len(text), width)]), expected)
        self.assertEqual(self.phrases("All right. *smiles. Still thinking"), ["All right."])

    def test_chunk_boundaries_do_not_change_spoken_output(self):
        examples = [
            "Dr. Mira measured 3.14 units. That worked!",
            "First sentence. ```python\nprint('Do not read. ')\n``` Next sentence. Final words",
            "See [this example](https://example.com/a.b) now. Then continue.",
            "Use `call(1.2)` before continuing. Yes.",
            'She said, "Hello." Then she left.',
            "**Hello there.** More words to explain this. That's all.",
            "A long explanation " * 40,
        ]
        for text in examples:
            with self.subTest(text=text[:40]):
                expected = self.phrases([text])
                self.assertEqual(self.phrases(text), expected)
                self.assertEqual(self.phrases([text[i:i + 7] for i in range(0, len(text), 7)]), expected)

    def test_code_and_unclosed_code_are_omitted(self):
        phrases = self.phrases("Start here. ```python\nsecret = 'Never speak this. '")
        self.assertEqual(phrases, ["Start here."])

    def test_abbreviations_decimals_and_urls_are_not_read_in_pieces(self):
        phrases = self.phrases("Dr. Mira used 3.14 units. Visit https://example.com/a.b for details. Done.")
        self.assertEqual(phrases, ["Dr. Mira used 3.14 units.", "Visit for details.", "Done."])

    def test_total_spoken_preview_is_bounded_across_many_sentences(self):
        phrases = self.phrases("Another complete sentence with useful words. " * 200)
        self.assertLess(len(" ".join(phrases)), 2400)
        self.assertEqual(phrases.count("You can read the rest in the conversation."), 1)

    def test_unclosed_huge_code_block_does_not_grow_without_limit(self):
        segmenter = SpeechSegmenter()
        segmenter.feed("```\n" + "x" * 66000)
        self.assertTrue(segmenter.capped)
        self.assertEqual(segmenter.buffer, "")


class SpeechProtocolTests(unittest.TestCase):
    def test_engine_is_reused_and_status_protocol_stays_valid(self):
        class Speaker:
            calls = []

            def speak(self, text, voice, volume, report, rate=100):
                self.calls.append((text, voice, volume, rate))
                print("Third-party output belongs on stderr")
                report("speaking")

        speaker = Speaker()
        commands = "\n".join(json.dumps({"id": str(i), "text": "Hi", "voice": "alba", "volume": 70}) for i in range(2))
        output = io.StringIO()
        run(io.StringIO(commands), output, speaker)
        events = [json.loads(line) for line in output.getvalue().splitlines()]
        self.assertEqual(len(speaker.calls), 2)
        self.assertEqual([e["id"] for e in events if e["type"] == "done"], ["0", "1"])

    def test_engine_failure_does_not_expose_exception_or_kill_loop(self):
        class Speaker:
            def speak(self, *args):
                raise RuntimeError("secret exception detail")
        output = io.StringIO()
        command = json.dumps({"id": "1", "text": "Hi", "voice": "alba", "volume": 70})
        run(io.StringIO(command), output, Speaker())
        self.assertNotIn("secret exception", output.getvalue())
        self.assertEqual(json.loads(output.getvalue().splitlines()[-1])["type"], "error")


FAKE_ENGINE = '''
import json, sys, time
for line in sys.stdin:
    command = json.loads(line)
    print(json.dumps({"id": command["id"], "type": "status", "state": "speaking"}), flush=True)
    if command["text"].startswith("wait"):
        time.sleep(30)
    print(json.dumps({"id": command["id"], "type": "done"}), flush=True)
'''


class SpeechControllerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = application()

    def setUp(self):
        self.speech = SpeechController()
        self.speech.process.setArguments(["-u", "-c", FAKE_ENGINE])
        self.states = []
        self.errors = []
        self.speech.changed.connect(self.states.append)
        self.speech.failed.connect(self.errors.append)

    def tearDown(self):
        self.speech.shutdown()
        self.speech.deleteLater()
        self.app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.app.processEvents()

    def wait_until(self, condition):
        deadline = time.monotonic() + 4
        while not condition() and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(0.005)
        self.app.processEvents()
        self.assertTrue(condition(), "Speech process did not finish in time")

    def test_two_requests_reuse_one_process(self):
        self.speech.speak("Hi", "alba", 70)
        self.wait_until(lambda: not self.speech.busy)
        pid = self.speech.process.processId()
        self.speech.speak("Again", "alba", 70)
        self.wait_until(lambda: not self.speech.busy)
        self.assertEqual(self.speech.process.processId(), pid)
        self.assertIn("Speaking…", self.states)
        self.assertEqual(self.errors, [])

    def test_new_request_replaces_a_stalled_request(self):
        self.speech.speak("wait", "alba", 70)
        self.wait_until(lambda: "Speaking…" in self.states)
        self.speech.speak("New reply", "anna", 40)
        self.wait_until(lambda: not self.speech.busy)
        self.assertEqual(self.states[-1], "Voice ready")
        self.assertEqual(self.errors, [])

    def test_stop_and_shutdown_reap_only_the_speech_child(self):
        self.speech.speak("wait", "alba", 70)
        self.wait_until(lambda: "Speaking…" in self.states)
        self.speech.stop()
        self.wait_until(lambda: self.speech.process.state() == QProcess.ProcessState.NotRunning)
        self.assertFalse(self.speech.busy)
        self.assertEqual(self.errors, [])

    def test_activity_state_distinguishes_preparation_from_actual_playback(self):
        self.speech.speak("wait", "alba", 70)
        self.assertEqual(self.speech.state, "preparing")
        self.wait_until(lambda: self.speech.state == "speaking")
        self.speech.stop()
        self.assertEqual(self.speech.state, "idle")
        self.assertFalse(self.speech.busy)

    def test_muting_does_not_start_a_process(self):
        self.speech.speak("Hi", "alba", 0)
        self.assertFalse(self.speech.busy)
        self.assertEqual(self.speech.process.state(), QProcess.ProcessState.NotRunning)
        self.assertEqual(self.states[-1], "Voice muted")

    def test_rate_is_bound_to_each_voice_session_and_queued_phrase(self):
        from unittest.mock import patch
        with patch.object(self.speech, "_start_or_dispatch"):
            self.speech.begin_reply("jane", 70, 94)
            self.assertEqual(self.speech._pending["rate"], 94)
            self.speech.feed_reply("A complete sentence. ")
            self.speech.finish_reply()
            self.speech._active_id = ""
            self.speech._advance()
            self.assertEqual(self.speech._pending["rate"], 94)
            self.assertEqual(self.speech._pending["text"], "A complete sentence.")
            self.speech.speak("Replay", "anna", 50, 100)
            self.assertEqual(self.speech._pending["rate"], 100)

    def test_hugging_face_token_is_only_in_child_environment_not_job_payload(self):
        from unittest.mock import patch
        with patch.object(self.speech, "_start_or_dispatch"):
            self.speech.set_hf_token("hf-secret")
            self.speech.begin_reply("reference.wav", 70)
            self.assertEqual(self.speech.process.processEnvironment().value("HF_TOKEN"), "hf-secret")
            self.assertNotIn("hf-secret", json.dumps(self.speech._pending))
            self.speech.set_hf_token("")
            self.assertFalse(self.speech.process.processEnvironment().contains("HF_TOKEN"))

    def test_streamed_phrases_play_in_order_without_repeating_at_finish(self):
        played = []
        self.speech.spoken.connect(played.append)
        self.speech.begin_reply("alba", 70)
        self.speech.feed_reply("First sentence. Second sentence. ")
        self.wait_until(lambda: len(played) == 2)
        self.assertTrue(self.speech.busy)  # More model text may still arrive.
        pid = self.speech.process.processId()
        self.speech.feed_reply("Final words")
        self.speech.finish_reply()
        self.wait_until(lambda: not self.speech.busy)
        self.assertEqual(played, ["First sentence.", "Second sentence.", "Final words"])
        self.assertEqual(self.speech.process.processId(), pid)

    def test_stop_discards_the_queue_and_late_text_from_the_old_stream(self):
        played = []
        self.speech.spoken.connect(played.append)
        self.speech.begin_reply("alba", 70)
        self.speech.feed_reply("wait. Old queued sentence. ")
        self.wait_until(lambda: self.speech._current_text == "wait." and self.states[-1] == "Speaking…")
        self.speech.stop()
        self.speech.feed_reply("Late old text. ")
        self.speech.finish_reply()
        self.speech.begin_reply("anna", 40)
        self.speech.feed_reply("Fresh reply. ")
        self.speech.finish_reply()
        self.wait_until(lambda: not self.speech.busy)
        self.assertEqual(played, ["Fresh reply."])
        self.assertEqual(self.errors, [])

    def test_voice_failure_clears_all_queued_and_future_stream_text(self):
        self.speech.process.setArguments(["-u", "-c", '''
import json, sys
for line in sys.stdin:
    c = json.loads(line)
    print(json.dumps({'id': c['id'], 'type': 'error', 'message': 'Test voice failure'}), flush=True)
'''])
        self.speech.begin_reply("alba", 70)
        self.speech.feed_reply("Should never play. More queued text. ")
        self.wait_until(lambda: bool(self.errors))
        self.speech.feed_reply("Late text. ")
        self.speech.finish_reply()
        self.assertFalse(self.speech.busy)
        self.assertEqual(self.errors, ["Test voice failure"])
