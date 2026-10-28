"""Math in her replies, written in LaTeX: $…$ or \\(…\\) in a line, $$…$$ or \\[…\\] on a line of its own.

Formulas are taken out before the Markdown is read (so its underscores and asterisks are left alone), drawn
with a real math font by ziamath (pure Python, no TeX installation), and put back as sharp images."""
import re

from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QImage, QPainter

INLINE_OPEN, INLINE_CLOSE, BLOCK_OPEN, BLOCK_CLOSE = '', '', '', ''
PLACEHOLDER = re.compile('([])(\\d+)[]')
_CODE = re.compile(r'(`+)(?:(?!\1).)+?\1', re.S)
_MATH = re.compile(
    r'\$\$(?P<d1>.+?)\$\$'                                  # $$ display $$
    r'|\\\[(?P<d2>.+?)\\\]'                                  # \[ display \]
    r'|\\\((?P<i1>.+?)\\\)'                                  # \( inline \)
    r'|(?<![\\$\w])\$(?P<i2>[^\s$](?:[^$\n]{0,300}?[^\s$\\])?)\$(?![\d$])',  # $inline$, not prices like $5 or $10
    re.S)
_cache = {}
# Relational algebra and set operators get the room TeX gives a binary operator (the renderer sets them tight);
# a subscript such as \bowtie_{c} stays attached.
_OPERATOR = re.compile(r'(\\(?:bowtie|Join|ltimes|rtimes|cup|cap|times|div|setminus|cdot|circ|leftarrow|rightarrow|'
                       r'Rightarrow|Leftrightarrow|to|land|lor|wedge|vee))(?![A-Za-z])'
                       r'((?:_\{[^{}]*\}|_\w)?(?:\^\{[^{}]*\}|\^\w)?)')


def spaced(latex):
    return _OPERATOR.sub(lambda m: r'\;' + m.group(1) + m.group(2) + r'\;', latex)


def extract(text):
    """(text with each formula replaced by a placeholder, [(latex, display)]). Code spans are left alone."""
    formulas, out, last = [], [], 0
    protected = [(m.start(), m.end()) for m in _CODE.finditer(text)]

    def touches_code(first, last):
        return any(first < end and start < last for start, end in protected)
    for match in _MATH.finditer(text):
        if touches_code(match.start(), match.end()):
            continue
        display = match.group('d1') is not None or match.group('d2') is not None
        latex = next(group for group in (match.group('d1'), match.group('d2'), match.group('i1'), match.group('i2'))
                     if group is not None).strip()
        if not latex or (match.group('i2') is not None and latex[0].isdigit() and ' ' in latex):
            continue  # "$10 and $5": prices, not a formula.
        out.append(text[last:match.start()])
        index = len(formulas)
        formulas.append((latex, display))
        out.append(f'\n\n{BLOCK_OPEN}{index}{BLOCK_CLOSE}\n\n' if display else f'{INLINE_OPEN}{index}{INLINE_CLOSE}')
        last = match.end()
    out.append(text[last:])
    return ''.join(out), formulas


PENDING = object()  # render(wait=False): being drawn in the background.
_pending = set()
_notifier = None
_pool = None


def notifier():
    """Its `ready` signal fires (on the main thread) when a formula drawn in the background is ready."""
    global _notifier
    if _notifier is None:
        from PySide6.QtCore import QObject, Signal

        class Notifier(QObject):
            ready = Signal()
        _notifier = Notifier()
    return _notifier


def _disk(key):
    import hashlib
    from ..core.config import PROJECT_ROOT
    name = hashlib.sha256(repr(key).encode('utf-8')).hexdigest()[:32]
    return PROJECT_ROOT / 'data' / 'cache' / 'math' / f'{name}.png'


def render(latex, size, colour, ratio=1.0, wait=True):
    """A formula as an image at the screen's pixel density: (image, logical width, height, baseline drop), or
    None when the LaTeX cannot be read. Drawn formulas are kept on disk, so each is drawn once. `wait` False
    (while she writes): a formula not drawn yet returns PENDING and is drawn in the background."""
    key = (latex, round(size, 1), colour, round(ratio, 2))
    if key in _cache:
        return _cache[key]
    stored = _load(key)
    if stored is not None:
        _cache[key] = stored
        return stored
    if not wait:
        if key not in _pending:
            global _pool
            from concurrent.futures import ThreadPoolExecutor
            _pool = _pool or ThreadPoolExecutor(max_workers=1, thread_name_prefix='math')
            _pending.add(key)
            notifier()  # Made here, on the main thread, so its signal reaches the window.

            def draw():
                try:
                    _draw(key, latex, size, colour, ratio)
                finally:
                    _pending.discard(key)
                    notifier().ready.emit()
            _pool.submit(draw)
        return PENDING
    return _draw(key, latex, size, colour, ratio)


def _load(key):
    path = _disk(key)
    if not path.is_file():
        return None
    image = QImage(str(path))
    try:
        width, height, drop, ratio = (float(part) for part in image.text('formula').split())
    except ValueError:
        return None
    image.setDevicePixelRatio(ratio)
    return image, width, height, drop


def _draw(key, latex, size, colour, ratio):
    try:
        import ziamath
        from PySide6.QtSvg import QSvgRenderer
        # Plain paths: Qt's SVG renderer draws no <symbol>/<use> glyphs (SVG 2), only their fraction bars.
        ziamath.config.svg2 = False
        formula = ziamath.Latex(spaced(latex), size=size, color=colour)
        svg = formula.svg()
        renderer = QSvgRenderer(QByteArray(svg.encode('utf-8')))
        if not renderer.isValid():
            raise ValueError('unreadable')
        box = renderer.defaultSize()
        width, height = box.width(), box.height()
        image = QImage(max(1, round(width * ratio)), max(1, round(height * ratio)), QImage.Format.Format_ARGB32_Premultiplied)
        image.setDevicePixelRatio(ratio)
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        renderer.render(painter, QRectF(0, 0, width, height))
        painter.end()
        drop = float(formula.getyofst()) if hasattr(formula, 'getyofst') else 0.0
        result = (image, width, height, drop)
        try:
            path = _disk(key)
            path.parent.mkdir(parents=True, exist_ok=True)
            image.setText('formula', f'{width} {height} {drop} {ratio}')
            image.save(str(path), 'PNG')
        except OSError:
            pass  # Drawn again next time.
    except Exception:  # Unknown commands or broken LaTeX: shown as written instead.
        result = None
    if len(_cache) > 400:
        _cache.clear()
    _cache[key] = result
    return result
