import sys

from PySide6.QtWidgets import QApplication, QMessageBox

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
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())

