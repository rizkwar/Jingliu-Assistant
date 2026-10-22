from PySide6.QtCore import Qt, QTimer, Signal, Slot
from PySide6.QtGui import QCloseEvent, QFont, QKeyEvent, QTextCharFormat, QTextCursor, QColor
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QHBoxLayout, QLabel, QMainWindow, QMessageBox, QPlainTextEdit,
    QProgressBar, QPushButton, QSlider, QTextBrowser, QVBoxLayout, QWidget,
)

from .config import Settings, VOICES, load_settings
from .speech import SpeechController
from .microphone import MicrophoneController
from .worker import ReplyWorker


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
    def __init__(self, settings: Settings, speech=None, microphone=None):
        super().__init__()
        self.settings = settings
        self._worker: ReplyWorker | None = None
        self._messages: list[dict[str, str]] = []
        self._reply = ""
        self._closing = False
        self._last_reply = ""
        self.speech = speech if speech is not None else SpeechController(self)
        self.microphone = microphone if microphone is not None else MicrophoneController(self)
        self._mic_draft = ""
        self._pending_transcription = ""
        self.setWindowTitle(f"{settings.name} · Desktop Companion")
        self.resize(740, 960)
        self.setMinimumSize(560, 740)
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
        subtitle = QLabel("A little company. A place to think out loud.")
        subtitle.setObjectName("subtitle")
        layout.addWidget(subtitle)

        toolbar = QHBoxLayout()
        self.new_chat = QPushButton("New conversation")
        self.reload = QPushButton("Reload settings")
        self.new_chat.clicked.connect(self._new_conversation)
        self.reload.clicked.connect(self._reload_settings)
        toolbar.addWidget(self.new_chat)
        toolbar.addStretch()
        toolbar.addWidget(self.reload)
        layout.addLayout(toolbar)

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
        layout.addLayout(voice_row)
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
        layout.addLayout(audio_row)
        self.voice_status = QLabel("Voice loads on first use")
        self.voice_status.setObjectName("hint")
        self.voice_status.setWordWrap(True)
        layout.addWidget(self.voice_status)
        self.speech.changed.connect(self._voice_changed)
        self.speech.failed.connect(self._voice_failed)
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
        self.record_button = QPushButton("Hold to talk")
        self.record_button.setToolTip("Hold to record, release to transcribe. Maximum 60 seconds.")
        self.record_button.pressed.connect(self._begin_recording)
        self.record_button.released.connect(self._finish_recording)
        mic_row.addWidget(self.record_button)
        layout.addLayout(mic_row)
        mic_options = QHBoxLayout()
        self.auto_send = QCheckBox("Send transcription automatically")
        self.auto_send.setChecked(settings.stt_auto_send)
        mic_options.addWidget(self.auto_send)
        self.mic_level = QProgressBar()
        self.mic_level.setRange(0, 100)
        self.mic_level.setValue(0)
        self.mic_level.setTextVisible(False)
        self.mic_level.setMaximumWidth(100)
        mic_options.addWidget(self.mic_level, 1)
        layout.addLayout(mic_options)
        self.mic_hint = QLabel("Hold to talk · Ctrl+Alt+Space toggles recording · 60-second limit")
        self.mic_hint.setObjectName("hint")
        self.mic_hint.setWordWrap(True)
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
        privacy = QLabel("Online replies · Session history clears when you close this window")
        privacy.setObjectName("hint")
        privacy.setWordWrap(True)
        layout.addWidget(privacy)
        self._welcome()
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
            "while this window is open.\n\n", "#a4adbf"
        )
        if not self.settings.api_key:
            self.status.setText("Add API key")
            self._write("Setup: add your OpenRouter key to .env, then click Reload settings.\n", "#d6be8c")
        else:
            self.status.setText("Ready")

    @Slot()
    def _send(self) -> None:
        text = self.input.toPlainText().strip()
        if self._closing or self._worker or self.microphone.busy or not text:
            return
        try:
            self.settings.validate_connection()
        except ValueError as exc:
            QMessageBox.information(self, "Connection settings", str(exc))
            return
        if len(text) > 16000:
            QMessageBox.information(self, "Message too long", "Please keep a message under 16,000 characters.")
            return
        self.speech.stop()
        self._pending_transcription = ""
        self._messages.append({"role": "user", "content": text})
        # Keep at most 12 previous exchanges; the full visible transcript remains.
        context = self._messages[-25:]
        while sum(len(message["content"]) for message in context) > 48000 and len(context) > 1:
            context = context[2:]
        self.input.clear()
        self._reply = ""
        self._write("\nYou\n", "#91c9d4", True)
        self._write(text + "\n\n")
        self._write(self.settings.name + "\n", "#c4baff", True)
        worker = ReplyWorker(self.settings, context, self)
        self._worker = worker
        worker.chunk.connect(self._on_chunk)
        worker.finished.connect(self._on_finished)
        self._set_busy(True)
        worker.start()

    def _set_busy(self, busy: bool) -> None:
        self._refresh_controls()
        self.status.setText("Thinking…" if busy else "Ready")
        if self.microphone.busy:
            self.status.setText("Listening…" if self.microphone.state in {"opening", "recording"} else "Transcribing…")

    def _refresh_controls(self) -> None:
        busy = self._worker is not None or self.microphone.busy
        self.send_button.setEnabled(not busy)
        self.input.setEnabled(not self.microphone.busy)
        self.stop_button.setEnabled(busy or self.speech.busy)
        self.new_chat.setEnabled(not busy)
        self.reload.setEnabled(not busy)
        self.preview.setEnabled(not busy and not self.speech.busy)
        self.replay.setEnabled(not busy and bool(self._last_reply) and not self.speech.busy)
        self.mic_device.setEnabled(not busy)
        self.refresh_mics.setEnabled(not busy)
        self.record_button.setEnabled(self.microphone.state not in {"loading", "transcribing"})

    @Slot(str, str)
    def _on_chunk(self, turn_id: str, text: str) -> None:
        worker = self._worker
        if not worker or worker.turn_id != turn_id or worker.stop_requested.is_set():
            return
        self.status.setText("Replying…")
        self._reply += text
        self._write(text)

    @Slot()
    def _on_finished(self) -> None:
        worker = self._worker
        if worker is None:
            return
        interrupted = worker.stop_requested.is_set() or bool(worker.error)
        if self._reply:
            self._last_reply = self._reply
            content = self._reply
            if interrupted:
                content += "\n[This reply was interrupted; only the text above was shown.]"
            self._messages.append({"role": "assistant", "content": content})
            self._messages = self._messages[-24:]
        else:
            self._messages.pop()  # Do not carry an unanswered failed turn into the next request.
        if worker.error:
            self._write("\n\n" + worker.error + "\n", "#ecb2af")
        elif interrupted:
            self._write("\n[Reply stopped]\n", "#a4adbf")
        else:
            self._write("\n")
        self._worker = None
        worker.deleteLater()
        self._set_busy(False)
        if self._closing:
            QTimer.singleShot(0, self.close)
        else:
            if self._reply and not interrupted and self.auto_speak.isChecked() and not self.microphone.busy:
                self._read_last_reply()
            if self._pending_transcription:
                QTimer.singleShot(0, self._send_pending_transcription)
            self.input.setFocus()

    @Slot()
    def _stop(self) -> None:
        self._pending_transcription = ""
        if self.microphone.busy:
            self.microphone.cancel()
            self.mic_status.setText("Recording or transcription cancelled")
        self.speech.stop()
        if self._worker:
            self._worker.stop()
            self.stop_button.setEnabled(False)
            self.status.setText("Stopping…")

    @Slot()
    def _new_conversation(self) -> None:
        if self._worker or self.microphone.busy:
            return
        self.speech.stop()
        self._last_reply = ""
        self._pending_transcription = ""
        self.replay.setEnabled(False)
        self._messages.clear()
        self.transcript.clear()
        self._welcome()
        self.input.setFocus()

    @Slot()
    def _reload_settings(self) -> None:
        if self._worker or self.microphone.busy:
            return
        try:
            settings = load_settings()
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "Could not reload settings", str(exc))
            return
        self.settings = settings
        self.speech.stop()
        self.auto_speak.setChecked(settings.tts_enabled)
        self.voice.setCurrentText(settings.tts_voice)
        self.volume.setValue(settings.tts_volume)
        self.auto_send.setChecked(settings.stt_auto_send)
        self.mic_device.clear()
        self.mic_device.addItem("Windows default microphone", None)
        if settings.stt_microphone:
            self.mic_device.addItem(settings.stt_microphone, settings.stt_microphone)
            self.mic_device.setCurrentIndex(1)
        self.title.setText(settings.name)
        self.setWindowTitle(f"{settings.name} · Desktop Companion")
        self.status.setText("Ready" if settings.api_key else "Add API key")
        self._write("\nSettings reloaded.\n", "#a4adbf")

    def closeEvent(self, event: QCloseEvent) -> None:
        self._closing = True
        self._pending_transcription = ""
        self.microphone.shutdown()
        self.speech.shutdown()
        if self._worker:
            self._closing = True
            self._stop()
            self.status.setText("Closing…")
            self.centralWidget().setEnabled(False)
            event.ignore()
        else:
            event.accept()

    @Slot()
    def _preview_voice(self) -> None:
        self.speech.speak(
            f"Hi, I'm {self.settings.name}. Let's think it through, one step at a time.",
            self.voice.currentText(), self.volume.value(),
        )

    @Slot()
    def _read_last_reply(self) -> None:
        if self._last_reply:
            self.speech.speak(self._last_reply, self.voice.currentText(), self.volume.value())

    @Slot(str)
    def _voice_changed(self, state: str) -> None:
        self.voice_status.setText(state)
        self._refresh_controls()

    @Slot(str)
    def _voice_failed(self, message: str) -> None:
        self.voice_status.setText(message)

    @Slot(bool)
    def _speech_toggled(self, enabled: bool) -> None:
        if not enabled:
            self.speech.stop()

    @Slot(int)
    def _volume_changed(self, volume: int) -> None:
        self.volume_label.setText(f"{volume}%")
        # The current process has a fixed gain; stop so mute takes effect immediately.
        self.speech.stop()

    @Slot(str)
    def _voice_selected(self, voice: str) -> None:
        self.speech.stop()

    @Slot()
    def _begin_recording(self) -> None:
        if self.microphone.busy or self._closing:
            return
        self._mic_draft = self.input.toPlainText()
        self._pending_transcription = ""
        self.speech.stop()
        if self._worker:
            self._worker.stop()
        self.microphone.start(self.mic_device.currentData(), self.settings.stt_model)

    @Slot()
    def _finish_recording(self) -> None:
        self.microphone.finish()

    @Slot()
    def _toggle_recording(self) -> None:
        if self._closing:
            return
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
            "loading": "Loading transcription model… First use downloads the model.",
            "transcribing": "Transcribing locally…",
        }
        self.mic_status.setText(labels.get(state, "Microphone off"))
        self.record_button.setText("Finish recording" if state in {"opening", "recording"} else "Hold to talk")
        self._refresh_controls()
        if state != "idle":
            self.status.setText("Listening…" if state in {"opening", "recording"} else "Transcribing…")
        elif not self._worker:
            self.status.setText("Ready")

    @Slot(str)
    def _on_transcribed(self, text: str) -> None:
        if self._closing:
            return
        text = text.strip()
        if not text:
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
                self.mic_status.setText("Transcript sent" if self._worker else "Transcript ready. Press Send.")
        else:
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
        self.mic_device.setCurrentIndex(max(0, index))
        self.mic_status.setText(f"Found {len(devices)} microphone inputs" if devices else "No microphone inputs found")

