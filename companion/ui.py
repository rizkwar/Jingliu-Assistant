from PySide6.QtCore import Qt, QTimer, Signal, Slot
from PySide6.QtGui import QCloseEvent, QFont, QKeyEvent, QTextCharFormat, QTextCursor, QColor
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QMainWindow, QMessageBox, QPlainTextEdit,
    QPushButton, QTextBrowser, QVBoxLayout, QWidget,
)

from .config import Settings, load_settings
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
    def __init__(self, settings: Settings):
        super().__init__()
        self.settings = settings
        self._worker: ReplyWorker | None = None
        self._messages: list[dict[str, str]] = []
        self._reply = ""
        self._closing = False
        self.setWindowTitle(f"{settings.name} · Desktop Companion")
        self.resize(720, 790)
        self.setMinimumSize(540, 580)
        self.setStyleSheet(STYLE)

        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(26, 24, 26, 22)
        layout.setSpacing(14)
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
        if self._worker or not text:
            return
        try:
            self.settings.validate_connection()
        except ValueError as exc:
            QMessageBox.information(self, "Connection settings", str(exc))
            return
        if len(text) > 16000:
            QMessageBox.information(self, "Message too long", "Please keep a message under 16,000 characters.")
            return
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
        self.send_button.setEnabled(not busy)
        self.stop_button.setEnabled(busy)
        self.new_chat.setEnabled(not busy)
        self.reload.setEnabled(not busy)
        self.status.setText("Thinking…" if busy else "Ready")

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
            self.input.setFocus()

    @Slot()
    def _stop(self) -> None:
        if self._worker:
            self._worker.stop()
            self.stop_button.setEnabled(False)
            self.status.setText("Stopping…")

    @Slot()
    def _new_conversation(self) -> None:
        if self._worker:
            return
        self._messages.clear()
        self.transcript.clear()
        self._welcome()
        self.input.setFocus()

    @Slot()
    def _reload_settings(self) -> None:
        if self._worker:
            return
        try:
            settings = load_settings()
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "Could not reload settings", str(exc))
            return
        self.settings = settings
        self.title.setText(settings.name)
        self.setWindowTitle(f"{settings.name} · Desktop Companion")
        self.status.setText("Ready" if settings.api_key else "Add API key")
        self._write("\nSettings reloaded.\n", "#a4adbf")

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._worker:
            self._closing = True
            self._stop()
            self.status.setText("Closing…")
            self.centralWidget().setEnabled(False)
            event.ignore()
        else:
            event.accept()

