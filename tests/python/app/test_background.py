import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent, QTimer
from PySide6.QtWidgets import QApplication, QSystemTrayIcon

from companion.app.tray import TrayController
from companion.core.config import DEFAULT_MODEL, Settings
from companion.ui.window import CompanionWindow
from tests.qt_test_support import application


class TrayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = application()

    def setUp(self):
        self.window = CompanionWindow(Settings("", DEFAULT_MODEL, "Jinger", "Hi"))
        self.tray = TrayController(self.window)

    def tearDown(self):
        self.tray.shutdown()
        self.window.request_quit()
        self.tray.deleteLater()
        self.window.deleteLater()
        self.app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.app.processEvents()

    def test_no_system_tray_falls_back_to_normal_window_close(self):
        closed = []
        self.window.closed.connect(lambda: closed.append(True))
        with patch.object(QSystemTrayIcon, "isSystemTrayAvailable", return_value=False):
            self.assertFalse(self.tray.start())
        self.assertFalse(self.window.close_to_tray.isEnabled())
        self.window.show()
        self.window.close()
        self.assertEqual(closed, [True])
        self.assertTrue(self.window._closing)

    def test_tray_activation_restores_hidden_window_and_suspend_menu_tracks_state(self):
        with patch.object(QSystemTrayIcon, "isSystemTrayAvailable", return_value=True), patch.object(self.tray.icon, "show"):
            self.assertTrue(self.tray.start())
        self.window.show()
        self.window.close()
        self.assertFalse(self.window.isVisible())
        self.tray._activated(QSystemTrayIcon.ActivationReason.Trigger)
        self.assertTrue(self.window.isVisible())
        self.tray.suspend_action.trigger()
        self.assertTrue(self.window.suspended)
        self.assertEqual(self.tray.suspend_action.text(), "Resume")
        self.assertIn("Suspended", self.tray.icon.toolTip())
        self.tray.suspend_action.trigger()
        self.assertFalse(self.window.suspended)

    def test_close_preference_can_fully_exit_even_when_tray_is_available(self):
        self.window.tray_enabled = True
        self.window.close_to_tray.setChecked(False)
        self.window.close()
        self.assertTrue(self.window._closing)

    def test_quit_closes_open_history_without_reading_closed_store(self):
        QTimer.singleShot(0, self.window.request_quit)
        self.window._open_history()
        self.assertTrue(self.window._closing)

    def test_tray_avatar_action_and_settings_toggle_stay_in_sync(self):
        self.tray.avatar_action.setChecked(True)
        self.assertTrue(self.window.show_avatar.isChecked())
        self.assertTrue(self.window.avatar.widget.isVisible())
        self.window.avatar.hide_avatar()
        self.assertFalse(self.tray.avatar_action.isChecked())
        self.assertFalse(self.window.avatar.widget.isVisible())
