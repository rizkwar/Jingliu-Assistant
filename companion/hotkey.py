"""A Windows hotkey using the OS message loop, without a keyboard hook."""

import ctypes
from ctypes import wintypes
import sys

from PySide6.QtCore import QAbstractNativeEventFilter, QCoreApplication, QObject, Signal


HOTKEY_ID = 0x4D49
WM_HOTKEY = 0x0312


class _NativeFilter(QAbstractNativeEventFilter):
    def __init__(self, activated):
        super().__init__()
        self.activated = activated

    def nativeEventFilter(self, event_type, message):
        if event_type in (b"windows_generic_MSG", b"windows_dispatcher_MSG"):
            msg = wintypes.MSG.from_address(int(message))
            if msg.message == WM_HOTKEY and msg.wParam == HOTKEY_ID:
                self.activated.emit()
                return True, 0
        return False, 0


class RecordingHotkey(QObject):
    activated = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.registered = False
        self.filter = _NativeFilter(self.activated)

    def register(self):
        if self.registered:
            return True
        if sys.platform != "win32":
            return False
        user32 = ctypes.windll.user32
        user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
        user32.RegisterHotKey.restype = wintypes.BOOL
        self.registered = bool(user32.RegisterHotKey(None, HOTKEY_ID, 0x4000 | 0x0001 | 0x0002, 0x20))
        if self.registered:
            QCoreApplication.instance().installNativeEventFilter(self.filter)
        return self.registered

    def unregister(self):
        if self.registered:
            QCoreApplication.instance().removeNativeEventFilter(self.filter)
            ctypes.windll.user32.UnregisterHotKey(None, HOTKEY_ID)
            self.registered = False
