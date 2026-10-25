"""A screenshot of the person's screen for her to look at, without her own windows in it.

Only the monitor the mouse is on is captured (where the person is looking). Jingliu's windows
are left out by asking Windows to exclude them from capture for that instant only, so they
still appear in the person's own screen recordings.
"""

import sys
import tempfile
import time
from pathlib import Path

WDA_NONE, WDA_EXCLUDEFROMCAPTURE = 0x0, 0x11


def _set_affinity(windows, affinity):
    if sys.platform != "win32":
        return []
    import ctypes
    from ctypes import wintypes
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.SetWindowDisplayAffinity.argtypes = (wintypes.HWND, wintypes.DWORD)
    user32.SetWindowDisplayAffinity.restype = wintypes.BOOL
    changed = []
    for window in windows:
        if window is None or not window.isVisible():
            continue
        handle = wintypes.HWND(int(window.winId()))
        if user32.SetWindowDisplayAffinity(handle, affinity):
            changed.append(window)
    return changed


def capture(exclude=(), folder=None):
    """Save the monitor under the mouse as a PNG and return its path, leaving out `exclude`."""
    from PySide6.QtGui import QCursor, QGuiApplication
    screen = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
    hidden = _set_affinity(exclude, WDA_EXCLUDEFROMCAPTURE)
    try:
        if hidden:
            time.sleep(0.12)  # The desktop compositor applies it on its next frame.
        pixmap = screen.grabWindow(0)
    finally:
        _set_affinity(hidden, WDA_NONE)
    folder = Path(folder or tempfile.mkdtemp(prefix="companion-screen-"))
    path = folder / f"screen-{time.strftime('%Y%m%d-%H%M%S')}.png"
    if pixmap.isNull() or not pixmap.save(str(path), "PNG"):
        raise OSError("The screen could not be captured.")
    return path
