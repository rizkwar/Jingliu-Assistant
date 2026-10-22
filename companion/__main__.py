import sys
import sqlite3

from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtCore import QEvent

from .config import load_settings
from .ui import CompanionWindow
from .hotkey import RecordingHotkey
from .storage import Store


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Desktop Companion")
    app.setStyle("Fusion")
    try:
        settings = load_settings()
        store = Store()
        window = CompanionWindow(settings, store=store)
    except (OSError, ValueError, sqlite3.Error) as exc:
        QMessageBox.critical(None, "Could not start companion", str(exc))
        return 1
    hotkey = RecordingHotkey(app)
    hotkey.activated.connect(window._toggle_recording)
    if not hotkey.register():
        window.mic_hint.setText("Hold the button to talk · Ctrl+Alt+Space is unavailable · 60-second limit")
    window.show()
    try:
        return app.exec()
    finally:
        hotkey.unregister()
        window.microphone.shutdown()
        window.speech.shutdown()
        window.deleteLater()
        app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        store.close()


if __name__ == "__main__":
    raise SystemExit(main())

