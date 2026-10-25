import os
import signal
import sys
import sqlite3

from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtCore import QEvent, QLockFile

from .config import PROJECT_ROOT, load_settings
from .ui import CompanionWindow
from .hotkey import RecordingHotkey
from .storage import Store
from .preferences import Preferences
from .background import TrayController


def main() -> int:
    # The see-through avatar window is a web page. With Qt's default Direct3D 11 backend it
    # sometimes showed a frame with the page (or parts of it) missing; OpenGL hands each
    # frame over intact. Set before the application exists; a user's own choice still wins.
    os.environ.setdefault("QSG_RHI_BACKEND", "opengl")
    app = QApplication(sys.argv)
    app.setApplicationName("Desktop Companion")
    app.setStyle("Fusion")
    data_dir = PROJECT_ROOT / "data"
    store = None
    try:
        data_dir.mkdir(parents=True, exist_ok=True)
        instance_lock = QLockFile(str(data_dir / "companion.lock"))
        instance_lock.setStaleLockTime(0)
        if not instance_lock.tryLock(0):
            if instance_lock.error() != QLockFile.LockError.LockFailedError:
                raise OSError("Could not lock the data folder. Check that this folder is writable.")
            QMessageBox.information(None, "Companion already running", "The companion may already be in your system tray (including the hidden icons). Open it from there. If another copy is starting, wait for its window.")
            return 0
        settings = load_settings()
        preferences = Preferences(data_dir / "preferences.json")
        try:
            settings = preferences.load(settings)
        except (OSError, ValueError) as exc:
            QMessageBox.warning(None, "Using default preferences", f"{exc}\nUsing .env defaults for this session. Open Settings and Save defaults to repair the preferences file.")
        store = Store()
        window = CompanionWindow(settings, store=store, preferences=preferences)
    except (OSError, ValueError, sqlite3.Error) as exc:
        if store is not None:
            store.close()
        QMessageBox.critical(None, "Could not start companion", str(exc))
        return 1
    tray = TrayController(window, app)
    tray_available = tray.start()
    app.setQuitOnLastWindowClosed(not tray_available)
    window.closed.connect(app.quit)
    hotkey = RecordingHotkey(app)
    hotkey.activated.connect(window._toggle_recording)
    if not hotkey.register():
        window.mic_hint.setText("Hold the button to talk · Ctrl+Alt+Space is unavailable · 60-second limit")
    window.show()
    try:
        return app.exec()
    finally:
        tray.shutdown()
        window.avatar.shutdown()
        hotkey.unregister()
        if window._worker:
            window._worker.stop()
            window._worker.wait()
            window._on_finished()
        window.microphone.shutdown()
        window.speech.shutdown()
        if os.environ.get("QSG_RHI_BACKEND") == "opengl":
            # Destroying the web views under OpenGL stalls in the graphics driver for about
            # fifteen seconds. Everything is saved and closed by now: end the process directly.
            store.close()
            instance_lock.unlock()
            for stream in (sys.stdout, sys.stderr):
                if stream is not None:  # pythonw has no console streams at all.
                    stream.flush()
            os.kill(os.getpid(), signal.SIGTERM)
        window.deleteLater()
        app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        store.close()
        instance_lock.unlock()


if __name__ == "__main__":
    raise SystemExit(main())

