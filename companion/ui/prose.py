"""Her written words, set like ChatGPT's: roomy lines, tables, links, inline code in rounded pills, and the
files she cites as chips with a file icon that open the file.

A QLabel cannot draw a rounded box inside a line of text, so her prose is a read-only QTextBrowser whose
inline code is replaced by small images drawn at the screen's pixel density (see pill_image)."""
import math
from pathlib import Path
import re

from PySide6.QtCore import QMimeData, QRectF, QRegularExpression, Qt, QUrl, Signal
from PySide6.QtGui import (QBrush, QColor, QDesktopServices, QFont, QFontMetricsF, QImage, QPainter, QPainterPath,
                           QTextBlockFormat, QTextCharFormat, QTextCursor, QTextDocument, QTextFormat, QTextFrameFormat,
                           QTextImageFormat, QTextTableFormat)
from PySide6.QtWidgets import QFrame, QSizePolicy, QTextBrowser

from .theme import ICON_FONT, font_family, tone

TEXT, KIND = QTextFormat.Property.UserProperty + 1, QTextFormat.Property.UserProperty + 2
OBJECT = '￼'
FEATURES = QTextDocument.MarkdownFeature(QTextDocument.MarkdownFeature.MarkdownDialectGitHub.value
                                         | QTextDocument.MarkdownFeature.MarkdownNoHTML.value)
FILE = re.compile(r'^[^\n/\\:*?"<>|]{1,120}\.(pdf|docx?|pptx?|xlsx?|csv|txt|md|sql|py|ipynb|java|cpp|c|h|js|ts|html|css|'
                  r'json|zip|png|jpe?g)$', re.I)
FILE_COLOURS = {'pdf': '#ff7a8a', 'doc': '#8cc4ff', 'docx': '#8cc4ff', 'ppt': '#f2b45c', 'pptx': '#f2b45c',
                'xls': '#7fd1b9', 'xlsx': '#7fd1b9', 'csv': '#7fd1b9'}
LINE_HEIGHT = 172       # Percent: ChatGPT's text breathes (about 28px at 16px).
resolve_file = None     # Set by the window: a file name she cited → its path in this conversation's materials, or None.


def body_size():
    """Her text's pixel size: 16, scaled by the chosen text size."""
    from . import theme
    return 16 * theme._font[1]


def _mono(size):
    font = QFont()
    font.setFamilies(['Cascadia Mono', 'Consolas'])
    font.setPixelSize(max(9, round(size * .82)))
    return font


def _ratio():
    from PySide6.QtGui import QGuiApplication
    screen = QGuiApplication.primaryScreen()
    return screen.devicePixelRatio() if screen else 1.0


def pill_image(text, kind):
    """Inline code as a rounded pill, or a cited file's icon, drawn at the screen's pixel density so it stays
    sharp. Returns (image, logical width, logical height)."""
    size, ratio = body_size(), _ratio()
    body = QFont(font_family())
    body.setPixelSize(round(size))
    # As tall as a line of her text, so a line with a pill is no taller than the others.
    height = QFontMetricsF(body).height()
    width = size * 1.2 if kind == 'file' else QFontMetricsF(_mono(size)).horizontalAdvance(text) + 14
    image = QImage(math.ceil(width * ratio), math.ceil(height * ratio), QImage.Format.Format_ARGB32_Premultiplied)
    image.setDevicePixelRatio(ratio)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    if kind == 'file':
        icon = QFont(ICON_FONT)
        icon.setPixelSize(round(size * .92))
        painter.setFont(icon)
        extension = text.rsplit('.', 1)[-1].lower()
        painter.setPen(QColor(tone(FILE_COLOURS.get(extension, '#a8d4ff'))))
        painter.drawText(QRectF(0, 0, width, height), Qt.AlignmentFlag.AlignCenter, '')
    else:
        path = QPainterPath()
        path.addRoundedRect(QRectF(0.5, 0.5, width - 1, height - 1), 6, 6)
        painter.fillPath(path, QColor(tone('#24324d')))
        painter.setFont(_mono(size))
        painter.setPen(QColor(tone('#e8f0ff')))
        painter.drawText(QRectF(0, 0, width, height), Qt.AlignmentFlag.AlignCenter, text)
    painter.end()
    return image, width, height


def _monospace(form):
    families = [family.lower() for family in (form.fontFamilies() or [])]
    return form.fontFixedPitch() or any('mono' in family or 'courier' in family or 'consolas' in family
                                        for family in families)


def _formulas(document, formulas):
    """Puts her formulas back as images: in the line, or centred on a line of their own. Returns the numbers of
    the blocks holding a formula in a line (they need room for its height)."""
    from . import math_render
    cursor, tall = QTextCursor(document), set()
    found = []
    position = 0
    while True:
        cursor = document.find(QRegularExpression(math_render.PLACEHOLDER.pattern), position)
        if cursor.isNull():
            break
        found.append((cursor.selectionStart(), cursor.selectionEnd(), cursor.selectedText()))
        position = cursor.selectionEnd()
    size = body_size()
    for start, end, token in reversed(found):
        match = math_render.PLACEHOLDER.fullmatch(token)
        if not match or int(match.group(2)) >= len(formulas):
            continue
        latex, display = formulas[int(match.group(2))]
        cursor = QTextCursor(document)
        cursor.setPosition(start)
        cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
        drawn = math_render.render(latex, size * (1.25 if display else 1.1), tone('#e6eefa'), _ratio())
        if drawn is None:
            form = QTextCharFormat()
            form.setFontFamilies(['Cascadia Mono', 'Consolas'])
            form.setForeground(QColor(tone('#f3a5b3')))
            form.setToolTip('This formula could not be drawn; it is shown as she wrote it.')
            cursor.insertText(('$$%s$$' if display else '$%s$') % latex, form)
            continue
        image, width, height, _drop = drawn
        name = f'math:{start}:{abs(hash(latex))}'
        document.addResource(QTextDocument.ResourceType.ImageResource, QUrl(name), image)
        form = QTextImageFormat()
        form.setName(name)
        form.setWidth(width)
        form.setHeight(height)
        form.setProperty(TEXT, ('$$%s$$' if display else '$%s$') % latex)  # Copying gives back the LaTeX.
        form.setProperty(KIND, 'math')
        form.setToolTip(latex)
        form.setVerticalAlignment(QTextCharFormat.VerticalAlignment.AlignMiddle)
        cursor.insertText(OBJECT, form)
        block = cursor.block()
        if display:
            centred = QTextBlockFormat(block.blockFormat())
            centred.setAlignment(Qt.AlignmentFlag.AlignHCenter)
            cursor.setBlockFormat(centred)
        if display or height > size * 1.4:
            tall.add(block.blockNumber())
    return tall


def shape(document, formulas=()):
    """Her Markdown, set for reading: line spacing, paragraph rhythm, links, formulas, tables and pills."""
    tall = _formulas(document, formulas) if formulas else set()
    cursor = QTextCursor(document)
    block = document.begin()
    while block.isValid():
        form = QTextBlockFormat(block.blockFormat())
        cursor.setPosition(block.position())
        if block.blockNumber() in tall:  # A formula: room for its height, then on with the text.
            form.setLineHeight(118, QTextBlockFormat.LineHeightTypes.ProportionalHeight.value)
            form.setTopMargin(4)
            form.setBottomMargin(14)
            cursor.setBlockFormat(form)
            block = block.next()
            continue
        if cursor.currentTable() is not None:  # Table cells: snug lines, the cell padding gives the room.
            form.setLineHeight(118, QTextBlockFormat.LineHeightTypes.ProportionalHeight.value)
            form.setTopMargin(0)
            form.setBottomMargin(0)
            cursor.setBlockFormat(form)
            block = block.next()
            continue
        if form.headingLevel():
            form.setLineHeight(130, QTextBlockFormat.LineHeightTypes.ProportionalHeight.value)
        else:  # A fixed height, so a line holding a pill or a file is no taller than the rest.
            form.setLineHeight(round(body_size() * LINE_HEIGHT / 100), QTextBlockFormat.LineHeightTypes.FixedHeight.value)
        if not block.textList() and form.headingLevel() == 0:
            form.setTopMargin(0)
            form.setBottomMargin(12)
        elif form.headingLevel():
            form.setTopMargin(14)
            form.setBottomMargin(8)
        else:
            form.setBottomMargin(4)
        cursor.setPosition(block.position())
        cursor.setBlockFormat(form)
        block = block.next()
    # Inline code and links: collected first, replaced from the end so positions stay valid.
    spans = []
    block = document.begin()
    while block.isValid():
        iterator = block.begin()
        while not iterator.atEnd():
            fragment = iterator.fragment()
            if fragment.isValid():
                form = fragment.charFormat()
                if _monospace(form) and fragment.text().strip() and not block.blockFormat().nonBreakableLines():
                    spans.append(('pill', fragment.position(), fragment.length(), fragment.text()))
                elif form.isAnchor():
                    spans.append(('link', fragment.position(), fragment.length(), form.anchorHref()))
            iterator += 1
        block = block.next()
    for kind, position, length, value in reversed(spans):
        cursor.setPosition(position)
        cursor.setPosition(position + length, QTextCursor.MoveMode.KeepAnchor)
        if kind == 'link':
            form = QTextCharFormat()
            form.setForeground(QColor(tone('#8cc4ff')))
            form.setUnderlineStyle(QTextCharFormat.UnderlineStyle.SingleUnderline)
            cursor.mergeCharFormat(form)
            continue
        text = value.strip()
        file = bool(FILE.match(text))
        kind = 'file' if file else 'code'
        image, width, height = pill_image(text, kind)
        name = f'pill:{kind}:{len(spans)}:{position}'
        document.addResource(QTextDocument.ResourceType.ImageResource, QUrl(name), image)
        form = QTextImageFormat()
        form.setName(name)
        form.setWidth(width)
        form.setHeight(height)
        form.setProperty(TEXT, '' if file else text)
        form.setProperty(KIND, kind)
        form.setVerticalAlignment(QTextCharFormat.VerticalAlignment.AlignMiddle)
        if file:
            # A cited file: its icon, then its name as real text (so it sits on the line), both opening it.
            href = 'material:' + QUrl.toPercentEncoding(text).data().decode()
            form.setAnchor(True)
            form.setAnchorHref(href)
            form.setToolTip(f'Open {text}')
            name_form = QTextCharFormat()
            name_form.setAnchor(True)
            name_form.setAnchorHref(href)
            name_form.setToolTip(f'Open {text}')
            name_form.setForeground(QColor(tone('#e6eefa')))
            name_form.setUnderlineStyle(QTextCharFormat.UnderlineStyle.SingleUnderline)
            name_form.setUnderlineColor(QColor(tone('#7d8fae')))
            name_form.setProperty(KIND, 'file')
            cursor.insertText(OBJECT, form)
            cursor.insertText(' ' + text, name_form)
            continue
        cursor.insertText(OBJECT, form)
    # Tables: fine borders, roomy cells, a tinted header row.
    for frame in document.rootFrame().childFrames():
        table = frame if hasattr(frame, 'cellAt') else None
        if table is None:
            continue
        form = QTextTableFormat(table.format())
        form.setBorder(1)
        form.setBorderBrush(QBrush(QColor(tone('#2c3f60'))))
        form.setBorderStyle(QTextFrameFormat.BorderStyle.BorderStyle_Solid)
        form.setBorderCollapse(True)
        form.setCellPadding(9)
        form.setCellSpacing(0)
        form.setTopMargin(6)
        form.setBottomMargin(14)
        form.setAlignment(Qt.AlignmentFlag.AlignHCenter)  # Centred, as ChatGPT sets a table apart from the text.
        table.setFormat(form)
        for column in range(table.columns()):
            cell = table.cellAt(0, column)
            cell_form = cell.format()
            cell_form.setBackground(QColor(tone('#182742')))
            cell.setFormat(cell_form)


def plain(document, start=0, end=None):
    """The text between two positions, with each pill as the code or file name it shows."""
    end = document.characterCount() - 1 if end is None else end
    out = []
    cursor = QTextCursor(document)
    for position in range(start, end):
        cursor.setPosition(position)
        cursor.setPosition(position + 1, QTextCursor.MoveMode.KeepAnchor)
        character = cursor.selectedText()
        if character == OBJECT:
            cursor.setPosition(position + 1)
            out.append(cursor.charFormat().property(TEXT) or '')
        else:
            out.append('\n' if character in '\u2029\u2028' else '' if character == '\u2009' else character)
    return ''.join(out)


class ProseView(QTextBrowser):
    """One stretch of her reply between code blocks, as tall as its text."""
    linkHovered = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('prose')
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setReadOnly(True)
        self.setOpenLinks(False)
        self.setUndoRedoEnabled(False)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse
                                     | Qt.TextInteractionFlag.LinksAccessibleByMouse
                                     | Qt.TextInteractionFlag.LinksAccessibleByKeyboard)
        self.document().setDocumentMargin(0)
        self.viewport().setCursor(Qt.CursorShape.IBeamCursor)
        self.anchorClicked.connect(self._open)
        self.highlighted.connect(lambda url: self.linkHovered.emit(url.toString()))
        self.markdown = None

    def set_markdown(self, text):
        if text == self.markdown:
            return
        self.markdown = text
        from .math_render import extract
        source, formulas = extract(text)
        self.document().setMarkdown(source, FEATURES)
        shape(self.document(), formulas)
        self._fit()

    def setText(self, html):  # Rich text that is not Markdown: her "…" while she thinks.
        self.markdown = None
        self.setHtml(html)
        self._fit()

    def text(self):
        return plain(self.document())

    def selectedText(self):
        cursor = self.textCursor()
        return plain(self.document(), cursor.selectionStart(), cursor.selectionEnd())

    def createMimeDataFromSelection(self):
        data = QMimeData()
        data.setText(self.selectedText())
        return data

    def _open(self, url):
        from .chat_view import open_link
        if url.scheme() == 'material':
            name = QUrl.fromPercentEncoding(url.path().encode())
            path = resolve_file(name) if resolve_file else None
            if path and Path(path).exists():
                QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
            return
        open_link(url.toString())

    def _fit(self):
        width = self.viewport().width() if self.viewport().width() > 10 else 600
        self.document().setTextWidth(width)
        height = math.ceil(self.document().size().height()) + 2
        if self.height() != height:
            self.setFixedHeight(height)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._fit()

    def wheelEvent(self, event):
        event.ignore()  # The conversation scrolls, not this paragraph.
