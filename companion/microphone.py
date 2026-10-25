"""Qt lifecycle and cancellation for the microphone/transcription process."""

import json
import time
from pathlib import Path
import sys
from uuid import uuid4

from PySide6.QtCore import QObject, QProcess, QProcessEnvironment, QTimer, Signal, Slot

from .config import PROJECT_ROOT


class MicrophoneController(QObject):
    changed = Signal(str)
    transcribed = Signal(str)
    failed = Signal(str)
    devices = Signal(list)
    level = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.state = "idle"
        self._active_id = ""
        self._device_id = ""
        self._pending = []
        self._stopping = False
        self._buffer = bytearray()
        self.process = QProcess(self)
        executable = Path(sys.executable)
        if executable.name.lower() == "pythonw.exe":
            executable = executable.with_name("python.exe")
        self.process.setProgram(str(executable))
        self.process.setArguments(["-u", "-m", "companion.microphone_process"])
        self.process.setWorkingDirectory(str(PROJECT_ROOT))
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
        self.deadline.timeout.connect(self._timed_out)

    @property
    def busy(self):
        return self.state != "idle"

    def _set_state(self, state):
        self.state = state
        self.changed.emit(state)

    def _send(self, command):
        self._pending.append(command)
        if self._stopping:
            return
        if self.process.state() == QProcess.ProcessState.NotRunning:
            self._buffer.clear()
            self.process.start()
        elif self.process.state() == QProcess.ProcessState.Running:
            self._dispatch()

    @Slot()
    def _dispatch(self):
        if self._stopping:
            return
        pending, self._pending = self._pending, []
        if pending:
            self.last_used = time.monotonic()
        for command in pending:
            self.process.write((json.dumps(command) + "\n").encode("utf-8"))

    def refresh_devices(self):
        if not self.busy:
            self._device_id = uuid4().hex
            self._send({"id": self._device_id, "action": "devices"})

    def start(self, device=None, model="base.en", *, hands_free=False, pause_ms=1200):
        if self.busy:
            return
        self._active_id = uuid4().hex
        self._set_state("opening")
        self.deadline.start(15_000)
        self._send({"id": self._active_id, "action": "start", "device": device, "model": model,
                    "hands_free": hands_free, "pause_ms": pause_ms})

    def finish(self):
        if self.state not in {"opening", "listening", "recording"}:
            return
        self._set_state("transcribing")
        self.deadline.start(600_000)
        self._send({"id": self._active_id, "action": "finish"})

    def cancel(self):
        self.deadline.stop()
        self._active_id = ""
        self._device_id = ""
        self._pending.clear()
        if self.process.state() != QProcess.ProcessState.NotRunning:
            self._stopping = True
            self.process.kill()
        self.level.emit(0)
        self._set_state("idle")

    def release(self, idle_seconds):
        """Unused for `idle_seconds`: close the recognizer to free its model. The next recording starts it again."""
        if (not self.busy and self.process.state() != QProcess.ProcessState.NotRunning
                and time.monotonic() - getattr(self, "last_used", 0.0) >= idle_seconds):
            self._stopping = True
            self.process.kill()
            return True
        return False

    def shutdown(self):
        self.cancel()
        if self.process.state() != QProcess.ProcessState.NotRunning:
            self.process.waitForFinished(1500)

    @Slot()
    def _read(self):
        self._buffer.extend(bytes(self.process.readAllStandardOutput()))
        while b"\n" in self._buffer:
            line, _, rest = self._buffer.partition(b"\n")
            self._buffer = bytearray(rest)
            try:
                event = json.loads(line)
            except (ValueError, UnicodeError):
                continue
            if not isinstance(event, dict):
                continue
            if event.get("type") == "devices" and event.get("id") == self._device_id:
                self.devices.emit(event.get("devices", []))
                continue
            if event.get("type") == "error" and event.get("id") == self._device_id:
                self.failed.emit(event.get("message", "Could not list microphones."))
                continue
            if not self._active_id or event.get("id") != self._active_id:
                continue
            kind = event.get("type")
            if kind == "status":
                state = event.get("state")
                if state in {"recording", "listening"}:
                    if self.state in {"opening", "listening"}:
                        self._set_state(state)
                        self.deadline.start(35_000 if state == "listening" else 65_000)
                elif state in {"transcribing", "loading"}:
                    self._set_state(state)
                    self.deadline.start(600_000)
            elif kind == "level":
                self.level.emit(event.get("value", 0))
            elif kind in {"transcript", "error"}:
                self.deadline.stop()
                self._active_id = ""
                self.level.emit(0)
                self._set_state("idle")
                if kind == "transcript":
                    self.transcribed.emit(event.get("text", ""))
                else:
                    self.failed.emit(event.get("message", "Microphone transcription failed."))

    @Slot()
    def _drain_errors(self):
        self.process.readAllStandardError()

    @Slot(int, QProcess.ExitStatus)
    def _exited(self, code, status):
        expected = self._stopping
        self._stopping = False
        self._buffer.clear()
        if expected and self._pending:
            self.process.start()
        elif self.busy:
            self.cancel()
            self.failed.emit("The microphone engine stopped. Please try again.")

    @Slot(QProcess.ProcessError)
    def _process_error(self, error):
        if error == QProcess.ProcessError.FailedToStart:
            self.cancel()
            self.failed.emit("Could not start the microphone engine. Check your Python environment.")

    @Slot()
    def _timed_out(self):
        if self.state == "recording":
            self.finish()
        else:
            self.cancel()
            self.failed.emit("Microphone setup or transcription took too long. Please try again.")
