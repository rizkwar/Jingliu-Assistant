"""Rebuild the shortcut icon from the same local drawing as the tray icon."""

import os
from pathlib import Path
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from PySide6.QtWidgets import QApplication
from companion.background import companion_icon

app = QApplication([])
output = ROOT / "assets" / "mira.ico"
output.parent.mkdir(parents=True, exist_ok=True)
if not companion_icon().pixmap(64, 64).save(str(output), "ICO"):
    raise SystemExit("Qt could not write the shortcut icon.")
print("Wrote assets/mira.ico")
