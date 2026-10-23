"""A locally drawn desktop mascot. It never starts recording or makes requests."""

import math

from PySide6.QtCore import QObject, QPoint, QPointF, QRectF, QSignalBlocker, Qt, QTimer, Signal, Slot
from PySide6.QtGui import QColor, QFont, QGuiApplication, QPainter, QPainterPath, QPen, QRegion
from PySide6.QtWidgets import QApplication, QMenu, QWidget


LABELS = {
    "ready": "Ready", "opening_mic": "Opening mic", "listening": "Listening",
    "transcribing": "Transcribing", "thinking": "Thinking", "replying": "Writing",
    "summarizing": "Summarizing", "preparing_voice": "Loading voice", "speaking": "Speaking",
    "suspended": "Suspended", "error": "Needs attention", "closing": "Closing",
}
COLORS = {"listening": "#91cdb8", "opening_mic": "#91cdb8", "speaking": "#f2bf9a",
          "error": "#edaaa8", "suspended": "#929bad"}


def activity_state(*, closing=False, suspended=False, microphone="idle", speech="idle",
                   speech_busy=False, working=False, summary=False, has_reply=False, error=False):
    if closing:
        return "closing"
    if suspended:
        return "suspended"
    if microphone == "opening":
        return "opening_mic"
    if microphone in {"recording", "listening"}:
        return "listening"
    if microphone in {"loading", "transcribing"}:
        return "transcribing"
    if speech_busy and speech == "speaking":
        return "speaking"
    if working:
        return "summarizing" if summary else "replying" if has_reply else "thinking"
    if speech_busy:
        return "preparing_voice"
    return "error" if error else "ready"


def visible_position(point, size, areas):
    """Choose the nearest available monitor and keep the entire avatar reachable."""
    candidates = []
    for area in areas:
        x = max(area.left(), min(point.x(), max(area.left(), area.right() - size.width() + 1)))
        y = max(area.top(), min(point.y(), max(area.top(), area.bottom() - size.height() + 1)))
        candidate = QPoint(x, y)
        candidates.append(((candidate - point).manhattanLength(), candidate))
    return min(candidates, key=lambda item: item[0])[1] if candidates else QPoint(20, 20)


class DesktopAvatar(QWidget):
    open_requested = Signal()
    hide_requested = Signal()
    menu_requested = Signal(QPoint)
    resized = Signal()

    def __init__(self):
        # A separate tool window stays reachable when the chat is hidden in the tray.
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint
                         | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_QuitOnClose, False)
        self.setFixedSize(168, 174)
        self.setMask(QRegion(18, 7, 132, 128, QRegion.RegionType.Ellipse)
                     | QRegion(18, 140, 132, 26))
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.state = "ready"
        self.name = "Mira"
        self.animated = True
        self.voice_level = 0.
        self._phase = 0
        self._press = None
        self._offset = QPoint()
        self._dragged = False
        self.timer = QTimer(self)
        self.timer.setInterval(80)
        self.timer.timeout.connect(self._tick)
        self.set_activity("ready")

    def set_name(self, name):
        self.name = name
        self.setWindowTitle(f"{name} · Desktop avatar")
        self.set_activity(self.state)

    def set_activity(self, state):
        self.state = state if state in LABELS else "ready"
        label = LABELS[self.state]
        self.setToolTip(f"{self.name}: {label}\nClick to open chat · Drag to move · Right-click for controls")
        self.setAccessibleName(f"{self.name} desktop avatar")
        self.setAccessibleDescription(label)
        self._sync_timer()
        self.update()

    def set_animated(self, animated):
        self.animated = animated
        if not animated:
            self._phase = 0
            self.reset_voice()
        self._sync_timer()
        self.update()

    def set_voice_level(self, level):
        self.voice_level = max(0., min(1., level)) if self.animated and self.isVisible() else 0.
        self.update()

    def reset_voice(self):
        self.voice_level = 0.
        self.update()

    def _sync_timer(self):
        if self.isVisible() and self.animated and self.state not in {"suspended", "error", "closing"}:
            self.timer.start()
        else:
            self.timer.stop()

    @Slot()
    def _tick(self):
        self._phase = (self._phase + 1) % 240
        self.update()

    def showEvent(self, event):
        super().showEvent(event)
        self._sync_timer()

    def hideEvent(self, event):
        self.timer.stop()
        self.reset_voice()
        self._press = None
        super().hideEvent(event)

    def closeEvent(self, event):
        self.hide_requested.emit()
        self.hide()
        event.ignore()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.resized.emit()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._press = event.globalPosition().toPoint()
            self._offset = self._press - self.pos()
            self._dragged = False
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()

    def mouseMoveEvent(self, event):
        if self._press is not None and event.buttons() & Qt.MouseButton.LeftButton:
            point = event.globalPosition().toPoint()
            if (point - self._press).manhattanLength() >= QApplication.startDragDistance():
                self._dragged = True
            if self._dragged:
                self.move(visible_position(point - self._offset, self.size(),
                                          [screen.availableGeometry() for screen in QGuiApplication.screens()]))
            event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._press is not None:
            self._press = None
            self.setCursor(Qt.CursorShape.OpenHandCursor)
            if not self._dragged:
                self.open_requested.emit()
            event.accept()

    def contextMenuEvent(self, event):
        self.menu_requested.emit(event.globalPos())
        event.accept()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        phase = self._phase if self.animated else 0
        bob = math.sin(phase / 10) * 2 if self.state not in {"suspended", "closing", "error"} else 0
        accent = QColor(COLORS.get(self.state, "#b7a9ff"))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(15, 18, 28, 55))
        painter.drawEllipse(QRectF(46, 125, 76, 9))
        painter.save()
        painter.translate(0, bob)
        painter.setBrush(QColor(accent.red(), accent.green(), accent.blue(), 30))
        radius = 60 + (math.sin(phase / 4) * 2 if self.state == "listening" else 0)
        painter.drawEllipse(QPointF(84, 70), radius, radius)
        painter.setBrush(accent.darker(115))
        painter.drawEllipse(QRectF(24, 73, 18, 28))
        painter.drawEllipse(QRectF(126, 73, 18, 28))
        painter.setBrush(accent)
        painter.drawRoundedRect(QRectF(34, 22, 100, 105), 46, 46)
        painter.setBrush(accent.lighter(115))
        painter.drawEllipse(QRectF(52, 32, 37, 12))
        painter.setPen(QPen(QColor("#28253c"), 4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        closed_eyes = self.state in {"suspended", "closing"} or (self.animated and phase % 72 in {65, 66})
        thinking = self.state in {"thinking", "replying", "summarizing", "preparing_voice", "transcribing"}
        shift = math.sin(phase / 9) * 2 if thinking else 0
        for x in (64, 104):
            if closed_eyes:
                painter.drawLine(QPointF(x - 5, 70), QPointF(x + 5, 70))
            else:
                painter.drawLine(QPointF(x + shift, 64), QPointF(x + shift, 75))
        if self.voice_level > 0:
            painter.setBrush(QColor("#28253c"))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(QRectF(77, 88, 14, 3 + self.voice_level * 10))
        else:
            smile = QPainterPath(QPointF(75, 90))
            smile.quadTo(QPointF(84, 98 if self.state != "error" else 83), QPointF(93, 90))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(smile)
        if thinking:
            painter.setPen(Qt.PenStyle.NoPen)
            for index in range(3):
                color = QColor("#eee7ff")
                color.setAlpha(230 if (phase // 4) % 3 == index else 85)
                painter.setBrush(color)
                painter.drawEllipse(QPointF(74 + index * 10, 111), 2, 2)
        painter.restore()
        painter.setPen(QPen(accent.darker(155), 1))
        painter.setBrush(QColor("#222633"))
        painter.drawRoundedRect(QRectF(18, 140, 132, 26), 12, 12)
        painter.setPen(QColor("#eceaf5"))
        font = QFont("Segoe UI")
        font.setPixelSize(12)
        painter.setFont(font)
        painter.drawText(QRectF(18, 140, 132, 26), Qt.AlignmentFlag.AlignCenter, LABELS[self.state])


class AvatarController(QObject):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.widget = None
        self._shutdown = False
        self._position = (window.settings.avatar_x, window.settings.avatar_y)
        self._dimensions = (window.settings.avatar_width, window.settings.avatar_height)
        self._preview_message = ''
        window.show_avatar.toggled.connect(self.set_enabled)
        window.animate_avatar.toggled.connect(self.set_animated)
        window.reset_avatar.clicked.connect(self.reset_position)
        window.avatar_size.valueChanged.connect(self.set_size)
        window.avatar_motion.valueChanged.connect(self.set_visual_controls)
        window.avatar_lip_sensitivity.valueChanged.connect(self.set_visual_controls)
        window.avatar_hd.toggled.connect(self.set_hd)
        window.avatar_cursor_attention.toggled.connect(self.set_attention_controls)
        window.avatar_gaze.valueChanged.connect(self.set_attention_controls)
        window.avatar_hair.valueChanged.connect(self.set_attention_controls)
        window.preview_avatar_motion.clicked.connect(self.toggle_motion_preview)
        window.hands_free.toggled.connect(self._preview_context_changed)
        window.speech.changed.connect(self._preview_context_changed)
        window.microphone.changed.connect(self._preview_context_changed)
        window.activity_changed.connect(self.set_activity)
        window.closed.connect(self.shutdown)
        if hasattr(window.speech, 'playback_level'):
            window.speech.playback_level.connect(self.set_voice_level)
            window.speech.playback_reset.connect(self.reset_voice)
        app = QGuiApplication.instance()
        app.screenAdded.connect(self._screen_added)
        app.screenRemoved.connect(self.constrain)
        for screen in app.screens():
            self._screen_added(screen)
        self.refresh()

    def refresh(self):
        self._position = (self.window.settings.avatar_x, self.window.settings.avatar_y)
        self._dimensions = (self.window.settings.avatar_width, self.window.settings.avatar_height)
        # A profile reload can replace an assignment without restarting the app.
        from .config import PROJECT_ROOT
        mapping = PROJECT_ROOT / 'data/avatars.json'
        try:
            revision = mapping.stat().st_mtime_ns if mapping.exists() else None
        except OSError:
            revision = None
        try:
            visual_model = self.window.avatar_models.selected(self.window.settings.character_path)['id']
        except (OSError, ValueError):
            visual_model = 'current'
        assignment = (self.window.settings.character_path, revision, visual_model)
        if self.widget is not None and assignment != getattr(self, '_assignment', None):
            self._release_widget()
        self._assignment = assignment
        if self.widget is not None:
            self.widget.set_name(self.window.settings.name)
            x, y = self._position
            if x is None or y is None:
                self.reset_position()
            else:
                self.widget.move(x, y)
                self.constrain()
        self.set_animated(self.window.animate_avatar.isChecked())
        self.set_enabled(self.window.show_avatar.isChecked())
        self._apply_dimensions()
        self.set_visual_controls()
        self.set_attention_controls()
        self._update_preview_controls()

    @Slot(bool)
    def set_enabled(self, enabled):
        if self._shutdown or self.window._closing:
            return
        self.window.reset_avatar.setEnabled(enabled)
        if enabled:
            if self.widget is None:
                self.widget = self._create_widget()
                self.widget.open_requested.connect(self.window.show_companion)
                self.widget.hide_requested.connect(self.hide_avatar)
                self.widget.menu_requested.connect(self.show_menu)
                self.widget.resized.connect(self.constrain)
                self.widget.resized.connect(self._resized)
                if hasattr(self.widget, 'preview_changed'):
                    self.widget.preview_changed.connect(self._preview_changed)
                self.widget.set_name(self.window.settings.name)
                self.widget.set_animated(self.window.animate_avatar.isChecked())
                self._apply_dimensions()
                self.set_visual_controls()
                self.set_attention_controls()
                x, y = self._position
                if x is None or y is None:
                    self.reset_position()
                else:
                    self.widget.move(x, y)
                self.constrain()
            self.widget.set_activity(self.window.activity)
            self.widget.show()
        elif self.widget is not None:
            self.widget.hide()
        self._update_preview_controls()

    def _create_widget(self):
        from .avatar_assets import assigned_avatar
        try:
            model = self.window.avatar_models.selected(self.window.settings.character_path)
        except (OSError, ValueError):
            model = {'kind': 'mesh'}  # A damaged experimental index must not block the original avatar.
        try:
            if model['kind'] == 'live2d':
                from .mesh_avatar import MeshDesktopAvatar
                widget = MeshDesktopAvatar(self.window.avatar_models.model_path(model), kind='live2d',
                                           appearance=model.get('appearance', {}))
                widget.set_framing(model.get('framing', 'portrait'))
                return widget
            path = assigned_avatar(self.window.settings.character_path)
            if path is not None:
                from .mesh_avatar import MeshDesktopAvatar
                return MeshDesktopAvatar(path)
        except (ImportError, OSError, ValueError):
            widget = DesktopAvatar()
            widget.setToolTip('Mesh avatar unavailable. See docs/avatar-stage4.md; using the simple mascot.')
            # A visible message as well as a tooltip, without blocking chat startup.
            from PySide6.QtWidgets import QLabel
            widget.clearMask()
            widget.setFixedSize(260, 235)
            notice = QLabel('Mesh avatar unavailable.\nSee docs/avatar-stage4.md.', widget)
            notice.setGeometry(0, 174, 260, 60)
            notice.setStyleSheet('background:#222633; color:#eceaf5; padding:6px')
            notice.setAlignment(Qt.AlignmentFlag.AlignCenter)
            return widget
        return DesktopAvatar()

    def _release_widget(self):
        self.widget.hide()
        if hasattr(self.widget, 'dispose'):
            self.widget.dispose()
        self.widget.deleteLater()
        self.widget = None

    def dimensions(self):
        return self._dimensions

    def _apply_dimensions(self):
        if self.widget is not None and hasattr(self.widget, 'set_visual_controls') and not self.widget.failed:
            self.widget.resize(*self._dimensions)
            self.constrain()

    def _resized(self):
        if self.widget is not None and hasattr(self.widget, 'set_visual_controls') and not self.widget.failed:
            self._dimensions = (self.widget.width(), self.widget.height())
            with QSignalBlocker(self.window.avatar_size):
                self.window.avatar_size.setValue(self.widget.width())
            self.window.avatar_size_label.setText(f'{self.widget.width()}px')

    @Slot(int)
    def set_size(self, width):
        self._dimensions = (width, round(width * 350 / 320))
        self._apply_dimensions()

    @Slot()
    def set_visual_controls(self):
        if self.widget is not None and hasattr(self.widget, 'set_visual_controls'):
            self.widget.set_visual_controls(self.window.avatar_motion.value(),
                                            self.window.avatar_lip_sensitivity.value())
            self.set_hd()
        self._update_preview_controls()

    def set_hd(self):
        if self.widget is not None and hasattr(self.widget, 'set_hd'):
            self.widget.set_hd(self.window.avatar_hd.isChecked())

    @Slot()
    def set_attention_controls(self):
        if self.widget is not None and hasattr(self.widget, 'set_attention_controls'):
            self.widget.set_attention_controls(self.window.avatar_cursor_attention.isChecked(),
                                               self.window.avatar_gaze.value(), self.window.avatar_hair.value())

    @Slot()
    def hide_avatar(self):
        self.window.show_avatar.setChecked(False)

    @Slot(bool)
    def set_animated(self, enabled):
        if self.widget is not None:
            self.widget.set_animated(enabled)
        self._update_preview_controls()

    @Slot(str)
    def set_activity(self, state):
        if self.widget is not None:
            self.widget.set_activity(state)
        self._preview_context_changed()

    def _preview_block_reason(self):
        window = self.window
        if self._shutdown or window._closing:
            return 'Movement preview is unavailable while closing.'
        if (window.suspended or window.activity != 'ready' or window._worker is not None
                or window.microphone.busy or window.speech.busy):
            return 'Movement preview is available when the conversation is idle.'
        if window.hands_free.isChecked():
            return 'Turn off Hands-free before previewing movement.'
        if self.widget is None or not hasattr(self.widget, 'start_motion_preview'):
            return 'Show a mesh avatar to preview its movement.'
        if getattr(self.widget, 'failed', False):
            return 'Movement preview needs a working mesh avatar. Try Reload avatar.'
        if not getattr(self.widget, 'ready', False):
            return 'Wait for the mesh avatar to finish loading.'
        if self.widget.state != 'ready':
            return 'Movement preview is available when the conversation is idle.'
        if (not self.widget.isVisible() or self.widget.isMinimized()
                or not getattr(self.widget, '_page_visible', True) or not self.widget.animated):
            return 'Show the avatar and enable Animate avatar to preview movement.'
        if window.avatar_motion.value() <= 0:
            return 'Increase Movement intensity above zero to preview movement.'
        return ''

    @Slot()
    def _preview_context_changed(self, *_):
        if (self.widget is not None and getattr(self.widget, '_preview_active', False)
                and self._preview_block_reason()):
            self.widget.stop_motion_preview()
        self._update_preview_controls()

    @Slot(bool, str)
    def _preview_changed(self, running, message):
        self._preview_message = message
        self.window._refresh_stop_button()
        self._update_preview_controls()

    def _update_preview_controls(self):
        running = self.widget is not None and getattr(self.widget, '_preview_active', False)
        reason = self._preview_block_reason()
        self.window.preview_avatar_motion.setText('Stop preview' if running else 'Preview movement')
        self.window.preview_avatar_motion.setEnabled(running or not reason)
        self.window.avatar_preview_status.setText(
            reason or self._preview_message or 'Silent preview of head turns, gaze and hair. No recording or speech.')

    @Slot()
    def toggle_motion_preview(self):
        if self.widget is not None and getattr(self.widget, '_preview_active', False):
            self.widget.stop_motion_preview()
        elif not self._preview_block_reason():
            self.widget.start_motion_preview()
        self._update_preview_controls()

    @Slot(float)
    def set_voice_level(self, level):
        if self.widget is not None and hasattr(self.widget, 'set_voice_level'):
            self.widget.set_voice_level(level)

    @Slot()
    def reset_voice(self):
        if self.widget is not None and hasattr(self.widget, 'reset_voice'):
            self.widget.reset_voice()

    @Slot()
    def reset_position(self):
        if self.widget is not None:
            screen = self.window.screen() or QGuiApplication.primaryScreen()
            if screen is None:
                return
            area = screen.availableGeometry()
            self.widget.move(area.right() - self.widget.width() - 23, area.bottom() - self.widget.height() - 23)
            self.constrain()

    @Slot()
    def constrain(self):
        if self.widget is not None:
            self.widget.move(visible_position(self.widget.pos(), self.widget.size(),
                                             [screen.availableGeometry() for screen in QGuiApplication.screens()]))

    def _screen_added(self, screen):
        screen.availableGeometryChanged.connect(self.constrain)
        self.constrain()

    def position(self):
        return (self.widget.x(), self.widget.y()) if self.widget is not None else self._position

    @Slot(QPoint)
    def show_menu(self, point):
        menu = QMenu(self.widget)
        menu.addAction("Open chat", self.window.show_companion)
        menu.addAction("Settings", self.window.open_settings)
        menu.addAction("Stop", self.window._stop)
        menu.addAction("Resume" if self.window.suspended else "Suspend", self.window.toggle_suspended)
        menu.addSeparator()
        menu.addAction("Reload avatar", self.reload_avatar)
        menu.addAction("Reset position", self.reset_position)
        menu.addAction("Hide avatar", self.hide_avatar)
        menu.addAction("Quit", self.window.request_quit)
        menu.aboutToHide.connect(menu.deleteLater)
        menu.popup(point)

    def reload_avatar(self):
        if self.widget is not None:
            self._position = self.position()
            self._release_widget()
        self.set_enabled(self.window.show_avatar.isChecked())

    @Slot()
    def shutdown(self):
        self._shutdown = True
        if self.widget is not None:
            self._release_widget()
