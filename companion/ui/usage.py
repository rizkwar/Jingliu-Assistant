"""Usage: what is left of her service, drawn as moons that wane as it is used, with the tokens behind it."""

import asyncio
from datetime import datetime, timedelta, timezone
import math

from PySide6.QtCore import QPointF, QRectF, QSize, QThread, QTimer, Qt, Signal
from PySide6.QtGui import QBrush, QIcon, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap, QRadialGradient
from PySide6.QtWidgets import (
    QButtonGroup, QDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea, QSizePolicy,
    QToolTip, QVBoxLayout, QWidget,
)

from ..chat import usage
from .theme import accent_hue, colour, is_light, repolish


def shadow_offset(left):
    """How far the shadow's disc sits from the moon's (in radii) so that `left` percent of the moon stays lit."""
    lit = max(0.0, min(1.0, (left if left is not None else 100) / 100))
    low, high = 0.0, 2.0
    for _ in range(40):
        middle = (low + high) / 2
        overlap = (2 * math.acos(middle / 2) - middle / 2 * math.sqrt(4 - middle * middle)) / math.pi
        if 1 - overlap < lit:
            low = middle
        else:
            high = middle
    return (low + high) / 2


def paint_moon(painter, centre, radius, left, ring=True):
    """A moon lit in proportion to what is left: full when everything is, new when nothing is."""
    low = left is not None and left < usage.LOW
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    if ring:
        painter.setPen(QPen(colour(226, 86, 110, 120) if left == 0 else colour(168, 212, 255, 46), 1.2))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(centre, radius * 1.21, radius * 1.21)
    painter.setPen(Qt.PenStyle.NoPen)
    if left is not None and left > 0:
        glow = QRadialGradient(centre, radius * 1.18)
        glow.setColorAt(.75, colour(230, 194, 140, 40) if low else colour(168, 212, 255, int(14 + left * .3)))
        glow.setColorAt(1, colour(168, 212, 255, 0))
        painter.setBrush(glow)
        painter.drawEllipse(centre, radius * 1.18, radius * 1.18)
    painter.setBrush(colour(24, 38, 63))
    painter.drawEllipse(centre, radius, radius)
    if left is not None and left > 0:
        disc = QPainterPath()
        disc.addEllipse(centre, radius, radius)
        shadow = QPainterPath()
        shadow.addEllipse(QPointF(centre.x() + shadow_offset(left) * radius, centre.y()), radius * 1.02, radius * 1.02)
        light = QRadialGradient(QPointF(centre.x() - radius * .2, centre.y() - radius * .3), radius * 1.3)
        if is_light():  # By day the moon is a clear blue (or amber), not the near-black its moonlight turns into.
            light.setColorAt(0, colour(150, 120, 70) if low else colour(140, 190, 245))
            light.setColorAt(1, colour(120, 92, 50) if low else colour(90, 150, 225))
        else:
            light.setColorAt(0, colour(255, 246, 228) if low else colour(242, 248, 255))
            light.setColorAt(1, colour(230, 194, 140) if low else colour(168, 212, 255))
        painter.setBrush(light)
        painter.drawPath(disc.subtracted(shadow) if left < 99.5 else disc)
    painter.restore()


def moon_icon_for(left, size=32):
    """The sidebar's Usage icon: a small moon in the phase of what is left (full when it is unknown)."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    paint_moon(painter, QPointF(size / 2, size / 2), size * .34, 100 if left is None else left, ring=False)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(QPen(colour(168, 212, 255, 150), 1.4))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawEllipse(QPointF(size / 2, size / 2), size * .34, size * .34)
    painter.end()
    return QIcon(pixmap)


class Moon(QWidget):
    def __init__(self, left, parent=None):
        super().__init__(parent)
        self.left = left
        self.setFixedSize(96, 96)

    def paintEvent(self, _event):
        painter = QPainter(self)
        paint_moon(painter, QPointF(48, 48), 38, self.left)


class DayChart(QWidget):
    """Tokens per day as stacked columns, input at the bottom, then output, then what was read from the cache.
    Each day is one rounded column; today is the brightest, and hovering a day shows its numbers."""
    AMBER = (230, 184, 120)

    @classmethod
    def parts(cls):
        """(name, colour) bottom to top: input in the theme's own blue, output crimson, cached jade. When the theme's
        hue is already close to crimson or jade, that part turns amber so the three stay apart."""
        def near(hue):
            return min(abs(accent_hue() - hue), 360 - abs(accent_hue() - hue)) < 45
        return (("input", (111, 168, 232)), ("output", cls.AMBER if near(350) else (226, 86, 110)),
                ("cached", cls.AMBER if near(162) else (127, 209, 185)))

    def __init__(self, days, parent=None):
        super().__init__(parent)
        self.days = days
        self.hovered = -1
        self.setMouseTracking(True)
        self.setMinimumSize(260, 214)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def _columns(self):
        area = QRectF(4, 22, self.width() - 8, self.height() - 22 - 56)
        step = area.width() / max(1, len(self.days))
        width = min(30.0, step * .66)
        return area, [QRectF(area.left() + step * index + (step - width) / 2, area.top(), width, area.height())
                      for index in range(len(self.days))]

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        area, columns = self._columns()
        peak = max([sum(day.values()) for _, day in self.days] + [1])
        font = self.font()
        font.setPixelSize(11)
        painter.setFont(font)
        # The busiest day, as a faint line to read the others against.
        if peak > 1:
            painter.setPen(QPen(colour(168, 212, 255, 40), 1, Qt.PenStyle.DashLine))
            painter.drawLine(QPointF(area.left(), area.top()), QPointF(area.right(), area.top()))
            painter.setPen(colour(95, 113, 146))
            painter.drawText(QRectF(area.left(), 0, area.width(), 18), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                             f"busiest {usage.short(peak)}")
        last = len(self.days) - 1
        for index, ((date, day), column) in enumerate(zip(self.days, columns)):
            total = sum(day.values())
            if index == self.hovered:
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(colour(168, 212, 255, 20))
                painter.drawRoundedRect(column.adjusted(-5, -6, 5, 4), 8, 8)
            painter.setOpacity(1.0 if index in (last, self.hovered) or self.hovered < 0 and index == last else
                               (.55 if self.hovered >= 0 else .82))
            height = max(3.0, column.height() * total / peak) if total else 3.0
            shape = QRectF(column.left(), column.bottom() - height, column.width(), height)
            radius = min(7.0, column.width() / 2, height / 2)
            if not total:
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(colour(168, 212, 255, 30))
                painter.drawRoundedRect(shape, 1.5, 1.5)
            else:
                outline = QPainterPath()
                outline.addRoundedRect(shape, radius, radius)
                painter.save()
                painter.setClipPath(outline)
                bottom = shape.bottom()
                for name, rgb in self.parts():
                    part = shape.height() * day[name] / total
                    if part <= 0:
                        continue
                    piece = QRectF(shape.left(), bottom - part, shape.width(), part)
                    fill = QLinearGradient(piece.topLeft(), piece.bottomLeft())
                    fill.setColorAt(0, colour(*rgb).lighter(118))
                    fill.setColorAt(1, colour(*rgb))
                    painter.fillRect(piece, QBrush(fill))
                    bottom -= part
                    if bottom > shape.top() + .5:  # A hairline of night between parts keeps the stack crisp.
                        painter.fillRect(QRectF(shape.left(), bottom - .6, shape.width(), 1.2), colour(10, 16, 30))
                painter.restore()
            painter.setOpacity(1.0)
            today = index == last
            painter.setPen(colour(226, 86, 110) if today else colour(95, 113, 146))
            text = date.strftime("%a")[0]  # Today's letter is in her crimson, with a dot beneath.
            painter.drawText(QRectF(column.center().x() - 20, area.bottom() + 6, 40, 16), Qt.AlignmentFlag.AlignCenter, text)
            if today:
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(colour(226, 86, 110))
                painter.drawEllipse(QPointF(column.center().x(), area.bottom() + 25), 2, 2)
        # The legend, centred under the chart.
        names = list(self.parts())
        widths = [painter.fontMetrics().horizontalAdvance(name) + 26 for name, _ in names]
        x = (self.width() - sum(widths)) / 2
        for (name, rgb), width in zip(names, widths):
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(colour(*rgb))
            painter.drawRoundedRect(QRectF(x, self.height() - 17, 9, 9), 2, 2)
            painter.setPen(colour(143, 163, 194))
            painter.drawText(QRectF(x + 14, self.height() - 22, width, 18), Qt.AlignmentFlag.AlignVCenter, name)
            x += width

    def mouseMoveEvent(self, event):
        _, columns = self._columns()
        x = event.position().x()
        hovered = next((index for index, column in enumerate(columns) if column.left() - 6 <= x <= column.right() + 6), -1)
        if hovered != self.hovered:
            self.hovered = hovered
            self.update()
        if hovered >= 0:
            date, day = self.days[hovered]
            label = "Today" if hovered == len(self.days) - 1 else date.strftime("%A %d %b")
            QToolTip.showText(event.globalPosition().toPoint(),
                              f"{label} · {usage.short(sum(day.values()))} tokens\n"
                              f"input {usage.short(day['input'])} · output {usage.short(day['output'])} · "
                              f"cached {usage.short(day['cached'])}", self)
        else:
            QToolTip.hideText()

    def leaveEvent(self, _event):
        self.hovered = -1
        self.update()


class ShareBar(QWidget):
    """A chat's share of the busiest chat's tokens."""

    def __init__(self, share, parent=None):
        super().__init__(parent)
        self.share = share
        self.setFixedHeight(5)

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        track = QRectF(self.rect())
        painter.setBrush(colour(168, 212, 255, 26))
        painter.drawRoundedRect(track, 2.5, 2.5)
        fill = QLinearGradient(track.topLeft(), track.topRight())
        fill.setColorAt(0, colour(111, 168, 232))
        fill.setColorAt(1, colour(168, 212, 255))
        painter.setBrush(fill)
        painter.drawRoundedRect(QRectF(0, 0, max(5.0, track.width() * self.share), track.height()), 2.5, 2.5)


class LimitsReader(QThread):
    """Reads a service's limits now (Codex, OpenRouter), away from the window."""
    read = Signal(list)
    failed = Signal(str)

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings = settings

    def run(self):
        try:
            windows = asyncio.run(usage.fetch_limits(self.settings))
        except Exception as exc:  # A ChatError is shown as it is; anything else stays generic.
            from ..chat.llm import ChatError
            self.failed.emit(str(exc) if isinstance(exc, ChatError) else "Could not read your limits just now.")
            return
        self.read.emit(windows or [])


def _clear(layout):
    while layout.count():
        item = layout.takeAt(0)
        if item.widget():
            item.widget().deleteLater()
        elif item.layout():
            _clear(item.layout())


def _label(text, name, align=None):
    label = QLabel(text)
    label.setObjectName(name)
    if align is not None:
        label.setAlignment(align)
    return label


def _card(heading):
    card = QFrame()
    card.setObjectName("usageCard")
    layout = QVBoxLayout(card)
    layout.setContentsMargins(18, 16, 18, 16)
    layout.setSpacing(12)
    top = QHBoxLayout()
    top.addWidget(_label(heading, "usageHeading"))
    top.addStretch()
    layout.addLayout(top)
    return card, layout, top


class UsageDialog(QDialog):
    """The Usage page: moons for what is left, tokens by day, and the chats that used the most."""
    open_conversation = Signal(str)
    limits_changed = Signal()
    RANGES = (("Today", 0), ("7 days", 7), ("30 days", 30))

    def __init__(self, store, settings, limits_path=None, parent=None):
        super().__init__(parent)
        self.store, self.settings, self.limits_path = store, settings, limits_path
        self.range = 7
        self.reader = None
        self.owner = parent  # Readers belong to the window: this page may be closed while one is still reading.
        self.problem = ""
        self.setWindowTitle("Usage")
        self.resize(820, 640)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        page = QWidget()
        page.setObjectName("panelBody")
        scroll.setWidget(page)
        outer.addWidget(scroll)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(22, 6, 22, 18)
        layout.setSpacing(14)

        head = QHBoxLayout()
        self.subtitle = _label("", "subtitle")
        self.subtitle.setWordWrap(True)
        head.addWidget(self.subtitle, 1)
        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.setObjectName("chip")
        self.refresh_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.refresh_button.clicked.connect(self.read_now)
        head.addWidget(self.refresh_button)
        layout.addLayout(head)

        card, card_layout, _ = _card("WHAT IS LEFT")
        self.moons = QHBoxLayout()
        self.moons.setSpacing(36)
        card_layout.addLayout(self.moons)
        layout.addWidget(card)

        self.lower = QGridLayout()
        self.lower.setHorizontalSpacing(14)
        self.lower.setVerticalSpacing(14)
        self.chart_card, chart_layout, _ = _card("TOKENS, LAST 14 DAYS")
        self.chart = DayChart([])
        chart_layout.addWidget(self.chart)
        chart_layout.addStretch()
        self.table_card, table_layout, table_top = _card("BY CONVERSATION")
        self.range_group = QButtonGroup(self)
        for text, days in self.RANGES:
            chip = QPushButton(text)
            chip.setObjectName("chipToggle")
            chip.setCheckable(True)
            chip.setChecked(days == self.range)
            chip.setCursor(Qt.CursorShape.PointingHandCursor)
            self.range_group.addButton(chip, days)
            table_top.addWidget(chip)
        self.range_group.idClicked.connect(self._range_chosen)
        self.table = QGridLayout()
        self.table.setHorizontalSpacing(16)
        self.table.setVerticalSpacing(8)
        self.table.setColumnStretch(0, 1)
        table_layout.addLayout(self.table)
        table_layout.addStretch()
        self.narrow = None
        layout.addLayout(self.lower)
        layout.addStretch()

        buttons = QHBoxLayout()
        buttons.setContentsMargins(22, 0, 22, 16)
        self.note = _label("", "hint")
        self.note.setWordWrap(True)
        buttons.addWidget(self.note, 1)
        close = QPushButton("Close")
        close.setObjectName("primary")
        close.clicked.connect(self.accept)
        buttons.addWidget(close)
        outer.addLayout(buttons)

        self._arrange(False)
        self.clock = QTimer(self)  # Reset countdowns and expired windows stay current while the page is open.
        self.clock.timeout.connect(self.refresh)
        self.clock.start(30_000)
        self.refresh()
        if settings.llm_provider in ("codex", "openrouter"):
            QTimer.singleShot(0, self.read_now)

    def _arrange(self, narrow):
        """Chart and table side by side, or one above the other when the window is narrow."""
        if narrow == self.narrow:
            return
        self.narrow = narrow
        self.lower.removeWidget(self.chart_card)
        self.lower.removeWidget(self.table_card)
        self.lower.addWidget(self.chart_card, 0, 0)
        self.lower.addWidget(self.table_card, 1 if narrow else 0, 0 if narrow else 1)
        self.lower.setColumnStretch(0, 1)
        self.lower.setColumnStretch(1, 0 if narrow else 1)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._arrange(self.width() < 760)

    def _range_chosen(self, days):
        self.range = days
        self.refresh()

    def _provider_line(self, entry):
        provider = self.settings.llm_provider
        parts = [usage.PROVIDERS.get(provider, provider)]
        if provider == "claude":
            from ..chat.claude import CLAUDE_MODELS, DEFAULT_CLAUDE_MODEL
            model = self.settings.claude_model or DEFAULT_CLAUDE_MODEL
            parts.append(next((name for name, key in CLAUDE_MODELS if key == model), model))
        elif provider == "codex":
            parts.append(self.settings.codex_model or "default model")
        else:
            parts.append(usage.model_name(self.settings.model))
        if entry.get("at"):
            parts.append("updated " + usage.ago(entry["at"]))
        return " · ".join(parts)

    def _empty_line(self):
        provider = self.settings.llm_provider
        if self.problem:
            return self.problem
        if provider == "claude":
            return "Claude reports your limits with each reply; they appear after her next one."
        if provider == "codex":
            return "Refresh to read your ChatGPT plan's limits."
        return "Add an OpenRouter key in Settings to see your credit balance." if not self.settings.api_key else \
            "Refresh to read your OpenRouter balance."

    def refresh(self):
        entry = usage.load_limits(self.limits_path).get(self.settings.llm_provider) or {}
        windows = usage.current(entry.get("windows") or [])
        self.subtitle.setText(self._provider_line(entry))
        moment = datetime.now(timezone.utc)
        try:
            rows = self.store.usage_since(moment - timedelta(days=31))
        except Exception:
            rows = []
        today = usage.today(rows)

        _clear(self.moons)
        self.moons.addStretch()
        for window in windows:
            self.moons.addLayout(self._moon(window))
        if not windows:
            self.moons.addLayout(self._moon({"label": "Plan limits", "left": None}, self._empty_line()))
        self.moons.addLayout(self._moon({"label": "Today", "left": 100.0, "detail": f"{usage.short(today['total'])} tokens"},
                                        f"{today['replies']} repl{'y' if today['replies'] == 1 else 'ies'}"))
        self.moons.addStretch()

        self.chart.days = usage.daily(rows)
        self.chart.update()

        since = (datetime.now().astimezone().replace(hour=0, minute=0, second=0, microsecond=0)
                 - timedelta(days=self.range)).astimezone(timezone.utc)
        chats = usage.by_conversation([row for row in rows if datetime.fromisoformat(row["at"]) >= since])
        self._fill_table(chats)
        self.note.setText("Token counts stay on this computer. Amber means less than "
                          f"{usage.LOW}% is left; a window refills when it resets.")

    def _moon(self, window, reset=None):
        column = QVBoxLayout()
        column.setSpacing(4)
        left = window.get("left")
        column.addWidget(Moon(left), 0, Qt.AlignmentFlag.AlignHCenter)
        column.addSpacing(4)
        column.addWidget(_label(window["label"], "usageLabel", Qt.AlignmentFlag.AlignCenter))
        if window.get("blocked"):
            text = "Limit reached"
        elif window.get("detail"):
            text = window["detail"]
        else:
            text = "—" if left is None else f"{left:.0f}% left"
        big = _label(text, "usageBig", Qt.AlignmentFlag.AlignCenter)
        repolish(big, warn=left is not None and 0 < left < usage.LOW, empty=bool(window.get("blocked") or left == 0))
        column.addWidget(big)
        hint = _label(reset if reset is not None else usage.until(window.get("resets_at")), "usageReset",
                      Qt.AlignmentFlag.AlignCenter)
        column.addWidget(hint, 0, Qt.AlignmentFlag.AlignHCenter)
        column.addStretch()  # Moons line up along the top, however many lines are beneath them.
        return column

    def _fill_table(self, chats):
        _clear(self.table)
        if not chats:
            empty = _label("No replies in this time yet." if self.range else "No replies today yet.", "hint")
            self.table.addWidget(empty, 0, 0, 1, 3)
            return
        for column, text in enumerate(("Chat", "Model", "Tokens")):
            head = _label(text, "usageHead", Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter if column == 2 else None)
            self.table.addWidget(head, 0, column)
        self.table.addWidget(self._rule(), 1, 0, 1, 3)
        most = max(chat["tokens"] for chat in chats) or 1
        for index, chat in enumerate(chats):
            row = 2 + index * 2
            cell = QVBoxLayout()
            cell.setSpacing(6)
            name = QPushButton(chat["title"])
            name.setObjectName("usageChat")
            name.setCursor(Qt.CursorShape.PointingHandCursor)
            name.setToolTip("Open this chat")
            name.setEnabled(chat["title"] != "A deleted chat")
            name.clicked.connect(lambda _=False, identifier=chat["id"]: self._open(identifier))
            name.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
            cell.addWidget(name)
            cell.addWidget(ShareBar(chat["tokens"] / most))
            self.table.addLayout(cell, row, 0)
            self.table.addWidget(_label(chat["model"], "usageModel"), row, 1)
            self.table.addWidget(_label(usage.short(chat["tokens"]), "usageTokens",
                                        Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter), row, 2)
            if index < len(chats) - 1:
                self.table.addWidget(self._rule(), row + 1, 0, 1, 3)

    @staticmethod
    def _rule():
        rule = QFrame()
        rule.setObjectName("usageRule")
        return rule

    def _open(self, identifier):
        self.open_conversation.emit(identifier)
        self.accept()

    def read_now(self):
        """Reads the limits now where the service allows it; Claude's arrive with her replies."""
        if self.settings.llm_provider not in ("codex", "openrouter"):
            self.refresh()
            return
        if self.reader is not None:
            return
        self.refresh_button.setEnabled(False)
        self.refresh_button.setText("Reading…")
        reader = LimitsReader(self.settings, self.owner)
        reader.read.connect(self._read)
        reader.failed.connect(self._failed)
        reader.finished.connect(self._done_reading)
        reader.finished.connect(reader.deleteLater)
        self.reader = reader
        reader.start()

    def _read(self, windows):
        self.problem = "" if windows else "Your plan did not report any limits."
        usage.save_limits(self.settings.llm_provider, windows, self.limits_path)
        self.limits_changed.emit()

    def _failed(self, message):
        self.problem = message

    def _done_reading(self):
        self.reader = None
        self.refresh_button.setEnabled(True)
        self.refresh_button.setText("Refresh")
        self.refresh()

    def done(self, result):
        self.clock.stop()
        super().done(result)
