import sys

from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtCore import QEvent

from .config import load_settings
from .ui import CompanionWindow


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
    window.show()
    try:
        return app.exec()
    finally:
        window.speech.shutdown()
        window.deleteLater()
        app.sendPostedEvents(None, QEvent.Type.DeferredDelete)


if __name__ == "__main__":
    raise SystemExit(main())

