import sys
import unittest
from unittest.mock import patch

from companion import autostart

TEST_KEY = r"Software\JingliuTests\Run"


@unittest.skipUnless(sys.platform == "win32", "Windows registry")
class AutostartTests(unittest.TestCase):
    def setUp(self):
        import winreg
        winreg.CreateKey(winreg.HKEY_CURRENT_USER, TEST_KEY).Close()
        patcher = patch.object(autostart, "KEY", TEST_KEY)  # Never the real Startup list.
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(lambda: winreg.DeleteKey(winreg.HKEY_CURRENT_USER, TEST_KEY))

    def test_turning_it_on_and_off(self):
        self.assertFalse(autostart.enabled())
        autostart.set_enabled(True)
        self.assertTrue(autostart.enabled())
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, TEST_KEY) as key:
            value, _ = winreg.QueryValueEx(key, autostart.NAME)
        self.assertIn("pythonw.exe", value)
        self.assertTrue(value.endswith("launch_mira.pyw\" --background"))
        autostart.set_enabled(False)
        self.assertFalse(autostart.enabled())
        autostart.set_enabled(False)  # Already off: nothing to remove, no error.


if __name__ == "__main__":
    unittest.main()
