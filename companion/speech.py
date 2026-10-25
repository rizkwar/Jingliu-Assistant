"""Qt controller for a lazy, reusable local speech process."""

import json
import math
import time
from collections import deque
from pathlib import Path
import sys
from uuid import uuid4

from PySide6.QtCore import QObject, QProcess, QProcessEnvironment, Qt, QTimer, Signal, Slot

from .config import PROJECT_ROOT
from .speech_text import SpeechSegmenter, spoken_text
from .voice_settings import validate_rate

# The natural voice engine has its own environment; see scripts/Setup-Chatterbox.ps1.
CHATTERBOX_PYTHON = PROJECT_ROOT / ".cache" / "voice-lab" / "venv" / "Scripts" / "python.exe"
ENGINES = ("pocket", "chatterbox")


class SpeechController(QObject):
    changed = Signal(str)
    failed = Signal(str)
    spoken = Signal(str)
    playback_level = Signal(float)
    playback_reset = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.state = "idle"
        self._active_id = ""
        self._pending = None
        self._stopping = False
        self._buffer = bytearray()
        self._queue = deque()
        self._segmenter = None
        self._stream_open = False
        self._session_active = False
        self._current_text = ""
        self._warming = False  # A background model load that new speech waits for, not cancels.
        self.last_used = time.monotonic()  # Every job and engine event; idle closing goes by this.
        self._voice = "alba"
        self._volume = 70
        self._rate = 100
        self.engine = "pocket"
        self.process = QProcess(self)
        self.process.setWorkingDirectory(str(PROJECT_ROOT))
        self._configure_program()
        env = QProcessEnvironment.systemEnvironment()
        env.remove("OPENROUTER_API_KEY")
        env.insert("HF_HOME", str(PROJECT_ROOT / ".cache" / "huggingface"))
        env.insert("HF_HUB_DISABLE_TELEMETRY", "1")
        env.insert("PYTHONIOENCODING", "utf-8")
        env.insert("TQDM_DISABLE", "1")  # Chatterbox's per-step progress bar costs time and goes nowhere.
        self.process.setProcessEnvironment(env)
        self._hf_token = env.value("HF_TOKEN", "")
        self.process.started.connect(self._dispatch)
        self.process.readyReadStandardOutput.connect(self._read)
        self.process.readyReadStandardError.connect(self._drain_errors)
        self.process.finished.connect(self._exited)
        self.process.errorOccurred.connect(self._process_error)
        self.deadline = QTimer(self)
        self.deadline.setSingleShot(True)
        self.deadline.setInterval(600_000)
        self.deadline.timeout.connect(self._timed_out)
        self._levels = deque(maxlen=128)
        self._level_timer = QTimer(self)
        self._level_timer.setSingleShot(True)
        self._level_timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._level_timer.timeout.connect(self._deliver_levels)
        self._level_watchdog = QTimer(self)
        self._level_watchdog.setSingleShot(True)
        self._level_watchdog.setInterval(200)
        self._level_watchdog.timeout.connect(self.playback_reset.emit)

    @property
    def busy(self):
        return bool(self._active_id or self._queue or self._stream_open)

    def _report(self, text, state):
        self.state = state
        self.changed.emit(text)

    def _configure_program(self):
        if self.engine == "chatterbox":
            self.process.setProgram(str(CHATTERBOX_PYTHON))
        else:
            # pythonw has no console streams; use the same venv's console executable for pipes.
            executable = Path(sys.executable)
            if executable.name.lower() == "pythonw.exe":
                executable = executable.with_name("python.exe")
            self.process.setProgram(str(executable))
        self.process.setArguments(["-u", "-m", "companion.speech_process", "--engine", self.engine])

    def set_engine(self, engine):
        """Pocket TTS (fast, CPU) or Chatterbox (more natural, best on a GPU)."""
        engine = engine if engine in ENGINES else "pocket"
        if engine == self.engine:
            return
        self.shutdown()  # The next phrase starts the chosen engine's process.
        self.engine = engine
        self._configure_program()
        env = self.process.processEnvironment()
        cache = ".cache/voice-lab/hf" if engine == "chatterbox" else ".cache/huggingface"
        env.insert("HF_HOME", str(PROJECT_ROOT / cache))
        self.process.setProcessEnvironment(env)

    @staticmethod
    def chatterbox_installed():
        return CHATTERBOX_PYTHON.is_file()

    def set_hf_token(self, token):
        if token == self._hf_token:
            return
        self.shutdown()
        env = self.process.processEnvironment()
        if token:
            env.insert("HF_TOKEN", token)
        else:
            env.remove("HF_TOKEN")
        self._hf_token = token
        self.process.setProcessEnvironment(env)

    def warm(self, voice):
        """Load the voice engine in the background (Pocket ~20 s, Chatterbox longer) so her next reply
        starts sooner. Does nothing while the engine is already running."""
        if self.busy or self.process.state() != QProcess.ProcessState.NotRunning:
            return
        self._voice = voice
        self._warming = True
        self._session_active = True  # So it ends with "Voice ready", not a lingering "Loading voice…".
        self._queue.append(("prepare", ""))
        self._advance()

    def speak(self, text, voice, volume, rate=100):
        self.stop(keep_warmup=True)
        self._rate = validate_rate(rate)
        if volume <= 0:
            self._report("Voice muted", "idle")
            return
        text = spoken_text(text)
        if not text:
            self._report("No spoken text", "idle")
            return
        self._voice, self._volume = voice, volume
        self._session_active = True
        self._queue.append(("speak", text))
        self._advance()

    def begin_reply(self, voice, volume, rate=100):
        """Warm the voice while the language model thinks; enqueue phrases as they arrive."""
        self.stop(keep_warmup=True)
        self._rate = validate_rate(rate)
        if volume <= 0:
            self._report("Voice muted", "idle")
            return
        self._voice, self._volume = voice, volume
        self._segmenter = SpeechSegmenter()
        self._stream_open = True
        self._session_active = True
        self._queue.append(("prepare", ""))
        self._advance()

    def feed_reply(self, text):
        if self._segmenter is not None:
            self._enqueue(self._segmenter.feed(text))
            self._advance()

    def _enqueue(self, phrases):
        for phrase in phrases:
            self._queue.append(("speak", phrase))
            self._announce(phrase)

    def _announce(self, phrase):
        """Chatterbox renders slower than it speaks: let it start on phrases it will say next."""
        if self.engine == "chatterbox" and self.process.state() == QProcess.ProcessState.Running and not self._stopping:
            self.process.write((json.dumps({"id": "", "action": "ahead", "text": phrase, "voice": self._voice})
                                + "\n").encode("utf-8"))

    def finish_reply(self):
        if self._segmenter is None:
            return
        self._enqueue(self._segmenter.finish())
        self._segmenter = None
        self._stream_open = False
        self._advance()

    def _advance(self):
        if self._active_id:
            return
        if not self._queue:
            if self._stream_open:
                self._report("Waiting for next phrase…", "waiting")
            elif self._session_active:
                self._session_active = False
                self._report("Voice ready", "idle")
            return
        action, text = self._queue.popleft()
        self.last_used = time.monotonic()
        self._current_text = text
        self._active_id = uuid4().hex
        self._pending = {
            "id": self._active_id, "action": action, "text": text,
            "voice": self._voice, "volume": self._volume, "rate": self._rate,
        }
        self._report("Loading voice…" if action == "prepare" else "Preparing speech…",
                     "loading" if action == "prepare" else "preparing")
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

    def stop(self, keep_warmup=False):
        if keep_warmup and self._warming and self._active_id and not self._queue:
            # The model is still loading in the background: new speech queues behind it.
            self._warming = False
            self._reset_playback()
            self._segmenter = None
            self._stream_open = False
            return
        self._warming = False
        self._reset_playback()
        was_busy = self.busy
        self.state = "idle"
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
            self._report("Voice stopped", "idle")

    def release(self, idle_seconds):
        """Unused for `idle_seconds`: close the engine to free its model. The next phrase starts it again."""
        if (not self.busy and self.process.state() != QProcess.ProcessState.NotRunning
                and time.monotonic() - self.last_used >= idle_seconds):
            self._stopping = True
            self.process.kill()
            return True
        return False

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
            if kind == "playback":
                self._accept_level(event)
            elif kind == "status":
                labels = {"loading": "Loading voice…", "preparing": "Preparing speech…", "speaking": "Speaking…"}
                state = event.get("state")
                self._report(labels.get(state, "Preparing speech…"), state if state in labels else "preparing")
            elif kind == "done":
                self.last_used = time.monotonic()
                self._warming = False
                self._reset_playback()
                self.deadline.stop()
                self._active_id = ""
                text, self._current_text = self._current_text, ""
                if text:
                    self.spoken.emit(text)
                self._advance()
            elif kind == "error":
                self._fail(event.get("message", "Voice playback failed. Text chat still works."))
            elif kind == "info" and isinstance(event.get("message"), str):
                self.changed.emit(event["message"][:300])

    def _reset_playback(self):
        self._level_timer.stop()
        self._level_watchdog.stop()
        self._levels.clear()
        self.playback_reset.emit()

    def _accept_level(self, event):
        level, at = event.get('level'), event.get('at')
        if (type(level) not in (float, int) or type(at) not in (float, int)
                or not math.isfinite(level) or not math.isfinite(at)
                or not 0 <= level <= 1 or not -.5 <= at - time.monotonic() <= 2):
            return
        if self._levels and at < self._levels[-1][0]:
            return
        self._levels.append((at, self._active_id, level))
        if not self._level_timer.isActive():
            self._deliver_levels()

    @Slot()
    def _deliver_levels(self):
        now = time.monotonic()
        latest = None
        while self._levels and self._levels[0][0] <= now:
            latest = self._levels.popleft()
        if latest is not None and latest[1] == self._active_id and self._active_id:
            # After a blocked UI, skip obsolete mouth frames rather than replaying.
            if now - latest[0] < .2:
                self.playback_level.emit(latest[2])
                self._level_watchdog.start()
            else:
                self.playback_reset.emit()
        if self._levels:
            self._level_timer.start(max(1, math.ceil((self._levels[0][0] - time.monotonic()) * 1000)))

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
            self._fail("Chatterbox is not installed yet. Run Setup Chatterbox.cmd, or switch the voice engine to "
                       "Pocket TTS in Settings." if self.engine == "chatterbox" else
                       "Could not start the voice engine. Check your Python environment.")

    def _fail(self, message):
        self.stop()
        self._report("Voice unavailable", "error")
        self.failed.emit(message)

    @Slot()
    def _timed_out(self):
        self._fail("Voice setup or playback took too long. Check your connection and try Preview again.")
