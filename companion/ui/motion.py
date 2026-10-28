"""Motion: the small, quick animations that make the window feel smooth instead of switching in one frame.

Timings follow what chat apps use: things ease out (fast, then settling), exits are quicker than entries, and
nothing waits on an animation: the new state is set at once and the motion only plays over it. Windows' "Show
animations in Windows" setting (Accessibility → Visual effects) turns all of it off, and so does an offscreen or
test run.
"""

import os
import sys

from PySide6.QtCore import QEasingCurve, QEvent, QObject, QPropertyAnimation, QTimer, QVariantAnimation, Qt
from PySide6.QtGui import QColor, QGuiApplication
from PySide6.QtWidgets import (QAbstractScrollArea, QAbstractSlider, QAbstractSpinBox, QComboBox, QGraphicsOpacityEffect,
                               QLabel, QMenu, QStackedWidget)

EASE = QEasingCurve.Type.OutCubic
SWITCH_MS = 180  # A page or chat crossfading into the next.
APPEAR_MS = 200  # A new message fading in.
MENU_MS = 140
HOVER_MS = 120
SCROLL_MS = 160  # One wheel notch gliding, instead of jumping.
# Hover backgrounds that fade in (by object name): the colour of the stylesheet's :hover rule.
HOVERS = {"sideItem": (168, 212, 255, .07), "sideNew": (168, 212, 255, .07), "chip": (168, 212, 255, .13),
          "chipToggle": (168, 212, 255, .07), "modelPicker": (168, 212, 255, .07), "sideIcon": (168, 212, 255, .08),
          "icon": (168, 212, 255, .10)}
_enabled = None


def enabled():
    """Whether to animate: not in tests or offscreen, and not when Windows' animations are turned off."""
    global _enabled
    if _enabled is None:
        _enabled = _system_allows()
    return _enabled


def _system_allows():
    if QGuiApplication.platformName() in ("offscreen", "minimal") or os.environ.get("JINGLIU_MOTION") == "0":
        return False
    if sys.platform == "win32":
        try:
            import ctypes
            value = ctypes.c_int(1)
            ctypes.windll.user32.SystemParametersInfoW(0x1042, 0, ctypes.byref(value), 0)  # SPI_GETCLIENTAREAANIMATION
            return bool(value.value)
        except (OSError, AttributeError):
            return True
    return True


def crossfade(widget, duration=SWITCH_MS):
    """Call just before `widget` changes: a picture of how it looked fades away over its new content."""
    if not enabled() or not widget.isVisible() or widget.width() < 2 or widget.height() < 2:
        return
    veil = QLabel(widget)
    veil.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
    veil.setPixmap(widget.grab())
    veil.setGeometry(widget.rect())
    veil.show()
    veil.raise_()
    QTimer.singleShot(0, lambda: veil.raise_() if veil.isVisible() else None)  # Above whatever the change shows.
    effect = QGraphicsOpacityEffect(veil)
    veil.setGraphicsEffect(effect)
    animation = QPropertyAnimation(effect, b"opacity", veil)
    animation.setDuration(duration)
    animation.setStartValue(1.0)
    animation.setEndValue(0.0)
    animation.setEasingCurve(EASE)
    animation.finished.connect(veil.deleteLater)
    animation.start()


def fade_in(widget, duration=APPEAR_MS):
    """A new widget fades in (a message as you send it, her reply as it begins)."""
    if not enabled() or widget.graphicsEffect() is not None:
        return
    effect = QGraphicsOpacityEffect(widget)
    effect.setOpacity(0.0)
    widget.setGraphicsEffect(effect)
    animation = QPropertyAnimation(effect, b"opacity", widget)
    animation.setDuration(duration)
    animation.setStartValue(0.0)
    animation.setEndValue(1.0)
    animation.setEasingCurve(EASE)
    # An opacity effect draws the widget off screen; it goes as soon as the fade is done.
    animation.finished.connect(lambda: widget.setGraphicsEffect(None))
    animation.start()


def glide(bar, value, duration=SCROLL_MS):
    """Moves a scroll bar to `value` smoothly, carrying on from wherever a glide in progress has got to."""
    value = max(bar.minimum(), min(bar.maximum(), int(value)))
    if not enabled():
        bar.setValue(value)
        return
    animation = getattr(bar, "_glide", None)
    if animation is None:
        animation = QVariantAnimation(bar)
        animation.setEasingCurve(EASE)
        animation.valueChanged.connect(lambda position: bar.setValue(int(round(position))))
        bar._glide = animation
    animation.stop()
    animation.setDuration(duration)
    animation.setStartValue(float(bar.value()))
    animation.setEndValue(float(value))
    animation._target = value
    animation.start()


def gliding_to(bar):
    """Where a glide in progress is heading, or the bar's value."""
    animation = getattr(bar, "_glide", None)
    if animation is not None and animation.state() == QVariantAnimation.State.Running:
        return animation._target
    return bar.value()


class FadingStack(QStackedWidget):
    """A stack of pages that crossfade into one another."""

    def setCurrentWidget(self, widget):
        if widget is not self.currentWidget():
            crossfade(self)
        super().setCurrentWidget(widget)

    def setCurrentIndex(self, index):
        if index != self.currentIndex():
            crossfade(self)
        super().setCurrentIndex(index)


class Motion(QObject):
    """App-wide: menus fade in, the mouse wheel glides, and hovers ease in and out."""

    def eventFilter(self, watched, event):
        kind = event.type()
        if kind == QEvent.Type.Show and isinstance(watched, QMenu):
            self._menu(watched)
        elif kind == QEvent.Type.Wheel:
            return self._wheel(watched, event)
        elif kind in (QEvent.Type.Enter, QEvent.Type.Leave) and watched.objectName() in HOVERS:
            self._hover(watched, kind == QEvent.Type.Enter)
        return False

    @staticmethod
    def _menu(menu):
        menu.setWindowOpacity(0.0)
        animation = QPropertyAnimation(menu, b"windowOpacity", menu)
        animation.setDuration(MENU_MS)
        animation.setStartValue(0.0)
        animation.setEndValue(1.0)
        animation.setEasingCurve(EASE)
        animation.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)

    @staticmethod
    def _wheel(widget, event):
        """A mouse wheel notch glides the nearest scrollable area; touchpads, which scroll smoothly already,
        and anything that uses the wheel itself (lists in a combo box, sliders, spin boxes) are left alone."""
        if (event.phase() != Qt.ScrollPhase.NoScrollPhase or not event.pixelDelta().isNull()
                or event.modifiers() != Qt.KeyboardModifier.NoModifier or not event.angleDelta().y()):
            return False
        area = widget
        while area is not None:
            if isinstance(area, (QComboBox, QAbstractSpinBox, QAbstractSlider)):
                return False
            if isinstance(area, QAbstractScrollArea):
                bar = area.verticalScrollBar()
                if bar.maximum() > bar.minimum() and area.verticalScrollBarPolicy() != Qt.ScrollBarPolicy.ScrollBarAlwaysOff:
                    break
            area = area.parentWidget()
        if area is None:
            return False
        from PySide6.QtWidgets import QApplication
        bar = area.verticalScrollBar()
        step = bar.singleStep() * QApplication.wheelScrollLines() * event.angleDelta().y() / 120
        glide(bar, gliding_to(bar) - step)
        return True

    @staticmethod
    def _hover(widget, entering):
        """The stylesheet's hover background, faded in and out instead of switched."""
        from .theme import tone
        if getattr(widget, "isChecked", lambda: False)() or not widget.isEnabled():
            return
        red, green, blue, alpha = HOVERS[widget.objectName()]
        colour = QColor(tone(f"#{red:02x}{green:02x}{blue:02x}"))
        animation = getattr(widget, "_hover_fade", None)
        if animation is None:
            animation = QVariantAnimation(widget)
            animation.setEasingCurve(EASE)
            animation.valueChanged.connect(lambda level: widget.setStyleSheet(
                f"background: rgba({colour.red()}, {colour.green()}, {colour.blue()}, {alpha * level:.3f});"))
            # Done: the stylesheet's own rules (hover, or none) take over again.
            animation.finished.connect(lambda: widget.setStyleSheet(""))
            widget._hover_fade = animation
        start = animation.currentValue() if animation.state() == QVariantAnimation.State.Running else (0.0 if entering else 1.0)
        animation.stop()
        animation.setDuration(HOVER_MS if entering else int(HOVER_MS * .8))
        animation.setStartValue(float(start))
        animation.setEndValue(1.0 if entering else 0.0)
        widget.setStyleSheet(f"background: rgba({colour.red()}, {colour.green()}, {colour.blue()}, {alpha * start:.3f});")
        animation.start()


_installed = None


def install(app):
    """Once per app: menus, the wheel and hovers (nothing when motion is off)."""
    global _installed
    if _installed is None and enabled():
        _installed = Motion(app)
        app.installEventFilter(_installed)
