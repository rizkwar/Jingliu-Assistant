"""Conversation view: message bubbles, rendered Markdown replies and an empty-state welcome."""
from pathlib import Path
import re

from datetime import datetime
import time

from PySide6.QtCore import Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QGuiApplication, QPixmap, QTextBlockFormat, QTextCursor, QTextDocument
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QLineEdit, QMenu, QPushButton, QScrollArea, QSizePolicy, QVBoxLayout,
                               QWidget)

from .code_block import CodeBlock, segments
from .prose import ProseView
from .theme import ICONS, glyph_icon, tone

_FEATURES = QTextDocument.MarkdownFeature(QTextDocument.MarkdownFeature.MarkdownDialectGitHub.value
                                          | QTextDocument.MarkdownFeature.MarkdownNoHTML.value)
_BODY = re.compile(r'<body[^>]*>(.*)</body>', re.S)
_MONO = "font-family:'Consolas';"  # On every Windows; rich text does not fall back along a list.


def markdown_html(text):
    """Model Markdown as rich text. Raw HTML in a reply is shown as text, never interpreted."""
    document = QTextDocument()
    document.setMarkdown(text, _FEATURES)
    spacing = QTextBlockFormat()
    spacing.setLineHeight(145,QTextBlockFormat.LineHeightTypes.ProportionalHeight.value)
    cursor = QTextCursor(document)
    cursor.select(QTextCursor.SelectionType.Document)
    cursor.mergeBlockFormat(spacing)
    match = _BODY.search(document.toHtml())
    html = match.group(1) if match else ''
    # Inline code: a soft tint, like ChatGPT's, not a typewriter font.
    html = html.replace("font-family:'monospace';", _MONO + _INLINE)
    html = html.replace("font-family:'Courier New,courier';", _MONO + _INLINE)
    html = html.replace(' color:#0000ff;', _LINK)  # Qt's default link blue is lost on the night sky.
    html = _TABLE.sub(_table, html)
    return tone(html.replace('margin-top:12px;', 'margin-top:6px;'))  # In the chosen theme.


_TABLE = re.compile(r'<table[^>]*>(.*?)</table>', re.S)


def _table(match):
    """A table in the night palette: fine borders, roomy cells, and a tinted header row."""
    rows = match.group(1).split('</tr>', 1)
    head = rows[0].replace('<td', '<td bgcolor="#182742"').replace('<th', '<th bgcolor="#182742"')
    return ('<table border="1" cellspacing="0" cellpadding="8" style="border-collapse:collapse; '
            'border-color:#2c3f60; border-style:solid; margin-top:8px; margin-bottom:8px;">'
            + head + ('</tr>' + rows[1] if len(rows) > 1 else '') + '</table>')


_LINK = ' color:#8cc4ff; text-decoration: underline;'
_INLINE = ' font-size:13px; background-color:#1a2842; color:#dcecff;'
LINK_SCHEMES = {'http', 'https', 'mailto'}


def open_link(url):
    """Opens a link from her reply in your browser or mail app; anything else (files, scripts) is not opened."""
    link = QUrl(url)
    if link.scheme().lower() not in LINK_SCHEMES or not link.isValid():
        return False
    return QDesktopServices.openUrl(link)


KIND_LABELS = {'image': 'IMAGE', 'pdf': 'PDF', 'text': 'FILE'}


class AttachmentCard(QFrame):
    """A shared image or file. Images show a thumbnail; clicking opens the stored copy."""
    removed = Signal(str)

    def __init__(self, item, thumbnail=56, removable=False, parent=None):
        super().__init__(parent)
        self.item = item
        self.setObjectName('attachment')
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(item['name'] + (' · click to open' if not removable else ''))
        row = QHBoxLayout(self)
        row.setContentsMargins(6, 6, 8, 6)
        row.setSpacing(8)
        pixmap = QPixmap(item['path']) if item['kind'] == 'image' else QPixmap()
        if not pixmap.isNull():
            preview = QLabel()
            preview.setObjectName('thumbnail')
            preview.setPixmap(pixmap.scaled(thumbnail * 2, thumbnail, Qt.AspectRatioMode.KeepAspectRatio,
                                            Qt.TransformationMode.SmoothTransformation))
            row.addWidget(preview)
        else:
            glyph = QLabel(ICONS['image' if item['kind'] == 'image' else 'document'])
            glyph.setObjectName('attachmentIcon')
            row.addWidget(glyph)
        if not pixmap.isNull() and not removable:
            row.setContentsMargins(4, 4, 4, 4)  # A shared picture speaks for itself; its name is in the tooltip.
            return
        names = QVBoxLayout()
        names.setSpacing(0)
        name = QLabel(item['name'] if len(item['name']) <= 28 else item['name'][:25] + '…')
        name.setObjectName('attachmentName')
        kind = QLabel(KIND_LABELS.get(item['kind'], 'FILE'))
        kind.setObjectName('attachmentKind')
        names.addWidget(name)
        names.addWidget(kind)
        row.addLayout(names)
        if removable:
            remove = QPushButton(ICONS['close'])
            remove.setObjectName('remove')
            remove.setToolTip('Remove')
            remove.setCursor(Qt.CursorShape.PointingHandCursor)
            remove.clicked.connect(lambda: self.removed.emit(item['path']))
            row.addWidget(remove, 0, Qt.AlignmentFlag.AlignTop)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and Path(self.item['path']).exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(self.item['path']))
        super().mouseReleaseEvent(event)


def _clock(timestamp):
    try:
        return datetime.fromisoformat(timestamp).astimezone().strftime('%H:%M') if timestamp else ''
    except ValueError:
        return ''


class Bubble(QFrame):
    speak = Signal(str)
    quote = Signal(str)

    def __init__(self, role, speaker, parent=None, attachments=(), plain=False, when=''):
        super().__init__(parent)
        self.role = role
        self.speaker = speaker
        self.text = ''
        self.attachments = list(attachments)
        self.setObjectName('user' if role == 'user' else 'assistant')
        self.setProperty('plain', plain and role != 'user')
        self.setSizePolicy(QSizePolicy.Policy.Expanding if self.property('plain') else QSizePolicy.Policy.Maximum,
                           QSizePolicy.Policy.Preferred)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(*((2, 4, 8, 4) if self.property('plain') else
                                    (16, 11, 16, 12) if role != 'user' else (15, 9, 15, 10)))
        layout.setSpacing(4)
        if role != 'user':
            name = QLabel(speaker.upper())
            name.setObjectName('speaker')
            layout.addWidget(name)
        if self.attachments:
            cards = QVBoxLayout()
            cards.setSpacing(6)
            for item in self.attachments:
                cards.addWidget(AttachmentCard(item, thumbnail=150), 0, Qt.AlignmentFlag.AlignRight)
            layout.addLayout(cards)
        self.link = ''
        self.body = self._prose()
        layout.addWidget(self.body)
        # The rest of her reply after its first paragraphs: code boxes, and the text between them.
        self.parts = QVBoxLayout()
        self.parts.setContentsMargins(0, 0, 0, 0)
        self.parts.setSpacing(8)
        self._parts = []
        layout.addLayout(self.parts)
        self.notice = QLabel()
        self.notice.setObjectName('notice')
        self.notice.setWordWrap(True)
        self.notice.hide()
        layout.addWidget(self.notice)
        self.error = QLabel()
        self.error.setObjectName('error')
        self.error.setWordWrap(True)
        self.error.setTextFormat(Qt.TextFormat.PlainText)
        self.error.hide()
        layout.addWidget(self.error)
        self.actions = QWidget()
        actions = QHBoxLayout(self.actions)
        actions.setContentsMargins(0, 2, 0, 0)
        actions.setSpacing(2)
        for glyph, tip, slot in (('copy', 'Copy', self._copy), ('speaker', 'Read aloud', lambda: self.speak.emit(self.text))):
            button = QPushButton(ICONS[glyph])
            button.setObjectName('replyAction')
            button.setToolTip(tip)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(slot)
            actions.addWidget(button)
        self.time = QLabel(_clock(when))
        self.time.setObjectName('replyTime')
        actions.addWidget(self.time)
        actions.addStretch()
        self.actions.hide()
        layout.addWidget(self.actions)

    def set_plain(self, plain):
        if self.role != 'user':
            self.setProperty('plain', plain)
            self.style().unpolish(self)
            self.style().polish(self)
            self.layout().setContentsMargins(*((2, 4, 8, 4) if plain else (16, 11, 16, 12)))
            self.setSizePolicy(QSizePolicy.Policy.Expanding if plain else QSizePolicy.Policy.Maximum,
                               QSizePolicy.Policy.Preferred)

    def finish(self, when=''):
        """A complete reply of hers: show copy, read aloud and the time beneath it."""
        if self.role != 'user' and self.text:
            if when:
                self.time.setText(_clock(when))
            self.actions.show()

    def _copy(self):
        QGuiApplication.clipboard().setText(self.text)

    def _prose(self):
        """Her text (Markdown, set like ChatGPT's, see prose.py) or yours (a plain label): selectable, links
        open, right-click menu."""
        if self.role != 'user':
            view = ProseView()
            view.linkHovered.connect(lambda url, view=view: self._hover_link(url, view))
            view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            view.customContextMenuRequested.connect(lambda position, view=view: self._menu(position, view))
            return view
        label = QLabel()
        label.setObjectName('body')
        label.setWordWrap(True)
        label.setTextFormat(Qt.TextFormat.PlainText if self.role == 'user' else Qt.TextFormat.RichText)
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse
                                      | Qt.TextInteractionFlag.LinksAccessibleByMouse
                                      | Qt.TextInteractionFlag.LinksAccessibleByKeyboard)
        label.setOpenExternalLinks(False)  # Opened by open_link, which only allows web and mail links.
        label.linkActivated.connect(open_link)
        label.linkHovered.connect(lambda url, label=label: self._hover_link(url, label))
        label.setCursor(Qt.CursorShape.IBeamCursor)
        label.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        label.customContextMenuRequested.connect(lambda position, label=label: self._menu(position, label))
        return label

    def _hover_link(self, url, label=None):
        """Shows where a link goes before it is clicked."""
        self.link = url
        (label or self.body).setToolTip(url)

    def _menu(self, position, label=None):
        label = label or self.body
        selected = label.selectedText().strip()
        menu = QMenu(self)
        if self.link:
            link = self.link
            menu.addAction(glyph_icon('open'), 'Open link', lambda: open_link(link))
            menu.addAction(glyph_icon('copy'), 'Copy link', lambda: QGuiApplication.clipboard().setText(link))
            menu.addSeparator()
        if selected:
            menu.addAction(glyph_icon('quote'), 'Quote in reply', lambda: self.quote.emit(selected))
            menu.addAction(glyph_icon('copy'), 'Copy', lambda: QGuiApplication.clipboard().setText(selected))
        else:
            menu.addAction(glyph_icon('copy'), 'Copy message', self._copy)
        if self.role != 'user' and self.text:
            menu.addAction(glyph_icon('speaker'), 'Read aloud', lambda: self.speak.emit(selected or self.text))
        menu.exec((label.viewport() if isinstance(label, ProseView) else label).mapToGlobal(position))

    def set_text(self, text):
        self.text = text
        if self.role == 'user':
            self.body.setText(text)
            self.body.setVisible(bool(text))
            self.fit()
            return
        pieces = segments(text)
        first = pieces.pop(0) if pieces and pieces[0][0] == 'text' else None
        self.body.set_markdown(first[1] if first else '')
        self.body.setVisible(bool(first) or not pieces)
        # Pieces already shown are updated in place as she writes; only new ones are added.
        for index, piece in enumerate(pieces):
            widget = self._parts[index] if index < len(self._parts) else None
            if widget is not None and isinstance(widget, CodeBlock) != (piece[0] == 'code'):
                for old in self._parts[index:]:
                    old.deleteLater()
                del self._parts[index:]
                widget = None
            if widget is None:
                widget = CodeBlock() if piece[0] == 'code' else self._prose()
                self.parts.addWidget(widget)
                self._parts.append(widget)
            if piece[0] == 'code':
                widget.set_code(piece[1], piece[2])
            else:
                widget.set_markdown(piece[1])
        for old in self._parts[len(pieces):]:
            old.deleteLater()
        del self._parts[len(pieces):]

    def fit(self):
        """A wrapped label otherwise picks a narrow width: give a short message room for one line."""
        if self.role != 'user':
            return
        limit = self.maximumWidth() - 30 if self.maximumWidth() < 10000 else 520
        longest = max((self.body.fontMetrics().horizontalAdvance(line) for line in self.text.splitlines()), default=0)
        self.body.setMinimumWidth(max(0, min(longest + 4, limit)))

    def set_waiting(self, frame):
        self.body.setText(tone('<span style="color:#8fa3c2; letter-spacing:3px;">') + '●' * (frame % 3 + 1) + '</span>')

    def set_notice(self, text):
        self.notice.setText(text)
        self.notice.setVisible(bool(text))

    def set_error(self, text):
        self.error.setText(text)
        self.error.setVisible(bool(text))

    def plain(self):
        lines = ['You' if self.role == 'user' else self.speaker]
        lines += [f"[Attached: {item['name']}]" for item in self.attachments]
        lines += [self.text] if self.text else []
        lines += [label.text() for label in (self.notice, self.error) if label.text()]
        return '\n'.join(lines)


class TaskCard(QFrame):
    """A computer task in progress: the request, her latest steps, and the state."""
    STEPS = 6
    undo_requested = Signal()
    steer = Signal(str)  # Something the person tells her while she works.

    def __init__(self, speaker, request, parent=None):
        super().__init__(parent)
        self.setObjectName('task')
        self.request, self.steps, self.status_text = request, [], ''
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 11, 16, 12)
        layout.setSpacing(4)
        name = QLabel(f'{speaker.upper()} · TASK')
        name.setObjectName('speaker')
        layout.addWidget(name)
        title = QLabel(request if len(request) <= 160 else request[:157] + '…')
        title.setObjectName('taskTitle')
        title.setWordWrap(True)
        title.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(title)
        self.list = QLabel()
        self.list.setObjectName('taskSteps')
        self.list.setWordWrap(True)
        self.list.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.list)
        # What she is doing right now, and for how long: a long wait is visible, never a silent freeze.
        self.live = QLabel()
        self.live.setObjectName('taskLive')
        self.live.setTextFormat(Qt.TextFormat.PlainText)
        self.live.hide()
        layout.addWidget(self.live)
        self.live_text, self.live_since = '', time.monotonic()
        self.clock = QTimer(self)
        self.clock.timeout.connect(self._tick)
        self.clock.start(1000)
        self.message = QLineEdit()
        self.message.setObjectName('taskMessage')
        self.message.setPlaceholderText('Tell her something while she works… (Enter)')
        self.message.setToolTip('She stops what she is doing, reads this, and carries on with it in mind')
        self.message.returnPressed.connect(self._steer)
        layout.addWidget(self.message)
        footer = QHBoxLayout()
        footer.setSpacing(8)
        self.status = QLabel()
        self.status.setObjectName('taskStatus')
        footer.addWidget(self.status, 1)
        self.undo_button = QPushButton('Undo this task')
        self.undo_button.setObjectName('taskUndo')
        self.undo_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.undo_button.setToolTip('Put back the files she created, changed, moved or deleted')
        self.undo_button.clicked.connect(self.undo_requested.emit)
        self.undo_button.hide()
        footer.addWidget(self.undo_button)
        layout.addLayout(footer)
        self.set_status('Working…', 'working')

    def offer_undo(self, available=True):
        self.undo_button.setVisible(available)

    def add_step(self, text):
        self.steps.append(text)
        self.list.setText('\n'.join('· ' + step for step in self.steps[-self.STEPS:]))
        self.set_live('')

    def set_live(self, text):
        """The line under the steps: what she is doing now, with how long it has taken."""
        if text != self.live_text:
            self.live_text, self.live_since = text, time.monotonic()
        self._tick()

    def _tick(self):
        seconds = int(time.monotonic() - self.live_since)
        working = self.status.property('state') == 'working'
        text = self.live_text or ('Working…' if working and seconds >= 20 else '')
        self.live.setVisible(bool(text) and working)
        if text:
            # After half a minute on one thing, the time shows, so a slow step is never mistaken for a freeze.
            self.live.setText(text + (f'  ·  {seconds // 60}:{seconds % 60:02d}' if seconds >= 30 else ''))

    def _steer(self):
        text = self.message.text().strip()
        if text:
            self.message.clear()
            self.add_step('You: ' + text)
            self.steer.emit(text)

    def set_status(self, text, state):
        self.status_text = text
        self.status.setText(text)
        self.status.setProperty('state', state)
        self.status.style().unpolish(self.status)
        self.status.style().polish(self.status)
        running = state in ('working', 'approval')
        self.message.setVisible(running)
        if not running:
            self.clock.stop()
            self.live.hide()
        elif not self.clock.isActive():
            self.clock.start(1000)
        self._tick()

    def plain(self):
        return '\n'.join(['Task: ' + self.request, *self.steps, self.status_text])


class OfferCard(QFrame):
    """A task she has proposed. The person confirms with a click, or simply answers in words."""
    accepted = Signal(str)
    declined = Signal()

    def __init__(self, description, parent=None):
        super().__init__(parent)
        self.setObjectName('task')
        self.description, self.state = description, 'Waiting for your answer'
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 11, 16, 12)
        layout.setSpacing(6)
        name = QLabel('PROPOSED TASK')
        name.setObjectName('speaker')
        layout.addWidget(name)
        plan = QLabel(description)
        plan.setObjectName('taskTitle')
        plan.setWordWrap(True)
        plan.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(plan)
        self.row = QHBoxLayout()
        self.row.setSpacing(8)
        self.yes = QPushButton('Yes, do it')
        self.yes.setObjectName('primary')
        self.no = QPushButton('Not now')
        for button in (self.yes, self.no):
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            self.row.addWidget(button)
        self.row.addStretch()
        layout.addLayout(self.row)
        self.status = QLabel('Or just tell her, for example “yes, but skip the PDFs”.')
        self.status.setObjectName('taskStatus')
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.yes.clicked.connect(lambda: self.accepted.emit(self.description))
        self.no.clicked.connect(self.declined.emit)

    def close_offer(self, text, state='done'):
        self.state = text
        self.yes.hide()
        self.no.hide()
        self.status.setText(text)
        self.status.setProperty('state', state)
        self.status.style().unpolish(self.status)
        self.status.style().polish(self.status)

    @property
    def open(self):
        return self.yes.isVisibleTo(self)

    def plain(self):
        return '\n'.join(['Proposed task: ' + self.description, self.state])


class MemoryNote(QFrame):
    """"Memory saved" / "Forgot" in the conversation, with Undo, like other assistants show it."""
    undo = Signal()

    def __init__(self, text, can_undo=True, parent=None, button='Undo', icon='memories'):
        super().__init__(parent)
        self.setObjectName('memoryNote')
        self.text = text
        row = QHBoxLayout(self)
        row.setContentsMargins(12, 5, 6, 5)
        row.setSpacing(8)
        glyph = QLabel(ICONS[icon])
        glyph.setObjectName('memoryIcon')
        row.addWidget(glyph)
        self.label = QLabel(text)
        self.label.setObjectName('memoryText')
        self.label.setWordWrap(True)
        self.label.setTextFormat(Qt.TextFormat.PlainText)
        row.addWidget(self.label, 1)
        self.button = QPushButton(button)
        self.button.setObjectName('memoryUndo')
        self.button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.button.setVisible(can_undo)
        self.button.clicked.connect(self.undo.emit)
        row.addWidget(self.button)

    def settle(self, text):
        self.text = text
        self.label.setText(text)
        self.button.hide()

    def plain(self):
        return self.text


class Welcome(QWidget):
    suggestion = Signal(str)

    def __init__(self, name, suggestions, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 36, 0, 12)
        layout.setSpacing(8)
        moon = QLabel(ICONS['moon'])
        moon.setObjectName('welcomeMoon')
        from ..chat.check_ins import part_of_day
        part = part_of_day(datetime.now())
        greeting = 'It is late. ' if part == 'late night' else f'Good {part}. '
        title = QLabel(f'{greeting}{name} is here.')
        title.setObjectName('welcomeTitle')
        self.text = QLabel('Say anything, or hold the microphone to speak. '
                           'Conversations are saved on this computer; /remember keeps a note across chats.')
        self.text.setObjectName('welcomeText')
        self.text.setWordWrap(True)
        self.text.setFixedWidth(440)  # A fixed width lets the wrapped label report its full height.
        self.text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        for widget in (moon, title, self.text):
            layout.addWidget(widget, 0, Qt.AlignmentFlag.AlignHCenter)
        chips = QHBoxLayout()
        chips.setSpacing(8)
        chips.addStretch()
        for text in suggestions:
            chip = QPushButton(text)
            chip.setObjectName('chip')
            chip.setCursor(Qt.CursorShape.PointingHandCursor)
            chip.clicked.connect(lambda _=False, text=text: self.suggestion.emit(text))
            chips.addWidget(chip)
        chips.addStretch()
        layout.addSpacing(10)
        layout.addLayout(chips)

    def plain(self):
        return self.text.text()


class ChatView(QScrollArea):
    """Drop-in for the old transcript: clear(), toPlainText() and verticalScrollBar() still work."""
    suggestion = Signal(str)
    speak_requested = Signal(str)
    quote_requested = Signal(str)
    plain = False  # Her replies as plain text (like Codex) instead of bubbles.
    SUGGESTIONS = ('I’m back. How have you been?', 'Help me focus for a while', 'Tell me about yourself')

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        body = QWidget()
        body.setObjectName('chatBody')
        self.rows = QVBoxLayout(body)
        self.rows.setContentsMargins(4, 8, 8, 16)
        self.rows.setSpacing(14)
        self.rows.addStretch()
        self.setWidget(body)
        self._items = []
        self._live = None
        self._frame = 0
        self._stick = True
        self._render = QTimer(self)
        self._render.setSingleShot(True)
        self._render.setInterval(40)  # Coalesce streamed chunks into one Markdown render.
        self._render.timeout.connect(self._render_live)
        self._dots = QTimer(self)
        self._dots.setInterval(320)
        self._dots.timeout.connect(self._tick)
        # Following her as she writes: only while you are at the very bottom. Any scroll up lets go at once
        # (a near-bottom threshold pulled a small scroll back down with each new word: a flicker).
        bar = self.verticalScrollBar()
        self._last = 0
        self._following = False  # True while the view itself moves to the bottom.
        bar.valueChanged.connect(self._scrolled)
        bar.rangeChanged.connect(self._grown)
        self.latest = QPushButton(ICONS['chevron'], self.viewport())
        self.latest.setObjectName('jumpLatest')
        self.latest.setToolTip('Jump to the latest message')
        self.latest.setCursor(Qt.CursorShape.PointingHandCursor)
        self.latest.clicked.connect(self.scroll_to_latest)
        self.latest.hide()

    def _scrolled(self, value):
        bar = self.verticalScrollBar()
        if not self._following:
            if value < self._last:
                self._stick = False
            if value >= bar.maximum() - 2:
                self._stick = True
        self._last = value
        self._place_latest()

    def _grown(self, _low, high):
        if self._stick:
            self._following = True
            self.verticalScrollBar().setValue(high)
            self._following = False
        self._place_latest()

    def scroll_to_latest(self):
        self._stick = True
        self._grown(0, self.verticalScrollBar().maximum())

    def _place_latest(self):
        """ChatGPT's round ↓: shown while you have scrolled up, to come back to her latest words."""
        bar = self.verticalScrollBar()
        away = bar.maximum() - bar.value() > 120
        self.latest.setVisible(away)
        if away:
            size = 36
            self.latest.setGeometry((self.viewport().width() - size) // 2, self.viewport().height() - size - 14, size, size)
            self.latest.raise_()

    def _bubble_width(self, item=None):
        if isinstance(item, Bubble) and item.property('plain'):
            return max(260, self.viewport().width() - 24)
        return max(260, int(self.viewport().width() * 0.82))

    def set_plain(self, plain):
        self.plain = plain
        for item in self._items:
            if isinstance(item, Bubble):
                item.set_plain(plain)
                item.setMaximumWidth(self._bubble_width(item))
                row = self._row_of(item)
                if row is not None and item.role != 'user':
                    row.setStretchFactor(item, 1 if plain else 0)

    def _row_of(self, widget):
        for index in range(self.rows.count() - 1):
            row = self.rows.itemAt(index).layout()
            if row is not None and row.indexOf(widget) >= 0:
                return row
        return None

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._place_latest()
        for item in self._items:
            if isinstance(item, (Bubble, TaskCard, OfferCard)):
                item.setMaximumWidth(self._bubble_width(item))
                if isinstance(item, Bubble):
                    item.fit()

    def _add(self, widget, align):
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        if align != 'left': row.addStretch()
        # Widgets that may grow (her messages) take the row up to their maximum width.
        row.addWidget(widget, 1 if widget.sizePolicy().horizontalPolicy() == QSizePolicy.Policy.Expanding else 0)
        if align != 'right': row.addStretch()
        self.rows.insertLayout(self.rows.count() - 1, row)
        if not isinstance(widget, Welcome):
            self._remove_welcome()
        self._items.append(widget)
        self._stick = True
        return widget

    def _remove(self, widget):
        if widget in self._items: self._items.remove(widget)
        for index in range(self.rows.count() - 1):
            row = self.rows.itemAt(index).layout()
            if row is not None and row.indexOf(widget) >= 0:
                self.rows.takeAt(index)
                row.deleteLater()
                break
        widget.hide()
        widget.deleteLater()

    def _remove_welcome(self):
        for item in [item for item in self._items if isinstance(item, Welcome)]:
            self._remove(item)

    def show_welcome(self, name):
        welcome = Welcome(name, self.SUGGESTIONS)
        welcome.suggestion.connect(self.suggestion)
        self._add(welcome, 'center')

    def add_message(self, role, speaker, text, notice='', attachments=(), when=''):
        bubble = Bubble(role, speaker, attachments=attachments, plain=self.plain, when=when)
        bubble.setMaximumWidth(self._bubble_width(bubble))
        bubble.set_text(text)
        bubble.set_notice(notice)
        bubble.speak.connect(self.speak_requested)
        bubble.quote.connect(self.quote_requested)
        if text:
            bubble.finish()
        return self._add(bubble, 'right' if role == 'user' else 'left')

    def add_offer(self, description):
        card = OfferCard(description)
        card.setMaximumWidth(self._bubble_width())
        return self._add(card, 'left')

    def add_memory_note(self, text, can_undo=True, button='Undo', icon='memories'):
        note = MemoryNote(text, can_undo, button=button, icon=icon)
        note.setMaximumWidth(self._bubble_width())
        return self._add(note, 'left')

    def add_task_card(self, speaker, request):
        card = TaskCard(speaker, request)
        card.setMaximumWidth(self._bubble_width())
        return self._add(card, 'left')

    def add_note(self, text, tone=''):
        note = QLabel(text.strip())
        note.setObjectName('note')
        note.setProperty('tone', tone)
        note.setWordWrap(True)
        note.setTextFormat(Qt.TextFormat.PlainText)
        note.setAlignment(Qt.AlignmentFlag.AlignCenter)
        note.setMaximumWidth(self._bubble_width())
        note.plain = note.text
        return self._add(note, 'center')

    def begin_reply(self, speaker):
        self._live = self.add_message('assistant', speaker, '')
        self._frame = 0
        self._live.set_waiting(0)
        self._dots.start()

    def append_reply(self, text):
        if self._live is None: return
        self._live.text += text
        self._dots.stop()
        if not self._render.isActive(): self._render.start()

    def end_reply(self, notice='', error=''):
        live, self._live = self._live, None
        self._dots.stop()
        self._render.stop()
        if live is None: return
        if not live.text:
            self._remove(live)
            if error or notice:
                self.add_note(error or notice, 'error' if error else '')
            return
        live.set_text(live.text)
        live.set_notice(notice)
        live.set_error(error)
        live.finish(datetime.now().astimezone().isoformat())

    def _render_live(self):
        if self._live is not None:
            self._live.set_text(self._live.text)

    def _tick(self):
        self._frame += 1
        if self._live is not None and not self._live.text:
            self._live.set_waiting(self._frame)

    def clear(self):
        self._dots.stop()
        self._render.stop()
        self._live = None
        self._items.clear()
        while self.rows.count() > 1:
            item = self.rows.takeAt(0)
            layout = item.layout()
            if layout is not None:
                while layout.count():
                    child = layout.takeAt(0).widget()
                    if child is not None:
                        child.hide()
                        child.deleteLater()
                layout.deleteLater()
        self._stick = True

    def toPlainText(self):
        return '\n\n'.join(item.plain() for item in self._items)
