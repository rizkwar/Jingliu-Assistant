import asyncio
import os
import time
import threading
import json
import sqlite3
import unittest
from dataclasses import replace
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import httpx
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QEvent, QObject, QTimer, Signal

from companion.config import DEFAULT_MODEL, Settings
from companion.ui import CompanionWindow
from companion.worker import ReplyWorker
from companion.speech_text import SpeechSegmenter
from companion.storage import Store
from companion.summary_ui import SummaryDialog


SETTINGS = Settings("test-key", DEFAULT_MODEL, "Mira", "You are Mira.", tts_enabled=False)
REAL_CLIENT = httpx.AsyncClient


class FakeSpeech(QObject):
    changed = Signal(str)
    failed = Signal(str)
    spoken = Signal(str)

    def __init__(self):
        super().__init__()
        self.busy = False
        self.calls = []
        self.segmenter = None

    def begin_reply(self, voice, volume):
        self.voice, self.volume = voice, volume
        self.segmenter = SpeechSegmenter()
        self.busy = True
        self.changed.emit("Waiting for next phrase…")

    def feed_reply(self, text):
        if self.segmenter is not None:
            for phrase in self.segmenter.feed(text):
                self.speak(phrase, self.voice, self.volume)

    def finish_reply(self):
        if self.segmenter is not None:
            for phrase in self.segmenter.finish():
                self.speak(phrase, self.voice, self.volume)
            self.segmenter = None

    def speak(self, text, voice, volume):
        self.calls.append((text, voice, volume))
        self.busy = True
        self.changed.emit("Speaking…")

    def stop(self):
        self.busy = False
        self.segmenter = None
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

    def test_completed_reply_speaks_and_next_message_replaces_voice_session(self):
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
            self.assertTrue(self.window._streaming_voice)
            self.assertEqual(speech.calls, [("Hello", "alba", 70)])
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

    def start_streaming_reply(self):
        speech, mic = self.use_fake_microphone()
        self.window.auto_speak.setChecked(True)
        gate = threading.Event()
        class Stream(httpx.AsyncByteStream):
            async def __aiter__(self):
                yield b'data: {"choices":[{"delta":{"content":"First sentence. "}}]}\n\n'
                while not gate.is_set():
                    await asyncio.sleep(0.005)
                yield b'data: {"choices":[{"delta":{"content":"Final sentence."},"finish_reason":"stop"}]}\n\n'
                yield b'data: [DONE]\n\n'
        return speech, mic, gate, self.mock_client(lambda request: httpx.Response(200, stream=Stream()))

    def test_first_sentence_speaks_before_api_stream_finishes_without_final_replay(self):
        speech, _, gate, client = self.start_streaming_reply()
        with client:
            try:
                self.send()
                self.wait_until(lambda: len(speech.calls) == 1)
                self.assertIsNotNone(self.window._worker)
                self.assertEqual(speech.calls[0][0], "First sentence.")
                gate.set()
                self.wait_until(lambda: self.window._worker is None)
            finally:
                gate.set()
        self.assertEqual([c[0] for c in speech.calls], ["First sentence.", "Final sentence."])

    def test_microphone_interrupts_stream_and_context_tracks_completed_audio(self):
        speech, mic, gate, client = self.start_streaming_reply()
        with client:
            try:
                self.send()
                self.wait_until(lambda: len(speech.calls) == 1)
                speech.spoken.emit("First sentence.")
                self.window._begin_recording()
                gate.set()
                self.wait_until(lambda: self.window._worker is None)
            finally:
                gate.set()
        self.assertTrue(mic.busy)
        self.assertFalse(speech.busy)
        self.assertEqual([c[0] for c in speech.calls], ["First sentence."])
        self.assertIn("Completed spoken phrases: First sentence.", self.window._messages[-1]["content"])

    def test_voice_failure_does_not_stop_text_stream_or_retry_speech(self):
        speech, _, gate, client = self.start_streaming_reply()
        with client:
            try:
                self.send()
                self.wait_until(lambda: len(speech.calls) == 1)
                speech.stop()
                speech.failed.emit("Test voice failure")
                gate.set()
                self.wait_until(lambda: self.window._worker is None)
            finally:
                gate.set()
        self.assertIn("Final sentence.", self.window.transcript.toPlainText())
        self.assertEqual(len(speech.calls), 1)
        self.assertEqual(self.window.voice_status.text(), "Test voice failure")

    def test_replay_replaces_the_previous_interruption_note(self):
        speech, _ = self.use_fake_microphone()
        note = "[Voice playback was interrupted.]"
        message = {"role": "assistant", "content": "Hello\n" + note}
        self.window._messages = [message]
        self.window._voice_message = message
        self.window._voice_note = note
        self.window._last_reply = "Hello"
        self.window._read_last_reply()
        self.assertEqual(message["content"], "Hello")
        self.assertEqual(speech.calls[0][0], "Hello")

    def use_shared_store(self):
        self.window.close()
        self.window.deleteLater()
        store = Store(":memory:")
        self.addCleanup(store.close)
        self.window = CompanionWindow(SETTINGS, store=store)
        return store

    def test_saved_conversation_is_restored_without_playing_audio(self):
        store = self.use_shared_store()
        def handler(request):
            return httpx.Response(200, text='data: {"choices":[{"delta":{"content":"Saved answer"},"finish_reason":"stop"}]}\n\ndata: [DONE]\n\n')
        with self.mock_client(handler):
            self.send("Remember our discussion")
            self.wait_until(lambda: self.window._worker is None)
        conversation = self.window._conversation_id
        self.window.close()
        self.window.deleteLater()
        self.window = CompanionWindow(SETTINGS, store=store)
        self.assertEqual(self.window._conversation_id, conversation)
        self.assertIn("Saved answer", self.window.transcript.toPlainText())
        self.assertEqual(self.window._messages[-1]["content"], "Saved answer")
        self.assertFalse(self.window.speech.busy)

    def test_new_conversation_keeps_history_and_memories_but_clears_context(self):
        store = self.use_shared_store()
        old = self.window._conversation_id
        turn = store.start_turn(old, "Earlier question")
        store.save_turn(turn, "Earlier answer", "Earlier answer", "complete")
        store.save_memory("Prefer examples first")
        self.window._restore_conversation(old)
        self.window._new_conversation()
        self.assertNotEqual(self.window._conversation_id, old)
        self.assertEqual(self.window._messages, [])
        self.assertEqual(len(store.messages(old)), 2)
        self.assertEqual(len(store.memories()), 1)

    def test_memory_commands_work_without_a_key_and_are_not_model_context(self):
        self.window.settings = replace(SETTINGS, api_key="")
        self.send("/remember Prefer examples first")
        memory_id = self.window.store.memories()[0]["id"]
        self.assertIn(f"Saved memory #{memory_id}", self.window.transcript.toPlainText())
        self.assertEqual(self.window._messages, [])
        self.assertIsNone(self.window._worker)
        self.send(f"/forget {memory_id}")
        self.assertEqual(self.window.store.memories(), [])

    def test_only_selected_memories_enter_prompt_and_key_is_not_saved(self):
        self.window.store.save_memory("Prefer examples first")
        self.window.store.save_memory("Orchids bloom in winter", False)
        payloads = []
        def handler(request):
            payloads.append(json.loads(request.content))
            return httpx.Response(200, text='data: {"choices":[{"delta":{"content":"An example"},"finish_reason":"stop"}]}\n\ndata: [DONE]\n\n')
        with self.mock_client(handler):
            self.send("Explain recursion")
            self.wait_until(lambda: self.window._worker is None)
        prompt = payloads[0]["messages"][0]["content"]
        self.assertIn("Prefer examples first", prompt)
        self.assertNotIn("Orchids", prompt)
        self.assertNotIn(SETTINGS.api_key, "\n".join(self.window.store.connection.iterdump()))

    def test_partial_reply_can_be_restored_from_a_checkpoint(self):
        store = self.use_shared_store()
        conversation = self.window._conversation_id
        turn = store.start_turn(conversation, "Question")
        store.save_turn(turn, "Partial text", "Partial text", "pending")
        self.window._restore_conversation(conversation)
        self.assertIn("Interrupted during a previous session", self.window.transcript.toPlainText())
        self.assertIn("app closed during", self.window._messages[-1]["content"])

    def test_final_save_failure_keeps_reply_and_can_be_retried(self):
        def handler(request):
            return httpx.Response(200, text='data: {"choices":[{"delta":{"content":"Keep this reply"},"finish_reason":"stop"}]}\n\ndata: [DONE]\n\n')
        with self.mock_client(handler), patch.object(self.window.store, "save_turn", side_effect=sqlite3.OperationalError("disk full")):
            self.send()
            self.wait_until(lambda: self.window._worker is None)
            self.assertIn("not fully saved", self.window.privacy.text())
            self.assertIsNotNone(self.window._active_turn)
            self.assertIn("Keep this reply", self.window.transcript.toPlainText())
        self.assertTrue(self.window._save_active_turn())
        self.assertIsNone(self.window._active_turn)
        self.assertEqual(self.window.store.context(self.window._conversation_id)[-1]["content"], "Keep this reply")

    def test_message_save_failure_does_not_send_request_or_clear_draft(self):
        with patch.object(self.window.store, "start_turn", side_effect=sqlite3.OperationalError("locked")):
            self.send("Unsent draft")
        self.assertEqual(self.window.input.toPlainText(), "Unsent draft")
        self.assertIsNone(self.window._worker)
        self.assertIn("No request was sent", self.window.privacy.text())

    def test_saved_memory_is_confirmed_even_if_archiving_its_command_fails(self):
        with patch.object(self.window.store, "local_exchange", side_effect=sqlite3.OperationalError("locked")):
            self.send("/remember Prefer short examples")
        self.assertEqual(len(self.window.store.memories()), 1)
        self.assertIn("Saved memory #", self.window.transcript.toPlainText())
        self.assertIn("Memory changed", self.window.privacy.text())

    def test_close_to_tray_cancels_recording_and_preserves_draft(self):
        _, mic = self.use_fake_microphone()
        self.window.tray_enabled = True
        self.window.show()
        self.window.input.setPlainText("Unsent draft")
        self.window._begin_recording()
        self.window._pending_transcription = "Pending words"
        self.window.close()
        self.assertFalse(self.window.isVisible())
        self.assertFalse(self.window._closing)
        self.assertFalse(mic.busy)
        self.assertEqual(self.window._pending_transcription, "")
        self.assertEqual(self.window.input.toPlainText(), "Unsent draft")
        self.window.show_companion()
        self.assertTrue(self.window.isVisible())
        self.window.tray_enabled = False

    def test_quit_from_hidden_tray_waits_for_stream_and_saves_partial_reply(self):
        speech, _, gate, client = self.start_streaming_reply()
        self.window.tray_enabled = True
        closed = []
        self.window.closed.connect(lambda: closed.append(True))
        with client:
            self.send()
            self.wait_until(lambda: len(speech.calls) == 1)
            self.window.hide_to_tray()
            self.window.request_quit()
            self.wait_until(lambda: self.window._worker is None and bool(closed))
        self.assertTrue(self.window._closing)
        self.assertFalse(speech.busy)
        self.assertFalse(self.window.isVisible())
        self.window.tray_enabled = False

    def test_suspend_cancels_stream_and_ignores_shortcut_and_late_transcript(self):
        speech, mic, gate, client = self.start_streaming_reply()
        with client:
            self.send()
            self.wait_until(lambda: len(speech.calls) == 1)
            self.window.toggle_suspended()
            self.wait_until(lambda: self.window._worker is None)
        self.window._toggle_recording()
        mic.deliver("Late transcript")
        self.window._preview_voice()
        self.send("Blocked while suspended")
        self.assertFalse(mic.busy)
        self.assertFalse(speech.busy)
        self.assertIsNone(self.window._worker)
        self.assertEqual(self.window.status.text(), "Suspended")
        self.assertFalse(self.window.send_button.isEnabled())
        self.window.toggle_suspended()
        self.assertTrue(self.window.send_button.isEnabled())
        self.assertEqual(self.window.input.toPlainText(), "Blocked while suspended")
        self.assertEqual(self.window.status.text(), "Ready")

    def test_disabling_saved_memory_retrieval_keeps_local_memories(self):
        self.window.store.save_memory("A private preference")
        self.window.use_memories.setChecked(False)
        payloads = []
        def handler(request):
            payloads.append(json.loads(request.content))
            return httpx.Response(200, text='data: {"choices":[{"delta":{"content":"Hello"},"finish_reason":"stop"}]}\n\ndata: [DONE]\n\n')
        with self.mock_client(handler):
            self.send()
            self.wait_until(lambda: self.window._worker is None)
        self.assertNotIn("A private preference", json.dumps(payloads))
        self.assertEqual(len(self.window.store.memories()), 1)
        self.assertIn("retrieval is off", self.window.privacy.text())

    def test_settings_save_preserves_device_zero_and_reload_keeps_saved_preferences(self):
        self.window.volume.setValue(15)
        self.window.mic_device.addItem("Microphone zero", 0)
        self.window.mic_device.setCurrentIndex(1)
        self.window.use_memories.setChecked(False)
        self.window._save_preferences()
        self.assertEqual(self.window.settings.stt_microphone, "0")
        with patch("companion.ui.load_settings", return_value=replace(SETTINGS, name="Luna")):
            self.window._reload_settings()
        self.assertEqual(self.window.volume.value(), 15)
        self.assertFalse(self.window.use_memories.isChecked())
        self.assertEqual(self.window.title.text(), "Luna")
        self.window._mic_devices([{"id": 0, "name": "Microphone zero"}])
        self.assertEqual(self.window.mic_device.currentData(), 0)

    def test_failed_preference_save_is_reported_without_changing_saved_settings(self):
        self.window.volume.setValue(12)
        with patch.object(self.window.preferences, "save", side_effect=OSError("disk full")):
            self.window._save_preferences()
        self.assertIn("Could not save defaults", self.window.preference_status.text())
        self.assertEqual(self.window.settings.tts_volume, SETTINGS.tts_volume)

    def prepare_summary(self):
        speech, microphone = self.use_fake_microphone()
        for index in range(15):
            turn = self.window.store.start_turn(self.window._conversation_id, f"Earlier question {index}")
            self.window.store.save_turn(turn, f"Earlier answer {index}", f"Earlier answer {index}", "complete")
        self.window._restore_conversation(self.window._conversation_id)
        dialog = SummaryDialog(self.window.store, self.window._conversation_id, self.window)
        dialog.cancel_requested.connect(self.window._stop)
        dialog.saved.connect(self.window._refresh_continuity)
        self.window._summary_dialog = dialog
        return dialog, speech, microphone

    def test_summary_generation_is_reviewed_before_saving_and_never_spoken_or_archived(self):
        dialog, speech, _ = self.prepare_summary()
        self.window.auto_speak.setChecked(True)
        self.window.store.save_memory("Unrelated personal memory")
        before = self.window.transcript.toPlainText()
        archived = len(self.window.store.messages(self.window._conversation_id))
        payloads = []
        def handler(request):
            payloads.append(json.loads(request.content))
            return httpx.Response(200, text='data: {"choices":[{"delta":{"content":"We chose Python and local voice."},"finish_reason":"stop"}]}\n\ndata: [DONE]\n\n')
        with self.mock_client(handler):
            self.window._generate_summary()
            self.wait_until(lambda: self.window._worker is None)
        self.assertEqual(dialog.editor.toPlainText(), "We chose Python and local voice.")
        self.assertIsNone(self.window.store.summary(self.window._conversation_id))
        self.assertEqual(self.window.transcript.toPlainText(), before)
        self.assertEqual(len(self.window.store.messages(self.window._conversation_id)), archived)
        self.assertEqual(speech.calls, [])
        self.assertNotIn("Unrelated personal memory", json.dumps(payloads))
        source = json.loads(payloads[0]["messages"][1]["content"])
        self.assertEqual(len(source["older_exchanges"]), 3)
        self.assertEqual(source["older_exchanges"][-1]["user"], "Earlier question 2")
        dialog._save()
        summary = self.window.store.summary(self.window._conversation_id)
        self.assertEqual(summary["content"], "We chose Python and local voice.")
        self.assertEqual(summary["through_id"], 6)
        self.assertIn("Saved summary", self.window.context_hint.text())

    def test_saved_summary_is_sent_only_for_its_conversation_and_without_extra_requests(self):
        dialog, _, _ = self.prepare_summary()
        dialog.editor.setPlainText("A unique older decision: build in Python.")
        dialog._save()
        self.window.use_memories.setChecked(False)
        payloads = []
        def handler(request):
            payloads.append(json.loads(request.content))
            return httpx.Response(200, text='data: {"choices":[{"delta":{"content":"A reply"},"finish_reason":"stop"}]}\n\ndata: [DONE]\n\n')
        with self.mock_client(handler):
            self.send("Continue our project")
            self.wait_until(lambda: self.window._worker is None)
            self.window._new_conversation()
            self.send("A separate conversation")
            self.wait_until(lambda: self.window._worker is None)
        self.assertEqual(len(payloads), 2)
        self.assertIn("A unique older decision", payloads[0]["messages"][0]["content"])
        self.assertNotIn("A unique older decision", json.dumps(payloads[1]))
        self.assertEqual(payloads[0]["messages"][1]["content"], "Earlier question 3")
        self.assertEqual(len(payloads[0]["messages"]), 26)

    def test_failed_summary_generation_preserves_saved_notes_and_draft_edits(self):
        dialog, _, _ = self.prepare_summary()
        self.window.store.save_summary(self.window._conversation_id, "Saved notes")
        dialog.editor.setPlainText("Unsaved corrections")
        with self.mock_client(lambda request: httpx.Response(429, json={"error": {"message": "rate limit"}})):
            self.window._generate_summary()
            self.wait_until(lambda: self.window._worker is None)
        self.assertIn("rate limit", dialog.status.text())
        self.assertEqual(dialog.editor.toPlainText(), "Unsaved corrections")
        self.assertEqual(self.window.store.summary(self.window._conversation_id)["content"], "Saved notes")
        self.assertEqual(dialog.through_id, 0)

    def test_oversized_model_summary_is_discarded_without_advancing_coverage(self):
        dialog, _, _ = self.prepare_summary()
        dialog.editor.setPlainText("Keep these notes")
        content = json.dumps({"choices": [{"delta": {"content": "x" * 6001}, "finish_reason": "stop"}]})
        with self.mock_client(lambda request: httpx.Response(200, text=f"data: {content}\n\ndata: [DONE]\n\n")):
            self.window._generate_summary()
            self.wait_until(lambda: self.window._worker is None)
        self.assertIn("exceeded", dialog.status.text())
        self.assertEqual(dialog.editor.toPlainText(), "Keep these notes")
        self.assertEqual(dialog.through_id, 0)
        self.assertIsNone(self.window.store.summary(self.window._conversation_id))

    def test_suspending_summary_cancels_partial_draft_and_keeps_existing_notes(self):
        dialog, speech, _ = self.prepare_summary()
        dialog.editor.setPlainText("Keep these notes")
        class Stream(httpx.AsyncByteStream):
            async def __aiter__(self):
                yield b'data: {"choices":[{"delta":{"content":"Partial new notes"}}]}\n\n'
                await asyncio.sleep(10)
        with self.mock_client(lambda request: httpx.Response(200, stream=Stream())):
            self.window._generate_summary()
            self.wait_until(lambda: bool(self.window._summary_text))
            self.window.toggle_suspended()
            self.wait_until(lambda: self.window._worker is None)
        self.assertEqual(dialog.editor.toPlainText(), "Keep these notes")
        self.assertEqual(dialog.through_id, 0)
        self.assertIn("cancelled", dialog.status.text())
        self.assertEqual(self.window.status.text(), "Suspended")
        self.assertFalse(speech.busy)

    def test_quit_during_summary_waits_for_worker_and_does_not_save_partial_draft(self):
        dialog, _, _ = self.prepare_summary()
        class Stream(httpx.AsyncByteStream):
            async def __aiter__(self):
                yield b'data: {"choices":[{"delta":{"content":"Partial notes"}}]}\n\n'
                await asyncio.sleep(10)
        with self.mock_client(lambda request: httpx.Response(200, stream=Stream())):
            self.window._generate_summary()
            self.wait_until(lambda: bool(self.window._summary_text))
            self.window.request_quit()
            self.wait_until(lambda: self.window._worker is None and not self.window.isVisible())
        self.assertTrue(self.window._closing)
        self.assertEqual(dialog.editor.toPlainText(), "")

    def test_pending_transcript_after_summary_interruption_is_sent_once(self):
        dialog, _, mic = self.prepare_summary()
        payloads = []
        class Stream(httpx.AsyncByteStream):
            async def __aiter__(self):
                yield b'data: {"choices":[{"delta":{"content":"Partial notes"}}]}\n\n'
                await asyncio.sleep(10)
        def handler(request):
            payloads.append(json.loads(request.content))
            if len(payloads) == 1:
                return httpx.Response(200, stream=Stream())
            return httpx.Response(200, text='data: {"choices":[{"delta":{"content":"Heard you"},"finish_reason":"stop"}]}\n\ndata: [DONE]\n\n')
        with self.mock_client(handler):
            self.window._generate_summary()
            self.wait_until(lambda: bool(self.window._summary_text))
            self.window._begin_recording()
            mic.deliver("A spoken interruption")
            self.wait_until(lambda: len(payloads) == 2 and self.window._worker is None)
        self.assertEqual(payloads[1]["messages"][-1]["content"], "A spoken interruption")
        self.assertEqual(dialog.editor.toPlainText(), "")

    def test_closing_real_context_dialog_cancels_generation_before_dialog_is_deleted(self):
        dialog, _, _ = self.prepare_summary()
        self.window._summary_dialog = None
        dialog.deleteLater()
        class Stream(httpx.AsyncByteStream):
            async def __aiter__(self):
                yield b'data: {"choices":[{"delta":{"content":"Partial notes"}}]}\n\n'
                await asyncio.sleep(10)
        timer = QTimer(self.window)
        timer.setInterval(5)
        state = []
        def advance():
            active = self.window._summary_dialog
            if active is not None and not state:
                state.append("started")
                active.generate.click()
            elif active is not None and self.window._summary_text:
                state.append("closed")
                timer.stop()
                active.reject()
        timer.timeout.connect(advance)
        timeout = QTimer(self.window)
        timeout.setSingleShot(True)
        timeout.timeout.connect(self.window.request_quit)
        with self.mock_client(lambda request: httpx.Response(200, stream=Stream())):
            timer.start()
            timeout.start(3000)
            self.window._open_summary()
            timeout.stop()
        self.assertEqual(state, ["started", "closed"])
        self.assertIsNone(self.window._worker)
        self.assertIsNone(self.window._summary_dialog)
        self.assertIsNone(self.window.store.summary(self.window._conversation_id))
        self.assertTrue(self.window.send_button.isEnabled())

