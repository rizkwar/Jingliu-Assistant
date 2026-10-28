"""Motion: crossfades, fading in, gliding scrolls, newest-first filling and an even reveal, with motion turned on."""

import os
import time
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import QLabel, QScrollArea, QStackedWidget, QVBoxLayout, QWidget

from companion.ui import motion
from companion.ui.chat_view import Bubble, ChatView
from tests.qt_test_support import application


def wait(app, condition, limit=2.0):
    deadline = time.monotonic() + limit
    while not condition() and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(.005)
    return condition()


class MotionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = application()

    def setUp(self):
        patcher = patch.object(motion, "_enabled", True)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_motion_is_off_in_tests_and_when_windows_turns_animations_off(self):
        with patch.object(motion, "_enabled", None):
            self.assertFalse(motion.enabled())  # Offscreen.
        with patch.dict(os.environ, {"JINGLIU_MOTION": "0"}), patch.object(motion, "_enabled", None), \
                patch("companion.ui.motion.QGuiApplication.platformName", return_value="windows"):
            self.assertFalse(motion.enabled())

    def test_a_page_switch_crossfades_and_the_veil_goes_away(self):
        stack = motion.FadingStack()
        first, second = QLabel("first"), QLabel("second")
        stack.addWidget(first)
        stack.addWidget(second)
        stack.resize(300, 200)
        stack.show()
        self.app.processEvents()
        stack.setCurrentWidget(second)
        self.assertIs(stack.currentWidget(), second)  # The new page at once; the motion plays over it.
        def veils():
            self.app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            return [child for child in stack.findChildren(QLabel) if child not in (first, second)]
        self.assertEqual(len(veils()), 1)  # A picture of the old page, fading over the new one…
        self.assertTrue(wait(self.app, lambda: not veils()))  # …and then gone.

    def test_a_wheel_notch_glides_instead_of_jumping(self):
        area = QScrollArea()
        content = QWidget()
        content.setMinimumHeight(4000)
        area.setWidget(content)
        area.resize(300, 300)
        area.show()
        self.app.processEvents()
        filter_ = motion.Motion()
        bar = area.verticalScrollBar()
        event = QWheelEvent(QPointF(10, 10), QPointF(10, 10), QPoint(0, 0), QPoint(0, -120), Qt.MouseButton.NoButton,
                            Qt.KeyboardModifier.NoModifier, Qt.ScrollPhase.NoScrollPhase, False)
        self.assertTrue(filter_.eventFilter(area.viewport(), event))
        self.assertEqual(bar.value(), 0)  # Not jumped there…
        target = motion.gliding_to(bar)
        self.assertGreater(target, 0)
        self.assertTrue(wait(self.app, lambda: bar.value() == target))  # …glided there.
        touchpad = QWheelEvent(QPointF(10, 10), QPointF(10, 10), QPoint(0, -30), QPoint(0, -30), Qt.MouseButton.NoButton,
                               Qt.KeyboardModifier.NoModifier, Qt.ScrollPhase.ScrollUpdate, False)
        self.assertFalse(filter_.eventFilter(area.viewport(), touchpad))  # Already smooth: left alone.

    def test_a_conversation_shows_its_newest_messages_first_and_the_rest_fills_in_above_in_order(self):
        view = ChatView()
        view.resize(700, 600)
        view.show()
        entries = [lambda index=index: view.add_message("user" if index % 2 else "assistant", "Jingliu",
                                                        f"Message {index}") for index in range(20)]
        view.fill(entries)
        shown = [item.text for item in view._items if isinstance(item, Bubble)]
        self.assertEqual(shown, [f"Message {index}" for index in range(14, 20)])  # The latest at once.
        self.assertTrue(wait(self.app, lambda: not view._pending))
        self.assertEqual([item.text for item in view._items if isinstance(item, Bubble)],
                         [f"Message {index}" for index in range(20)])  # Then the rest, in order, above.
        view.fill(entries)
        self.assertIn("Message 0", view.toPlainText())  # Reading the transcript shows everything at once.

    def test_her_words_appear_at_an_even_pace_and_all_of_them_at_the_end(self):
        view = ChatView()
        view.resize(700, 600)
        view.show()
        view.begin_reply("Jingliu")
        text = "A B-tree node splits around its middle key, which moves up to the parent. " * 6
        view.append_reply(text)
        shown = len(view._live.text)
        self.assertLess(shown, len(text))  # A burst is revealed over a few frames, not at once.
        self.assertTrue(wait(self.app, lambda: view._live is None or len(view._live.text) == len(text)))
        live = view._live
        view.append_reply(" More.")
        view.end_reply()
        self.assertEqual(live.text, text + " More.")

    def test_hover_background_fades_and_hands_back_to_the_stylesheet(self):
        from PySide6.QtWidgets import QPushButton
        button = QPushButton("New chat")
        button.setObjectName("sideNew")
        button.show()
        filter_ = motion.Motion()
        filter_.eventFilter(button, QEvent(QEvent.Type.Enter))
        self.assertIn("background: rgba(", button.styleSheet())
        self.assertTrue(wait(self.app, lambda: button.styleSheet() == ""))


if __name__ == "__main__":
    unittest.main()
