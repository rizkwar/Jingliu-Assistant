import io
import json
import os
import time
import threading
from types import SimpleNamespace
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
from PySide6.QtCore import QEvent, QProcess
from PySide6.QtWidgets import QApplication

from companion.microphone import MicrophoneController
from companion.microphone_process import run
from companion.transcription import Transcriber


class TranscriptionTests(unittest.TestCase):
    def test_short_and_silent_recordings_do_not_load_a_model(self):
        transcriber = Transcriber()
        self.assertEqual(transcriber.transcribe(np.zeros(16000), 16000), "")
        self.assertEqual(transcriber.transcribe(np.ones(100), 16000), "")
        self.assertEqual(transcriber.models, {})

    def test_resamples_to_16khz_and_uses_english_vad(self):
        class Model:
            def transcribe(self, audio, **options):
                self.audio = audio
                self.options = options
                return iter([SimpleNamespace(text=" hello "), SimpleNamespace(text="world")]), None
        model = Model()
        transcriber = Transcriber()
        transcriber.models["base.en"] = model
        result = transcriber.transcribe(np.ones(48000, dtype=np.float32) * 0.1, 48000)
        self.assertEqual(result, "hello world")
        self.assertEqual(len(model.audio), 16000)
        self.assertEqual(model.audio.dtype, np.float32)
        self.assertTrue(model.options["vad_filter"])
        self.assertEqual(model.options["language"], "en")

    def test_nonfinite_audio_is_rejected(self):
        with self.assertRaises(ValueError):
            Transcriber().transcribe(np.full(16000, np.nan), 16000)


class ProtocolTests(unittest.TestCase):
    def automatic_events(self, timed_out=False):
        finished = threading.Event()
        instances = []
        class Input:
            def __iter__(self):
                yield json.dumps({"id": "auto", "action": "start", "device": 0, "model": "base.en", "hands_free": True, "pause_ms": 800})
                finished.wait(3)
        class Output(io.StringIO):
            def write(self, value):
                super().write(value)
                if json.loads(value)["type"] in {"transcript", "error"}:
                    finished.set()
        class Automatic:
            full = False
            speaking = False
            overflowed = False
            def __init__(self, device, pause):
                self.device, self.pause = device, pause
                self.timed_out = timed_out
                self.closed = False
                instances.append(self)
            def poll(self):
                self.full = True
                self.speaking = not self.timed_out
            def level(self):
                return 0
            def close(self):
                self.closed = True
            def finish(self):
                self.close()
                return np.ones(16000), 16000
        class Transcriber:
            def transcribe(self, *args):
                if timed_out or not instances[0].closed:
                    raise AssertionError("Invalid transcription while idle or microphone still open")
                return "A hands-free turn"
        output = Output()
        run(Input(), output, transcriber=Transcriber(), automatic_factory=Automatic)
        self.assertEqual(instances[0].device, 0)
        self.assertEqual(instances[0].pause, 800)
        self.assertTrue(instances[0].closed)
        return [json.loads(line) for line in output.getvalue().splitlines()]

    def test_automatic_turn_closes_microphone_before_transcription(self):
        events = self.automatic_events()
        states = [event["state"] for event in events if event["type"] == "status"]
        self.assertEqual(states, ["listening", "recording", "transcribing"])
        self.assertEqual(events[-1]["text"], "A hands-free turn")

    def test_automatic_idle_timeout_does_not_transcribe_or_send_silence(self):
        events = self.automatic_events(timed_out=True)
        self.assertEqual(events[-1]["type"], "error")
        self.assertIn("30 seconds", events[-1]["message"])
        self.assertFalse(any(event["type"] == "transcript" for event in events))

    def test_microphone_closes_before_transcription_and_can_be_reused(self):
        instances = []
        class Capture:
            full = False
            overflowed = False
            def __init__(self, device):
                self.closed = False
                instances.append(self)
            def finish(self):
                self.close()
                return np.ones(16000), 16000
            def close(self):
                self.closed = True
        class Transcriber:
            def transcribe(self, *args):
                self.assert_closed = instances[-1].closed
                return "Hello Mira"
        transcriber = Transcriber()
        commands = []
        for i in range(2):
            commands.extend([
                {"id": str(i), "action": "start", "model": "base.en", "device": None},
                {"id": str(i), "action": "finish"},
            ])
        output = io.StringIO()
        run(io.StringIO("\n".join(map(json.dumps, commands))), output, Capture, transcriber)
        events = [json.loads(line) for line in output.getvalue().splitlines()]
        self.assertTrue(transcriber.assert_closed)
        self.assertTrue(all(c.closed for c in instances))
        self.assertEqual(len([e for e in events if e["type"] == "transcript"]), 2)

    def test_input_closure_releases_a_recording(self):
        class Capture:
            closed = False
            def __init__(self, device):
                pass
            def close(self):
                Capture.closed = True
        command = {"id": "test", "action": "start", "model": "base.en"}
        run(io.StringIO(json.dumps(command)), io.StringIO(), Capture)
        self.assertTrue(Capture.closed)

    def test_open_error_is_actionable_and_does_not_expose_exception(self):
        def bad_capture(device):
            raise RuntimeError("private internals")
        command = {"id": "test", "action": "start", "model": "base.en"}
        output = io.StringIO()
        run(io.StringIO(json.dumps(command)), output, bad_capture)
        self.assertNotIn("private internals", output.getvalue())
        self.assertIn("permissions", output.getvalue())


FAKE_ENGINE = '''
import json, sys
for line in sys.stdin:
    c = json.loads(line)
    if c['action'] == 'devices':
        event = {'type': 'devices', 'devices': [{'id': 1, 'name': 'Test microphone'}]}
    elif c['action'] == 'start':
        event = {'type': 'status', 'state': 'recording'}
    else:
        event = {'type': 'transcript', 'text': 'Hello Mira'}
    print(json.dumps({'id': c['id'], **event}), flush=True)
'''


class ControllerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.mic = MicrophoneController()
        self.mic.process.setArguments(["-u", "-c", FAKE_ENGINE])
        self.texts = []
        self.errors = []
        self.mic.transcribed.connect(self.texts.append)
        self.mic.failed.connect(self.errors.append)

    def tearDown(self):
        self.mic.shutdown()
        self.mic.deleteLater()
        self.app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.app.processEvents()

    def wait_until(self, condition):
        deadline = time.monotonic() + 4
        while not condition() and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(0.005)
        self.app.processEvents()
        self.assertTrue(condition())

    def test_finish_queued_before_process_starts_is_not_lost(self):
        self.mic.start()
        self.mic.finish()
        self.wait_until(lambda: bool(self.texts))
        self.assertEqual(self.texts, ["Hello Mira"])
        self.assertFalse(self.mic.busy)
        self.assertEqual(self.errors, [])

    def test_normal_recording_and_model_process_reuse(self):
        for i in range(2):
            self.mic.start()
            self.wait_until(lambda: self.mic.state == "recording")
            if i == 0:
                pid = self.mic.process.processId()
            self.mic.finish()
            self.wait_until(lambda: len(self.texts) == i + 1)
        self.assertEqual(self.mic.process.processId(), pid)

    def test_cancel_ignores_late_transcripts(self):
        self.mic.start()
        self.wait_until(lambda: self.mic.state == "recording")
        self.mic.cancel()
        self.wait_until(lambda: self.mic.process.state() == QProcess.ProcessState.NotRunning)
        self.assertFalse(self.mic.busy)
        self.assertEqual(self.texts, [])

    def test_device_listing_does_not_start_recording(self):
        devices = []
        self.mic.devices.connect(devices.extend)
        self.mic.refresh_devices()
        self.wait_until(lambda: bool(devices))
        self.assertEqual(devices[0]["name"], "Test microphone")
        self.assertFalse(self.mic.busy)

    def test_cancel_then_immediately_record_again_starts_the_new_turn(self):
        self.mic.start()
        self.wait_until(lambda: self.mic.state == "recording")
        self.mic.cancel()
        self.mic.start()
        self.wait_until(lambda: self.mic.state == "recording")
        self.mic.finish()
        self.wait_until(lambda: bool(self.texts))
        self.assertEqual(self.errors, [])

    def test_listening_state_transitions_to_recording_and_cancel_ignores_old_job(self):
        self.mic.process.setArguments(["-u", "-c", '''
import json,sys,time
c=json.loads(sys.stdin.readline())
for state in ['listening','recording']:
    print(json.dumps({'id':c['id'],'type':'status','state':state}),flush=True)
    time.sleep(.1)
time.sleep(10)
'''])
        self.mic.start(hands_free=True, pause_ms=1800)
        self.wait_until(lambda: self.mic.state == "listening")
        self.assertTrue(self.mic.busy)
        self.assertEqual(self.mic.deadline.interval(), 35000)
        self.wait_until(lambda: self.mic.state == "recording")
        self.mic.cancel()
        self.wait_until(lambda: self.mic.process.state() == QProcess.ProcessState.NotRunning)
        self.assertEqual(self.texts, [])
