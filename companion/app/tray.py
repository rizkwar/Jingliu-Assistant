"""System tray integration; the window owns activity and graceful shutdown."""

from PySide6.QtCore import QObject, Slot
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from ..ui.theme import moon_icon


def companion_icon() -> QIcon:
    return moon_icon(64)


class TrayController(QObject):
    def __init__(self, window, parent=None):
        super().__init__(parent)
        self.window = window
        self.menu = QMenu(window)
        self.menu.addAction("Show companion", window.show_companion)
        self.menu.addAction("Hide to tray", window.hide_to_tray)
        self.menu.addAction("Settings", window.open_settings)
        self.suspend_action = self.menu.addAction("Suspend", window.toggle_suspended)
        self.avatar_action = self.menu.addAction("Show desktop avatar")
        self.avatar_action.setCheckable(True)
        self.avatar_action.setChecked(window.show_avatar.isChecked())
        self.avatar_action.toggled.connect(window.show_avatar.setChecked)
        window.show_avatar.toggled.connect(self.avatar_action.setChecked)
        self.menu.addSeparator()
        self.menu.addAction("Quit", window.request_quit)
        self.icon = QSystemTrayIcon(companion_icon(), self)
        self.icon.setContextMenu(self.menu)
        self.icon.activated.connect(self._activated)
        window.suspended_changed.connect(self._suspended)
        window.notify.connect(self._notify)
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

    @Slot(str, str)
    def _notify(self, title, message):
        if self.icon.isVisible():
            self.icon.showMessage(title, message, self.icon.icon(), 8000)

    @Slot(bool)
    def _suspended(self, suspended):
        self.suspend_action.setText("Resume" if suspended else "Suspend")
        self.icon.setToolTip("Desktop Companion · " + ("Suspended" if suspended else "Ready"))

    def shutdown(self):
        self.icon.hide()
