import os
import unittest
from dataclasses import replace
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent, QPoint, QPointF, QRect, QSize, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication, QMenu

from companion.avatar import DesktopAvatar, activity_state, visible_position
from companion.config import DEFAULT_MODEL, Settings
from companion.ui import CompanionWindow
from qt_test_support import application


SETTINGS = Settings("", DEFAULT_MODEL, "Mira", "Hi", tts_enabled=False)


class ActivityTests(unittest.TestCase):
    def test_activity_precedence_tracks_real_audio_instead_of_queued_speech(self):
        cases = [
            ({}, "ready"),
            ({"working": True}, "thinking"),
            ({"working": True, "has_reply": True}, "replying"),
            ({"working": True, "summary": True}, "summarizing"),
            ({"speech_busy": True, "speech": "loading"}, "preparing_voice"),
            ({"speech_busy": True, "speech": "speaking", "working": True}, "speaking"),
            ({"speech_busy": False, "speech": "speaking"}, "ready"),
            ({"microphone": "listening", "speech_busy": True, "speech": "speaking"}, "listening"),
            ({"microphone": "opening"}, "opening_mic"),
            ({"microphone": "loading"}, "transcribing"),
            ({"error": True}, "error"),
            ({"suspended": True, "microphone": "recording", "error": True}, "suspended"),
            ({"closing": True, "suspended": True}, "closing"),
        ]
        for values, expected in cases:
            with self.subTest(values=values):
                self.assertEqual(activity_state(**values), expected)

    def test_positions_remain_reachable_on_negative_and_disconnected_monitors(self):
        size = QSize(168, 174)
        primary, secondary = QRect(0, 0, 1920, 1040), QRect(-1280, 0, 1280, 984)
        saved = QPoint(-1000, 600)
        self.assertEqual(visible_position(saved, size, [primary, secondary]), saved)
        self.assertEqual(visible_position(saved, size, [primary]), QPoint(0, 600))
        bottom = visible_position(QPoint(99999, 99999), size, [primary])
        self.assertTrue(primary.contains(QRect(bottom, size)))


class AvatarWindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = application()

    def setUp(self):
        self.window = CompanionWindow(SETTINGS)
        self.window.show()
        self.app.processEvents()

    def tearDown(self):
        self.window.request_quit()
        self.window.deleteLater()
        self.app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.app.processEvents()

    def enable(self):
        self.window.show_avatar.setChecked(True)
        self.app.processEvents()
        return self.window.avatar.widget

    def test_avatar_is_lazy_and_showing_it_does_not_start_audio(self):
        self.assertIsNone(self.window.avatar.widget)
        widget = self.enable()
        self.assertTrue(widget.isVisible())
        self.assertFalse(widget.testAttribute(Qt.WidgetAttribute.WA_QuitOnClose))
        self.assertFalse(self.window.microphone.busy)
        self.assertFalse(self.window.speech.busy)
        self.assertFalse(self.window.hands_free.isChecked())

    def test_fallback_mouth_uses_output_level_and_resets_when_hidden(self):
        widget = self.enable()
        widget.set_activity('speaking')
        self.assertEqual(widget.voice_level, 0)
        self.window.avatar.set_voice_level(.7)
        self.assertEqual(widget.voice_level, .7)
        self.window.avatar.reset_voice()
        self.assertEqual(widget.voice_level, 0)
        self.window.avatar.set_voice_level(.7)
        self.window.show_avatar.setChecked(False)
        self.assertEqual(widget.voice_level, 0)

    def test_hidden_suspended_and_reduced_motion_avatar_do_not_run_timer(self):
        widget = self.enable()
        self.assertTrue(widget.timer.isActive())
        self.window.animate_avatar.setChecked(False)
        self.assertFalse(widget.timer.isActive())
        self.window.animate_avatar.setChecked(True)
        self.window.toggle_suspended()
        self.assertEqual(widget.state, "suspended")
        self.assertFalse(widget.timer.isActive())
        self.window.toggle_suspended()
        self.assertTrue(widget.timer.isActive())
        self.window.show_avatar.setChecked(False)
        self.assertFalse(widget.timer.isActive())
        self.assertFalse(widget.isVisible())

    def test_a_hidden_avatar_is_unloaded_after_a_while_and_comes_back_in_place(self):
        widget = self.enable()
        widget.move(123, 145)
        self.window.show_avatar.setChecked(False)
        self.assertTrue(self.window.avatar._unload_timer.isActive())
        self.window.show_avatar.setChecked(True)  # A quick toggle keeps her loaded.
        self.assertFalse(self.window.avatar._unload_timer.isActive())
        self.assertIs(self.window.avatar.widget, widget)
        self.window.show_avatar.setChecked(False)
        self.window.avatar._unload_hidden()
        self.assertIsNone(self.window.avatar.widget)
        self.assertEqual(self.window.avatar.position(), (123, 145))
        again = self.enable()
        self.assertIsNot(again, widget)
        self.assertEqual((again.x(), again.y()), (123, 145))

    def test_engines_close_only_while_hidden_and_the_window_trims_itself(self):
        from unittest.mock import patch
        asked = []
        for engine in (self.window.speech, self.window.microphone):
            engine.release = lambda seconds, engine=engine: asked.append((engine, seconds))
        with patch("companion.memory_saver.trim") as trim:
            self.window._save_memory_when_idle()
            self.assertEqual(asked, [])        # The window is open: she stays ready.
            trim.assert_not_called()
            self.window.hide()
            self.window._save_memory_when_idle()  # Engines decide by their own last use.
            self.assertEqual({seconds for _, seconds in asked}, {600})
            trim.assert_not_called()            # Just hidden: not yet.
            self.window._hidden_at -= 60
            self.window._save_memory_when_idle()
            self.window._save_memory_when_idle()  # Not again within ten minutes.
        self.assertEqual(trim.call_count, 1)
        trim.assert_called_with()                # Only this process; the engines are not paged out.

    def test_avatar_stays_visible_in_tray_and_click_reopens_chat(self):
        widget = self.enable()
        self.window.tray_enabled = True
        self.window.close()
        self.assertFalse(self.window.isVisible())
        self.assertTrue(widget.isVisible())
        widget.open_requested.emit()
        self.assertTrue(self.window.isVisible())
        self.assertFalse(self.window.microphone.busy)

    def test_drag_moves_avatar_without_opening_chat(self):
        widget = self.enable()
        self.window.tray_enabled = True
        self.window.hide_to_tray()
        widget.move(250, 250)
        start = QPointF(310, 310)
        widget.mousePressEvent(QMouseEvent(QEvent.Type.MouseButtonPress, QPointF(60, 60), start,
                                           Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier))
        widget.mouseMoveEvent(QMouseEvent(QEvent.Type.MouseMove, QPointF(80, 90), start + QPointF(20, 30),
                                          Qt.MouseButton.NoButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier))
        widget.mouseReleaseEvent(QMouseEvent(QEvent.Type.MouseButtonRelease, QPointF(80, 90), start + QPointF(20, 30),
                                             Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier))
        self.assertEqual(widget.pos(), QPoint(270, 280))
        self.assertFalse(self.window.isVisible())

    def test_closing_avatar_hides_it_without_quitting_or_closing_chat(self):
        widget = self.enable()
        widget.close()
        self.assertFalse(self.window.show_avatar.isChecked())
        self.assertFalse(widget.isVisible())
        self.assertFalse(self.window._closing)
        self.assertTrue(self.window.isVisible())

    def test_avatar_preferences_restore_position_motion_and_name(self):
        widget = self.enable()
        widget.move(120, 130)
        self.window.animate_avatar.setChecked(False)
        self.window._save_preferences()
        self.window.show_avatar.setChecked(False)
        self.window.animate_avatar.setChecked(True)
        with patch("companion.ui.load_settings", return_value=replace(SETTINGS, name="Luna")):
            self.window._reload_settings()
        self.assertTrue(widget.isVisible())
        self.assertEqual(widget.pos(), QPoint(120, 130))
        self.assertFalse(widget.timer.isActive())
        self.assertIn("Luna", widget.toolTip())

    def test_visual_controls_persist_when_avatar_is_not_created(self):
        self.window.avatar_size.setValue(480)
        self.window.avatar_motion.setValue(25)
        self.window.avatar_lip_sensitivity.setValue(160)
        self.window.avatar_cursor_attention.setChecked(False)
        self.window.avatar_gaze.setValue(35)
        self.window.avatar_hair.setValue(70)
        self.window._save_preferences()
        with patch('companion.ui.load_settings', return_value=SETTINGS):
            self.window._reload_settings()
        self.assertIsNone(self.window.avatar.widget)
        self.assertEqual(self.window.avatar.dimensions(), (480, 525))
        self.assertEqual(self.window.avatar_motion.value(), 25)
        self.assertEqual(self.window.avatar_lip_sensitivity.value(), 160)
        self.assertFalse(self.window.avatar_cursor_attention.isChecked())
        self.assertEqual(self.window.avatar_gaze.value(), 35)
        self.assertEqual(self.window.avatar_hair.value(), 70)

    def test_attention_controls_apply_immediately_and_after_avatar_reload(self):
        def create_widget():
            widget = DesktopAvatar()
            widget.set_attention_controls = Mock()
            return widget

        with patch.object(self.window.avatar, '_create_widget', side_effect=create_widget):
            widget = self.enable()
            widget.set_attention_controls.assert_called_with(True, 100, 45)
            self.window.avatar_gaze.setValue(35)
            widget.set_attention_controls.assert_called_with(True, 35, 45)
            self.window.avatar_hair.setValue(70)
            widget.set_attention_controls.assert_called_with(True, 35, 70)
            self.window.avatar_cursor_attention.setChecked(False)
            widget.set_attention_controls.assert_called_with(False, 35, 70)
            self.window.avatar.reload_avatar()
            replacement = self.window.avatar.widget
            self.assertIsNot(widget, replacement)
            replacement.set_attention_controls.assert_called_with(False, 35, 70)

    def test_context_menu_stop_and_suspend_use_existing_controls(self):
        widget = self.enable()
        self.window.avatar.show_menu(widget.pos())
        menu = widget.findChild(QMenu)
        actions = {action.text(): action for action in menu.actions()}
        self.assertNotIn("Record", actions)
        actions["Suspend"].trigger()
        self.assertTrue(self.window.suspended)
        menu.hide()
        self.window.avatar.show_menu(widget.pos())
        menu = widget.findChildren(QMenu)[-1]
        actions = {action.text(): action for action in menu.actions()}
        actions["Resume"].trigger()
        self.assertFalse(self.window.suspended)
        menu.hide()

    def test_quit_deletes_independent_avatar_and_stops_animation(self):
        widget = self.enable()
        self.window.request_quit()
        self.assertFalse(widget.isVisible())
        self.assertFalse(widget.timer.isActive())
        self.assertIsNone(self.window.avatar.widget)

    def test_reload_replaces_widget_preserves_position_and_keeps_audio_idle(self):
        old = self.enable()
        old.move(120, 130)
        self.window.avatar.reload_avatar()
        new = self.window.avatar.widget
        self.assertIsNot(old, new)
        self.assertFalse(old.isVisible())
        self.assertTrue(new.isVisible())
        self.assertEqual(new.pos(), QPoint(120, 130))
        self.assertFalse(self.window.microphone.busy)
        self.assertFalse(self.window.speech.busy)

    def test_bad_assignment_uses_readable_fallback_without_blocking_chat(self):
        with patch('companion.avatar_assets.assigned_avatar', side_effect=ValueError('bad map')):
            widget = self.enable()
        from PySide6.QtWidgets import QLabel
        self.assertIn('Mesh avatar unavailable', widget.findChild(QLabel).text())
        self.assertTrue(self.window.isVisible())
        self.assertTrue(widget.isVisible())

    def test_switching_profiles_replaces_old_renderer_without_starting_audio(self):
        old = self.enable()
        self.window.settings = replace(SETTINGS, name='Luna', character_path='other.toml')
        with patch('companion.avatar_assets.assigned_avatar', return_value=None):
            self.window.avatar.refresh()
        self.assertIsNot(self.window.avatar.widget, old)
        self.assertFalse(old.isVisible())
        self.assertEqual(self.window.avatar.widget.name, 'Luna')
        self.assertFalse(self.window.microphone.busy)

    def test_missing_webengine_uses_readable_fallback(self):
        with patch('companion.avatar_assets.assigned_avatar', return_value='test.mavatar'), \
                patch.dict('sys.modules', {'companion.mesh_avatar': None}):
            widget = self.enable()
        from PySide6.QtWidgets import QLabel
        self.assertIn('Mesh avatar unavailable', widget.findChild(QLabel).text())


class AvatarShapeTests(unittest.TestCase):
    def test_window_keeps_the_shape_of_her_framing(self):
        from types import SimpleNamespace
        from companion.mesh_avatar import MeshDesktopAvatar
        window = SimpleNamespace(aspect=.78, minimumWidth=lambda: 220, minimumHeight=lambda: 240,
                                 maximumWidth=lambda: 640, maximumHeight=lambda: 900)
        fitted = lambda *args, **kwargs: MeshDesktopAvatar.fitted(window, *args, **kwargs)
        self.assertEqual(fitted(480), (480, 615))       # No empty margin beside her.
        self.assertEqual(fitted(height=385), (300, 385))  # Dragging the bottom edge follows height.
        self.assertEqual(fitted(100), (220, 282))       # Never below the minimum.
        window.aspect = .45                              # Full body: tall and narrow, within the maximum.
        self.assertEqual(fitted(640), (405, 900))
