"""Moonlit frost theme: Jingliu's palette of night navy, glacial blue, silver and a crimson accent."""
from pathlib import Path
import random

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QIcon, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap, QRadialGradient
from PySide6.QtWidgets import QPushButton, QWidget


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
QLabel {{ background: transparent; }}
QToolTip {{ background: #111b31; color: {FROST}; border: 1px solid #2a3b5e; padding: 6px 8px; border-radius: 6px; }}

QLabel#title {{ font-family: 'Segoe UI Variable Display Light', 'Segoe UI Light'; font-size: 26px; letter-spacing: 1px; }}
QLabel#seal {{ font-family: 'Microsoft YaHei UI Light'; font-size: 15px; color: {ICE_DEEP}; padding-top: 6px; }}
QLabel#subtitle {{ color: {MUTED}; font-size: 12px; }}
QLabel#hint, QLabel#footer {{ color: {DIM}; font-size: 12px; }}
QLabel#section {{ color: {ICE}; font-size: 11px; font-weight: 600; letter-spacing: 2px; padding-top: 8px; }}
QLabel#emblem {{ font-family: '{ICON_FONT}'; font-size: 20px; color: {ICE};
    background: qradialgradient(cx:0.5, cy:0.5, radius:0.6, fx:0.4, fy:0.35, stop:0 #1d3256, stop:1 #0d1528);
    border: 1px solid #2c4470; border-radius: 22px; }}
QFrame#pill {{ background: rgba(168, 212, 255, 0.07); border: 1px solid rgba(168, 212, 255, 0.16); border-radius: 13px; }}
QLabel#status {{ color: #cfe3fb; font-size: 12px; }}

QPushButton {{ background: rgba(168, 212, 255, 0.06); border: 1px solid rgba(168, 212, 255, 0.16);
    border-radius: 9px; padding: 7px 14px; }}
QPushButton:hover {{ background: rgba(168, 212, 255, 0.13); border-color: rgba(168, 212, 255, 0.32); }}
QPushButton:pressed {{ background: rgba(168, 212, 255, 0.20); }}
QPushButton:checked {{ background: rgba(111, 168, 232, 0.24); border-color: {ICE_DEEP}; }}
QPushButton:disabled {{ color: #4a5a78; border-color: rgba(168, 212, 255, 0.07); }}
QPushButton#primary {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #cfe6ff, stop:1 {ICE_DEEP});
    color: #08111f; border: none; font-weight: 600; }}
QPushButton#primary:hover {{ background: #d9ecff; }}

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
    min-width: 34px; max-width: 34px; min-height: 34px; max-height: 34px; border: none; color: #08111f;
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #d6eaff, stop:1 {ICE_DEEP}); }}
QPushButton#send:hover {{ background: #e3f1ff; }}
QPushButton#send:disabled {{ background: rgba(168, 212, 255, 0.10); color: #3b4966; }}

QFrame#composer {{ background: rgba(13, 21, 40, 0.92); border: 1px solid rgba(168, 212, 255, 0.16); border-radius: 20px; }}
QFrame#composer[focused="true"] {{ border-color: rgba(168, 212, 255, 0.45); }}
QPlainTextEdit#input {{ background: transparent; border: none; padding: 2px 4px; font-size: 15px;
    selection-background-color: #2f5487; }}

QFrame#assistant {{ background: rgba(18, 29, 52, 0.84); border: 1px solid rgba(168, 212, 255, 0.10);
    border-radius: 16px; border-top-left-radius: 4px; }}
QFrame#user {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 rgba(111, 168, 232, 0.30), stop:1 rgba(80, 120, 190, 0.22));
    border: 1px solid rgba(168, 212, 255, 0.26); border-radius: 16px; border-top-right-radius: 4px; }}
QLabel#speaker {{ color: {ICE}; font-size: 11px; font-weight: 600; letter-spacing: 2px; }}
QLabel#body {{ font-size: 15px; selection-background-color: #2f5487; }}
QLabel#notice {{ color: {MUTED}; font-size: 12px; font-style: italic; }}
QLabel#error {{ color: #f3b3bd; font-size: 13px; }}
QLabel#note {{ color: {MUTED}; font-size: 12px; background: rgba(168, 212, 255, 0.05);
    border: 1px solid rgba(168, 212, 255, 0.10); border-radius: 11px; padding: 4px 12px; }}
QLabel#note[tone="warning"] {{ color: {AMBER}; border-color: rgba(230, 194, 140, 0.30); }}
QLabel#note[tone="error"] {{ color: #f3b3bd; border-color: rgba(226, 86, 110, 0.35); }}
QLabel#welcomeTitle {{ font-family: 'Segoe UI Variable Display Light', 'Segoe UI Light'; font-size: 22px; color: {FROST}; }}
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
QPushButton#chip {{ background: rgba(168, 212, 255, 0.05); border: 1px solid rgba(168, 212, 255, 0.18);
    border-radius: 15px; padding: 6px 14px; color: #c9dcf5; font-size: 13px; }}
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

QComboBox {{ background: rgba(168, 212, 255, 0.06); border: 1px solid rgba(168, 212, 255, 0.18); border-radius: 8px; padding: 6px 10px; }}
QComboBox:hover {{ border-color: rgba(168, 212, 255, 0.34); }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox QAbstractItemView {{ background: #0f1830; border: 1px solid #263756; selection-background-color: #1f3357; outline: none; }}
QLineEdit, QPlainTextEdit, QTextEdit, QTextBrowser, QListWidget, QTableWidget, QTreeWidget {{
    background: rgba(10, 17, 33, 0.9); border: 1px solid rgba(168, 212, 255, 0.16); border-radius: 10px; padding: 6px;
    selection-background-color: #2f5487; }}
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus {{ border-color: rgba(168, 212, 255, 0.45); }}
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
        halo.setColorAt(0, QColor(168, 212, 255, 46))
        halo.setColorAt(0.35, QColor(111, 168, 232, 16))
        halo.setColorAt(1, QColor(111, 168, 232, 0))
        painter.fillRect(self.rect(), QBrush(halo))
        radius = min(width, height) * 0.09
        moon = QPainterPath()
        moon.addEllipse(centre, radius, radius)
        cut = QPainterPath()
        cut.addEllipse(centre + QPointF(radius * 0.42, -radius * 0.22), radius * 0.92, radius * 0.92)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(214, 232, 255, 20))
        painter.drawPath(moon.subtracted(cut))
        for x, y, size, alpha in self._motes:
            painter.setBrush(QColor(200, 225, 255, alpha))
            painter.drawEllipse(QPointF(x * width, y * height), size, size)
        # One long, faint sword-light stroke across the lower sky.
        stroke = QLinearGradient(0, height * 0.9, width, height * 0.55)
        stroke.setColorAt(0, QColor(168, 212, 255, 0))
        stroke.setColorAt(0.5, QColor(168, 212, 255, 22))
        stroke.setColorAt(1, QColor(226, 86, 110, 0))
        painter.setPen(QPen(QBrush(stroke), 1.2))
        painter.drawLine(QPointF(-10, height * 0.92), QPointF(width + 10, height * 0.58))
        painter.end()


def display_font(pixels, light=True):
    font = QFont('Segoe UI Variable Display Light' if light else 'Segoe UI Variable Display')
    font.setPixelSize(pixels)
    return font
