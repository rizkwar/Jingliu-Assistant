import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent

from companion.chat_view import Bubble, ChatView, Welcome, markdown_html
from companion.config import DEFAULT_MODEL, Settings
from companion.ui import CompanionWindow
from qt_test_support import application


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
        self.assertIn('Cascadia Mono', html)
        self.assertNotIn('<img', html)
        self.assertNotIn('<script', html)
        self.assertIn('&lt;script&gt;', html)

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
