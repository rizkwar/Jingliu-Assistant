from dataclasses import replace
import sqlite3
from pathlib import Path

from PySide6.QtCore import QEvent, Qt, QTimer, QUrl, Signal, Slot
from PySide6.QtGui import QCloseEvent, QDesktopServices, QFont, QKeyEvent, QTextCharFormat, QTextCursor, QColor
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QHBoxLayout, QLabel, QMainWindow, QMessageBox, QPlainTextEdit,
    QProgressBar, QPushButton, QSlider, QTextBrowser, QVBoxLayout, QWidget,
)

from .config import Settings, VOICES, load_settings
from .speech import SpeechController
from .microphone import MicrophoneController
from .worker import ReplyWorker
from .storage import Store
from .library_ui import HistoryDialog, MemoryDialog
from .preferences import Preferences
from .continuity import MAX_SUMMARY_CHARS, SUMMARY_PROMPT, recent_messages, split_turns
from .summary_ui import SummaryDialog
from .avatar import AvatarController, activity_state
from .prompts import reply_prompt


STYLE = """
QWidget { background: #151820; color: #e9eaf0; font-family: 'Segoe UI'; font-size: 14px; }
QLabel#eyebrow { color: #a7a2e0; font-size: 11px; font-weight: 600; }
QLabel#title { font-size: 30px; font-weight: 600; }
QLabel#subtitle, QLabel#hint { color: #929bad; font-size: 12px; }
QLabel#status { color: #b9b2fc; padding: 7px 12px; background: #29263c; border-radius: 10px; }
QTextBrowser { background: #1b1f2a; border: 1px solid #303646; border-radius: 12px; padding: 16px; }
QPlainTextEdit { background: #1b1f2a; border: 1px solid #3c4357; border-radius: 10px; padding: 10px; }
QPlainTextEdit:focus { border-color: #a99df5; }
QComboBox { background: #292e3c; border: 1px solid #3c4357; border-radius: 6px; padding: 6px 10px; }
QComboBox QAbstractItemView { background: #292e3c; selection-background-color: #454055; }
QSlider::groove:horizontal { height: 4px; background: #3c4357; border-radius: 2px; }
QSlider::handle:horizontal { background: #b7a9ff; width: 13px; margin: -5px 0; border-radius: 6px; }
QProgressBar { background: #292e3c; border: none; border-radius: 3px; max-height: 6px; }
QProgressBar::chunk { background: #8fc7b2; border-radius: 3px; }
QPushButton { background: #292e3c; border: 1px solid #3c4357; border-radius: 8px; padding: 8px 14px; }
QPushButton:hover { background: #363d50; }
QPushButton:checked { background: #454055; border-color: #b7a9ff; color: #dfd6ff; }
QPushButton:disabled { color: #636d80; border-color: #303646; }
QPushButton#send { background: #b7a9ff; color: #191627; border: none; font-weight: 600; }
QPushButton#send:hover { background: #cbbfff; }
QPushButton#send:disabled { background: #454055; color: #8c839e; }
"""


class MessageInput(QPlainTextEdit):
    submitted = Signal()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and not (
            event.modifiers() & Qt.KeyboardModifier.ShiftModifier
        ):
            self.submitted.emit()
            event.accept()
        else:
            super().keyPressEvent(event)


class CompanionWindow(QMainWindow):
    closed = Signal()
    suspended_changed = Signal(bool)
    activity_changed = Signal(str)

    def __init__(self, settings: Settings, speech=None, microphone=None, store=None, preferences=None):
        super().__init__()
        self.settings = settings
        self.activity = "ready"
        self._activity_error = False
        self._worker: ReplyWorker | None = None
        self._worker_kind = "reply"
        self._summary_dialog = None
        self._summary_text = ""
        self._summary_error = ""
        self._summary_through = 0
        self._messages: list[dict[str, str]] = []
        self._reply = ""
        self._closing = False
        self._quitting = False
        self.tray_enabled = False
        self.suspended = False
        self.preferences = preferences if preferences is not None else Preferences()
        self._last_reply = ""
        self.speech = speech if speech is not None else SpeechController(self)
        self.microphone = microphone if microphone is not None else MicrophoneController(self)
        self._mic_draft = ""
        self._handsfree_capture = False
        self._handsfree_timer = QTimer(self)
        self._handsfree_timer.setSingleShot(True)
        self._handsfree_timer.timeout.connect(self._arm_handsfree)
        self._pending_transcription = ""
        self._streaming_voice = False
        self._voice_for_reply = False
        self._spoken_phrases = []
        self._voice_note = ""
        self._voice_message = None
        # The entry point injects a disk store. Isolated previews/tests use RAM.
        self.store = store if store is not None else Store(":memory:")
        self._owns_store = store is None
        conversations = self.store.conversations()
        self._conversation_id = conversations[0]["id"] if conversations else self.store.create_conversation()
        self._active_turn = None
        self._reply_status = "pending"
        self._reply_notice = ""
        self._last_reply_id = None
        self._voice_message_id = None
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(500)
        self._save_timer.timeout.connect(self._save_active_turn)
        self._scroll_timer = QTimer(self)
        self._scroll_timer.setSingleShot(True)
        self._scroll_timer.timeout.connect(self._scroll_to_latest)
        self.setWindowTitle(f"{settings.name} · Desktop Companion")
        self.resize(740, 800)
        self.setMinimumSize(600, 660)
        self.setStyleSheet(STYLE)

        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(26, 24, 26, 22)
        layout.setSpacing(10)
        eyebrow = QLabel("YOUR DESKTOP COMPANION")
        eyebrow.setObjectName("eyebrow")
        layout.addWidget(eyebrow)
        heading = QHBoxLayout()
        self.title = QLabel(settings.name)
        self.title.setObjectName("title")
        heading.addWidget(self.title)
        heading.addStretch()
        self.status = QLabel("Ready")
        self.status.setObjectName("status")
        heading.addWidget(self.status)
        layout.addLayout(heading)
        self.conversation_title = QLabel("New conversation")
        self.conversation_title.setObjectName("subtitle")
        layout.addWidget(self.conversation_title)
        self.context_hint = QLabel()
        self.context_hint.setObjectName("hint")
        self.context_hint.setWordWrap(True)
        layout.addWidget(self.context_hint)

        toolbar = QHBoxLayout()
        self.new_chat = QPushButton("New")
        self.new_chat.setToolTip("Start a new conversation; keep the current one in History")
        self.reload = QPushButton("Reload .env + character")
        self.reload.setToolTip("Reload connection and character; keep saved app preferences")
        self.settings_button = QPushButton("Settings")
        self.settings_button.clicked.connect(self.open_settings)
        self.history_button = QPushButton("History")
        self.memory_button = QPushButton("Memories")
        self.context_button = QPushButton("Context")
        self.context_button.setToolTip("Inspect or summarize older exchanges in this conversation")
        self.context_button.clicked.connect(self._open_summary)
        self.history_button.clicked.connect(self._open_history)
        self.memory_button.clicked.connect(self._open_memories)
        self.new_chat.clicked.connect(self._new_conversation)
        self.reload.clicked.connect(self._reload_settings)
        toolbar.addWidget(self.new_chat)
        toolbar.addWidget(self.history_button)
        toolbar.addWidget(self.memory_button)
        toolbar.addWidget(self.context_button)
        toolbar.addStretch()
        toolbar.addWidget(self.settings_button)
        layout.addLayout(toolbar)

        self.settings_dialog = QDialog(self)
        self.settings_dialog.setWindowTitle("Companion settings")
        self.settings_dialog.setMinimumWidth(540)
        settings_layout = QVBoxLayout(self.settings_dialog)
        settings_layout.setContentsMargins(22, 22, 22, 22)
        settings_layout.setSpacing(14)
        settings_hint = QLabel("Changes apply now. Save defaults to keep them after restarting.")
        settings_hint.setObjectName("hint")
        settings_hint.setWordWrap(True)
        settings_layout.addWidget(settings_hint)
        character_row = QHBoxLayout()
        self.character_label = QLabel()
        self.character_label.setWordWrap(True)
        character_row.addWidget(self.character_label, 1)
        self.edit_character = QPushButton("Edit character profile")
        self.edit_character.clicked.connect(self._edit_character)
        character_row.addWidget(self.edit_character)
        settings_layout.addLayout(character_row)
        self._refresh_character_label()
        voice_row = QHBoxLayout()
        self.auto_speak = QCheckBox("Speak replies")
        self.auto_speak.setChecked(settings.tts_enabled)
        voice_row.addWidget(self.auto_speak)
        voice_row.addStretch()
        voice_row.addWidget(QLabel("Voice"))
        self.voice = QComboBox()
        self.voice.addItems(VOICES)
        self.voice.setCurrentText(settings.tts_voice)
        voice_row.addWidget(self.voice)
        self.preview = QPushButton("Preview")
        self.preview.clicked.connect(self._preview_voice)
        voice_row.addWidget(self.preview)
        settings_layout.addLayout(voice_row)
        audio_row = QHBoxLayout()
        audio_row.addWidget(QLabel("Volume"))
        self.volume = QSlider(Qt.Orientation.Horizontal)
        self.volume.setRange(0, 100)
        self.volume.setValue(settings.tts_volume)
        self.volume.setMaximumWidth(130)
        audio_row.addWidget(self.volume)
        self.volume_label = QLabel(f"{settings.tts_volume}%")
        self.volume_label.setMinimumWidth(36)
        audio_row.addWidget(self.volume_label)
        audio_row.addStretch()
        self.replay = QPushButton("Read last reply")
        self.replay.setEnabled(False)
        self.replay.clicked.connect(self._read_last_reply)
        audio_row.addWidget(self.replay)
        settings_layout.addLayout(audio_row)
        self.voice_status = QLabel("Voice loads on first use")
        self.voice_status.setObjectName("hint")
        self.voice_status.setWordWrap(True)
        layout.addWidget(self.voice_status)
        self.speech.changed.connect(self._voice_changed)
        self.speech.failed.connect(self._voice_failed)
        self.speech.spoken.connect(self._phrase_spoken)
        self.auto_speak.toggled.connect(self._speech_toggled)
        self.voice.currentTextChanged.connect(self._voice_selected)
        self.volume.valueChanged.connect(self._volume_changed)

        mic_row = QHBoxLayout()
        self.mic_device = QComboBox()
        self.mic_device.setMinimumWidth(100)
        self.mic_device.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.mic_device.addItem("Windows default microphone", None)
        if settings.stt_microphone:
            self.mic_device.addItem(settings.stt_microphone, settings.stt_microphone)
            self.mic_device.setCurrentIndex(1)
        mic_row.addWidget(self.mic_device, 1)
        self.refresh_mics = QPushButton("Refresh")
        self.refresh_mics.setToolTip("Find available microphones")
        self.refresh_mics.clicked.connect(self.microphone.refresh_devices)
        mic_row.addWidget(self.refresh_mics)
        settings_layout.addLayout(mic_row)
        self.stt_model = QComboBox()
        self.stt_model.addItems(("tiny.en", "base.en", "small.en"))
        self.stt_model.setCurrentText(settings.stt_model)
        model_row = QHBoxLayout()
        model_row.addWidget(QLabel("English transcription model"))
        model_row.addStretch()
        model_row.addWidget(self.stt_model)
        settings_layout.addLayout(model_row)
        self.auto_send = QCheckBox("Send transcription automatically")
        self.auto_send.setChecked(settings.stt_auto_send)
        settings_layout.addWidget(self.auto_send)
        pause_row = QHBoxLayout()
        pause_row.addWidget(QLabel("Hands-free: finish after a pause"))
        pause_row.addStretch()
        self.speech_pause = QComboBox()
        for label, milliseconds in (("0.8 seconds", 800), ("1.2 seconds", 1200), ("1.8 seconds", 1800)):
            self.speech_pause.addItem(label, milliseconds)
        if self.speech_pause.findData(settings.stt_pause_ms) < 0:
            self.speech_pause.addItem(f"{settings.stt_pause_ms / 1000:g} seconds", settings.stt_pause_ms)
        self.speech_pause.setCurrentIndex(self.speech_pause.findData(settings.stt_pause_ms))
        pause_row.addWidget(self.speech_pause)
        settings_layout.addLayout(pause_row)
        self.use_memories = QCheckBox("Include relevant saved memories in online replies")
        self.use_memories.setChecked(settings.memory_enabled)
        self.use_memories.toggled.connect(self._memory_toggled)
        settings_layout.addWidget(self.use_memories)
        memory_hint = QLabel("Turning this off affects future requests. Existing conversation context still applies.")
        memory_hint.setObjectName("hint")
        memory_hint.setWordWrap(True)
        settings_layout.addWidget(memory_hint)
        self.close_to_tray = QCheckBox("Keep running in the system tray when I close the window")
        self.close_to_tray.setChecked(settings.close_to_tray)
        settings_layout.addWidget(self.close_to_tray)
        avatar_row = QHBoxLayout()
        self.show_avatar = QCheckBox("Show desktop avatar")
        self.show_avatar.setChecked(settings.avatar_enabled)
        avatar_row.addWidget(self.show_avatar)
        avatar_row.addStretch()
        self.reset_avatar = QPushButton("Reset position")
        avatar_row.addWidget(self.reset_avatar)
        settings_layout.addLayout(avatar_row)
        self.animate_avatar = QCheckBox("Animate avatar")
        self.animate_avatar.setChecked(settings.avatar_animated)
        settings_layout.addWidget(self.animate_avatar)
        self.preference_status = QLabel("API key stays in .env. Edit the character profile, then reload to apply it.")
        self.preference_status.setObjectName("hint")
        self.preference_status.setWordWrap(True)
        settings_layout.addWidget(self.preference_status)
        settings_actions = QHBoxLayout()
        settings_actions.addWidget(self.reload)
        settings_actions.addStretch()
        self.save_defaults = QPushButton("Save defaults")
        self.save_defaults.clicked.connect(self._save_preferences)
        settings_actions.addWidget(self.save_defaults)
        done = QPushButton("Done")
        done.clicked.connect(self.settings_dialog.hide)
        settings_actions.addWidget(done)
        settings_layout.addLayout(settings_actions)

        talk_row = QHBoxLayout()
        self.record_button = QPushButton("Hold to talk")
        self.record_button.setToolTip("Hold to record, release to transcribe. Maximum 60 seconds.")
        self.record_button.pressed.connect(self._begin_recording)
        self.record_button.released.connect(self._finish_recording)
        talk_row.addWidget(self.record_button)
        self.hands_free = QPushButton("Hands-free")
        self.hands_free.setCheckable(True)
        self.hands_free.setToolTip("Listen for a turn, pause during replies, then listen again. Starts off each session.")
        self.hands_free.toggled.connect(self._handsfree_toggled)
        talk_row.addWidget(self.hands_free)
        self.mic_level = QProgressBar()
        self.mic_level.setRange(0, 100)
        self.mic_level.setValue(0)
        self.mic_level.setTextVisible(False)
        self.mic_level.setMaximumWidth(100)
        talk_row.addWidget(self.mic_level)
        talk_row.addStretch()
        self.suspend_button = QPushButton("Suspend")
        self.suspend_button.clicked.connect(self.toggle_suspended)
        talk_row.addWidget(self.suspend_button)
        layout.addLayout(talk_row)
        self.mic_hint = QLabel("Hold to talk · Ctrl+Alt+Space toggles recording · 60-second limit")
        self.mic_hint.setObjectName("hint")
        self.mic_hint.setWordWrap(True)
        self._manual_mic_hint = self.mic_hint.text()
        layout.addWidget(self.mic_hint)
        self.mic_status = QLabel("Microphone off")
        self.mic_status.setObjectName("hint")
        self.mic_status.setWordWrap(True)
        layout.addWidget(self.mic_status)
        self.microphone.changed.connect(self._mic_changed)
        self.microphone.transcribed.connect(self._on_transcribed)
        self.microphone.failed.connect(self._mic_failed)
        self.microphone.devices.connect(self._mic_devices)
        self.microphone.level.connect(self.mic_level.setValue)
        self.transcript = QTextBrowser()
        self.transcript.setOpenLinks(False)
        self.transcript.setUndoRedoEnabled(False)
        layout.addWidget(self.transcript, 1)
        self.input = MessageInput()
        self.input.setPlaceholderText("What's on your mind?")
        self.input.setFixedHeight(104)
        self.input.submitted.connect(self._send)
        layout.addWidget(self.input)
        controls = QHBoxLayout()
        hint = QLabel("Enter to send · Shift+Enter for a new line")
        hint.setObjectName("hint")
        controls.addWidget(hint)
        controls.addStretch()
        self.stop_button = QPushButton("Stop")
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(self._stop)
        controls.addWidget(self.stop_button)
        self.send_button = QPushButton("Send")
        self.send_button.setObjectName("send")
        self.send_button.clicked.connect(self._send)
        controls.addWidget(self.send_button)
        layout.addLayout(controls)
        self.privacy = QLabel(self._privacy_text())
        self.privacy.setObjectName("hint")
        self.privacy.setWordWrap(True)
        layout.addWidget(self.privacy)
        self._restore_conversation(self._conversation_id)
        self.avatar = AvatarController(self)
        self.input.setFocus()

    def _write(self, text: str, color: str = "#e9eaf0", bold: bool = False) -> QTextCursor:
        cursor = self.transcript.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(color))
        fmt.setFontWeight(QFont.Weight.DemiBold if bold else QFont.Weight.Normal)
        cursor.insertText(text, fmt)
        self.transcript.setTextCursor(cursor)
        self.transcript.ensureCursorVisible()
        return cursor

    def _welcome(self) -> None:
        self._write("Start a conversation\n", "#c4baff", True)
        self._write(
            f"Type a message to {self.settings.name}. Recent messages stay in context "
            "and are saved locally. Use /remember to save a preference across conversations.\n\n", "#a4adbf"
        )
        if not self.settings.api_key:
            self.status.setText("Add API key")
            self._write("Setup: add your OpenRouter key to .env, then open Settings and reload .env.\n", "#d6be8c")
        else:
            self.status.setText("Ready")

    @Slot()
    def _send(self) -> None:
        text = self.input.toPlainText().strip()
        if self._closing or self.suspended or self._worker or self.microphone.busy or not text:
            return
        if self._local_command(text):
            return
        try:
            self.settings.validate_connection()
        except ValueError as exc:
            self._activity_error = True
            self._refresh_activity()
            QMessageBox.information(self, "Connection settings", str(exc))
            return
        if len(text) > 16000:
            QMessageBox.information(self, "Message too long", "Please keep a message under 16,000 characters.")
            return
        self._activity_error = False
        self._interrupt_speech()
        if self._active_turn and not self._save_active_turn():
            return
        try:
            turns = self.store.context_turns(self._conversation_id)
            summary = self.store.summary(self._conversation_id)
            recent_topics = "\n".join(message["content"] for message in self._messages[-4:] if message["role"] == "user")
            memories = self.store.relevant_memories(recent_topics[-4000:] + "\n" + text) if self.use_memories.isChecked() else []
            turn = self.store.start_turn(self._conversation_id, text)
        except sqlite3.Error:
            self.privacy.setText("Could not save this message. No request was sent. Please try again.")
            return
        self._active_turn = turn
        self._reply_status, self._reply_notice = "pending", ""
        self._spoken_phrases = []
        self._voice_note = ""
        self._voice_message = None
        self._voice_message_id = None
        self._pending_transcription = ""
        self._messages.append({"role": "user", "content": text})
        context = [*recent_messages(turns), {"role": "user", "content": text}]
        self.input.clear()
        self._reply = ""
        self._write("\nYou\n", "#91c9d4", True)
        self._write(text + "\n\n")
        self._write(self.settings.name + "\n", "#c4baff", True)
        prompt = reply_prompt(self.settings.system_prompt, memories, summary["content"] if summary else None)
        self._worker_kind = "reply"
        worker = ReplyWorker(replace(self.settings, system_prompt=prompt), context, self)
        self._worker = worker
        worker.chunk.connect(self._on_chunk)
        worker.finished.connect(self._on_finished)
        self._set_busy(True)
        self._streaming_voice = self.auto_speak.isChecked() and self.volume.value() > 0
        self._voice_for_reply = self._streaming_voice
        if self._streaming_voice:
            self.speech.begin_reply(self.voice.currentText(), self.volume.value())
        self._update_conversation_title()
        worker.start()

    def _set_busy(self, busy: bool) -> None:
        self._refresh_controls()
        self.status.setText("Thinking…" if busy else "Ready")
        if self.microphone.busy:
            self.status.setText("Listening…" if self.microphone.state in {"opening", "listening", "recording"} else "Transcribing…")
        if self.suspended:
            self.status.setText("Suspended")

    def _refresh_controls(self) -> None:
        busy = self._worker is not None or self.microphone.busy or self.suspended
        self.send_button.setEnabled(not busy)
        self.input.setEnabled(not self.microphone.busy)
        self.stop_button.setEnabled(self._worker is not None or self.microphone.busy or self.speech.busy or self.hands_free.isChecked())
        self.new_chat.setEnabled(not busy)
        self.reload.setEnabled(not busy)
        self.history_button.setEnabled(not busy)
        self.memory_button.setEnabled(not busy)
        self.context_button.setEnabled(not busy)
        self.preview.setEnabled(not busy and not self.speech.busy)
        self.replay.setEnabled(not busy and bool(self._last_reply) and not self.speech.busy)
        self.mic_device.setEnabled(not busy)
        self.refresh_mics.setEnabled(not busy)
        self.stt_model.setEnabled(not busy)
        self.speech_pause.setEnabled(not busy)
        self.hands_free.setEnabled(not self._closing and not self.suspended and (self.hands_free.isChecked() or not self.microphone.busy))
        self.record_button.setEnabled(not self.suspended and self.microphone.state not in {"loading", "transcribing"})
        self._refresh_activity()

    def _refresh_activity(self) -> None:
        state = activity_state(
            closing=self._closing, suspended=self.suspended, microphone=self.microphone.state,
            speech=getattr(self.speech, "state", "idle"), speech_busy=self.speech.busy,
            working=self._worker is not None, summary=self._worker_kind == "summary",
            has_reply=bool(self._reply), error=self._activity_error,
        )
        if state != self.activity:
            self.activity = state
            self.activity_changed.emit(state)

    @Slot(str, str)
    def _on_chunk(self, turn_id: str, text: str) -> None:
        worker = self._worker
        if not worker or worker.turn_id != turn_id or worker.stop_requested.is_set():
            return
        if self._worker_kind == "summary":
            if len(self._summary_text) + len(text) > MAX_SUMMARY_CHARS:
                self._summary_error = "The draft exceeded 6,000 characters. Your notes were kept; try again."
                worker.stop()
            else:
                self._summary_text += text
            return
        self.status.setText("Replying…")
        self._reply += text
        self._refresh_activity()
        self._write(text)
        if not self._save_timer.isActive():
            self._save_timer.start()
        if self._streaming_voice:
            self.speech.feed_reply(text)

    @Slot()
    def _on_finished(self) -> None:
        worker = self._worker
        if worker is None:
            return
        if self._worker_kind == "summary":
            self._finish_summary(worker)
            return
        interrupted = worker.stop_requested.is_set() or bool(worker.error)
        if interrupted:
            self._interrupt_speech()
        elif self._streaming_voice:
            self.speech.finish_reply()
        self._streaming_voice = False
        self._reply_status = "error" if worker.error else "interrupted" if interrupted else "complete"
        self._reply_notice = worker.error or ("Reply stopped" if interrupted else "")
        if self._reply:
            self._last_reply_id = self._active_turn[1] if self._active_turn else None
            self._last_reply = self._reply
            content = self._reply
            if interrupted:
                content += "\n[This reply was interrupted; only the text above was shown.]"
            if self._voice_note:
                content += "\n" + self._voice_note
            message = {"role": "assistant", "content": content}
            self._voice_message = message
            self._voice_message_id = self._last_reply_id
            self._messages.append(message)
            self._messages = self._messages[-24:]
        else:
            self._messages.pop()  # Do not carry an unanswered failed turn into the next request.
        self._save_timer.stop()
        self._save_active_turn()
        if worker.error:
            self._write("\n\n" + worker.error + "\n", "#ecb2af")
        elif interrupted:
            self._write("\n[Reply stopped]\n", "#a4adbf")
        else:
            self._write("\n")
        self._worker = None
        worker.deleteLater()
        if worker.error:
            self._activity_error = True
            self._end_handsfree()
        self._set_busy(False)
        self._refresh_continuity()
        if self._closing:
            QTimer.singleShot(0, self.close)
        else:
            if self._pending_transcription:
                QTimer.singleShot(0, self._send_pending_transcription)
            self.input.setFocus()
            self._schedule_handsfree()

    @Slot()
    def _stop(self) -> None:
        self._activity_error = False
        self._end_handsfree()
        self._pending_transcription = ""
        if self.microphone.busy:
            self.microphone.cancel()
            self.mic_status.setText("Recording or transcription cancelled")
        self._interrupt_speech()
        if self._worker:
            self._worker.stop()
            self.stop_button.setEnabled(False)
            self.status.setText("Stopping…")
        self._refresh_activity()

    @Slot()
    def _new_conversation(self) -> None:
        self._end_handsfree()
        if self._worker or self.microphone.busy:
            return
        self._interrupt_speech()
        if self._active_turn and not self._save_active_turn():
            return
        try:
            conversation_id = self.store.create_conversation()
        except sqlite3.Error:
            self.privacy.setText("Could not create a conversation. Please try again.")
            return
        self._restore_conversation(conversation_id)

    def _reset_conversation_view(self) -> None:
        self._activity_error = False
        self.speech.stop()
        self._streaming_voice = False
        self._voice_for_reply = False
        self._voice_message = None
        self._voice_message_id = None
        self._spoken_phrases = []
        self._voice_note = ""
        self._last_reply = ""
        self._last_reply_id = None
        self._pending_transcription = ""
        self.replay.setEnabled(False)
        self._messages.clear()
        self.transcript.clear()
        self._welcome()
        self.input.setFocus()

    @Slot()
    def _reload_settings(self) -> None:
        self._end_handsfree()
        if self._worker or self.microphone.busy:
            return
        try:
            settings = self.preferences.load(load_settings())
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "Could not reload settings", str(exc))
            return
        self.settings = settings
        self._refresh_character_label()
        self._interrupt_speech()
        self.auto_speak.setChecked(settings.tts_enabled)
        self.voice.setCurrentText(settings.tts_voice)
        self.volume.setValue(settings.tts_volume)
        self.auto_send.setChecked(settings.stt_auto_send)
        self.stt_model.setCurrentText(settings.stt_model)
        if self.speech_pause.findData(settings.stt_pause_ms) < 0:
            self.speech_pause.addItem(f"{settings.stt_pause_ms / 1000:g} seconds", settings.stt_pause_ms)
        self.speech_pause.setCurrentIndex(self.speech_pause.findData(settings.stt_pause_ms))
        self.use_memories.setChecked(settings.memory_enabled)
        self.close_to_tray.setChecked(settings.close_to_tray)
        self.show_avatar.setChecked(settings.avatar_enabled)
        self.animate_avatar.setChecked(settings.avatar_animated)
        self.mic_device.clear()
        self.mic_device.addItem("Windows default microphone", None)
        if settings.stt_microphone:
            self.mic_device.addItem(settings.stt_microphone, settings.stt_microphone)
            self.mic_device.setCurrentIndex(1)
        self.title.setText(settings.name)
        self.setWindowTitle(f"{settings.name} · Desktop Companion")
        self.status.setText("Ready" if settings.api_key else "Add API key")
        self._write("\nSettings reloaded.\n", "#a4adbf")
        self.preference_status.setText("Reloaded .env and the character profile, with saved app preferences.")
        self._activity_error = False
        self._refresh_activity()
        self.avatar.refresh()

    def _refresh_character_label(self) -> None:
        path = self.settings.character_path
        self.character_label.setText("Character: " + self.settings.name + (" · " + Path(path).name if path else ""))
        self.character_label.setToolTip(path)
        self.edit_character.setEnabled(bool(path))

    @Slot()
    def _edit_character(self) -> None:
        if self.settings.character_path and not QDesktopServices.openUrl(QUrl.fromLocalFile(self.settings.character_path)):
            self.preference_status.setText("Open this file in your editor: " + self.settings.character_path)

    @Slot()
    def open_settings(self) -> None:
        self._end_handsfree()
        if self._closing:
            return
        self.show_companion()
        self.settings_dialog.show()
        self.settings_dialog.raise_()
        self.settings_dialog.activateWindow()

    @Slot()
    def _save_preferences(self) -> None:
        settings = replace(
            self.settings, tts_enabled=self.auto_speak.isChecked(), tts_voice=self.voice.currentText(),
            tts_volume=self.volume.value(), stt_auto_send=self.auto_send.isChecked(),
            stt_model=self.stt_model.currentText(),
            stt_pause_ms=self.speech_pause.currentData(),
            stt_microphone="" if self.mic_device.currentData() is None else str(self.mic_device.currentData()),
            memory_enabled=self.use_memories.isChecked(), close_to_tray=self.close_to_tray.isChecked(),
            avatar_enabled=self.show_avatar.isChecked(), avatar_animated=self.animate_avatar.isChecked(),
            avatar_x=self.avatar.position()[0], avatar_y=self.avatar.position()[1],
        )
        try:
            self.preferences.save(settings)
        except (OSError, ValueError) as exc:
            self.preference_status.setText(f"Could not save defaults: {exc}")
            return
        self.settings = settings
        self.preference_status.setText("Defaults saved. These preferences override the audio defaults in .env.")

    def _privacy_text(self) -> str:
        return "Saved locally · " + (
            "Relevant memories accompany online replies" if self.use_memories.isChecked()
            else "Saved memory retrieval is off"
        )

    @Slot(bool)
    def _memory_toggled(self, enabled: bool) -> None:
        self.privacy.setText(self._privacy_text())

    @Slot()
    def show_companion(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    @Slot()
    def hide_to_tray(self) -> None:
        if not self.tray_enabled or self._closing:
            return
        self._end_handsfree()
        # Never leave an invisible recording or pending automatic send behind.
        self._pending_transcription = ""
        if self.microphone.busy:
            self.microphone.cancel()
            self.mic_status.setText("Recording or transcription cancelled when the window was hidden")
        self._dismiss_dialogs()
        self.hide()

    def _dismiss_dialogs(self) -> None:
        self.settings_dialog.hide()
        for dialog in self.findChildren(QDialog):
            if dialog is not self.settings_dialog and dialog.isVisible():
                dialog.reject()

    @Slot()
    def toggle_suspended(self) -> None:
        if self._closing:
            return
        self.suspended = not self.suspended
        if self.suspended:
            self._stop()
            self.microphone.shutdown()
            self.speech.shutdown()
        self.suspend_button.setText("Resume" if self.suspended else "Suspend")
        self._set_busy(self._worker is not None)
        self.suspended_changed.emit(self.suspended)

    @Slot()
    def request_quit(self) -> None:
        self._quitting = True
        self.close()

    def closeEvent(self, event: QCloseEvent) -> None:
        if self.tray_enabled and self.close_to_tray.isChecked() and not self._quitting:
            self.hide_to_tray()
            event.ignore()
            return
        self._end_handsfree()
        if self._worker is None and self._active_turn and not self._save_active_turn():
            if QMessageBox.question(self, "Reply not saved", "The latest reply could not be saved. Close anyway? The last successful checkpoint will remain in History.") != QMessageBox.StandardButton.Yes:
                self._closing = False
                self._quitting = False
                self.centralWidget().setEnabled(True)
                self._refresh_controls()
                self.show_companion()
                event.ignore()
                return
        self._closing = True
        self._refresh_activity()
        self._dismiss_dialogs()
        self._pending_transcription = ""
        self.microphone.shutdown()
        self._interrupt_speech()
        self.speech.shutdown()
        if self._worker:
            self._closing = True
            self._stop()
            self.status.setText("Closing…")
            self.centralWidget().setEnabled(False)
            event.ignore()
        else:
            self._save_timer.stop()
            self._scroll_timer.stop()
            if self._owns_store:
                self.store.close()
            event.accept()
            self.closed.emit()

    @Slot()
    def _preview_voice(self) -> None:
        if self.suspended or self._closing:
            return
        self._activity_error = False
        self._end_handsfree()
        self._interrupt_speech()
        self.speech.speak(
            self.settings.voice_preview or f"Hi, I'm {self.settings.name}. Let's think it through, one step at a time.",
            self.voice.currentText(), self.volume.value(),
        )

    @Slot()
    def _read_last_reply(self) -> None:
        if self._last_reply and not self.suspended and not self._closing:
            self._activity_error = False
            self._end_handsfree()
            self._interrupt_speech()
            if self._voice_message is not None and self._voice_note:
                self._voice_message["content"] = self._voice_message["content"].removesuffix("\n" + self._voice_note)
                self._save_voice_context()
            self._spoken_phrases = []
            self._voice_note = ""
            self._voice_for_reply = True
            self._voice_message = self._messages[-1] if self._messages and self._messages[-1]["role"] == "assistant" else None
            self._voice_message_id = self._last_reply_id
            self.speech.speak(self._last_reply, self.voice.currentText(), self.volume.value())

    @Slot(str)
    def _voice_changed(self, state: str) -> None:
        self.voice_status.setText(state)
        self._refresh_controls()
        if not self.speech.busy:
            self._schedule_handsfree()

    @Slot(str)
    def _voice_failed(self, message: str) -> None:
        self._activity_error = True
        self._end_handsfree()
        if self._voice_for_reply:
            self._record_voice_interruption()
        self._streaming_voice = False
        self._voice_for_reply = False
        self.voice_status.setText(message)
        self._refresh_activity()

    @Slot(bool)
    def _speech_toggled(self, enabled: bool) -> None:
        if not enabled:
            self._interrupt_speech()

    @Slot(int)
    def _volume_changed(self, volume: int) -> None:
        self.volume_label.setText(f"{volume}%")
        # The current process has a fixed gain; stop so mute takes effect immediately.
        self._interrupt_speech()

    @Slot(str)
    def _voice_selected(self, voice: str) -> None:
        self._interrupt_speech()

    @Slot(str)
    def _phrase_spoken(self, text: str) -> None:
        if self._voice_for_reply:
            self._spoken_phrases.append(text)

    def _record_voice_interruption(self) -> None:
        completed = " ".join(self._spoken_phrases) or "none confirmed"
        note = (
            "[Voice playback was interrupted. Completed spoken phrases: " + completed
            + ". Part of the current phrase may also have played; the reply text is visible on screen.]"
        )
        if self._voice_message is not None:
            content = self._voice_message["content"]
            if self._voice_note:
                content = content.removesuffix("\n" + self._voice_note)
            self._voice_message["content"] = content + "\n" + note
            self._save_voice_context()
        self._voice_note = note

    def _interrupt_speech(self) -> None:
        if self._voice_for_reply and self.speech.busy:
            self._record_voice_interruption()
        self._voice_for_reply = False
        self._streaming_voice = False
        self.speech.stop()

    @Slot(bool)
    def _handsfree_toggled(self, enabled: bool) -> None:
        self._handsfree_timer.stop()
        self.hands_free.setText("End hands-free" if enabled else "Hands-free")
        if not enabled:
            self.mic_hint.setText(self._manual_mic_hint)
            was_capturing = self._handsfree_capture
            self._handsfree_capture = False
            if was_capturing:
                self._pending_transcription = ""
                self.microphone.cancel()
            self.mic_status.setText("Hands-free off")
            self._refresh_controls()
            return
        self._manual_mic_hint = self.mic_hint.text()
        self.mic_hint.setText("Hands-free · Pause to finish a turn · 30-second turn limit")
        if self._closing or self.suspended or self.microphone.busy:
            self._end_handsfree()
            return
        if self.input.toPlainText().strip():
            self._end_handsfree()
            self.mic_status.setText("Send or clear your draft before starting hands-free mode.")
            return
        if self.auto_send.isChecked():
            try:
                self.settings.validate_connection()
            except ValueError:
                self._end_handsfree()
                self.mic_status.setText("Set up your API connection, or uncheck automatic sending in Settings to review transcripts offline.")
                return
        self.mic_status.setText(f"Hands-free waiting for {self.settings.name} to finish… Microphone off.")
        self._schedule_handsfree(0)
        self._refresh_controls()

    def _end_handsfree(self) -> None:
        self._handsfree_timer.stop()
        if self.hands_free.isChecked():
            self.hands_free.setChecked(False)

    def _schedule_handsfree(self, delay=800) -> None:
        if self.hands_free.isChecked() and not self._closing and not self.suspended:
            if not self._worker and not self.speech.busy and not self.microphone.busy:
                self.mic_status.setText("Hands-free: microphone off. Listening resumes shortly…")
                self._handsfree_timer.start(delay)

    @Slot()
    def _arm_handsfree(self) -> None:
        if not self.hands_free.isChecked() or self._closing or self.suspended:
            return
        if not self.isVisible() or self.isMinimized() or QApplication.activeModalWidget() is not None:
            self._end_handsfree()
            return
        if self._worker or self.speech.busy or self.microphone.busy:
            return
        if self.input.toPlainText().strip():
            self._end_handsfree()
            self.mic_status.setText("Hands-free paused for your draft. Send or clear it before restarting.")
            return
        self._mic_draft = ""
        self._pending_transcription = ""
        self._handsfree_capture = True
        self._activity_error = False
        self.microphone.start(self.mic_device.currentData(), self.stt_model.currentText(),
                              hands_free=True, pause_ms=self.speech_pause.currentData())

    def changeEvent(self, event) -> None:
        if event.type() == QEvent.Type.WindowStateChange and self.isMinimized() and hasattr(self, "hands_free"):
            self._end_handsfree()
        super().changeEvent(event)

    @Slot()
    def _begin_recording(self) -> None:
        self._end_handsfree()
        if self.microphone.busy or self._closing or self.suspended:
            return
        self._activity_error = False
        if self._summary_dialog is not None:
            self._summary_dialog.reject()
        self._mic_draft = self.input.toPlainText()
        self._pending_transcription = ""
        self._interrupt_speech()
        if self._worker:
            self._worker.stop()
        device = self.mic_device.currentData()
        if isinstance(device, str) and device.isdecimal():
            device = int(device)
        self.microphone.start(device, self.stt_model.currentText())

    @Slot()
    def _finish_recording(self) -> None:
        self.microphone.finish()

    @Slot()
    def _toggle_recording(self) -> None:
        if self._closing or self.suspended:
            return
        self._end_handsfree()
        if self.microphone.state in {"opening", "recording"}:
            self._finish_recording()
        elif not self.microphone.busy:
            self.showNormal()
            self.raise_()
            self.activateWindow()
            self._begin_recording()

    @Slot(str)
    def _mic_changed(self, state: str) -> None:
        labels = {
            "idle": "Microphone off", "opening": "Opening microphone… Wait for Listening before speaking.",
            "recording": "Listening… Release the button or press Ctrl+Alt+Space to finish.",
            "listening": "Hands-free listening… Speak normally. No speech for 30 seconds turns this mode off.",
            "loading": "Loading transcription model… First use downloads the model.",
            "transcribing": "Transcribing locally…",
        }
        self.mic_status.setText(labels.get(state, "Microphone off"))
        if self._handsfree_capture and state == "recording":
            self.mic_status.setText(f"Speech detected… A {self.speech_pause.currentData() / 1000:g}-second pause finishes this turn.")
        self.record_button.setText("Finish recording" if not self._handsfree_capture and state in {"opening", "recording"} else "Hold to talk")
        self._refresh_controls()
        if state != "idle":
            self.status.setText("Listening…" if state in {"opening", "listening", "recording"} else "Transcribing…")
        elif not self._worker:
            self.status.setText("Ready")
        if self.suspended:
            self.status.setText("Suspended")

    @Slot(str)
    def _on_transcribed(self, text: str) -> None:
        was_handsfree = self._handsfree_capture
        self._handsfree_capture = False
        if self._closing or self.suspended:
            return
        text = text.strip()
        if not text:
            if was_handsfree:
                self._end_handsfree()
            self.mic_status.setText("No clear speech detected. Try again a little closer to the microphone.")
            self.input.setFocus()
            return
        draft = self._mic_draft.strip()
        self.input.setPlainText(draft + "\n" + text if draft else text)
        self.input.setFocus()
        if self.auto_send.isChecked() and not draft:
            if self._worker:
                # The interrupted API task may still be cleaning up; send only after it exits.
                self.mic_status.setText("Transcript ready. Waiting for the interrupted reply to stop…")
                self._pending_transcription = text
            else:
                self._send()
                self.mic_status.setText(
                    f"Hands-free: microphone off while {self.settings.name} replies." if was_handsfree and self._worker
                    else "Transcript sent" if self._worker else "Transcript ready. Press Send."
                )
                if was_handsfree and not self._worker:
                    self._end_handsfree()
        else:
            if was_handsfree:
                self._end_handsfree()
            self.mic_status.setText("Transcript ready. Edit it if needed, then press Send.")

    def _send_pending_transcription(self) -> None:
        text, self._pending_transcription = self._pending_transcription, ""
        if (
            text and not self._closing and not self.microphone.busy and not self._worker
            and self.auto_send.isChecked() and self.input.toPlainText().strip() == text
        ):
            self._send()

    @Slot(str)
    def _mic_failed(self, message: str) -> None:
        self._activity_error = True
        self._end_handsfree()
        self.mic_status.setText(message)
        self._refresh_controls()

    @Slot(list)
    def _mic_devices(self, devices: list) -> None:
        selected = self.mic_device.currentData()
        self.mic_device.clear()
        self.mic_device.addItem("Windows default microphone", None)
        for device in devices:
            self.mic_device.addItem(device["name"], device["id"])
        index = self.mic_device.findData(selected)
        if index < 0:
            index = next((i for i in range(self.mic_device.count())
                          if str(self.mic_device.itemData(i)) == str(selected)), -1)
        if index < 0 and selected is not None:
            self.mic_device.addItem(str(selected) + " (saved device)", selected)
            index = self.mic_device.count() - 1
        self.mic_device.setCurrentIndex(max(0, index))
        self.mic_status.setText(f"Found {len(devices)} microphone inputs" if devices else "No microphone inputs found")

    def _update_conversation_title(self) -> None:
        conversation = self.store.conversation(self._conversation_id)
        if conversation:
            self.conversation_title.setText(conversation["title"])
            self.conversation_title.setToolTip(conversation["title"])

    def _restore_conversation(self, conversation_id) -> None:
        rows = self.store.messages(conversation_id)
        context = self.store.context(conversation_id)
        self.store.touch_conversation(conversation_id)
        self._reset_conversation_view()
        self._conversation_id = conversation_id
        self._active_turn = None
        self._messages = context
        for row in rows:
            name = "You" if row["role"] == "user" else self.settings.name
            color = "#91c9d4" if row["role"] == "user" else "#c4baff"
            self._write("\n" + name + "\n", color, True)
            self._write(row["display"] + "\n")
            notice = row["notice"]
            if row["status"] == "pending":
                notice = "Interrupted during a previous session"
            if notice:
                self._write("[" + notice + "]\n", "#a4adbf")
            if row["role"] == "assistant" and row["display"] and row["status"] != "local":
                self._last_reply = row["display"]
                self._last_reply_id = row["id"]
        self.replay.setEnabled(bool(self._last_reply))
        self._update_conversation_title()
        self._refresh_continuity()
        self.privacy.setText(self._privacy_text())
        self._refresh_activity()
        self._scroll_timer.start(0)

    @Slot()
    def _scroll_to_latest(self) -> None:
        self.transcript.ensureCursorVisible()

    @Slot()
    def _refresh_continuity(self) -> None:
        if self._closing:
            return
        try:
            summary = self.store.summary(self._conversation_id)
            older, _ = split_turns(self.store.context_turns(self._conversation_id))
            through_id = summary["through_id"] if summary else 0
            pending = sum(turn["assistant_id"] > through_id for turn in older)
        except sqlite3.Error:
            self.context_hint.setText("Conversation context could not be read.")
            return
        state = "Saved summary + recent exchanges" if summary else "Recent exchanges · No summary saved"
        if pending:
            state += f" · {pending} older {'exchange' if pending == 1 else 'exchanges'} to summarize in Context"
        self.context_hint.setText(state)

    @Slot()
    def _open_summary(self) -> None:
        self._end_handsfree()
        if self._closing or self._worker or self.microphone.busy or self.suspended:
            return
        self._interrupt_speech()
        if self._active_turn and not self._save_active_turn():
            return
        try:
            dialog = SummaryDialog(self.store, self._conversation_id, self)
            self._summary_dialog = dialog
            dialog.generate_requested.connect(self._generate_summary)
            dialog.cancel_requested.connect(self._stop)
            dialog.saved.connect(self._refresh_continuity)
            dialog.exec()
            self._summary_dialog = None
            dialog.deleteLater()
            self._refresh_continuity()
        except sqlite3.Error:
            QMessageBox.warning(self, "Could not open context", "Conversation context could not be read. Please try again.")

    @Slot()
    def _generate_summary(self) -> None:
        dialog = self._summary_dialog
        if dialog is None or self._worker or self._closing or self.microphone.busy:
            return
        if self.suspended:
            dialog.status.setText("Resume the companion before generating a summary.")
            return
        try:
            self.settings.validate_connection()
            batch = dialog.batch()
        except (ValueError, sqlite3.Error) as exc:
            dialog.status.setText(str(exc) if isinstance(exc, ValueError) else "Could not read older exchanges.")
            return
        if not batch.count:
            dialog.status.setText("No additional older exchanges to summarize. You can still write and save notes yourself.")
            return
        self._interrupt_speech()
        self._summary_text, self._summary_error = "", ""
        self._activity_error = False
        self._summary_through = batch.through_id
        self._worker_kind = "summary"
        worker = ReplyWorker(replace(self.settings, system_prompt=SUMMARY_PROMPT),
                             [{"role": "user", "content": batch.source}], self)
        self._worker = worker
        worker.chunk.connect(self._on_chunk)
        worker.finished.connect(self._on_finished)
        dialog.set_busy(True)
        self._refresh_controls()
        self.status.setText("Summarizing…")
        worker.start()

    def _finish_summary(self, worker) -> None:
        dialog = self._summary_dialog
        error = self._summary_error or worker.error
        if error:
            self._activity_error = True
        stopped = worker.stop_requested.is_set()
        text = self._summary_text.strip()
        self._worker = None
        self._worker_kind = "reply"
        worker.deleteLater()
        if dialog is not None:
            dialog.set_busy(False)
            if error:
                dialog.status.setText(error)
            elif stopped:
                dialog.status.setText("Summary generation cancelled. Your saved summary and draft were kept.")
            elif not text:
                dialog.status.setText("The model returned an empty summary. Your notes were kept.")
            else:
                dialog.draft_ready(text, self._summary_through)
        self._summary_text = ""
        self._set_busy(False)
        if self._closing:
            QTimer.singleShot(0, self.close)
        elif self._pending_transcription:
            QTimer.singleShot(0, self._send_pending_transcription)

    @Slot()
    def _save_active_turn(self) -> bool:
        if self._active_turn is None:
            return True
        context = self._reply
        if self._reply_status in {"error", "interrupted"} and context:
            context += "\n[This reply was interrupted; only the text above was shown.]"
        if self._voice_note:
            context += "\n" + self._voice_note
        try:
            self.store.save_turn(self._active_turn, self._reply, context or None, self._reply_status, self._reply_notice)
        except sqlite3.Error:
            self.privacy.setText("Reply not fully saved yet. Keep this window open and try again.")
            return False
        if self._reply_status != "pending":
            self._active_turn = None
        self.privacy.setText(self._privacy_text())
        return True

    def _save_voice_context(self) -> None:
        if self._voice_message_id is not None and self._voice_message is not None:
            try:
                self.store.update_context(self._voice_message_id, self._voice_message["content"])
            except sqlite3.Error:
                self.privacy.setText("The latest voice interruption note could not be saved.")

    @Slot()
    def _open_history(self) -> None:
        self._end_handsfree()
        if self._worker or self.microphone.busy:
            return
        self._interrupt_speech()
        if self._active_turn and not self._save_active_turn():
            return
        try:
            dialog = HistoryDialog(self.store, self)
            accepted = dialog.exec()
            if self._closing:
                dialog.deleteLater()
                return
            selected = dialog.selected_id if accepted else self._conversation_id
            if not self.store.conversation(selected):
                conversations = self.store.conversations()
                selected = conversations[0]["id"] if conversations else self.store.create_conversation()
            self._restore_conversation(selected)
            dialog.deleteLater()
        except sqlite3.Error:
            QMessageBox.warning(self, "Could not open history", "Saved conversations could not be read. Please try again.")

    @Slot()
    def _open_memories(self) -> None:
        self._end_handsfree()
        if self._worker or self.microphone.busy:
            return
        try:
            dialog = MemoryDialog(self.store, self)
            dialog.exec()
            dialog.deleteLater()
        except sqlite3.Error:
            QMessageBox.warning(self, "Could not open memories", "Saved memories could not be read. Please try again.")

    def _local_command(self, text) -> bool:
        parts = text.split(maxsplit=1)
        command, argument = parts[0], parts[1] if len(parts) > 1 else ""
        if command.lower() not in {"/remember", "/forget", "/memories"}:
            return False
        self._interrupt_speech()
        if command.lower() == "/memories":
            self.input.clear()
            self._open_memories()
            return True
        try:
            if command.lower() == "/remember":
                memory_id = self.store.save_memory(argument)
                response = f"Saved memory #{memory_id}. You can edit or delete it in Memories."
            else:
                if not argument.strip().isdecimal():
                    raise ValueError("Use /forget followed by a memory number, for example /forget 3.")
                deleted = self.store.delete_memory(int(argument))
                response = "Deleted that saved memory. Conversation messages are kept separately." if deleted else "No saved memory has that number."
        except ValueError as exc:
            self._write("\n" + str(exc) + "\n", "#d6be8c")
            return True
        except sqlite3.Error:
            self.privacy.setText("The memory command could not be saved. Please try again.")
            return True
        try:
            self.store.local_exchange(self._conversation_id, text, response)
        except sqlite3.Error:
            self.privacy.setText("Memory changed, but its confirmation could not be saved to History.")
        self.input.clear()
        self._write("\nYou\n", "#91c9d4", True)
        self._write(text + "\n\n")
        self._write(self.settings.name + "\n", "#c4baff", True)
        self._write(response + "\n")
        return True

