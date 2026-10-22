import ctypes
from ctypes import wintypes
import unittest

from PySide6.QtCore import QObject, Signal

from companion.hotkey import HOTKEY_ID, WM_HOTKEY, _NativeFilter


class HotkeyTests(unittest.TestCase):
    def test_native_dispatcher_message_activates_only_our_hotkey(self):
        class Receiver(QObject):
            activated = Signal()
        receiver = Receiver()
        activations = []
        receiver.activated.connect(lambda: activations.append(True))
        native = _NativeFilter(receiver.activated)
        message = wintypes.MSG()
        message.message = WM_HOTKEY
        message.wParam = HOTKEY_ID
        self.assertEqual(native.nativeEventFilter(b"windows_dispatcher_MSG", ctypes.addressof(message)), (True, 0))
        self.assertEqual(activations, [True])
        message.wParam = 0
        self.assertEqual(native.nativeEventFilter(b"windows_dispatcher_MSG", ctypes.addressof(message)), (False, 0))
        self.assertEqual(activations, [True])
