"""Rebuild the shortcut icon from the same local drawing as the window and tray icon."""

import os
from pathlib import Path
import struct
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from PySide6.QtCore import QBuffer, QIODevice
from PySide6.QtWidgets import QApplication
from companion.theme import moon_icon

SIZES = (16, 20, 24, 32, 40, 48, 64, 96, 128, 256)


def png_bytes(size):
    # Draw at each size rather than scaling one bitmap, so small sizes stay crisp.
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    if not moon_icon(size).pixmap(size, size).save(buffer, "PNG"):
        raise SystemExit(f"Qt could not render the {size}px icon.")
    return bytes(buffer.data())


app = QApplication([])
images = [(size, png_bytes(size)) for size in SIZES]
header = struct.pack("<HHH", 0, 1, len(images))
offset = len(header) + 16 * len(images)
entries, data = b"", b""
for size, image in images:
    # ICO directory entry; 0 means 256. PNG-compressed entries are supported since Windows Vista.
    entries += struct.pack("<BBBBHHII", size % 256, size % 256, 0, 0, 1, 32, len(image), offset + len(data))
    data += image
output = ROOT / "assets" / "jingliu.ico"
output.parent.mkdir(parents=True, exist_ok=True)
output.write_bytes(header + entries + data)
print("Wrote assets/jingliu.ico")
