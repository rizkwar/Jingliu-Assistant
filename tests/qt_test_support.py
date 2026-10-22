"""One offscreen application with explicit fonts for Windows Qt tests."""

import os
from pathlib import Path
import sys

from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import QApplication


_app = None


def application():
    global _app
    if _app is None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        _app = QApplication.instance() or QApplication([])
        # The offscreen plugin does not discover Windows system fonts itself.
        if sys.platform == "win32" and _app.platformName() == "offscreen":
            fonts = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
            for name in ("segoeui.ttf", "seguisb.ttf"):
                if (fonts / name).is_file():
                    QFontDatabase.addApplicationFont(str(fonts / name))
    return _app


# Initialize before discovery imports optional native audio/scientific libraries.
# Keep one strong application reference for the entire test process.
application()
