"""System tray integration; the window owns activity and graceful shutdown."""

from PySide6.QtCore import QObject, Qt, Slot
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QMenu, QSystemTrayIcon


def companion_icon() -> QIcon:
    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor("#b7a9ff"))
    painter.drawEllipse(3, 3, 58, 58)
    painter.setBrush(QColor("#191627"))
    painter.drawEllipse(17, 25, 8, 12)
    painter.drawEllipse(39, 25, 8, 12)
    painter.end()
    return QIcon(pixmap)


class TrayController(QObject):
    def __init__(self, window, parent=None):
        super().__init__(parent)
        self.window = window
        self.menu = QMenu(window)
        self.menu.addAction("Show companion", window.show_companion)
        self.menu.addAction("Hide to tray", window.hide_to_tray)
        self.menu.addAction("Settings", window.open_settings)
        self.suspend_action = self.menu.addAction("Suspend", window.toggle_suspended)
        self.menu.addSeparator()
        self.menu.addAction("Quit", window.request_quit)
        self.icon = QSystemTrayIcon(companion_icon(), self)
        self.icon.setContextMenu(self.menu)
        self.icon.activated.connect(self._activated)
        window.suspended_changed.connect(self._suspended)
        window.setWindowIcon(self.icon.icon())
        self._suspended(False)

    def start(self) -> bool:
        available = QSystemTrayIcon.isSystemTrayAvailable()
        self.window.tray_enabled = available
        self.window.close_to_tray.setEnabled(available)
        if available:
            self.icon.show()
            self.window.close_to_tray.setToolTip("Use Quit in the tray menu to fully exit.")
        else:
            self.window.close_to_tray.setToolTip("No system tray is available. Closing the window will exit.")
        return available

    @Slot(QSystemTrayIcon.ActivationReason)
    def _activated(self, reason):
        if reason in {QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick}:
            self.window.show_companion()

    @Slot(bool)
    def _suspended(self, suspended):
        self.suspend_action.setText("Resume" if suspended else "Suspend")
        self.icon.setToolTip("Desktop Companion · " + ("Suspended" if suspended else "Ready"))

    def shutdown(self):
        self.icon.hide()
