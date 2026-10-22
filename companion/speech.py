"""Qt controller for a lazy, reusable local speech process."""

import json
from pathlib import Path
import sys
from uuid import uuid4

from PySide6.QtCore import QObject, QProcess, QProcessEnvironment, QTimer, Signal, Slot

from .config import PROJECT_ROOT
from .speech_text import spoken_text


class SpeechController(QObject):
    changed = Signal(str)
    failed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._active_id = ""
        self._pending = None
        self._stopping = False
        self._buffer = bytearray()
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
        return bool(self._active_id)

    def speak(self, text, voice, volume):
        self.stop()
        if volume <= 0:
            self.changed.emit("Voice muted")
            return
        text = spoken_text(text)
        if not text:
            self.changed.emit("No spoken text")
            return
        self._active_id = uuid4().hex
        self._pending = {"id": self._active_id, "text": text, "voice": voice, "volume": volume}
        self.changed.emit("Loading voice…")
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
            elif kind in {"done", "error"}:
                self.deadline.stop()
                self._active_id = ""
                self.changed.emit("Voice ready" if kind == "done" else "Voice unavailable")
                if kind == "error":
                    self.failed.emit(event.get("message", "Voice playback failed. Text chat still works."))

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
            self._active_id = ""
            self._pending = None
            self.deadline.stop()
            self.changed.emit("Voice unavailable")
            self.failed.emit("The voice engine stopped unexpectedly. Try Preview again. Text chat still works.")

    @Slot(QProcess.ProcessError)
    def _process_error(self, error):
        if error == QProcess.ProcessError.FailedToStart:
            self._active_id = ""
            self._pending = None
            self.deadline.stop()
            self.changed.emit("Voice unavailable")
            self.failed.emit("Could not start the voice engine. Check your Python environment.")

    @Slot()
    def _timed_out(self):
        self.stop()
        self.changed.emit("Voice unavailable")
        self.failed.emit("Voice setup or playback took too long. Check your connection and try Preview again.")
