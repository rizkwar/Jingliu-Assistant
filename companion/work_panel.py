"""The "what she is doing" panel under the avatar during a computer task.

Drawn by Qt rather than inside the page: Chromium occasionally presented a frame without the
panel's layer while its text was typing out, a visible one-frame flicker. It is its own small
click-through window over her, because the web view is a native layer that would cover a
widget placed inside the avatar window.
"""

import math
import time

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QLinearGradient, QPainter, QPainterPath, QPen, QRadialGradient
from PySide6.QtWidgets import QWidget

LABELS = {"start": "Working", "think": "Thinking", "read": "Reading", "type": "Writing", "command": "Running",
          "look": "Using the screen", "wait": "Waiting for you", "done": "Done", "failed": "Stopped"}
SAMPLES = {"start": "Tidy the Downloads folder", "think": "Planning how to sort them…",
           "read": "Look for files: Downloads/*", "type": "Write the file Downloads/README.txt",
           "command": "Run a command: Move-Item *.png Pictures/Screenshots", "look": "Click at (412, 230) on the screen",
           "wait": "Run a command: Remove-Item old-installers", "done": "All 42 files are sorted.",
           "failed": "I stopped before finishing."}
# Label colour, border colour, moon colour per state.
TONES = {"wait": ("#e6c28c", QColor(230, 194, 140, 153), "#f2d7a8"),
         "done": ("#8fe0c6", QColor(127, 209, 185, 153), "#e6fff6"),
         "failed": ("#f3b3bd", QColor(226, 86, 110, 120), "#f3b3bd")}
NORMAL = ("#a8d4ff", QColor(168, 212, 255, 89), "#d9ecff")
HEIGHT, MARGIN, SLIDE = 50, 12, 14


class WorkPanel(QWidget):
    def __init__(self, avatar):
        # Owned by her window (a parent with window flags): Windows keeps it above her.
        super().__init__(avatar, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint
                         | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.WindowDoesNotAcceptFocus
                         | Qt.WindowType.WindowTransparentForInput)
        self.avatar = avatar
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_QuitOnClose, False)
        self.setWindowTitle("Jingliu task progress")
        self.state, self.text, self.typed = "", "", 0
        self.shown = 0.0       # 0 hidden … 1 shown; eased for the fade and slide.
        self.target = 0.0
        self.hide_at = None
        self.started = time.monotonic()
        self.timer = QTimer(self)
        self.timer.setInterval(33)
        self.timer.timeout.connect(self._tick)
        self.label_font = QFont("Segoe UI Variable Text")
        self.label_font.setPixelSize(10)
        self.label_font.setWeight(QFont.Weight.DemiBold)
        self.label_font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 2)
        self.step_font = QFont("Segoe UI Variable Text")
        self.step_font.setPixelSize(12)
        self.hide()

    def show_step(self, state, text):
        """A task step, typed out; 'done' and 'failed' fade away after a few seconds."""
        self.state = state if state in LABELS else "start"
        self.text = " ".join(str(text or "").split())[:140]
        self.typed = 0
        self.target = 1.0
        self.hide_at = time.monotonic() + 3.6 if state in {"done", "failed"} else None
        self.place()
        if self.avatar.isVisible():
            self.show()
            self.raise_()
        if not self.timer.isActive():
            self.timer.start()

    def clear(self):
        self.target, self.hide_at = 0.0, None

    def place(self):
        """Over the bottom of her window, wherever she is moved or resized to."""
        avatar = self.avatar
        width = min(300, int(avatar.width() * .88))
        corner = avatar.mapToGlobal(avatar.rect().topLeft())
        self.setGeometry(corner.x() + (avatar.width() - width) // 2, corner.y() + avatar.height() - HEIGHT - MARGIN,
                         width, HEIGHT + SLIDE)

    def follow(self):
        """Her window moved, resized, appeared or hid."""
        if not self.avatar.isVisible():
            self.hide()
        elif self.shown > 0:
            self.place()
            self.show()
            self.raise_()

    def _tick(self):
        now = time.monotonic()
        if self.hide_at is not None and now >= self.hide_at:
            self.clear()
        self.typed = min(len(self.text), self.typed + 4)  # About as quick as before: two letters per 18 ms.
        self.shown += (self.target - self.shown) * .22
        if self.target == 0 and self.shown < .02:
            self.shown = 0.0
            self.timer.stop()
            self.hide()
            return
        self.update()

    def paintEvent(self, event):
        if self.shown <= 0:
            return
        label_color, border, moon_color = TONES.get(self.state, NORMAL)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        ease = self.shown * self.shown * (3 - 2 * self.shown)
        painter.setOpacity(ease)
        painter.translate(0, SLIDE * (1 - ease))
        box = QRectF(.5, .5, self.width() - 1, HEIGHT - 1)
        shape = QPainterPath()
        shape.addRoundedRect(box, 14, 14)
        fill = QLinearGradient(box.topLeft(), box.bottomRight())
        fill.setColorAt(0, QColor(16, 28, 52, 219))
        fill.setColorAt(1, QColor(10, 18, 36, 230))
        painter.fillPath(shape, fill)
        painter.setPen(QPen(border, 1))
        painter.drawPath(shape)
        now = time.monotonic() - self.started
        self._moon(painter, QPointF(22, box.center().y()), moon_color, now)
        left, right = 42, box.width() - 12
        painter.setFont(self.label_font)
        painter.setPen(QColor(label_color))
        painter.drawText(QRectF(left, 8, right - left, 14), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                         LABELS.get(self.state, "Working").upper())
        painter.setFont(self.step_font)
        metrics = QFontMetricsF(self.step_font)
        caret = self.state not in {"done", "failed"} and int(now * 2) % 2 == 0
        shown = metrics.elidedText(self.text[:self.typed], Qt.TextElideMode.ElideRight, right - left - 10)
        painter.setPen(QColor("#dfe9f8"))
        line = QRectF(left, 23, right - left, 18)
        painter.drawText(line, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, shown)
        if caret:
            x = left + metrics.horizontalAdvance(shown) + 2
            painter.fillRect(QRectF(x, 27, 2, 11), QColor(168, 212, 255))
        if self.state not in {"done", "failed"}:
            # A thin light sweeping along the bottom edge while she works.
            sweep = (math.sin(now * 2 * math.pi / 1.8) + 1) / 2
            glow = QLinearGradient(QPointF(box.left(), 0), QPointF(box.right(), 0))
            centre = .2 + .6 * sweep
            tint = QColor(label_color)
            for at, alpha in ((centre - .2, 0), (centre, 230), (centre + .2, 0)):
                tint.setAlpha(alpha)
                glow.setColorAt(max(0, min(1, at)), QColor(tint))
            painter.save()
            painter.setClipPath(shape)
            painter.fillRect(QRectF(box.left(), box.bottom() - 2, box.width(), 2), glow)
            painter.restore()
        painter.end()

    def _moon(self, painter, centre, color, now):
        radius = 9.0
        if self.state == "done":
            glow = QRadialGradient(centre, radius)
            glow.setColorAt(0, QColor(230, 255, 246))
            glow.setColorAt(.4, QColor(230, 255, 246, 200))
            glow.setColorAt(1, QColor(127, 209, 185, 0))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(glow)
            painter.drawEllipse(centre, radius, radius)
            return
        # A crescent: a lit disc with a darker disc offset over it, slowly orbiting (breathing when waiting).
        if self.state == "wait":
            angle, scale = 0.0, 1 + .08 * math.sin(now * 2 * math.pi / 1.6)
        else:
            angle, scale = now * 2 * math.pi / 2.2, 1.0
        r = radius * scale
        lit = QPainterPath()
        lit.addEllipse(centre, r, r)
        shadow = QPainterPath()
        shadow.addEllipse(centre + QPointF(-4 * math.cos(angle) * scale - 1, -4 * math.sin(angle) * scale * .3), r * .92, r * .92)
        crescent = lit.subtracted(shadow)
        halo = QRadialGradient(centre, r * 1.8)
        tint = QColor(color)
        tint.setAlpha(70)
        halo.setColorAt(0, tint)
        tint.setAlpha(0)
        halo.setColorAt(1, tint)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(halo)
        painter.drawEllipse(centre, r * 1.8, r * 1.8)
        painter.setBrush(QColor(color))
        painter.drawPath(crescent)
