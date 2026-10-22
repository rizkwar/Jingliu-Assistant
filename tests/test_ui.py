import asyncio
import os
import time
import unittest
from dataclasses import replace
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import httpx
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QEvent, QObject, Signal

from companion.config import DEFAULT_MODEL, Settings
from companion.ui import CompanionWindow
from companion.worker import ReplyWorker


SETTINGS = Settings("test-key", DEFAULT_MODEL, "Mira", "You are Mira.", tts_enabled=False)
REAL_CLIENT = httpx.AsyncClient


class FakeSpeech(QObject):
    changed = Signal(str)
    failed = Signal(str)

    def __init__(self):
        super().__init__()
        self.busy = False
        self.calls = []

    def speak(self, text, voice, volume):
        self.calls.append((text, voice, volume))
        self.busy = True
        self.changed.emit("Speaking…")

    def stop(self):
        self.busy = False
        self.changed.emit("Voice stopped")

    def shutdown(self):
        self.stop()


class FakeMicrophone(QObject):
    changed = Signal(str)
    transcribed = Signal(str)
    failed = Signal(str)
    devices = Signal(list)
    level = Signal(int)

    def __init__(self):
        super().__init__()
        self.state = "idle"

    @property
    def busy(self):
        return self.state != "idle"

    def start(self, *args):
        self.state = "recording"
        self.changed.emit(self.state)

    def finish(self):
        self.state = "transcribing"
        self.changed.emit(self.state)

    def deliver(self, text):
        self.state = "idle"
        self.changed.emit(self.state)
        self.transcribed.emit(text)

    def cancel(self):
        self.state = "idle"
        self.changed.emit(self.state)

    def shutdown(self):
        self.cancel()

    def refresh_devices(self):
        self.devices.emit([])


class WindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setStyle("Fusion")

    def setUp(self):
        self.window = CompanionWindow(SETTINGS)
        self.window.show()

    def tearDown(self):
        if self.window._worker:
            self.window._stop()
            self.wait_until(lambda: self.window._worker is None)
        self.window.close()
        self.window.deleteLater()
        self.app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.app.processEvents()

    def wait_until(self, condition, timeout=3):
        deadline = time.monotonic() + timeout
        while not condition() and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(0.005)
        self.app.processEvents()
        self.assertTrue(condition(), "Desktop operation did not finish in time")

    def mock_client(self, handler):
        return patch("companion.worker.httpx.AsyncClient", side_effect=lambda **kwargs: REAL_CLIENT(
            transport=httpx.MockTransport(handler), trust_env=False, **kwargs,
        ))

    def send(self, text="Hi"):
        self.window.input.setPlainText(text)
        self.window._send()

    def test_completed_turn_is_shown_and_retained_as_plain_text(self):
        def handler(request):
            return httpx.Response(200, text=(
                'data: {"choices":[{"delta":{"content":"Hello <friend>"},"finish_reason":"stop"}]}\n\n'
                'data: [DONE]\n\n'
            ))
        with self.mock_client(handler):
            self.send("<script>Hello</script>")
            self.wait_until(lambda: self.window._worker is None)
        self.assertIn("Hello <friend>", self.window.transcript.toPlainText())
        self.assertIn("<script>Hello</script>", self.window.transcript.toPlainText())
        self.assertEqual(len(self.window._messages), 2)
        self.assertEqual(self.window.status.text(), "Ready")
        self.assertTrue(self.window.send_button.isEnabled())

    def test_failed_turn_is_visible_but_excluded_from_context(self):
        with self.mock_client(lambda request: httpx.Response(429, json={"error": {"message": "busy"}})):
            self.send()
            self.wait_until(lambda: self.window._worker is None)
        self.assertEqual(self.window._messages, [])
        self.assertIn("rate limit", self.window.transcript.toPlainText())

    def test_stop_cancels_waiting_network_and_keeps_only_visible_reply(self):
        class Stream(httpx.AsyncByteStream):
            async def __aiter__(self):
                yield b'data: {"choices":[{"delta":{"content":"Visible"}}]}\n\n'
                await asyncio.Event().wait()

        with self.mock_client(lambda request: httpx.Response(200, stream=Stream())):
            self.send()
            self.wait_until(lambda: self.window._reply == "Visible")
            self.window._stop()
            self.wait_until(lambda: self.window._worker is None)
        self.assertIn("Visible", self.window._messages[-1]["content"])
        self.assertIn("interrupted", self.window._messages[-1]["content"])

    def test_close_while_waiting_cancels_worker_then_closes(self):
        class Stream(httpx.AsyncByteStream):
            async def __aiter__(self):
                yield b': keep-alive\n\n'
                await asyncio.Event().wait()

        with self.mock_client(lambda request: httpx.Response(200, stream=Stream())):
            self.send()
            self.window.close()
            self.wait_until(lambda: self.window._worker is None and not self.window.isVisible())

    def test_cancel_before_worker_start(self):
        worker = ReplyWorker(SETTINGS, [], self.window)
        worker.stop()
        worker.start()
        self.assertTrue(worker.wait(1000))
        self.assertFalse(worker.error)

    def test_completed_reply_speaks_and_next_message_stops_playback(self):
        self.window.close()
        speech = FakeSpeech()
        self.window = CompanionWindow(replace(SETTINGS, tts_enabled=True), speech=speech)
        def handler(request):
            return httpx.Response(200, text=(
                'data: {"choices":[{"delta":{"content":"Hello"},"finish_reason":"stop"}]}\n\n'
                'data: [DONE]\n\n'
            ))
        with self.mock_client(handler):
            self.send()
            self.wait_until(lambda: self.window._worker is None)
            self.assertEqual(speech.calls, [("Hello", "alba", 70)])
            self.assertTrue(self.window.stop_button.isEnabled())
            self.send("Next question")
            self.assertFalse(speech.busy)
            self.wait_until(lambda: self.window._worker is None)
        self.window._new_conversation()
        self.assertFalse(speech.busy)
        self.assertFalse(self.window.replay.isEnabled())

    def test_preview_needs_no_api_key_and_voice_error_keeps_text_chat_usable(self):
        self.window.close()
        speech = FakeSpeech()
        self.window = CompanionWindow(replace(SETTINGS, api_key=""), speech=speech)
        self.window._preview_voice()
        self.assertIn("Mira", speech.calls[0][0])
        speech.busy = False
        speech.changed.emit("Voice unavailable")
        speech.failed.emit("No speaker available")
        self.assertEqual(self.window.voice_status.text(), "No speaker available")
        self.assertTrue(self.window.send_button.isEnabled())

    def use_fake_microphone(self):
        self.window.close()
        self.window.deleteLater()
        speech, microphone = FakeSpeech(), FakeMicrophone()
        self.window = CompanionWindow(SETTINGS, speech=speech, microphone=microphone)
        return speech, microphone

    def test_recording_stops_speech_and_preserves_existing_draft_for_review(self):
        speech, mic = self.use_fake_microphone()
        speech.busy = True
        self.window.input.setPlainText("A draft")
        self.window._begin_recording()
        self.assertFalse(speech.busy)
        self.assertFalse(self.window.input.isEnabled())
        self.window._finish_recording()
        mic.deliver("Recognized words")
        self.assertEqual(self.window.input.toPlainText(), "A draft\nRecognized words")
        self.assertTrue(self.window.input.isEnabled())
        self.assertIsNone(self.window._worker)

    def test_auto_send_routes_transcript_through_normal_chat(self):
        _, mic = self.use_fake_microphone()
        def handler(request):
            return httpx.Response(200, text=(
                'data: {"choices":[{"delta":{"content":"Hi"},"finish_reason":"stop"}]}\n\n'
                'data: [DONE]\n\n'
            ))
        with self.mock_client(handler):
            self.window._begin_recording()
            self.window._finish_recording()
            mic.deliver("Hello Mira")
            self.wait_until(lambda: self.window._worker is None)
        self.assertEqual(self.window._messages[0]["content"], "Hello Mira")

    def test_empty_transcript_and_cancel_do_not_send_anything(self):
        _, mic = self.use_fake_microphone()
        self.window._begin_recording()
        mic.deliver("")
        self.assertEqual(self.window._messages, [])
        self.assertIn("No clear speech", self.window.mic_status.text())
        self.window._begin_recording()
        self.window._stop()
        self.assertFalse(mic.busy)
        self.assertTrue(self.window.send_button.isEnabled())

    def test_review_mode_keeps_transcription_editable(self):
        _, mic = self.use_fake_microphone()
        self.window.auto_send.setChecked(False)
        self.window._begin_recording()
        mic.deliver("Edit these words")
        self.assertIsNone(self.window._worker)
        self.assertEqual(self.window.input.toPlainText(), "Edit these words")

    def test_pending_transcription_cannot_send_after_stop(self):
        self.use_fake_microphone()
        self.window.input.setPlainText("Pending words")
        self.window._pending_transcription = "Pending words"
        self.window._stop()
        self.window._send_pending_transcription()
        self.assertIsNone(self.window._worker)

    def test_pending_transcription_cannot_send_after_window_closes(self):
        self.use_fake_microphone()
        self.window.input.setPlainText("Pending words")
        self.window._pending_transcription = "Pending words"
        self.window.close()
        self.window._send_pending_transcription()
        self.assertIsNone(self.window._worker)

