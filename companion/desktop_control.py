"""See the screen and use the mouse and keyboard on Windows, for approved computer tasks.

Coordinates are in screenshot pixels; each screenshot reports its scale so clicks map
back to physical screen pixels. Windows input goes through SendInput (no dependencies).
"""

import ctypes
from ctypes import wintypes
import time

MAX_WIDTH = 1366  # Readable for the model, small enough to send quickly.

user32 = ctypes.windll.user32 if hasattr(ctypes, "windll") else None
ULONG_PTR = ctypes.c_size_t


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [("uMsg", wintypes.DWORD), ("wParamL", wintypes.WORD), ("wParamH", wintypes.WORD)]


class _UNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("union", _UNION)]


MOUSE, KEYBOARD = 0, 1
MOVE, ABSOLUTE, VIRTUALDESK, WHEEL = 0x0001, 0x8000, 0x4000, 0x0800
BUTTONS = {"left": (0x0002, 0x0004), "right": (0x0008, 0x0010), "middle": (0x0020, 0x0040)}
KEYUP, UNICODE = 0x0002, 0x0004
KEYS = {
    "ctrl": 0x11, "control": 0x11, "shift": 0x10, "alt": 0x12, "win": 0x5B, "windows": 0x5B,
    "enter": 0x0D, "return": 0x0D, "tab": 0x09, "esc": 0x1B, "escape": 0x1B, "space": 0x20,
    "backspace": 0x08, "delete": 0x2E, "del": 0x2E, "insert": 0x2D, "home": 0x24, "end": 0x23,
    "pageup": 0x21, "pagedown": 0x22, "up": 0x26, "down": 0x28, "left": 0x25, "right": 0x27,
    "capslock": 0x14, "printscreen": 0x2C, "menu": 0x5D,
    **{f"f{n}": 0x6F + n for n in range(1, 13)},
}


def _send(*inputs):
    array = (INPUT * len(inputs))(*inputs)
    if user32.SendInput(len(inputs), array, ctypes.sizeof(INPUT)) != len(inputs):
        raise OSError("Windows blocked the input (an elevated window may be focused).")


def _virtual_screen():
    # SM_XVIRTUALSCREEN, SM_YVIRTUALSCREEN, SM_CXVIRTUALSCREEN, SM_CYVIRTUALSCREEN: all monitors.
    return tuple(user32.GetSystemMetrics(index) for index in (76, 77, 78, 79))


def dpi_aware():
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # Per-monitor: physical pixels everywhere.
    except (AttributeError, OSError):
        user32.SetProcessDPIAware()


def screenshot(path):
    """Capture every monitor. Returns (width, height, scale) of the saved, downscaled PNG."""
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QGuiApplication
    app = QGuiApplication.instance() or QGuiApplication([])
    left, top, width, height = _virtual_screen()
    screen = app.primaryScreen()
    ratio = screen.devicePixelRatio()
    image = screen.grabWindow(0, int(left / ratio), int(top / ratio), int(width / ratio), int(height / ratio)).toImage()
    scale = min(1.0, MAX_WIDTH / max(1, image.width()))
    if scale < 1:
        image = image.scaledToWidth(int(image.width() * scale), Qt.TransformationMode.SmoothTransformation)
    image.save(str(path), "PNG")
    # Screenshot pixel → physical pixel: physical = left + x * (width / shot width).
    return image.width(), image.height(), width / image.width()


def _to_screen(x, y, factor):
    left, top, width, height = _virtual_screen()
    px, py = left + x * factor, top + y * factor
    if not (left <= px < left + width and top <= py < top + height):
        raise ValueError("That point is outside the screen.")
    # Absolute coordinates are 0..65535 across the virtual desktop.
    return int((px - left) * 65535 / max(1, width - 1)), int((py - top) * 65535 / max(1, height - 1))


def move(x, y, factor):
    ax, ay = _to_screen(x, y, factor)
    _send(INPUT(MOUSE, _UNION(mi=MOUSEINPUT(ax, ay, 0, MOVE | ABSOLUTE | VIRTUALDESK, 0, 0))))


def click(x, y, factor, button="left", count=1):
    down, up = BUTTONS.get(button, BUTTONS["left"])
    move(x, y, factor)
    time.sleep(.05)
    for _ in range(max(1, min(3, count))):
        _send(INPUT(MOUSE, _UNION(mi=MOUSEINPUT(0, 0, 0, down, 0, 0))),
              INPUT(MOUSE, _UNION(mi=MOUSEINPUT(0, 0, 0, up, 0, 0))))
        time.sleep(.06)


def scroll(x, y, factor, amount):
    """amount: positive scrolls up, negative down, in notches."""
    move(x, y, factor)
    _send(INPUT(MOUSE, _UNION(mi=MOUSEINPUT(0, 0, ctypes.c_ulong(int(amount) * 120 & 0xFFFFFFFF).value, WHEEL, 0, 0))))


def type_text(text):
    for character in text:
        if character == "\n":
            press("enter")
            continue
        code = ord(character)
        units = [code] if code <= 0xFFFF else [0xD800 + ((code - 0x10000) >> 10), 0xDC00 + ((code - 0x10000) & 0x3FF)]
        for unit in units:
            _send(INPUT(KEYBOARD, _UNION(ki=KEYBDINPUT(0, unit, UNICODE, 0, 0))),
                  INPUT(KEYBOARD, _UNION(ki=KEYBDINPUT(0, unit, UNICODE | KEYUP, 0, 0))))
        time.sleep(.004)


def press(combination):
    """A key or combination such as "enter", "ctrl+s", "alt+tab", "win+r"."""
    codes = []
    for name in [part.strip().lower() for part in combination.split("+") if part.strip()]:
        if name in KEYS:
            codes.append(KEYS[name])
        elif len(name) == 1 and (name.isalnum()):
            codes.append(ord(name.upper()))
        else:
            raise ValueError(f"Unknown key: {name}")
    if not codes:
        raise ValueError("No key given.")
    _send(*[INPUT(KEYBOARD, _UNION(ki=KEYBDINPUT(code, 0, 0, 0, 0))) for code in codes])
    _send(*[INPUT(KEYBOARD, _UNION(ki=KEYBDINPUT(code, 0, KEYUP, 0, 0))) for code in reversed(codes)])
