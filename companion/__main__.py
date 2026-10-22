import sys

from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtCore import QEvent

from .config import load_settings
from .ui import CompanionWindow
from .hotkey import RecordingHotkey


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Desktop Companion")
    app.setStyle("Fusion")
    try:
        settings = load_settings()
    except (OSError, ValueError) as exc:
        QMessageBox.critical(None, "Could not start companion", str(exc))
        return 1
    window = CompanionWindow(settings)
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


if __name__ == "__main__":
    raise SystemExit(main())

