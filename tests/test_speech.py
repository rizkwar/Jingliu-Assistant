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
from companion.speech_text import spoken_text


class SpokenTextTests(unittest.TestCase):
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


class SpeechProtocolTests(unittest.TestCase):
    def test_engine_is_reused_and_status_protocol_stays_valid(self):
        class Speaker:
            calls = []

            def speak(self, text, voice, volume, report):
                self.calls.append((text, voice, volume))
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
    if command["text"] == "wait":
        time.sleep(30)
    print(json.dumps({"id": command["id"], "type": "done"}), flush=True)
'''


class SpeechControllerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

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

    def test_muting_does_not_start_a_process(self):
        self.speech.speak("Hi", "alba", 0)
        self.assertFalse(self.speech.busy)
        self.assertEqual(self.speech.process.state(), QProcess.ProcessState.NotRunning)
        self.assertEqual(self.states[-1], "Voice muted")
