import os
import time
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent, Qt

from companion.ui.chat_view import Bubble, ChatView, Welcome, markdown_html
from companion.core.config import DEFAULT_MODEL, Settings
from companion.ui.window import CompanionWindow
from tests.qt_test_support import application


class ChatViewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = application()

    def flush(self):
        self.app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.app.processEvents()

    def test_markdown_renders_but_raw_html_stays_text(self):
        html = markdown_html('**Bold** and `code` <img src="x"><script>alert(1)</script>')
        self.assertIn('font-weight:700', html)
        self.assertIn('Consolas', html)
        self.assertNotIn('<img', html)
        self.assertNotIn('<script', html)
        self.assertIn('&lt;script&gt;', html)

    def test_links_she_sends_can_be_seen_and_opened(self):
        from unittest.mock import patch
        from PySide6.QtCore import QUrl
        from companion.ui import chat_view, prose
        bubble = Bubble('assistant', 'Jingliu')
        bubble.set_text('Watch https://youtu.be/abc?si=x or read [the docs](https://docs.live2d.com/en/).')
        html = bubble.body.toHtml()
        self.assertIn('href="https://youtu.be/abc?si=x"', html)
        self.assertNotIn('#0000ff', html)  # Not Qt's dark blue on the night sky.
        self.assertTrue(bubble.body.textInteractionFlags() & chat_view.Qt.TextInteractionFlag.LinksAccessibleByMouse)
        with patch.object(prose.QDesktopServices, 'openUrl', return_value=True) as web,                 patch.object(chat_view.QDesktopServices, 'openUrl', return_value=True) as opened:
            bubble.body.anchorClicked.emit(QUrl('https://docs.live2d.com/en/'))
            self.assertEqual(opened.call_args.args[0].toString(), 'https://docs.live2d.com/en/')
            for unsafe in ('file:///C:/Windows/System32/cmd.exe', 'javascript:alert(1)', 'ms-settings:'):
                self.assertFalse(chat_view.open_link(unsafe))
            self.assertEqual(opened.call_count, 1)  # Only web and mail links open.
            web.assert_not_called()
        bubble.body.linkHovered.emit('https://docs.live2d.com/en/')
        self.assertEqual(bubble.body.toolTip(), 'https://docs.live2d.com/en/')
        bubble.deleteLater()

    def test_inline_code_is_a_pill_and_cited_files_are_chips(self):
        import tempfile
        from pathlib import Path
        from unittest.mock import patch
        from PySide6.QtCore import QUrl
        from companion.ui import prose
        bubble = Bubble('assistant', 'Jingliu')
        bubble.set_text('Use `GRANT` and `REVOKE`; see `Slide 7 - SQL - Data Definition.pdf`.')
        document = bubble.body.document()
        self.assertEqual(bubble.body.text(), 'Use GRANT and REVOKE; see Slide 7 - SQL - Data Definition.pdf.')
        kinds = []
        block = document.begin()
        iterator = block.begin()
        while not iterator.atEnd():
            form = iterator.fragment().charFormat()
            if form.isImageFormat() and form.property(prose.KIND):
                kinds.append((form.property(prose.KIND), form.property(prose.TEXT) or ''))
            iterator += 1
        self.assertEqual(kinds, [('code', 'GRANT'), ('code', 'REVOKE'), ('file', '')])  # The file: an icon, then its name.
        bubble.body.selectAll()
        self.assertIn('REVOKE', bubble.body.createMimeDataFromSelection().text())  # Copying keeps the words.
        folder = Path(tempfile.mkdtemp())
        (folder / 'Slide 7 - SQL - Data Definition.pdf').write_bytes(b'%PDF')
        with patch.object(prose, 'resolve_file', lambda name: folder / name),                 patch.object(prose.QDesktopServices, 'openUrl', return_value=True) as opened:
            bubble.body.anchorClicked.emit(QUrl('material:' + QUrl.toPercentEncoding('Slide 7 - SQL - Data Definition.pdf').data().decode()))
        self.assertTrue(opened.call_args.args[0].toLocalFile().endswith('Data Definition.pdf'))
        bubble.deleteLater()

    def test_code_gets_its_own_box_and_tables_render(self):
        from companion.ui.code_block import CodeBlock, describe, segments
        text = 'Try this:\n\n```sql\nSELECT * FROM T;\n```\n\n| A | B |\n|---|---|\n| 1 | 2 |\n\n```cpp main.cpp\nint x;'
        self.assertEqual([piece[0] for piece in segments(text)], ['text', 'code', 'text', 'code'])
        self.assertEqual(segments(text)[3], ('code', 'int x;', 'cpp main.cpp'))  # Still open while she writes.
        self.assertEqual(describe('cpp main.cpp'), ('main.cpp · C++', 'cpp'))
        self.assertEqual(describe('main.py'), ('main.py · Python', 'python'))
        self.assertEqual(describe(''), ('Code', ''))
        bubble = Bubble('assistant', 'Jingliu')
        bubble.set_text(text)
        blocks = [part for part in bubble._parts if isinstance(part, CodeBlock)]
        self.assertEqual([block.code for block in blocks], ['SELECT * FROM T;', 'int x;'])
        self.assertIn('Try this:', bubble.body.text())
        self.assertNotIn('SELECT', bubble.body.text())
        table = [frame for frame in bubble._parts[1].document().rootFrame().childFrames() if hasattr(frame, 'cellAt')][0]
        self.assertEqual(table.cellAt(0, 0).format().background().color().name(), '#182742')  # A tinted header row.
        first = blocks[0]
        bubble.set_text(text + '\nint y;\n```\nDone.')  # Streaming: the same boxes are updated, not rebuilt.
        self.assertIs(bubble._parts[0], first)
        self.assertEqual(bubble._parts[2].code, 'int x;\nint y;')
        first.copy.click()
        self.assertEqual(self.app.clipboard().text(), 'SELECT * FROM T;')
        self.assertEqual(first.copy.toolTip(), 'Copied')
        first.wrap.click()                                      # Long lines can wrap instead of scrolling.
        self.assertEqual(first.view.lineWrapMode(), first.view.LineWrapMode.WidgetWidth)
        table_form = table.format()
        self.assertEqual(table_form.alignment(), Qt.AlignmentFlag.AlignHCenter)  # Tables sit in the middle.
        bubble.deleteLater()

    def test_latex_is_drawn_and_copies_back_as_latex(self):
        from companion.ui import math_render, prose
        text, formulas = math_render.extract(r'Join: $$R_1 \bowtie_{c} R_2 = \sigma_{c}(R_1 \times R_2)$$ and '
                                             r'$x^2$, but $5 and $10 are prices and `$PATH` is code.')
        self.assertEqual(formulas, [(r'R_1 \bowtie_{c} R_2 = \sigma_{c}(R_1 \times R_2)', True), ('x^2', False)])
        self.assertIn('$5 and $10', text)
        self.assertIn('`$PATH`', text)
        self.assertEqual(math_render.spaced(r'R \bowtie_{c} S'), r'R \;\bowtie_{c}\; S')
        bubble = Bubble('assistant', 'Jingliu')
        bubble.set_text(r'The join $$R_1 \bowtie_{c} R_2 = \sigma_{c}(R_1 \times R_2)$$ and $a_i^2$ inline. '
                        r'Broken: $\frac{1$ stays readable.')
        document = bubble.body.document()
        kinds = []
        block = document.begin()
        while block.isValid():
            iterator = block.begin()
            while not iterator.atEnd():
                form = iterator.fragment().charFormat()
                if form.isImageFormat() and form.property(prose.KIND) == 'math':
                    kinds.append((form.property(prose.TEXT), block.blockFormat().alignment()))
                iterator += 1
            block = block.next()
        self.assertEqual(kinds[0], (r'$$R_1 \bowtie_{c} R_2 = \sigma_{c}(R_1 \times R_2)$$', Qt.AlignmentFlag.AlignHCenter))
        self.assertEqual(kinds[1][0], '$a_i^2$')
        self.assertIn('$a_i^2$', bubble.body.text())            # Copying gives back the LaTeX.
        self.assertIn(r'\frac{1', bubble.body.text())            # Unreadable LaTeX is shown as written.
        bubble.deleteLater()

    def test_scrolling_up_while_she_writes_stays_put(self):
        view = ChatView()
        view.resize(700, 500)
        view.show()
        for index in range(8):
            view.add_message('user', 'You', f'Question {index}')
            view.add_message('assistant', 'Jingliu', 'A long answer. ' * 60)
        self.flush()
        view.begin_reply('Jingliu')
        bar = view.verticalScrollBar()
        view.scroll_to_latest()
        self.flush()
        bar.setValue(bar.maximum() - 30)  # One small wheel step up: within the old 48px "still at the bottom".
        held = bar.value()
        for _ in range(4):
            view.append_reply('More words as she writes. ' * 8)
            view._render_live()
            self.flush()
        self.assertEqual(bar.value(), held)                     # Not pulled back down: no flicker.
        self.assertTrue(view.latest.isVisibleTo(view))          # The round ↓ offers the way back.
        view.latest.click()
        self.flush()
        self.assertEqual(bar.value(), bar.maximum())
        view.deleteLater()

    def test_streamed_reply_and_failures_keep_plain_text(self):
        view = ChatView()
        view.show_welcome('Jingliu')
        view.add_message('user', 'You', 'Hello <friend>')
        self.flush()
        self.assertFalse(any(isinstance(item, Welcome) for item in view._items))
        view.begin_reply('Jingliu')
        view.append_reply('Quiet, ')
        view.append_reply('but well.')
        view.end_reply(notice='Reply stopped')
        self.assertIn('You\nHello <friend>', view.toPlainText())
        self.assertIn('Jingliu\nQuiet, but well.\nReply stopped', view.toPlainText())
        view.begin_reply('Jingliu')
        view.end_reply(error='The provider rate limit was reached.')
        self.flush()
        self.assertFalse(any(isinstance(item, Bubble) and not item.text for item in view._items))
        self.assertTrue(view.toPlainText().endswith('The provider rate limit was reached.'))
        view.clear()
        self.assertEqual(view.toPlainText(), '')


class WindowChromeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = application()

    def setUp(self):
        self.window = CompanionWindow(Settings('test-key', DEFAULT_MODEL, 'Jingliu', 'x', tts_enabled=False))

    def tearDown(self):
        self.window.request_quit()
        self.window.deleteLater()
        self.app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.app.processEvents()

    def test_mouse_wheel_scrolls_the_chat(self):
        from PySide6.QtCore import QPoint, QPointF, Qt
        from PySide6.QtGui import QWheelEvent
        self.window.resize(700, 600)
        self.window.show()
        for index in range(30):
            self.window.transcript.add_message('user', 'You', f'Message {index} ' * 8)
        bar = self.window.transcript.verticalScrollBar()
        deadline = time.monotonic() + 3
        while bar.maximum() == 0 and time.monotonic() < deadline:
            self.app.processEvents()
        bar.setValue(bar.maximum())
        self.assertGreater(bar.maximum(), 0)
        viewport = self.window.transcript.viewport()
        point = QPointF(viewport.rect().center())
        for target in (viewport, bar):  # Over the messages, and over the scroll bar itself.
            before = bar.value()
            event = QWheelEvent(point, QPointF(viewport.mapToGlobal(point.toPoint())), QPoint(), QPoint(0, 120),
                                Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
                                Qt.ScrollPhase.NoScrollPhase, False)
            self.app.sendEvent(target, event)
            self.assertLess(bar.value(), before, target)

    def test_header_speaker_mirrors_speak_replies_setting(self):
        self.assertFalse(self.window.speak_toggle.isChecked())
        self.window.speak_toggle.click()
        self.assertTrue(self.window.auto_speak.isChecked())
        self.window.auto_speak.setChecked(False)
        self.assertFalse(self.window.speak_toggle.isChecked())
        self.assertEqual(self.window.seal.text(), '镜流')

    def test_suggestion_fills_and_sends_only_when_idle(self):
        sent = []
        self.window._send = lambda: sent.append(self.window.input.toPlainText())
        self.window._use_suggestion('Tell me about yourself')
        self.assertEqual(sent, ['Tell me about yourself'])
        self.window.suspended = True
        self.window._use_suggestion('Ignored')
        self.assertEqual(sent, ['Tell me about yourself'])

    def test_footer_surfaces_recent_status_then_returns_to_hint(self):
        self.window.privacy.setText('Could not save this message. No request was sent. Please try again.')
        self.assertIn('Could not save', self.window.footer.text())
        self.window._fresh_until = 0
        self.window._refresh_footer()
        self.assertEqual(self.window.footer.text(), self.window.mic_hint.text())
        self.window.mic_status.setText('Microphone off')  # Idle states never displace the hint.
        self.assertEqual(self.window.footer.text(), self.window.mic_hint.text())
