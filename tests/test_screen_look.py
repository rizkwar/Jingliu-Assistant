import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QEvent
from PySide6.QtGui import QColor, QImage

from companion.avatar_cues import CueFilter
from companion.config import DEFAULT_MODEL, Settings
from companion.prompts import reply_prompt
from qt_test_support import application

SETTINGS = Settings("test-key", DEFAULT_MODEL, "Jingliu", "Profile.", tts_enabled=False)


class LookPromptTests(unittest.TestCase):
    def test_the_cue_is_silent_and_her_instructions_follow_the_setting(self):
        cues = CueFilter()
        clean, found = cues.feed("Let me see it. [[look]]")
        self.assertEqual((clean + cues.finish()).strip(), "Let me see it.")
        self.assertEqual([cue for _, cue in found], ["look"])
        self.assertIn("[[look]]", reply_prompt("Profile", look=True))
        self.assertNotIn("[[look]]", reply_prompt("Profile"))


class WindowLookTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = application()

    def setUp(self):
        from companion.ui import CompanionWindow
        self.window = CompanionWindow(SETTINGS)
        self.window.preferences.remember = lambda *args: None
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.shot = Path(folder.name) / "screen.png"
        image = QImage(64, 40, QImage.Format.Format_RGB32)
        image.fill(QColor("#123456"))
        image.save(str(self.shot))

    def tearDown(self):
        self.window.request_quit()
        self.window.deleteLater()
        self.app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.app.processEvents()

    def test_the_screen_button_attaches_a_screenshot_to_the_message(self):
        with patch.object(self.window, "_capture_screen", return_value=self.shot):
            self.window.screen_button.click()
        self.assertEqual(self.window._pending_files, [str(self.shot)])

    def test_when_she_asks_to_look_the_screenshot_is_sent_as_the_next_turn(self):
        started = []
        with patch.object(self.window, "_capture_screen", return_value=self.shot), \
                patch.object(self.window, "_begin_reply", side_effect=lambda *a, **k: started.append((a, k)) or True):
            self.window._look_at_screen()
        (text, files), options = started[0]
        self.assertIn("My screen", text)
        self.assertEqual(files, [str(self.shot)])
        self.assertTrue(options["looking"])  # Her reply to it cannot ask to look again.

    def test_her_own_windows_are_left_out_of_the_capture(self):
        captured = []
        with patch("companion.screen_capture.capture", side_effect=lambda windows: captured.append(windows) or self.shot):
            self.window._capture_screen()
        self.assertIn(self.window, captured[0])

    def test_the_setting_is_remembered(self):
        saved = []
        self.window.preferences.remember = lambda settings, keys: saved.append((settings.look_at_screen, keys))
        self.window.look_at_screen.setChecked(False)
        self.assertEqual(saved, [(False, ("look_at_screen",))])


if __name__ == "__main__":
    unittest.main()
