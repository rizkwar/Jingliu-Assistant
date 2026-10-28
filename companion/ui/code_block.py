"""Code in her replies, as its own box: the language (or file) on top, a Copy button, colours by kind of
word, and long lines that scroll sideways instead of wrapping. Like ChatGPT's code blocks."""
import re

from PySide6.QtCore import QRegularExpression, Qt, QTimer
from PySide6.QtGui import (QColor, QFont, QGuiApplication, QSyntaxHighlighter, QTextBlockFormat, QTextCharFormat,
                           QTextCursor, QTextOption)
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QTextBrowser, QVBoxLayout

from .theme import ICONS, tone

_FENCE = re.compile(r'^( {0,3})(`{3,}|~{3,})[ \t]*([^\n`]*)$')
MAX_HEIGHT = 520  # Taller code scrolls inside its box.

NAMES = {'sql': 'SQL', 'py': 'Python', 'python': 'Python', 'cpp': 'C++', 'c++': 'C++', 'cc': 'C++', 'c': 'C',
         'h': 'C', 'java': 'Java', 'js': 'JavaScript', 'javascript': 'JavaScript', 'ts': 'TypeScript',
         'typescript': 'TypeScript', 'html': 'HTML', 'css': 'CSS', 'json': 'JSON', 'bash': 'Bash', 'sh': 'Shell',
         'shell': 'Shell', 'powershell': 'PowerShell', 'ps1': 'PowerShell', 'cs': 'C#', 'csharp': 'C#', 'go': 'Go',
         'rust': 'Rust', 'rs': 'Rust', 'kotlin': 'Kotlin', 'php': 'PHP', 'ruby': 'Ruby', 'yaml': 'YAML', 'yml': 'YAML',
         'xml': 'XML', 'markdown': 'Markdown', 'md': 'Markdown', 'toml': 'TOML', 'ini': 'INI', 'r': 'R',
         'matlab': 'MATLAB', 'text': 'Text', 'txt': 'Text', 'csv': 'CSV', 'diff': 'Diff', 'dockerfile': 'Dockerfile'}
_EXTENSIONS = {'py': 'python', 'cpp': 'cpp', 'cc': 'cpp', 'hpp': 'cpp', 'h': 'c', 'c': 'c', 'java': 'java',
               'js': 'js', 'ts': 'ts', 'sql': 'sql', 'html': 'html', 'css': 'css', 'json': 'json', 'sh': 'bash',
               'ps1': 'powershell', 'cs': 'cs', 'go': 'go', 'rs': 'rust', 'kt': 'kotlin', 'php': 'php', 'rb': 'ruby',
               'yaml': 'yaml', 'yml': 'yaml', 'xml': 'xml', 'md': 'markdown', 'toml': 'toml', 'r': 'r', 'csv': 'csv'}

KEYWORDS = {
    'sql': '''select from where group by having order asc desc join inner left right full outer on as and or not in
              is null like between exists distinct insert into values update set delete create table view index
              alter drop primary foreign key references unique check default constraint union all intersect except
              case when then else end limit offset begin commit rollback trigger procedure function returns return
              declare if for each row before after instead of with recursive grant revoke database schema use count
              sum avg min max int integer varchar char text date decimal numeric float boolean serial''',
    'python': '''def class return if elif else for while in not and or is None True False import from as with try
                 except finally raise lambda yield pass break continue global nonlocal assert del async await self''',
    'c': '''int long short char float double void unsigned signed const static struct enum union typedef sizeof
            return if else for while do switch case default break continue goto include define bool true false
            auto using namespace std class public private protected template typename new delete virtual override
            vector string map set pair nullptr this operator inline''',
    'java': '''public private protected class interface extends implements static final void int long double float
               boolean char byte short new return if else for while do switch case default break continue try catch
               finally throw throws import package this super null true false var String''',
    'js': '''function const let var return if else for while do switch case default break continue new class
             extends import export from as async await try catch finally throw typeof instanceof null undefined
             true false this of in yield interface type''',
}
for alias, base in {'cpp': 'c', 'c++': 'c', 'cc': 'c', 'h': 'c', 'cs': 'java', 'csharp': 'java', 'kotlin': 'java',
                    'ts': 'js', 'typescript': 'js', 'javascript': 'js', 'py': 'python', 'go': 'c', 'rust': 'c',
                    'rs': 'c', 'php': 'js'}.items():
    KEYWORDS[alias] = KEYWORDS[base]
_COMMENTS = {'sql': r'--[^\n]*', 'python': r'#[^\n]*', 'py': r'#[^\n]*', 'bash': r'#[^\n]*', 'sh': r'#[^\n]*',
             'shell': r'#[^\n]*', 'powershell': r'#[^\n]*', 'yaml': r'#[^\n]*', 'yml': r'#[^\n]*', 'toml': r'#[^\n]*',
             'ruby': r'#[^\n]*', 'r': r'#[^\n]*'}
# Her palette for code: rose keywords (her crimson, like ChatGPT's pink), jade strings, peach numbers.
COLOURS = {'keyword': '#f38ba8', 'string': '#a6e3a1', 'comment': '#7f8ba3', 'number': '#fab387',
           'function': '#89b4fa', 'preprocessor': '#cba6f7'}


def segments(text):
    """Her reply in pieces: ('text', markdown) and ('code', code, info). A fence still open while she writes
    is code already, so the box appears as the first line of code arrives."""
    parts, prose, code, fence, info = [], [], [], None, ''
    for line in text.split('\n'):
        match = _FENCE.match(line)
        if fence is None and match:
            fence, info = match.group(2), match.group(3).strip()
            if prose:
                parts.append(('text', '\n'.join(prose)))
                prose = []
        elif fence is not None and line.strip().startswith(fence[0] * len(fence)) and not line.strip().strip(fence[0]):
            parts.append(('code', '\n'.join(code), info))
            fence, code = None, []
        elif fence is not None:
            code.append(line)
        else:
            prose.append(line)
    if fence is not None:
        parts.append(('code', '\n'.join(code), info))
    elif prose:
        parts.append(('text', '\n'.join(prose)))
    return [part for part in parts if part[0] == 'code' or part[1].strip()]


def describe(info):
    """(label, language) from a fence's info: ```sql, ```python main.py, ```main.cpp."""
    words = info.split()
    language, name = (words[0].lower() if words else ''), ''
    if len(words) > 1:
        name = words[-1]
    elif '.' in language and language.rsplit('.', 1)[1] in _EXTENSIONS:
        name, language = words[0], _EXTENSIONS[language.rsplit('.', 1)[1]]
    title = NAMES.get(language, language.capitalize() if language else 'Code')
    return (f'{name} · {title}' if name else title), language


class CodeHighlighter(QSyntaxHighlighter):
    """Colours for keywords, strings, comments, numbers and calls; block comments span lines."""

    def __init__(self, document, language):
        super().__init__(document)
        self.rules = []

        def rule(pattern, kind, options=QRegularExpression.PatternOption.NoPatternOption):
            form = QTextCharFormat()
            form.setForeground(QColor(tone(COLOURS[kind])))
            if kind == 'comment':
                form.setFontItalic(True)
            self.rules.append((QRegularExpression(pattern, options), form))
        words = KEYWORDS.get(language, '').split()
        if words:
            insensitive = QRegularExpression.PatternOption.CaseInsensitiveOption if language == 'sql' else \
                QRegularExpression.PatternOption.NoPatternOption
            rule(r'\b(' + '|'.join(map(re.escape, words)) + r')\b', 'keyword', insensitive)
        rule(r'\b[A-Za-z_]\w*(?=\s*\()', 'function')
        rule(r'\b(0x[0-9a-fA-F]+|\d+(\.\d+)?([eE][+-]?\d+)?)\b', 'number')
        if language in {'c', 'cpp', 'c++', 'cc', 'h'}:
            rule(r'^\s*#\s*\w+', 'preprocessor')
        rule(r'"(\\.|[^"\\])*"|\'(\\.|[^\'\\])*\'' + ('|`[^`]*`' if language in {'js', 'ts', 'javascript'} else ''),
             'string')
        rule(_COMMENTS.get(language, r'//[^\n]*'), 'comment')
        self.block = None
        if language not in {'python', 'py', 'bash', 'sh', 'shell', 'yaml', 'yml', 'toml', 'text', 'txt', 'csv', ''}:
            self.block = (QRegularExpression(r'/\*'), QRegularExpression(r'\*/'))
            self.block_format = self.rules[-1][1]

    def highlightBlock(self, text):
        for expression, form in self.rules:
            found = expression.globalMatch(text)
            while found.hasNext():
                match = found.next()
                self.setFormat(match.capturedStart(), match.capturedLength(), form)
        self.setCurrentBlockState(0)
        if not self.block:
            return
        opening, closing = self.block
        start = 0 if self.previousBlockState() == 1 else text.find('/*')
        while start >= 0:
            end = closing.match(text, start + (0 if self.previousBlockState() == 1 and start == 0 else 2))
            if end.hasMatch():
                length = end.capturedEnd() - start
            else:
                self.setCurrentBlockState(1)
                length = len(text) - start
            self.setFormat(start, length, self.block_format)
            start = text.find('/*', start + length)


class CodeBlock(QFrame):
    """One code block of hers."""

    def __init__(self, code='', info='', parent=None):
        super().__init__(parent)
        self.setObjectName('codeBlock')
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        # The header, as ChatGPT's: </> and the language on the left; wrap and copy as icons on the right.
        header = QHBoxLayout()
        header.setContentsMargins(20, 12, 12, 2)
        header.setSpacing(4)
        mark = QLabel('</>')
        mark.setObjectName('codeMark')
        header.addWidget(mark)
        self.title = QLabel()
        self.title.setObjectName('codeTitle')
        header.addWidget(self.title)
        header.addStretch()
        self.wrap = QPushButton('')
        self.wrap.setObjectName('codeAction')
        self.wrap.setCheckable(True)
        self.wrap.setToolTip('Wrap long lines')
        self.wrap.setCursor(Qt.CursorShape.PointingHandCursor)
        self.wrap.toggled.connect(self._wrap)
        header.addWidget(self.wrap)
        self.copy = QPushButton(ICONS['copy'])
        self.copy.setObjectName('codeAction')
        self.copy.setToolTip('Copy the code')
        self.copy.setCursor(Qt.CursorShape.PointingHandCursor)
        self.copy.clicked.connect(self._copy)
        header.addWidget(self.copy)
        layout.addLayout(header)
        self.view = QTextBrowser()
        self.view.setObjectName('code')
        self.view.setFrameShape(QFrame.Shape.NoFrame)
        self.view.setWordWrapMode(QTextOption.WrapMode.NoWrap)
        self.view.setLineWrapMode(QTextBrowser.LineWrapMode.NoWrap)
        self.view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.view.setOpenLinks(False)
        self.view.setContextMenuPolicy(Qt.ContextMenuPolicy.DefaultContextMenu)
        font = QFont()
        font.setFamilies(['Cascadia Mono', 'Consolas', 'Courier New'])
        font.setStyleHint(QFont.StyleHint.TypeWriter)
        font.setFixedPitch(True)
        font.setPixelSize(13)
        self.view.setFont(font)
        self.view.document().setDocumentMargin(20)
        self.view.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        layout.addWidget(self.view)
        self.code, self.info, self.highlighter = None, None, None
        self.set_code(code, info)

    def set_code(self, code, info=''):
        if code == self.code and info == self.info:
            return
        if info != self.info:
            label, language = describe(info)
            self.title.setText(label)
            self.title.setToolTip(info or label)
            self.highlighter = CodeHighlighter(self.view.document(), language)
        self.code, self.info = code, info
        scroll = self.view.horizontalScrollBar().value()
        self.view.setPlainText(code)
        spacing = QTextCursor(self.view.document())
        spacing.select(QTextCursor.SelectionType.Document)
        form = QTextBlockFormat()
        form.setLineHeight(150, QTextBlockFormat.LineHeightTypes.ProportionalHeight.value)  # Code breathes too.
        spacing.mergeBlockFormat(form)
        self.view.horizontalScrollBar().setValue(scroll)
        self._fit()

    def _fit(self):
        """As tall as the code (up to MAX_HEIGHT), plus room for the sideways scrollbar when lines are long."""
        document = self.view.document()
        document.setTextWidth(self.view.viewport().width() if self.wrap.isChecked() else -1)
        height = int(document.size().height()) - 8  # Less room above than the margin gives below.
        wide = not self.wrap.isChecked() and document.idealWidth() > max(1, self.view.viewport().width())
        bar = self.view.horizontalScrollBar().sizeHint().height() if wide else 0
        self.view.setFixedHeight(min(MAX_HEIGHT, height + bar + 2))
        self.view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded if height + bar > MAX_HEIGHT
                                             else Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._fit()

    def _wrap(self, wrapped):
        mode = QTextBrowser.LineWrapMode.WidgetWidth if wrapped else QTextBrowser.LineWrapMode.NoWrap
        self.view.setLineWrapMode(mode)
        self.view.setWordWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere if wrapped else QTextOption.WrapMode.NoWrap)
        self.wrap.setToolTip('Show long lines in full (scroll sideways)' if wrapped else 'Wrap long lines')
        self._fit()

    def _copy(self):
        QGuiApplication.clipboard().setText(self.code)
        self.copy.setText('')  # A check mark, as ChatGPT's copy button turns into.
        self.copy.setToolTip('Copied')
        QTimer.singleShot(1600, self, lambda: (self.copy.setText(ICONS['copy']), self.copy.setToolTip('Copy the code')))

    def plain(self):
        return self.code
