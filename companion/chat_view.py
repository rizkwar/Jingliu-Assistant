"""Conversation view: message bubbles, rendered Markdown replies and an empty-state welcome."""
from pathlib import Path
import re

from PySide6.QtCore import Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QPixmap, QTextBlockFormat, QTextCursor, QTextDocument
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea, QSizePolicy, QVBoxLayout, QWidget

from .theme import ICONS

_FEATURES = QTextDocument.MarkdownFeature(QTextDocument.MarkdownFeature.MarkdownDialectGitHub.value
                                          | QTextDocument.MarkdownFeature.MarkdownNoHTML.value)
_BODY = re.compile(r'<body[^>]*>(.*)</body>', re.S)
_MONO = "font-family:'Cascadia Mono','Consolas';"


def markdown_html(text):
    """Model Markdown as rich text. Raw HTML in a reply is shown as text, never interpreted."""
    document = QTextDocument()
    document.setMarkdown(text, _FEATURES)
    spacing = QTextBlockFormat()
    spacing.setLineHeight(135,QTextBlockFormat.LineHeightTypes.ProportionalHeight.value)
    cursor = QTextCursor(document)
    cursor.select(QTextCursor.SelectionType.Document)
    cursor.mergeBlockFormat(spacing)
    match = _BODY.search(document.toHtml())
    html = match.group(1) if match else ''
    html = html.replace("font-family:'monospace';", _MONO + ' background-color:#0a1222; color:#cfe6ff;')
    html = html.replace("font-family:'Courier New,courier';", _MONO + ' background-color:#0a1222; color:#cfe6ff;')
    return html.replace('margin-top:12px;', 'margin-top:6px;')


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


class Bubble(QFrame):
    def __init__(self, role, speaker, parent=None, attachments=(), named=True):
        super().__init__(parent)
        self.role = role
        self.speaker = speaker
        self.text = ''
        self.attachments = list(attachments)
        self.setObjectName('user' if role == 'user' else 'assistant')
        # Her text runs to the reading width like a page; your messages hug their words.
        self.setSizePolicy(QSizePolicy.Policy.Maximum if role == 'user' else QSizePolicy.Policy.Expanding,
                           QSizePolicy.Policy.Preferred)
        layout = QVBoxLayout(self)
        # Her lines sit beside a thin line of moonlight; her name heads each run of her messages only.
        layout.setContentsMargins(*((16, 2, 6, 4) if role != 'user' else (15, 9, 15, 10)))
        layout.setSpacing(4)
        if role != 'user' and named:
            name = QLabel(speaker)
            name.setObjectName('speaker')
            layout.addWidget(name)
        if self.attachments:
            cards = QVBoxLayout()
            cards.setSpacing(6)
            for item in self.attachments:
                cards.addWidget(AttachmentCard(item, thumbnail=150), 0, Qt.AlignmentFlag.AlignRight)
            layout.addLayout(cards)
        self.body = QLabel()
        self.body.setObjectName('body')
        self.body.setWordWrap(True)
        self.body.setTextFormat(Qt.TextFormat.PlainText if role == 'user' else Qt.TextFormat.RichText)
        self.body.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.body.setCursor(Qt.CursorShape.IBeamCursor)
        layout.addWidget(self.body)
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

    def set_text(self, text):
        self.text = text
        self.body.setText(text if self.role == 'user' else markdown_html(text))
        self.body.setVisible(bool(text) or self.role != 'user')
        self.fit()

    def fit(self):
        """A wrapped label otherwise picks a narrow width: give a short message room for one line."""
        if self.role != 'user':
            return
        limit = self.maximumWidth() - 30 if self.maximumWidth() < 10000 else 520
        longest = max((self.body.fontMetrics().horizontalAdvance(line) for line in self.text.splitlines()), default=0)
        self.body.setMinimumWidth(max(0, min(longest + 4, limit)))

    def set_waiting(self, frame):
        self.body.setText('<span style="color:#8fa3c2; letter-spacing:3px;">' + '●' * (frame % 3 + 1) + '</span>')

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

    def __init__(self, speaker, request, parent=None):
        super().__init__(parent)
        self.setObjectName('task')
        self.request, self.steps, self.status_text = request, [], ''
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 11, 16, 12)
        layout.setSpacing(4)
        name = QLabel(f'{speaker} · task')
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

    def set_status(self, text, state):
        self.status_text = text
        self.status.setText(text)
        self.status.setProperty('state', state)
        self.status.style().unpolish(self.status)
        self.status.style().polish(self.status)

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
        name = QLabel('Proposed task')
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
        title = QLabel(f'{name} is here.')
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
        self.rows.setSpacing(16)
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
        bar = self.verticalScrollBar()
        bar.valueChanged.connect(lambda value: setattr(self, '_stick', value >= bar.maximum() - 48))
        bar.rangeChanged.connect(lambda _low, high: self._stick and bar.setValue(high))

    def _bubble_width(self):
        return max(260, int(self.viewport().width() * 0.82))

    def _reading_width(self):
        # About 75 characters of her serif text: comfortable to read on a wide window.
        return max(260, min(680, int(self.viewport().width() * 0.9)))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        for item in self._items:
            if isinstance(item, (Bubble, TaskCard, OfferCard)):
                item.setMaximumWidth(self._bubble_width() if not isinstance(item, Bubble) or item.role == 'user'
                                     else self._reading_width())
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

    def add_message(self, role, speaker, text, notice='', attachments=()):
        previous = self._items[-1] if self._items else None
        named = role == 'user' or not (isinstance(previous, Bubble) and previous.role != 'user')
        bubble = Bubble(role, speaker, attachments=attachments, named=named)
        bubble.setMaximumWidth(self._bubble_width() if role == 'user' else self._reading_width())
        bubble.set_text(text)
        bubble.set_notice(notice)
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
