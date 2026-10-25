"""Moonlit frost theme: Jingliu's palette of night navy, glacial blue, silver and a crimson accent."""
from pathlib import Path
import random

from PySide6.QtCore import QEvent, QObject, QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QIcon, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap, QRadialGradient
from PySide6.QtWidgets import QAbstractSlider, QAbstractSpinBox, QComboBox, QPushButton, QScrollBar, QWidget


NIGHT = '#070b15'
NIGHT_HIGH = '#0d1528'
SURFACE = 'rgba(16, 26, 46, 0.86)'
FROST = '#e6eefa'
MUTED = '#8fa3c2'
DIM = '#5f7192'
ICE = '#a8d4ff'
ICE_DEEP = '#6fa8e8'
CRIMSON = '#e2566e'
AMBER = '#e6c28c'

ASSETS = (Path(__file__).resolve().parent / 'theme_assets').as_posix()
ICON_FONT = 'Segoe Fluent Icons'
ICONS = {
    'new': '', 'more': '', 'mic': '', 'mic_live': '', 'send': '',
    'stop': '', 'settings': '', 'history': '', 'speaker': '', 'muted': '',
    'handsfree': '', 'memories': '', 'context': '', 'pause': '', 'play': '',
    'moon': '', 'attach': '', 'close': '', 'document': '', 'image': '',
    'delete': '', 'clock': '', 'back': '',
}
# Activity → status dot colour.
ACTIVITY_COLORS = {
    'ready': '#7fd1b9', 'listening': CRIMSON, 'opening_mic': CRIMSON, 'transcribing': AMBER, 'thinking': ICE,
    'replying': ICE, 'summarizing': ICE, 'preparing_voice': AMBER, 'speaking': '#d6eaff',
    'suspended': DIM, 'error': CRIMSON, 'closing': DIM,
}

STYLE = f"""
* {{ font-family: 'Segoe UI Variable Text', 'Segoe UI'; font-size: 14px; color: {FROST}; }}
QMainWindow, QDialog {{ background: {NIGHT}; }}
QWidget#column, QWidget#chatBody, QScrollArea, QScrollArea > QWidget > QWidget {{ background: transparent; }}
QStackedWidget#pages, QWidget#panel, QWidget#panelBody, QDialog[embedded="true"] {{ background: transparent; }}
QListWidget#nav {{ background: transparent; border: none; padding: 0; outline: none; }}
QListWidget#nav::item {{ color: {MUTED}; padding: 7px 12px; margin-bottom: 2px; border-radius: 6px;
    border-left: 2px solid transparent; }}
QListWidget#nav::item:hover {{ color: {FROST}; background: rgba(168, 212, 255, 0.05); }}
QListWidget#nav::item:selected {{ color: {FROST}; background: rgba(168, 212, 255, 0.08); border-left: 2px solid {ICE}; }}
QLabel {{ background: transparent; }}
QToolTip {{ background: #111b31; color: {FROST}; border: 1px solid #2a3b5e; padding: 6px 8px; border-radius: 6px; }}

QLabel#title {{ font-family: 'Sitka Display', 'Sitka Heading', 'Cambria', 'Georgia'; font-size: 28px; font-weight: 400; color: #eef4fd; }}
QLabel#seal {{ font-family: 'Microsoft YaHei UI Light'; font-size: 15px; color: {ICE_DEEP}; padding-top: 6px; }}
QLabel#subtitle {{ color: {MUTED}; font-size: 12px; }}
QLabel#hint, QLabel#footer {{ color: {DIM}; font-size: 12px; }}
QLabel#section {{ font-family: 'Sitka Display', 'Sitka Heading', 'Cambria', 'Georgia'; font-size: 17px; color: #eef4fd; padding: 16px 0 6px 0;
    border-bottom: 1px solid rgba(168, 212, 255, 0.10); }}
QLabel#emblem {{ font-family: '{ICON_FONT}'; font-size: 20px; color: {ICE};
    background: qradialgradient(cx:0.5, cy:0.5, radius:0.6, fx:0.4, fy:0.35, stop:0 #1d3256, stop:1 #0d1528);
    border: 1px solid #2c4470; border-radius: 22px; }}
QFrame#pill {{ background: rgba(168, 212, 255, 0.07); border: 1px solid rgba(168, 212, 255, 0.16); border-radius: 13px; }}
QLabel#status {{ color: #cfe3fb; font-size: 12px; }}

QPushButton {{ background: rgba(255, 255, 255, 0.035); border: 1px solid rgba(168, 212, 255, 0.13);
    border-radius: 6px; padding: 7px 14px; color: #d8e4f4; }}
QPushButton:hover {{ background: rgba(168, 212, 255, 0.09); border-color: rgba(168, 212, 255, 0.26); color: {FROST}; }}
QPushButton:pressed {{ background: rgba(168, 212, 255, 0.15); }}
QPushButton:checked {{ background: rgba(111, 168, 232, 0.24); border-color: {ICE_DEEP}; }}
QPushButton:disabled {{ color: #4a5a78; border-color: rgba(168, 212, 255, 0.07); }}
QPushButton#primary {{ background: #d3e6fb; color: #0a1424; border: none; font-weight: 600; }}
QPushButton#primary:hover {{ background: #e6f1fd; }}

QPushButton#icon {{ font-family: '{ICON_FONT}'; font-size: 15px; padding: 0; border-radius: 17px;
    min-width: 34px; max-width: 34px; min-height: 34px; max-height: 34px; color: #c4d8f2;
    background: transparent; border: 1px solid transparent; }}
QPushButton#icon:hover {{ background: rgba(168, 212, 255, 0.10); border-color: rgba(168, 212, 255, 0.18); }}
QPushButton#icon:checked {{ color: {ICE}; background: rgba(111, 168, 232, 0.16); border-color: rgba(168, 212, 255, 0.28); }}
QPushButton#icon:disabled {{ color: #3b4966; }}
QPushButton#icon[live="true"] {{ color: #fff; background: {CRIMSON}; border-color: #ff8fa1; }}
QPushButton#icon[danger="true"] {{ color: #ffb3bf; }}
QPushButton#icon::menu-indicator {{ image: none; width: 0; }}
QPushButton#send {{ font-family: '{ICON_FONT}'; font-size: 15px; padding: 0; border-radius: 17px;
    min-width: 34px; max-width: 34px; min-height: 34px; max-height: 34px; border: none; color: #0a1424;
    background: #d3e6fb; }}
QPushButton#send:hover {{ background: #e3f1ff; }}
QPushButton#send:disabled {{ background: rgba(168, 212, 255, 0.10); color: #3b4966; }}

QFrame#composer {{ background: rgba(12, 19, 36, 0.94); border: 1px solid rgba(168, 212, 255, 0.12); border-radius: 16px; }}
QFrame#composer[focused="true"] {{ border-color: rgba(168, 212, 255, 0.45); }}
QPlainTextEdit#input {{ background: transparent; border: none; padding: 2px 4px; font-size: 15px;
    selection-background-color: #2f5487; }}

QFrame#assistant {{ background: transparent; border: none; border-left: 2px solid rgba(168, 212, 255, 0.34); }}
QFrame#assistant QLabel#body {{ font-family: 'Sitka Text', 'Cambria', 'Georgia'; font-size: 16px; color: #e9f0fa; }}
QFrame#user {{ background: rgba(168, 212, 255, 0.075); border: none; border-radius: 14px; }}
QFrame#user QLabel#body {{ color: #dbe6f5; }}
QFrame#task {{ background: rgba(12, 20, 38, 0.72); border: 1px solid rgba(168, 212, 255, 0.12);
    border-left: 2px solid rgba(168, 212, 255, 0.45); border-radius: 4px; }}
QLabel#taskTitle {{ font-size: 14px; color: {FROST}; }}
QLabel#taskSteps {{ font-size: 12px; color: {MUTED}; font-family: 'Cascadia Mono', 'Consolas'; }}
QLabel#taskStatus {{ font-size: 12px; font-weight: 600; color: {ICE}; }}
QLabel#taskStatus[state="approval"] {{ color: {AMBER}; }}
QLabel#taskStatus[state="done"] {{ color: #7fd1b9; }}
QLabel#taskStatus[state="failed"] {{ color: #f3b3bd; }}
QLabel#taskStatus[state="undone"] {{ color: {MUTED}; }}
QPushButton#taskUndo {{ background: transparent; border: 1px solid rgba(168, 212, 255, 0.28); border-radius: 9px;
    color: {ICE}; font-size: 12px; padding: 3px 12px; }}
QPushButton#taskUndo:hover {{ background: rgba(168, 212, 255, 0.10); color: {FROST}; }}
QLabel#approvalAction {{ font-family: 'Cascadia Mono', 'Consolas'; font-size: 13px; color: {FROST};
    background: rgba(10, 17, 33, 0.9); border: 1px solid rgba(168, 212, 255, 0.18); border-radius: 8px; padding: 10px; }}
QListWidget#history {{ background: transparent; border: none; padding: 0; outline: none; }}
QListWidget#history::item {{ background: transparent; border: none; padding: 0; }}
QFrame#historyRow {{ background: rgba(255, 255, 255, 0.025); border: 1px solid rgba(168, 212, 255, 0.08); border-radius: 6px; }}
QListWidget#history::item:hover QFrame#historyRow {{ background: rgba(168, 212, 255, 0.07); }}
QListWidget#history::item:selected {{ background: rgba(111, 168, 232, 0.12); border: 1px solid rgba(168, 212, 255, 0.32); border-radius: 6px; }}
QLabel#historyTitle {{ font-family: 'Sitka Display', 'Sitka Heading', 'Cambria', 'Georgia'; font-size: 16px; color: #eef4fd; }}
QLabel#historyMeta {{ font-size: 11px; color: {ICE}; letter-spacing: 0.3px; }}
QLabel#historyPreview {{ font-size: 12px; color: {MUTED}; }}
QLabel#historyBadge {{ font-size: 10px; font-weight: 600; letter-spacing: 1px; color: {NIGHT}; background: {ICE};
    border-radius: 8px; padding: 1px 8px; }}
QPushButton#historyDelete {{ font-family: '{ICON_FONT}'; font-size: 13px; color: {DIM}; background: transparent;
    border: none; border-radius: 8px; min-width: 32px; max-width: 32px; min-height: 32px; max-height: 32px; padding: 0; }}
QPushButton#historyDelete:hover {{ color: {CRIMSON}; background: rgba(226, 86, 110, 0.12); }}
QPushButton#danger {{ color: #f3a5b3; border-color: rgba(226, 86, 110, 0.35); }}
QPushButton#danger:hover {{ background: rgba(226, 86, 110, 0.14); color: #ffd0d8; }}
QPushButton#danger:disabled, QPushButton#primary:disabled {{ color: #4a5a78; background: transparent; border-color: #1c2a45; }}
QFrame#memoryNote {{ background: rgba(168, 212, 255, 0.045); border: none; border-radius: 6px; }}
QLabel#memoryIcon {{ font-family: '{ICON_FONT}'; font-size: 13px; color: {ICE}; }}
QLabel#memoryText {{ font-size: 12px; color: #cfe0f6; }}
QPushButton#memoryUndo {{ background: transparent; border: none; color: {ICE}; font-size: 12px; padding: 2px 8px; }}
QPushButton#memoryUndo:hover {{ color: {FROST}; text-decoration: underline; }}
QLabel#speaker {{ font-family: 'Sitka Display', 'Sitka Heading', 'Cambria', 'Georgia'; color: {ICE}; font-size: 14px; font-style: italic; }}
QLabel#body {{ font-size: 15px; selection-background-color: #2f5487; }}
QLabel#notice {{ color: {MUTED}; font-size: 12px; font-style: italic; }}
QLabel#error {{ color: #f3b3bd; font-size: 13px; }}
QLabel#note {{ color: {MUTED}; font-size: 12px; background: transparent; border: none; padding: 2px 12px; }}
QLabel#note[tone="warning"] {{ color: {AMBER}; border-color: rgba(230, 194, 140, 0.30); }}
QLabel#note[tone="error"] {{ color: #f3b3bd; border-color: rgba(226, 86, 110, 0.35); }}
QLabel#welcomeTitle {{ font-family: 'Sitka Display', 'Sitka Heading', 'Cambria', 'Georgia'; font-size: 26px; color: #eef4fd; }}
QLabel#welcomeText {{ color: {MUTED}; font-size: 13px; }}
QLabel#welcomeMoon {{ font-family: '{ICON_FONT}'; font-size: 40px; color: {ICE}; }}
QFrame#attachment {{ background: rgba(168, 212, 255, 0.07); border: 1px solid rgba(168, 212, 255, 0.18); border-radius: 10px; }}
QFrame#attachment:hover {{ border-color: rgba(168, 212, 255, 0.38); }}
QLabel#attachmentIcon {{ font-family: '{ICON_FONT}'; font-size: 18px; color: {ICE}; }}
QLabel#attachmentName {{ font-size: 12px; color: #cfe0f6; }}
QLabel#attachmentKind {{ font-size: 10px; color: {MUTED}; letter-spacing: 1px; }}
QLabel#thumbnail {{ border-radius: 8px; background: rgba(0, 0, 0, 0.25); }}
QPushButton#remove {{ font-family: '{ICON_FONT}'; font-size: 9px; padding: 0; border-radius: 9px; border: none;
    min-width: 18px; max-width: 18px; min-height: 18px; max-height: 18px; color: {MUTED}; background: rgba(168, 212, 255, 0.10); }}
QPushButton#remove:hover {{ color: #fff; background: {CRIMSON}; }}
QWidget#dropHint {{ background: rgba(7, 12, 24, 0.88); border: 2px dashed rgba(168, 212, 255, 0.55); border-radius: 20px; }}
QLabel#dropText {{ color: {ICE}; font-size: 18px; font-family: 'Segoe UI Variable Display Light', 'Segoe UI Light'; }}
QPushButton#chip {{ background: transparent; border: 1px solid rgba(168, 212, 255, 0.16);
    border-radius: 6px; padding: 6px 14px; color: #c9dcf5; font-size: 13px; }}
QPushButton#chip:hover {{ background: rgba(168, 212, 255, 0.13); color: {FROST}; }}

QScrollBar:vertical {{ background: transparent; width: 10px; margin: 4px 2px; }}
QScrollBar::handle:vertical {{ background: rgba(168, 212, 255, 0.16); border-radius: 3px; min-height: 40px; }}
QScrollBar::handle:vertical:hover {{ background: rgba(168, 212, 255, 0.30); }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical, QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ height: 0; background: none; }}
QScrollBar:horizontal {{ height: 0; }}

QProgressBar {{ background: rgba(168, 212, 255, 0.08); border: none; border-radius: 2px; max-height: 4px; min-height: 4px; }}
QProgressBar::chunk {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {ICE_DEEP}, stop:1 {CRIMSON}); border-radius: 2px; }}

QMenu {{ background: #0f1830; border: 1px solid #263756; border-radius: 10px; padding: 6px; }}
QMenu::item {{ padding: 8px 26px 8px 12px; border-radius: 6px; background: transparent; }}
QMenu::item:selected {{ background: rgba(168, 212, 255, 0.12); }}
QMenu::item:disabled {{ color: #4a5a78; }}
QMenu::separator {{ height: 1px; background: #223250; margin: 5px 8px; }}

QTabWidget::pane {{ border: none; border-top: 1px solid #1d2a44; top: -1px; }}
QTabBar {{ background: transparent; qproperty-drawBase: 0; }}
QTabBar::tab {{ background: transparent; color: {MUTED}; padding: 9px 16px; border: none; border-bottom: 2px solid transparent; }}
QTabBar::tab:selected {{ color: {FROST}; border-bottom-color: {ICE}; }}
QTabBar::tab:hover {{ color: {FROST}; }}

QComboBox {{ background: rgba(255, 255, 255, 0.035); border: 1px solid rgba(168, 212, 255, 0.12); border-radius: 6px; padding: 6px 10px; }}
QComboBox:hover {{ border-color: rgba(168, 212, 255, 0.28); }}
QComboBox:focus {{ border-bottom: 1px solid {ICE}; }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox QAbstractItemView {{ background: #0f1830; border: 1px solid #263756; selection-background-color: #1f3357; outline: none; }}
QLineEdit, QPlainTextEdit, QTextEdit, QTextBrowser, QListWidget, QTableWidget, QTreeWidget {{
    background: rgba(255, 255, 255, 0.03); border: 1px solid rgba(168, 212, 255, 0.12); border-radius: 6px; padding: 6px;
    selection-background-color: #2f5487; }}
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus {{ border-color: rgba(168, 212, 255, 0.22); border-bottom: 1px solid {ICE}; }}
QHeaderView::section {{ background: #0f1830; color: {MUTED}; border: none; padding: 6px; }}
QCheckBox {{ spacing: 9px; }}
QCheckBox::indicator {{ width: 36px; height: 20px; image: url("{ASSETS}/switch-off.svg"); }}
QCheckBox::indicator:checked {{ image: url("{ASSETS}/switch-on.svg"); }}QCheckBox:disabled {{ color: #4a5a78; }}
QSlider::groove:horizontal {{ height: 4px; background: rgba(168, 212, 255, 0.14); border-radius: 2px; }}
QSlider::sub-page:horizontal {{ background: {ICE_DEEP}; border-radius: 2px; }}
QSlider::handle:horizontal {{ background: {FROST}; width: 14px; height: 14px; margin: -6px 0; border-radius: 7px; border: 2px solid {ICE_DEEP}; }}
"""


def icon_button(glyph, tooltip, name='icon', checkable=False):
    button = QPushButton(ICONS[glyph])
    button.setObjectName(name)
    button.setToolTip(tooltip)
    button.setAccessibleName(tooltip)
    button.setCheckable(checkable)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    return button


def glyph_icon(glyph, color=ICE, size=32):
    """Menu icon drawn from the system icon font."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    font = QFont(ICON_FONT)
    font.setPixelSize(int(size * 0.62))
    painter.setFont(font)
    painter.setPen(QColor(color))
    painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, ICONS[glyph])
    painter.end()
    return QIcon(pixmap)


def repolish(widget, **properties):
    for name, value in properties.items():
        widget.setProperty(name, value)
    widget.style().unpolish(widget)
    widget.style().polish(widget)


def moon_icon(size=64):
    """A crescent moon over glacial blue, used for the window and tray."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    disc = QRadialGradient(size * 0.38, size * 0.32, size * 0.7)
    disc.setColorAt(0, QColor('#25406b'))
    disc.setColorAt(1, QColor('#0b1324'))
    painter.setBrush(disc)
    painter.setPen(QPen(QColor('#4f7cb8'), size / 32))
    painter.drawEllipse(QRectF(size * 0.04, size * 0.04, size * 0.92, size * 0.92))
    moon = QPainterPath()
    moon.addEllipse(QRectF(size * 0.22, size * 0.2, size * 0.56, size * 0.56))
    cut = QPainterPath()
    cut.addEllipse(QRectF(size * 0.36, size * 0.12, size * 0.52, size * 0.52))
    shine = QLinearGradient(0, size * 0.2, 0, size * 0.8)
    shine.setColorAt(0, QColor('#f2f8ff'))
    shine.setColorAt(1, QColor(ICE))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(shine)
    painter.drawPath(moon.subtracted(cut))
    painter.setBrush(QColor(CRIMSON))
    painter.drawEllipse(QPointF(size * 0.71, size * 0.7), size * 0.045, size * 0.045)
    painter.end()
    return QIcon(pixmap)


class NightSky(QWidget):
    """Static backdrop: deep night gradient, a faint moon halo and drifting frost motes."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        generator = random.Random(1123)  # Fixed seed: the sky never flickers between repaints.
        self._motes = [(generator.random(), generator.random() ** 1.6, generator.uniform(0.6, 1.8),
                        generator.randint(18, 70)) for _ in range(70)]

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        width, height = self.width(), self.height()
        sky = QLinearGradient(0, 0, 0, height)
        sky.setColorAt(0, QColor(NIGHT_HIGH))
        sky.setColorAt(0.55, QColor('#090f1d'))
        sky.setColorAt(1, QColor(NIGHT))
        painter.fillRect(self.rect(), sky)
        centre = QPointF(width * 0.86, height * 0.06)
        halo = QRadialGradient(centre, max(width, height) * 0.55)
        halo.setColorAt(0, QColor(168, 212, 255, 30))
        halo.setColorAt(0.35, QColor(111, 168, 232, 10))
        halo.setColorAt(1, QColor(111, 168, 232, 0))
        painter.fillRect(self.rect(), QBrush(halo))
        radius = min(width, height) * 0.09
        moon = QPainterPath()
        moon.addEllipse(centre, radius, radius)
        cut = QPainterPath()
        cut.addEllipse(centre + QPointF(radius * 0.42, -radius * 0.22), radius * 0.92, radius * 0.92)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(214, 232, 255, 12))
        painter.drawPath(moon.subtracted(cut))
        for x, y, size, alpha in self._motes[::2]:
            painter.setBrush(QColor(200, 225, 255, alpha * 2 // 3))
            painter.drawEllipse(QPointF(x * width, y * height), size * .8, size * .8)
        painter.end()


def _colorref(hex_color):
    color = QColor(hex_color)
    return color.red() | color.green() << 8 | color.blue() << 16


def style_title_bar(window):
    """Windows 11: a night-navy caption, moonlit text and a frost border, so the
    system title bar belongs to the window. Older Windows ignores what it lacks."""
    import sys
    from PySide6.QtGui import QGuiApplication
    if sys.platform != "win32" or QGuiApplication.platformName() != "windows":
        return  # Offscreen rendering and other platforms have no system caption.
    import ctypes
    hwnd = ctypes.c_void_p(int(window.winId()))
    dwm = ctypes.windll.dwmapi
    for attribute, value in ((20, 1),                          # Immersive dark mode
                             (35, _colorref(NIGHT_HIGH)),      # Caption colour
                             (36, _colorref("#cfe3fb")),       # Caption text
                             (34, _colorref("#22324f"))):      # Border
        data = ctypes.c_int(value)
        try:
            dwm.DwmSetWindowAttribute(hwnd, attribute, ctypes.byref(data), ctypes.sizeof(data))
        except OSError:
            pass


CONTROLS = (QComboBox, QAbstractSlider, QAbstractSpinBox)


class WindowChrome(QObject):
    """Per window: a themed title bar, and a mouse wheel that scrolls the page instead of
    changing a combo box or slider you are only scrolling past (click one to adjust it)."""

    def watch(self, window):
        window.installEventFilter(self)
        if window.isVisible():
            self._prepare(window)

    def _prepare(self, window):
        style_title_bar(window)
        self.guard(window)

    def guard(self, widget):
        """The wheel scrolls past lists and sliders in `widget` unless one was clicked first."""
        # Scroll bars are sliders too, but the wheel is how a page scrolls: leave them alone.
        controls = [control for kind in CONTROLS for control in widget.findChildren(kind)
                    if not isinstance(control, QScrollBar)]
        for control in controls:
            if control.property("wheelGuard") is None:
                control.setProperty("wheelGuard", True)
                # A combo box would otherwise take focus from the wheel itself, then change.
                control.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
                control.installEventFilter(self)

    def eventFilter(self, watched, event):
        kind = event.type()
        if kind == QEvent.Type.Wheel and isinstance(watched, CONTROLS) and not watched.hasFocus():
            event.ignore()  # Ignored wheel events continue to the scroll area underneath.
            return True
        if kind == QEvent.Type.Show and isinstance(watched, QWidget) and watched.isWindow():
            self._prepare(watched)
        return False


def display_font(pixels, light=True):
    font = QFont('Segoe UI Variable Display Light' if light else 'Segoe UI Variable Display')
    font.setPixelSize(pixels)
    return font
