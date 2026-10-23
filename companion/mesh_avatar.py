"""Transparent local mesh renderer, with activity cues and playback lip-sync."""
from PySide6.QtCore import QEvent, QFile, QIODevice, QObject, Qt, QTimer, QUrl, Signal, Slot
from PySide6.QtGui import QColor, QCursor
from PySide6.QtWidgets import QLabel, QSizeGrip, QVBoxLayout
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineCore import (QWebEnginePage, QWebEngineProfile,
                                     QWebEngineSettings, QWebEngineUrlRequestInterceptor)
from PySide6.QtWebEngineWidgets import QWebEngineView

from .avatar import DesktopAvatar
from .avatar_assets import AvatarAssets


class LocalRequests(QWebEngineUrlRequestInterceptor):
    def __init__(self, url, parent):
        super().__init__(parent)
        self.base = url.rsplit('/', 1)[0] + '/'

    def interceptRequest(self, info):
        url = info.requestUrl().toString()
        if not (url.startswith(self.base) or url.startswith('blob:') or url == 'about:blank'):
            info.block(True)


class RendererBridge(QObject):
    pauseChanged = Signal(bool)
    voiceChanged = Signal(float, int, bool)
    activityChanged = Signal(str, int)
    controlsChanged = Signal(int, int, int)
    attentionChanged = Signal(bool, int, int, int)
    cursorChanged = Signal(float, float, bool, int)
    previewChanged = Signal(bool, int)
    previewEnded = Signal(int, bool)
    pageVisibility = Signal(bool)
    visibilityChanged = Signal(bool)
    qualityChanged = Signal(bool)
    status = Signal(str)

    @Slot(str)
    def report(self, status):
        if status in {'ready', 'error'}:
            self.status.emit(status)

    @Slot(int, bool)
    def finishPreview(self, sequence, completed):
        self.previewEnded.emit(sequence, completed)

    @Slot(bool)
    def reportVisibility(self, visible):
        self.pageVisibility.emit(visible)


class MeshDesktopAvatar(DesktopAvatar):
    preview_changed = Signal(bool, str)

    def __init__(self, path):
        super().__init__()
        self.assets = None
        self.ready = False
        self.failed = False
        self._disposed = False
        self._voice_sequence = 0
        self._activity_sequence = 0
        self._controls_sequence = 0
        self._motion = 100
        self._sensitivity = 100
        self._hd = True
        self._cursor_attention = True
        self._gaze = 100
        self._hair = 45
        self._attention_sequence = 0
        self._cursor_sequence = 0
        self._cursor_sample = None
        self._preview_active = False
        self._preview_sequence = 0
        self._page_visible = True
        self.cursor_timer = QTimer(self)
        self.cursor_timer.setInterval(100)  # Local logical coordinates; no input hook.
        self.cursor_timer.timeout.connect(self._sample_cursor)
        self.clearMask()
        self.setMinimumSize(220, 240)
        self.setMaximumSize(640, 700)
        self.resize(320, 350)
        self.timer.stop()  # The native mascot's timer never drives the mesh.
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.view = QWebEngineView(self)
        self.view.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.view.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.view.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
        self.view.setStyleSheet('background: transparent')
        layout.addWidget(self.view, 1)
        self.notice = QLabel('Loading avatar…', self)
        self.notice.setWordWrap(True)
        self.notice.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.notice.setStyleSheet('QLabel { background:#222633; color:#eceaf5; padding:6px; border-radius:8px; }')
        layout.addWidget(self.notice)
        self.grip = QSizeGrip(self)
        self.grip.setFixedSize(18, 18)
        layout.addWidget(self.grip, 0, Qt.AlignmentFlag.AlignRight)
        # Off-the-record profile: no cookies or cache persisted into user data.
        self.profile = QWebEngineProfile(self)
        self.page = QWebEnginePage(self.profile, self.view)
        self.view.setPage(self.page)
        self.page.setBackgroundColor(QColor(Qt.GlobalColor.transparent))
        self.page.settings().setAttribute(QWebEngineSettings.WebAttribute.PlaybackRequiresUserGesture, True)
        self.page.settings().setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, False)
        self.page.settings().setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, False)
        self.page.permissionRequested.connect(lambda permission: permission.deny())
        self.channel = QWebChannel(self.page)
        self.bridge = RendererBridge(self.channel)
        self.channel.registerObject('renderer', self.bridge)
        self.page.setWebChannel(self.channel)
        self.bridge.status.connect(self._status)
        self.bridge.previewEnded.connect(self._preview_finished)
        self.bridge.pageVisibility.connect(self._page_visibility)
        self.page.renderProcessTerminated.connect(lambda *_: self._status('error'))
        self.view.loadFinished.connect(lambda ok: None if ok else self._status('error'))
        self.timeout = QTimer(self)
        self.timeout.setSingleShot(True)
        self.timeout.timeout.connect(lambda: self._status('error'))
        try:
            script = QFile(':/qtwebchannel/qwebchannel.js')
            if not script.open(QIODevice.OpenModeFlag.ReadOnly):
                raise ValueError('Qt WebChannel resource is missing.')
            bridge_script = bytes(script.readAll())
            script.close()
            self.assets = AvatarAssets(path, bridge_script=bridge_script)
            self.interceptor = LocalRequests(self.assets.url, self.profile)
            self.profile.setUrlRequestInterceptor(self.interceptor)
            self.timeout.start(20000)
            self.view.setUrl(QUrl(self.assets.url))
        except (OSError, ValueError):
            self._status('error')

    @Slot(str)
    def _status(self, status):
        if self._disposed or self.failed:
            return
        self.timeout.stop()
        if status == 'ready':
            self.ready = True
            self.notice.hide()
            self._publish_activity()
            self.set_visual_controls(self._motion, self._sensitivity)
            self.set_hd(self._hd)
            self.set_attention_controls(self._cursor_attention, self._gaze, self._hair)
            self._sync_timer()
            self.preview_changed.emit(False, 'Ready for a silent movement preview.')
        else:
            self.failed = True
            self.ready = False
            self.view.hide()
            self.grip.hide()
            self.setFixedSize(280, 280)
            self.notice.setText('Avatar unavailable. Using the simple mascot.\nCheck local files / graphics support.\nSee docs/avatar-stage4.md.')
            self.notice.show()
            # Leave space above the error message for the native mascot.
            self.layout().insertSpacing(0, 174)
            if self.assets:
                self.assets.close()
                self.assets = None
            self._sync_timer()
            self.update()
            self.preview_changed.emit(False, 'Movement preview needs a working mesh avatar.')

    def _sync_timer(self):
        if not hasattr(self, 'bridge'):
            self.timer.stop()
            return
        self.timer.stop()
        present = self.isVisible() and not self.isMinimized() and self._page_visible
        if getattr(self, '_preview_active', False) and not (
                self.ready and not self.failed and not self._disposed and present
                and self.animated and self._motion > 0 and self.state == 'ready'):
            self._end_preview('Movement preview stopped.')
        if hasattr(self, 'cursor_timer'):
            active = (self.ready and not self.failed and not self._disposed and present
                      and self.animated and self._cursor_attention and self._motion > 0
                      and self.state == 'ready' and not self._preview_active)
            if active:
                self.cursor_timer.start()
                # First sample runs on the next timer turn, after visibility,
                # pause and activity signals have reached the renderer.
            else:
                self.cursor_timer.stop()
                self._clear_cursor()
        if self.failed:
            DesktopAvatar._sync_timer(self)
        self.bridge.visibilityChanged.emit(present)
        self.bridge.pauseChanged.emit(not (present and self.animated and self.ready
                                          and self.state not in {'suspended', 'closing'}))

    @Slot(bool)
    def _page_visibility(self, visible):
        if self._disposed:
            return
        self._page_visible = bool(visible)
        self._sync_timer()
        self.preview_changed.emit(self._preview_active, '')

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.Type.WindowStateChange and hasattr(self, 'bridge'):
            self._sync_timer()
            self.preview_changed.emit(self._preview_active, '')

    def paintEvent(self, event):
        if self.failed:
            super().paintEvent(event)

    def set_activity(self, state):
        super().set_activity(state)
        if getattr(self, 'ready', False) and not self.failed and not self._disposed:
            self._publish_activity()

    def _publish_activity(self):
        self._activity_sequence += 1
        self.bridge.activityChanged.emit(self.state, self._activity_sequence)

    def hideEvent(self, event):
        if hasattr(self, 'bridge'):
            self.bridge.visibilityChanged.emit(False)
            self.reset_voice()
        super().hideEvent(event)
        self._sync_timer()

    def set_visual_controls(self, motion, sensitivity):
        self._motion = max(0, min(100, motion))
        self._sensitivity = max(25, min(200, sensitivity))
        self._controls_sequence += 1
        if self.ready and not self.failed and not self._disposed:
            self.bridge.controlsChanged.emit(self._motion, self._sensitivity, self._controls_sequence)
        self._sync_timer()

    def set_attention_controls(self, enabled, gaze, hair):
        self._cursor_attention = bool(enabled)
        self._gaze = max(0, min(100, gaze))
        self._hair = max(20, min(80, hair))
        self._attention_sequence += 1
        if self.ready and not self.failed and not self._disposed:
            self.bridge.attentionChanged.emit(self._cursor_attention, self._gaze, self._hair,
                                               self._attention_sequence)
        self._sync_timer()

    def _clear_cursor(self):
        if self._cursor_sample is not None:
            self._cursor_sample = None
            self._cursor_sequence += 1
            self.bridge.cursorChanged.emit(0., 0., False, self._cursor_sequence)

    def _sample_cursor(self):
        if not self.cursor_timer.isActive():
            return
        # QCursor and QWidget geometry share Qt's logical desktop coordinates,
        # including negative monitor origins. Map into the view before crossing
        # the bridge; JS uses the canvas's CSS coordinates, never device pixels.
        point = self.view.mapFromGlobal(QCursor.pos())
        if self._press is not None:  # Don't chase the hand that drags this window.
            self._clear_cursor()
            return
        sample = (point.x(), point.y(), self.view.width(), self.view.height())
        if sample != self._cursor_sample:
            self._cursor_sample = sample
            self._cursor_sequence += 1
            self.bridge.cursorChanged.emit(point.x() / max(1, self.view.width()),
                                           point.y() / max(1, self.view.height()), True,
                                           self._cursor_sequence)

    def set_hd(self, enabled):
        self._hd = bool(enabled)
        if self.ready and not self.failed and not self._disposed:
            self.bridge.qualityChanged.emit(self._hd)

    def start_motion_preview(self):
        if (self._preview_active or not self.ready or self.failed or self._disposed
                or not self.isVisible() or self.isMinimized() or not self._page_visible
                or not self.animated or self._motion <= 0
                or self.state != 'ready'):
            return False
        self._preview_active = True
        self._preview_sequence += 1
        self._sync_timer()  # Stop cursor polling before the finite demo starts.
        self.bridge.previewChanged.emit(True, self._preview_sequence)
        self.preview_changed.emit(True, 'Silent preview: left, right, a small tilt, then rest.')
        return True

    def _end_preview(self, message):
        if not getattr(self, '_preview_active', False):
            return
        self._preview_active = False
        self._preview_sequence += 1
        self.bridge.previewChanged.emit(False, self._preview_sequence)
        self.preview_changed.emit(False, message)

    def stop_motion_preview(self):
        self._end_preview('Movement preview stopped.')
        self._sync_timer()

    @Slot(int, bool)
    def _preview_finished(self, sequence, completed):
        if sequence != self._preview_sequence or not self._preview_active or self._disposed:
            return
        self._preview_active = False
        message = ('Movement preview finished. Normal idle has resumed.' if completed else
                   'Movement preview stopped. Try again when idle and visible.')
        self.preview_changed.emit(False, message)
        self._sync_timer()

    def set_voice_level(self, level):
        was_previewing = self._preview_active
        self._end_preview('Movement preview stopped for voice playback.')
        if was_previewing:
            self._sync_timer()
        if self.failed:
            DesktopAvatar.set_voice_level(self, level)
            return
        if self.ready and not self.failed and not self._disposed and self.isVisible() and self.animated:
            self._voice_sequence += 1
            self.bridge.voiceChanged.emit(level, self._voice_sequence, False)

    def reset_voice(self):
        was_previewing = self._preview_active
        self._end_preview('Movement preview stopped.')
        if was_previewing:
            self._sync_timer()
        self.voice_level = 0.
        self._voice_sequence += 1
        self.bridge.voiceChanged.emit(0., self._voice_sequence, True)

    def dispose(self):
        if self._disposed:
            return
        self._end_preview('Movement preview stopped.')
        self._disposed = True
        self.cursor_timer.stop()
        self._clear_cursor()
        self.reset_voice()
        self.timeout.stop()
        self.bridge.pauseChanged.emit(True)
        self.view.stop()
        self.page.runJavaScript("window.dispatchEvent(new Event('pagehide'))")
        self.view.setUrl(QUrl('about:blank'))
        if self.assets:
            self.assets.close()
            self.assets = None
