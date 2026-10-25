"""Transparent local mesh renderer, with activity cues and playback lip-sync."""
import time

from PySide6.QtCore import QEvent, QFile, QIODevice, QObject, Qt, QTimer, QUrl, Signal, Slot
from PySide6.QtGui import QColor, QCursor, QFont, QPainter, QPixmap
from PySide6.QtWidgets import QLabel, QSizeGrip, QVBoxLayout
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineCore import (QWebEnginePage, QWebEngineProfile,
                                     QWebEngineSettings, QWebEngineUrlRequestInterceptor)
from PySide6.QtWebEngineWidgets import QWebEngineView

from .avatar import DesktopAvatar


class ShapeGrip(QSizeGrip):
    """The corner grip, resizing her window in her own proportions as it is dragged.
    (A plain grip sets any size; correcting it afterwards made the two fight and the window jitter.)"""

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return super().mousePressEvent(event)
        self._start = (event.globalPosition(), self.window().size())
        event.accept()

    def mouseMoveEvent(self, event):
        start = getattr(self, '_start', None)
        if start is None or not event.buttons() & Qt.MouseButton.LeftButton:
            return super().mouseMoveEvent(event)
        origin, size = start
        delta = event.globalPosition() - origin
        window = self.window()
        ratio = window.aspect or size.width() / max(1, size.height())
        # Whichever way the pointer went further sets the size; the other edge follows.
        width = max(size.width() + delta.x(), (size.height() + delta.y()) * ratio)
        fitted = window.fitted(round(width))
        if fitted != (window.width(), window.height()):
            window.resize(*fitted)
        event.accept()

    def mouseReleaseEvent(self, event):
        if getattr(self, '_start', None) is None:
            return super().mouseReleaseEvent(event)
        self._start = None
        event.accept()
from .avatar_assets import AvatarAssets
from .work_panel import SAMPLES, WorkPanel


class PetStrokes:
    """Pointer strokes, not passes: two direction changes (on either axis, each after
    at least 8 px of travel) within 1.5 seconds."""

    def __init__(self):
        self.reset()

    def reset(self):
        self.last, self.direction, self.travel, self.turns = None, [0, 0], [0., 0.], []

    def feed(self, x, y, now):
        point = (x, y)
        if self.last is not None:
            for axis in (0, 1):
                delta = point[axis] - self.last[axis]
                if abs(delta) < 1.5:
                    continue
                direction = 1 if delta > 0 else -1
                if direction != self.direction[axis]:
                    if self.direction[axis] and self.travel[axis] >= 8:
                        self.turns.append(now)
                    self.direction[axis], self.travel[axis] = direction, 0.
                self.travel[axis] += abs(delta)
        self.last = point
        self.turns = [turn for turn in self.turns if now - turn < 1.5]
        return len(self.turns) >= 2


_PAT = None


def _pat_cursor():
    """A small hand, palm down, while you pet her."""
    global _PAT
    if _PAT is None:
        pixmap = QPixmap(40, 40)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        font = QFont("Segoe UI Emoji")
        font.setPixelSize(28)
        painter.setFont(font)
        painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "🫳")
        painter.end()
        _PAT = QCursor(pixmap, 20, 26)
    return _PAT


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
    framingChanged = Signal(str)
    appearanceChanged = Signal(str)
    lifeChanged = Signal(int, int)
    gestureRequested = Signal(str, int)
    workChanged = Signal(str, str, int)
    status = Signal(str)
    life = Signal(str)
    petChanged = Signal(float, float, bool, int)
    petting = Signal(bool)
    aspect = Signal(float)

    @Slot(float)
    def reportAspect(self, ratio):
        if 0.2 <= ratio <= 3:
            self.aspect.emit(ratio)

    @Slot(str)
    def report(self, status):
        if status in {'ready', 'error'}:
            self.status.emit(status)

    @Slot(str)
    def reportLife(self, state):
        if state in {'awake', 'drowsy', 'asleep'}:
            self.life.emit(state)

    @Slot(bool)
    def reportPetting(self, active):
        self.petting.emit(bool(active))

    @Slot(int, bool)
    def finishPreview(self, sequence, completed):
        self.previewEnded.emit(sequence, completed)

    @Slot(bool)
    def reportVisibility(self, visible):
        self.pageVisibility.emit(visible)


class MeshDesktopAvatar(DesktopAvatar):
    preview_changed = Signal(bool, str)

    def __init__(self, path, *, kind='mesh', appearance=None):
        super().__init__()
        self.kind = kind
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
        self._framing = 'portrait'
        self._appearance = dict(appearance or {})
        self._cursor_attention = True
        self._gaze = 100
        self._hair = 45
        self._attention_sequence = 0
        self._cursor_sequence = 0
        self._cursor_sample = None
        self._preview_active = False
        self._preview_sequence = 0
        self._page_visible = True
        self._sleep_minutes = 5
        self._life_sequence = 0
        self._gesture_sequence = 0
        self._work_sequence = 0
        self.life_state = 'awake'
        # Petting: back-and-forth pointer strokes, no button needed (pressing still drags).
        self._pet_sequence = 0
        self._strokes = PetStrokes()
        self._pet_active = False
        self._pet_sent = 0.
        self._pet_end = QTimer(self)
        self._pet_end.setSingleShot(True)
        self._pet_end.setInterval(650)
        self._pet_end.timeout.connect(self._stop_petting)
        self.setMouseTracking(True)
        self.cursor_timer = QTimer(self)
        self.cursor_timer.setInterval(100)  # Local logical coordinates; no input hook.
        self.cursor_timer.timeout.connect(self._sample_cursor)
        self.clearMask()
        self.setMinimumSize(220, 240)
        self.setMaximumSize(640, 900)
        self.aspect = None  # Width / height of what the page shows; the window keeps it.
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
        # Floats over the corner rather than taking a row of its own below her.
        self.grip = ShapeGrip(self)
        self.grip.setFixedSize(18, 18)
        self.work_panel = WorkPanel(self)
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
        self.bridge.life.connect(self._life_changed)
        self.bridge.aspect.connect(self._set_aspect)
        self.bridge.petting.connect(self._petting_changed)
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
            self.assets = AvatarAssets(path, bridge_script=bridge_script, kind=kind)
            self.interceptor = LocalRequests(self.assets.url, self.profile)
            self.profile.setUrlRequestInterceptor(self.interceptor)
            self.timeout.start(60000 if kind == 'live2d' else 20000)
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
            self.set_framing(self._framing)
            self.set_appearance(self._appearance)
            self.set_attention_controls(self._cursor_attention, self._gaze, self._hair)
            self.set_sleep_delay(self._sleep_minutes)
            self._sync_timer()
            self.preview_changed.emit(False, 'Ready for a silent movement preview.')
        else:
            self.failed = True
            self.ready = False
            self.view.hide()
            self.grip.hide()
            self.setFixedSize(280, 280)
            self.notice.setText(
                'Live2D unavailable. Choose AI portrait in Settings to restore it.\n'
                'Check the model and run Setup Live2D.cmd.\nSee docs/experimental-live2d.md.'
                if self.kind == 'live2d' else
                'Layered avatar unavailable. Choose AI portrait in Settings to restore it.\n'
                'Rebuild the local art files. See docs/ai-layered-rig.md.'
                if self.kind == 'layered' else
                'Avatar unavailable. Using the simple mascot.\nCheck local files / graphics support.\nSee docs/avatar-stage4.md.')
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
        if getattr(self, 'life_state', 'awake') != 'awake':
            self._life_tooltip()
        if getattr(self, 'ready', False) and not self.failed and not self._disposed:
            self._publish_activity()

    def set_sleep_delay(self, minutes):
        """Minutes without interaction before she dozes off; 0 keeps her awake."""
        self._sleep_minutes = max(0, min(120, int(minutes)))
        self._life_sequence += 1
        if self.ready and not self.failed and not self._disposed:
            self.bridge.lifeChanged.emit(self._sleep_minutes * 60, self._life_sequence)  # seconds

    def mouseMoveEvent(self, event):
        super().mouseMoveEvent(event)
        if not event.buttons():
            self._track_pet(event.position())

    def leaveEvent(self, event):
        self._stop_petting()
        super().leaveEvent(event)

    def _track_pet(self, position):
        if not (self.ready and not self.failed and not self._disposed and self.animated):
            return
        now = time.monotonic()
        if self._strokes.feed(position.x(), position.y(), now) or self._pet_active:
            self._pet_active = True
            self._pet_end.start()
            if now - self._pet_sent >= .04:
                self._pet_sent = now
                view = self.view.mapFrom(self, position.toPoint())
                self._pet_sequence += 1
                self.bridge.petChanged.emit(view.x() / max(1, self.view.width()), view.y() / max(1, self.view.height()),
                                            True, self._pet_sequence)

    @Slot()
    def _stop_petting(self):
        self._pet_end.stop()
        self._strokes.reset()
        if self._pet_active:
            self._pet_active = False
            self._pet_sequence += 1
            self.bridge.petChanged.emit(0., 0., False, self._pet_sequence)

    @Slot(bool)
    def _petting_changed(self, active):
        self.setCursor(_pat_cursor() if active else Qt.CursorShape.OpenHandCursor)

    def mouseReleaseEvent(self, event):
        clicked = event.button() == Qt.MouseButton.LeftButton and self._press is not None and not self._dragged
        super().mouseReleaseEvent(event)
        if clicked and self.ready and not self.failed and not self._disposed:
            self._gesture_sequence += 1
            self.bridge.gestureRequested.emit('poke', self._gesture_sequence)

    def set_work(self, state, text=""):
        """A computer task's progress: start, a step kind, wait, done or failed."""
        if self.ready and not self.failed and not self._disposed and self.animated:
            self._work_sequence += 1
            self.bridge.workChanged.emit(state, str(text)[:200], self._work_sequence)
            self.work_panel.show_step(state, text)

    def play_cue(self, name):
        """An expression cue, or an animation-tester command; True when sent to the rig."""
        from .avatar_cues import CUES, TESTS
        if (name in CUES or name in TESTS) and self.ready and not self.failed and not self._disposed and self.animated:
            self._gesture_sequence += 1
            self.bridge.gestureRequested.emit(name, self._gesture_sequence)
            if name.startswith('test:work:'):
                kind = name[len('test:work:'):]
                self.work_panel.show_step(kind, SAMPLES.get(kind, ''))
            return True
        return False

    def fitted(self, width=None, height=None):
        """The window size matching her framing, from a width (or a height when only that is given)."""
        ratio = self.aspect or 320 / 350
        if width is None:
            width = round(height * ratio)
        width = max(self.minimumWidth(), min(width, self.maximumWidth(), int(self.maximumHeight() * ratio)))
        return width, max(self.minimumHeight(), round(width / ratio))

    @Slot(float)
    def _set_aspect(self, ratio):
        self.aspect = ratio
        # Once, when the page reports her framing; sizes set later are fitted before they apply.
        if not (self._disposed or self.failed) and self.fitted(self.width()) != (self.width(), self.height()):
            self.resize(*self.fitted(self.width()))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'work_panel'):
            self.work_panel.follow()
        if hasattr(self, 'grip'):
            self.grip.move(self.width() - self.grip.width(), self.height() - self.grip.height())
            self.grip.raise_()

    @Slot(str)
    def _life_changed(self, state):
        self.life_state = state
        self._life_tooltip()

    def _life_tooltip(self):
        from .avatar import LABELS
        label = {'drowsy': 'Drowsy', 'asleep': 'Sleeping'}.get(self.life_state) or LABELS[self.state]
        self.setToolTip(f"{self.name}: {label}\nClick to open chat · Drag to move · Right-click for controls")

    def _publish_activity(self):
        self._activity_sequence += 1
        self.bridge.activityChanged.emit(self.state, self._activity_sequence)

    def moveEvent(self, event):
        super().moveEvent(event)
        if hasattr(self, 'work_panel'):
            self.work_panel.follow()

    def showEvent(self, event):
        super().showEvent(event)
        if hasattr(self, 'work_panel'):
            self.work_panel.follow()

    def hideEvent(self, event):
        if hasattr(self, 'work_panel'):
            self.work_panel.hide()
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

    def set_framing(self, value):
        self._framing = value if value in {'portrait', 'full'} else 'portrait'
        if self.ready and not self.failed and not self._disposed:
            self.bridge.framingChanged.emit(self._framing)

    def set_appearance(self, values):
        import json
        self._appearance = dict(values)
        if self.ready and not self.failed and not self._disposed:
            self.bridge.appearanceChanged.emit(json.dumps(self._appearance))

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
        self.work_panel.timer.stop()
        self.work_panel.close()
        self.work_panel.deleteLater()
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
