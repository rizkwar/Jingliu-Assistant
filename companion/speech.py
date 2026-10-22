"""Qt controller for a lazy, reusable local speech process."""

import json
from collections import deque
from pathlib import Path
import sys
from uuid import uuid4

from PySide6.QtCore import QObject, QProcess, QProcessEnvironment, QTimer, Signal, Slot

from .config import PROJECT_ROOT
from .speech_text import SpeechSegmenter, spoken_text


class SpeechController(QObject):
    changed = Signal(str)
    failed = Signal(str)
    spoken = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._active_id = ""
        self._pending = None
        self._stopping = False
        self._buffer = bytearray()
        self._queue = deque()
        self._segmenter = None
        self._stream_open = False
        self._session_active = False
        self._current_text = ""
        self._voice = "alba"
        self._volume = 70
        self.process = QProcess(self)
        self.process.setWorkingDirectory(str(PROJECT_ROOT))
        # pythonw has no console streams; use the same venv's console executable for pipes.
        executable = Path(sys.executable)
        if executable.name.lower() == "pythonw.exe":
            executable = executable.with_name("python.exe")
        self.process.setProgram(str(executable))
        self.process.setArguments(["-u", "-m", "companion.speech_process"])
        env = QProcessEnvironment.systemEnvironment()
        env.remove("OPENROUTER_API_KEY")
        env.insert("HF_HOME", str(PROJECT_ROOT / ".cache" / "huggingface"))
        env.insert("HF_HUB_DISABLE_TELEMETRY", "1")
        env.insert("PYTHONIOENCODING", "utf-8")
        self.process.setProcessEnvironment(env)
        self.process.started.connect(self._dispatch)
        self.process.readyReadStandardOutput.connect(self._read)
        self.process.readyReadStandardError.connect(self._drain_errors)
        self.process.finished.connect(self._exited)
        self.process.errorOccurred.connect(self._process_error)
        self.deadline = QTimer(self)
        self.deadline.setSingleShot(True)
        self.deadline.setInterval(600_000)
        self.deadline.timeout.connect(self._timed_out)

    @property
    def busy(self):
        return bool(self._active_id or self._queue or self._stream_open)

    def speak(self, text, voice, volume):
        self.stop()
        if volume <= 0:
            self.changed.emit("Voice muted")
            return
        text = spoken_text(text)
        if not text:
            self.changed.emit("No spoken text")
            return
        self._voice, self._volume = voice, volume
        self._session_active = True
        self._queue.append(("speak", text))
        self._advance()

    def begin_reply(self, voice, volume):
        """Warm the voice while the language model thinks; enqueue phrases as they arrive."""
        self.stop()
        if volume <= 0:
            self.changed.emit("Voice muted")
            return
        self._voice, self._volume = voice, volume
        self._segmenter = SpeechSegmenter()
        self._stream_open = True
        self._session_active = True
        self._queue.append(("prepare", ""))
        self._advance()

    def feed_reply(self, text):
        if self._segmenter is not None:
            self._queue.extend(("speak", phrase) for phrase in self._segmenter.feed(text))
            self._advance()

    def finish_reply(self):
        if self._segmenter is None:
            return
        self._queue.extend(("speak", phrase) for phrase in self._segmenter.finish())
        self._segmenter = None
        self._stream_open = False
        self._advance()

    def _advance(self):
        if self._active_id:
            return
        if not self._queue:
            if self._stream_open:
                self.changed.emit("Waiting for next phrase…")
            elif self._session_active:
                self._session_active = False
                self.changed.emit("Voice ready")
            return
        action, text = self._queue.popleft()
        self._current_text = text
        self._active_id = uuid4().hex
        self._pending = {
            "id": self._active_id, "action": action, "text": text,
            "voice": self._voice, "volume": self._volume,
        }
        self.changed.emit("Loading voice…" if action == "prepare" else "Preparing speech…")
        self.deadline.start()
        if self._stopping:
            return  # The newest pending job starts after the old process exits.
        self._start_or_dispatch()

    def _start_or_dispatch(self):
        if self.process.state() == QProcess.ProcessState.NotRunning:
            self._buffer.clear()
            self.process.start()
        elif self.process.state() == QProcess.ProcessState.Running:
            self._dispatch()

    @Slot()
    def _dispatch(self):
        if self._pending and not self._stopping:
            command, self._pending = self._pending, None
            self.process.write((json.dumps(command) + "\n").encode("utf-8"))

    def stop(self):
        was_busy = self.busy
        self.deadline.stop()
        self._active_id = ""
        self._pending = None
        self._queue.clear()
        self._segmenter = None
        self._stream_open = False
        self._session_active = False
        self._current_text = ""
        if was_busy and self.process.state() != QProcess.ProcessState.NotRunning:
            self._stopping = True
            self.process.kill()
        if was_busy:
            self.changed.emit("Voice stopped")

    def shutdown(self):
        self.stop()
        if self.process.state() != QProcess.ProcessState.NotRunning:
            self._stopping = True
            self.process.kill()
            # Reap only this app's child, even if it was idle with a model loaded.
            self.process.waitForFinished(1500)

    @Slot()
    def _read(self):
        self._buffer.extend(bytes(self.process.readAllStandardOutput()))
        while b"\n" in self._buffer:
            line, _, remainder = self._buffer.partition(b"\n")
            self._buffer = bytearray(remainder)
            try:
                event = json.loads(line)
            except (ValueError, UnicodeError):
                continue
            if not isinstance(event, dict) or event.get("id") != self._active_id:
                continue
            kind = event.get("type")
            if kind == "status":
                labels = {"loading": "Loading voice…", "preparing": "Preparing speech…", "speaking": "Speaking…"}
                self.changed.emit(labels.get(event.get("state"), "Preparing speech…"))
            elif kind == "done":
                self.deadline.stop()
                self._active_id = ""
                text, self._current_text = self._current_text, ""
                if text:
                    self.spoken.emit(text)
                self._advance()
            elif kind == "error":
                self._fail(event.get("message", "Voice playback failed. Text chat still works."))

    @Slot()
    def _drain_errors(self):
        self.process.readAllStandardError()

    @Slot(int, QProcess.ExitStatus)
    def _exited(self, code, status):
        expected = self._stopping
        self._stopping = False
        self._buffer.clear()
        if expected and self._pending:
            self._start_or_dispatch()
        elif not expected and self.busy:
            self._fail("The voice engine stopped unexpectedly. Try Preview again. Text chat still works.")

    @Slot(QProcess.ProcessError)
    def _process_error(self, error):
        if error == QProcess.ProcessError.FailedToStart:
            self._fail("Could not start the voice engine. Check your Python environment.")

    def _fail(self, message):
        self.stop()
        self.changed.emit("Voice unavailable")
        self.failed.emit(message)

    @Slot()
    def _timed_out(self):
        self._fail("Voice setup or playback took too long. Check your connection and try Preview again.")
