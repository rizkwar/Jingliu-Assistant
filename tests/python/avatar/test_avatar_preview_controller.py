"""Offline controller checks: no native browser, microphone, or audio process."""

import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtCore import QEvent, QObject, QSignalBlocker, Signal

from companion.avatar.window import AvatarController, DesktopAvatar
from companion.character.library import CharacterLibrary
from companion.core.config import DEFAULT_MODEL, Settings
from companion.core.preferences import Preferences
from companion.ui.window import CompanionWindow
from tests.qt_test_support import application


class PreviewSpeech(QObject):
    changed = Signal(str)
    failed = Signal(str)
    spoken = Signal(str)
    playback_level = Signal(float)
    playback_reset = Signal()

    def __init__(self):
        super().__init__()
        self.busy = False
        self.state = 'idle'

    def speak(self, *args):
        raise AssertionError('A movement preview must not start speech')

    def stop(self):
        self.busy = False
        self.state = 'idle'
        self.changed.emit('Ready')
        self.playback_reset.emit()

    def shutdown(self):
        self.stop()


class PreviewMicrophone(QObject):
    changed = Signal(str)
    transcribed = Signal(str)
    failed = Signal(str)
    devices = Signal(list)
    level = Signal(int)

    def __init__(self):
        super().__init__()
        self.state = 'idle'

    @property
    def busy(self):
        return self.state != 'idle'

    def start(self, *args, **kwargs):
        raise AssertionError('A movement preview must not start the microphone')

    def refresh_devices(self):
        self.devices.emit([])

    def cancel(self):
        self.state = 'idle'
        self.changed.emit('idle')

    def shutdown(self):
        self.cancel()


class PreviewMesh(DesktopAvatar):
    """Imitate the native mesh's lifecycle contract without importing WebEngine."""

    preview_changed = Signal(bool, str)

    def __init__(self):
        super().__init__()
        self.ready = False
        self.failed = False
        self._preview_active = False
        self._motion = 100
        self.starts = 0
        self.stops = 0
        self.voice_resets = 0

    def _sync_timer(self):
        super()._sync_timer()
        if getattr(self, '_preview_active', False) and not (
                self.ready and not self.failed and self.isVisible() and self.animated
                and self.state == 'ready' and self._motion > 0):
            self.stop_motion_preview()

    def become_ready(self):
        self.ready = True
        self.preview_changed.emit(False, 'Ready for a silent movement preview.')

    def start_motion_preview(self):
        self.starts += 1
        self._preview_active = True
        self.preview_changed.emit(True, 'Silent preview is running.')
        return True

    def stop_motion_preview(self):
        if self._preview_active:
            self.stops += 1
            self._preview_active = False
            self.preview_changed.emit(False, 'Movement preview stopped.')

    def finish_preview(self):
        self._preview_active = False
        self.preview_changed.emit(False, 'Movement preview finished. Normal idle has resumed.')

    def set_visual_controls(self, motion, sensitivity):
        self._motion = motion
        self._sync_timer()

    def set_voice_level(self, level):
        self.stop_motion_preview()
        super().set_voice_level(level)

    def reset_voice(self):
        # DesktopAvatar invokes reset_voice during initialization too.
        if hasattr(self, 'voice_resets'):
            self.voice_resets += 1
            self.stop_motion_preview()
        super().reset_voice()

    def dispose(self):
        self.stop_motion_preview()
        self.timer.stop()


class AvatarPreviewControllerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = application()

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        self.speech = PreviewSpeech()
        self.microphone = PreviewMicrophone()
        self.created = []
        self.widget_type = PreviewMesh

        def create_widget():
            widget = self.widget_type()
            self.created.append(widget)
            return widget

        self.factory_patch = patch.object(AvatarController, '_create_widget', side_effect=create_widget)
        self.factory_patch.start()
        self.addCleanup(self.factory_patch.stop)
        self.speech_start = patch.object(self.speech, 'speak', wraps=self.speech.speak).start()
        self.mic_start = patch.object(self.microphone, 'start', wraps=self.microphone.start).start()
        self.addCleanup(patch.stopall)
        settings = Settings('', DEFAULT_MODEL, 'Preview test', 'Test personality', tts_enabled=False)
        self.window = CompanionWindow(
            settings, speech=self.speech, microphone=self.microphone,
            preferences=Preferences(self.root / 'preferences.json'),
            characters=CharacterLibrary(self.root))

    def tearDown(self):
        self.window._worker = None
        self.window._closing = False
        self.window.request_quit()
        self.window.deleteLater()
        self.app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.app.processEvents()
        self.speech_start.assert_not_called()
        self.mic_start.assert_not_called()

    def mesh(self):
        self.window.show_avatar.setChecked(True)
        self.app.processEvents()
        widget = self.window.avatar.widget
        widget.become_ready()
        return widget

    def start_preview(self):
        self.assertTrue(self.window.preview_avatar_motion.isEnabled())
        self.window.preview_avatar_motion.click()
        self.assertTrue(self.window.avatar.widget._preview_active)

    def set_handsfree_flag(self, enabled):
        # Exercise the preview gate without invoking the real hands-free action.
        with QSignalBlocker(self.window.hands_free):
            self.window.hands_free.setChecked(enabled)
        self.window.avatar._preview_context_changed()

    def test_readiness_button_toggle_and_renderer_completion(self):
        self.assertFalse(self.window.preview_avatar_motion.isEnabled())
        self.window.show_avatar.setChecked(True)
        widget = self.window.avatar.widget
        self.assertFalse(self.window.preview_avatar_motion.isEnabled())
        self.assertIn('loading', self.window.avatar_preview_status.text())
        widget.become_ready()
        self.assertTrue(self.window.preview_avatar_motion.isEnabled())
        self.start_preview()
        self.assertEqual(self.window.preview_avatar_motion.text(), 'Stop preview')
        self.assertIn('running', self.window.avatar_preview_status.text())
        self.window.preview_avatar_motion.click()
        self.assertFalse(widget._preview_active)
        self.assertEqual(widget.stops, 1)
        self.assertEqual(self.window.preview_avatar_motion.text(), 'Preview movement')
        self.start_preview()
        widget.finish_preview()
        self.assertFalse(widget._preview_active)
        self.assertIn('finished', self.window.avatar_preview_status.text())
        self.assertTrue(self.window.preview_avatar_motion.isEnabled())

    def test_fallback_mascot_and_failed_mesh_cannot_start_a_preview(self):
        self.widget_type = DesktopAvatar
        self.window.show_avatar.setChecked(True)
        self.assertFalse(self.window.preview_avatar_motion.isEnabled())
        self.assertIn('mesh', self.window.avatar_preview_status.text())
        self.window.avatar.toggle_motion_preview()
        self.widget_type = PreviewMesh
        self.window.avatar.reload_avatar()
        widget = self.window.avatar.widget
        widget.ready = True
        widget.failed = True
        widget.preview_changed.emit(False, 'Renderer unavailable')
        self.assertFalse(self.window.preview_avatar_motion.isEnabled())
        self.window.avatar.toggle_motion_preview()
        self.assertEqual(widget.starts, 0)

    def test_all_context_gates_reject_even_direct_preview_requests(self):
        widget = self.mesh()
        controller = self.window.avatar
        cases = [
            ('hands-free', lambda: self.set_handsfree_flag(True), lambda: self.set_handsfree_flag(False)),
            ('speech', lambda: setattr(self.speech, 'busy', True), lambda: setattr(self.speech, 'busy', False)),
            ('microphone', lambda: setattr(self.microphone, 'state', 'recording'), lambda: setattr(self.microphone, 'state', 'idle')),
            ('worker', lambda: setattr(self.window, '_worker', object()), lambda: setattr(self.window, '_worker', None)),
            ('activity', lambda: setattr(self.window, 'activity', 'thinking'), lambda: setattr(self.window, 'activity', 'ready')),
            ('suspended', lambda: setattr(self.window, 'suspended', True), lambda: setattr(self.window, 'suspended', False)),
            ('closing', lambda: setattr(self.window, '_closing', True), lambda: setattr(self.window, '_closing', False)),
            ('zero movement', lambda: self.window.avatar_motion.setValue(0), lambda: self.window.avatar_motion.setValue(100)),
            ('hidden', lambda: self.window.show_avatar.setChecked(False), lambda: self.window.show_avatar.setChecked(True)),
            ('paused', lambda: self.window.animate_avatar.setChecked(False), lambda: self.window.animate_avatar.setChecked(True)),
        ]
        for label, block, restore in cases:
            with self.subTest(context=label):
                block()
                controller._preview_context_changed()
                self.assertFalse(self.window.preview_avatar_motion.isEnabled())
                self.assertTrue(self.window.avatar_preview_status.text())
                starts = widget.starts
                controller.toggle_motion_preview()
                self.assertEqual(widget.starts, starts)
                restore()
                controller._preview_context_changed()
                self.assertTrue(self.window.preview_avatar_motion.isEnabled())

    def test_speech_microphone_handsfree_and_activity_cancel_a_running_preview(self):
        widget = self.mesh()
        self.start_preview()
        self.speech.busy = True
        self.speech.state = 'loading'
        self.speech.changed.emit('Loading voice')
        self.assertFalse(widget._preview_active)
        self.speech.stop()
        self.start_preview()
        self.microphone.state = 'recording'
        self.microphone.changed.emit('recording')
        self.assertFalse(widget._preview_active)
        self.microphone.cancel()
        self.start_preview()
        self.set_handsfree_flag(True)
        self.assertFalse(widget._preview_active)
        self.set_handsfree_flag(False)
        self.start_preview()
        self.window.activity = 'thinking'
        self.window.activity_changed.emit('thinking')
        self.assertFalse(widget._preview_active)
        self.assertEqual(widget.stops, 4)

    def test_stop_and_playback_reset_cancel_without_changing_conversation(self):
        widget = self.mesh()
        before = (self.window.activity, list(self.window._messages), self.window._conversation_id)
        self.start_preview()
        resets = widget.voice_resets
        self.assertTrue(self.window.stop_button.isEnabled())
        self.window.stop_button.click()
        self.assertFalse(widget._preview_active)
        self.assertFalse(self.window.stop_button.isEnabled())
        self.assertGreater(widget.voice_resets, resets, 'Stop must reach the normal playback-reset path')
        self.assertEqual((self.window.activity, self.window._messages, self.window._conversation_id), before)
        self.start_preview()
        self.speech.playback_reset.emit()
        self.assertFalse(widget._preview_active)
        self.start_preview()
        self.speech.playback_level.emit(.5)
        self.assertFalse(widget._preview_active)
        self.assertEqual(widget.stops, 3)

    def test_hide_pause_zero_movement_and_reload_release_running_preview(self):
        widget = self.mesh()
        self.start_preview()
        self.window.show_avatar.setChecked(False)
        self.assertFalse(widget._preview_active)
        self.window.show_avatar.setChecked(True)
        self.start_preview()
        self.window.animate_avatar.setChecked(False)
        self.assertFalse(widget._preview_active)
        self.window.animate_avatar.setChecked(True)
        self.start_preview()
        self.window.avatar_motion.setValue(0)
        self.assertFalse(widget._preview_active)
        self.window.avatar_motion.setValue(100)
        self.start_preview()
        self.window.avatar.reload_avatar()
        self.assertFalse(widget._preview_active)
        self.assertIsNot(self.window.avatar.widget, widget)
        self.assertFalse(self.window.preview_avatar_motion.isEnabled(), 'Replacement must finish loading first')


if __name__ == '__main__':
    unittest.main()
