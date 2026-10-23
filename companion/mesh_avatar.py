"""Transparent Qt host for the local mesh renderer (display/idle only)."""
from PySide6.QtCore import QFile, QIODevice, QObject, Qt, QTimer, QUrl, Signal, Slot
from PySide6.QtGui import QColor
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
    status = Signal(str)

    @Slot(str)
    def report(self, status):
        if status in {'ready', 'error'}:
            self.status.emit(status)


class MeshDesktopAvatar(DesktopAvatar):
    def __init__(self, path):
        super().__init__()
        self.assets = None
        self.ready = False
        self.failed = False
        self._disposed = False
        self._voice_sequence = 0
        self.clearMask()
        self.setMinimumSize(220, 240)
        self.setMaximumSize(720, 760)
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
            self._sync_timer()
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

    def _sync_timer(self):
        if not hasattr(self, 'bridge'):
            self.timer.stop()
            return
        self.timer.stop()
        if self.failed:
            DesktopAvatar._sync_timer(self)
        self.bridge.pauseChanged.emit(not (self.isVisible() and self.animated and self.ready
                                          and self.state not in {'suspended', 'closing'}))

    def paintEvent(self, event):
        if self.failed:
            super().paintEvent(event)

    def hideEvent(self, event):
        if hasattr(self, 'bridge'):
            self.reset_voice()
        super().hideEvent(event)
        self._sync_timer()

    def set_voice_level(self, level):
        if self.failed:
            DesktopAvatar.set_voice_level(self, level)
            return
        if self.ready and not self.failed and not self._disposed and self.isVisible() and self.animated:
            self._voice_sequence += 1
            self.bridge.voiceChanged.emit(level, self._voice_sequence, False)

    def reset_voice(self):
        self.voice_level = 0.
        self._voice_sequence += 1
        self.bridge.voiceChanged.emit(0., self._voice_sequence, True)

    def dispose(self):
        if self._disposed:
            return
        self._disposed = True
        self.reset_voice()
        self.timeout.stop()
        self.bridge.pauseChanged.emit(True)
        self.view.stop()
        self.page.runJavaScript("window.dispatchEvent(new Event('pagehide'))")
        self.view.setUrl(QUrl('about:blank'))
        if self.assets:
            self.assets.close()
            self.assets = None
