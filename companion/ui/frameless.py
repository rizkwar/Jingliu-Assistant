"""A window without Windows' title bar, like Claude's desktop app: her header is the title bar, with thin
minimize, maximize and close buttons in its corner.

The window keeps its native frame styles underneath, so Windows still gives it a shadow, rounded corners,
minimize and maximize animations, Snap (drag to an edge, or hover the maximize button for Snap Layouts) and
the system menu; WM_NCCALCSIZE takes the visible frame away and WM_NCHITTEST says which parts drag, resize
or maximize. Elsewhere (other platforms, tests) the ordinary frame stays."""
import ctypes
import sys

from PySide6.QtCore import QEvent, QObject, QSize, Qt, QTimer
from PySide6.QtGui import QCursor, QGuiApplication
from PySide6.QtWidgets import (QAbstractButton, QAbstractScrollArea, QAbstractSlider, QAbstractSpinBox, QComboBox,
                               QHBoxLayout, QLineEdit, QPushButton, QTabBar, QWidget)

WM_NCCALCSIZE, WM_NCHITTEST = 0x0083, 0x0084
WM_NCLBUTTONDOWN, WM_NCLBUTTONUP, WM_NCLBUTTONDBLCLK = 0x00A1, 0x00A2, 0x00A3
HTCAPTION, HTMAXBUTTON = 2, 9
HTLEFT, HTRIGHT, HTTOP, HTTOPLEFT, HTTOPRIGHT, HTBOTTOM, HTBOTTOMLEFT, HTBOTTOMRIGHT = 10, 11, 12, 13, 14, 15, 16, 17
BORDER = 6          # Logical pixels at the edge that resize the window.
GLYPHS = {'minimize': '', 'maximize': '', 'restore': '', 'close': ''}
INTERACTIVE = (QAbstractButton, QLineEdit, QComboBox, QAbstractScrollArea, QAbstractSpinBox, QAbstractSlider, QTabBar)


def available():
    return sys.platform == 'win32' and QGuiApplication.platformName() == 'windows'


class RECT(ctypes.Structure):
    _fields_ = [('left', ctypes.c_long), ('top', ctypes.c_long), ('right', ctypes.c_long), ('bottom', ctypes.c_long)]


class MONITORINFO(ctypes.Structure):
    _fields_ = [('cbSize', ctypes.c_ulong), ('rcMonitor', RECT), ('rcWork', RECT), ('dwFlags', ctypes.c_ulong)]


def work_area(hwnd):
    """The work area (the screen less the taskbar) of the monitor the window is on, in physical pixels."""
    user32 = ctypes.windll.user32
    user32.MonitorFromWindow.restype = ctypes.c_void_p
    monitor = user32.MonitorFromWindow(ctypes.c_void_p(hwnd), 2)  # The nearest monitor.
    info = MONITORINFO()
    info.cbSize = ctypes.sizeof(MONITORINFO)
    if not monitor or not user32.GetMonitorInfoW(ctypes.c_void_p(monitor), ctypes.byref(info)):
        return None
    return info.rcWork


class WindowControls(QWidget):
    """Minimize, maximize (restore) and close, as thin Windows 11 caption glyphs."""

    def __init__(self, window, parent=None):
        super().__init__(parent)
        self.window = window
        self.setObjectName('windowControls')
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        self.minimize = self._button('minimize', 'Minimize', window.showMinimized)
        self.maximize = self._button('maximize', 'Maximize', self.toggle)
        self.close = self._button('close', 'Close', window.close, 'captionClose')
        for button in (self.minimize, self.maximize, self.close):
            row.addWidget(button)

    def _button(self, glyph, tip, slot, name='caption'):
        button = QPushButton(GLYPHS[glyph])
        button.setObjectName(name)
        button.setToolTip(tip)
        button.setFixedSize(QSize(46, 36))
        button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        button.clicked.connect(slot)
        return button

    def toggle(self):
        self.window.showNormal() if self.window.isMaximized() else self.window.showMaximized()

    def refresh(self):
        maximized = self.window.isMaximized()
        self.maximize.setText(GLYPHS['restore' if maximized else 'maximize'])
        self.maximize.setToolTip('Restore down' if maximized else 'Maximize')

    def hover_maximize(self, hovered, pressed=False):
        """Windows owns the maximize button's mouse (for Snap Layouts), so its hover is set from here."""
        state = 'pressed' if pressed else 'hover' if hovered else ''
        if self.maximize.property('state') != state:
            self.maximize.setProperty('state', state)
            self.maximize.style().unpolish(self.maximize)
            self.maximize.style().polish(self.maximize)


class Frame(QObject):
    """Makes `window` frameless on Windows. `drag(point)` says whether a window point is title bar."""

    def __init__(self, window, controls, drag):
        super().__init__(window)
        self.window, self.controls, self.drag = window, controls, drag
        self.active = available()
        controls.setVisible(self.active)
        if self.active:
            window.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
        window.installEventFilter(self)
        self.prepared = False

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.Show and not self.prepared and self.active:
            self.prepared = True
            self._native_styles()
        elif event.type() == QEvent.Type.WindowStateChange:
            self.controls.refresh()
            if self.prepared:
                QTimer.singleShot(0, self._frame_changed)  # Once Windows has the new state: fit it again.
        elif event.type() == QEvent.Type.Show and self.prepared and self.window.isMaximized():
            QTimer.singleShot(0, self._frame_changed)  # Back from the tray, maximized.
        return False

    def _frame_changed(self):
        """Asks Windows to work out the window's frame again (WM_NCCALCSIZE), so maximized content fits, with
        square corners and no border while maximized (after a restore, Windows would keep rounding them)."""
        try:
            hwnd = ctypes.c_void_p(int(self.window.winId()))
            self._corners(hwnd)
            ctypes.windll.user32.SetWindowPos(hwnd, None, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0004 | 0x0010 | 0x0020)
        except (OSError, AttributeError):
            pass

    def _corners(self, hwnd):
        maximized = bool(ctypes.windll.user32.IsZoomed(hwnd))
        dwm = ctypes.windll.dwmapi
        corner = ctypes.c_int(1 if maximized else 2)  # Square when maximized, round otherwise (Windows 11).
        dwm.DwmSetWindowAttribute(hwnd, 33, ctypes.byref(corner), ctypes.sizeof(corner))
        border = ctypes.c_uint(0xFFFFFFFE if maximized else 0xFFFFFFFF)  # No border line, or the default.
        dwm.DwmSetWindowAttribute(hwnd, 34, ctypes.byref(border), ctypes.sizeof(border))

    def _native_styles(self):
        """Gives the frameless window back the styles behind the shadow, snapping and animations."""
        try:
            user32, dwm = ctypes.windll.user32, ctypes.windll.dwmapi
            hwnd = ctypes.c_void_p(int(self.window.winId()))
            get = user32.GetWindowLongPtrW
            get.restype = ctypes.c_ssize_t
            style = get(hwnd, -16)
            style |= 0x00C00000 | 0x00040000 | 0x00020000 | 0x00010000 | 0x00080000  # Caption, frame, min, max, menu.
            user32.SetWindowLongPtrW(hwnd, -16, ctypes.c_ssize_t(style))

            class MARGINS(ctypes.Structure):
                _fields_ = [('left', ctypes.c_int), ('right', ctypes.c_int), ('top', ctypes.c_int), ('bottom', ctypes.c_int)]
            dwm.DwmExtendFrameIntoClientArea(hwnd, ctypes.byref(MARGINS(0, 0, 1, 0)))  # The drop shadow.
            corner = ctypes.c_int(2)  # Windows 11: round corners.
            dwm.DwmSetWindowAttribute(hwnd, 33, ctypes.byref(corner), ctypes.sizeof(corner))
            user32.SetWindowPos(hwnd, None, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0004 | 0x0010 | 0x0020)  # Frame changed.
        except (OSError, AttributeError):
            pass

    def native_event(self, event_type, message):
        """(handled, result) for the window's nativeEvent, or None to leave the message to Qt."""
        if not self.active or event_type != b'windows_generic_MSG':
            return None
        from ctypes import wintypes
        msg = wintypes.MSG.from_address(int(message))
        if msg.message == WM_NCCALCSIZE and msg.wParam:
            # Windows' own idea of the state, not Qt's: they differ for a moment after the tray or a minimize.
            if ctypes.windll.user32.IsZoomed(msg.hWnd):
                # Maximized, the content fills the monitor's work area exactly. Windows usually hangs the frame off
                # the screen's edges, but after a restore it may not, so a fixed inset would leave a gap.
                work = work_area(msg.hWnd)
                if work is not None:
                    rect = RECT.from_address(msg.lParam)
                    rect.left, rect.top, rect.right, rect.bottom = work.left, work.top, work.right, work.bottom
            return True, 0
        if msg.message == WM_NCHITTEST:
            hit = self.hit(self.window.mapFromGlobal(QCursor.pos()))
            self.controls.hover_maximize(hit == HTMAXBUTTON)
            return (True, hit) if hit else None
        if msg.message in (WM_NCLBUTTONDOWN, WM_NCLBUTTONDBLCLK) and msg.wParam == HTMAXBUTTON:
            self.controls.hover_maximize(True, pressed=True)
            return True, 0
        if msg.message == WM_NCLBUTTONUP and msg.wParam == HTMAXBUTTON:
            self.controls.hover_maximize(False)
            self.controls.toggle()
            return True, 0
        return None

    def hit(self, point):
        """What a point of the window is to Windows: an edge to resize, the maximize button, title bar, or
        (0) the window's own content."""
        window = self.window
        if not window.isMaximized() and not window.isFullScreen():
            width, height = window.width(), window.height()
            left, right = point.x() < BORDER, point.x() >= width - BORDER
            top, bottom = point.y() < BORDER, point.y() >= height - BORDER
            edge = {(True, False, True, False): HTTOPLEFT, (False, True, True, False): HTTOPRIGHT,
                    (True, False, False, True): HTBOTTOMLEFT, (False, True, False, True): HTBOTTOMRIGHT,
                    (True, False, False, False): HTLEFT, (False, True, False, False): HTRIGHT,
                    (False, False, True, False): HTTOP, (False, False, False, True): HTBOTTOM}.get((left, right, top, bottom))
            if edge:
                return edge
        maximize = self.controls.maximize
        if maximize.isVisible() and maximize.rect().contains(maximize.mapFrom(window, point)):
            return HTMAXBUTTON
        if not self.drag(point):
            return 0
        child = window.childAt(point)
        while child is not None and child is not window:
            if isinstance(child, INTERACTIVE) or child.property('noDrag'):
                return 0
            child = child.parentWidget()
        return HTCAPTION
