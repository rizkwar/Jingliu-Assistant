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
        self.assertTrue(value.endswith("launch_jinger.pyw\" --background"))
        autostart.set_enabled(False)
        self.assertFalse(autostart.enabled())
        autostart.set_enabled(False)  # Already off: nothing to remove, no error.

    def test_an_entry_from_an_old_name_or_folder_is_repaired(self):
        import winreg
        old = r'"C:\Old\.venv\Scripts\pythonw.exe" "C:\Old\launch_mira.pyw" --background'
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, TEST_KEY, 0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, autostart.NAME, 0, winreg.REG_SZ, old)
        self.assertTrue(autostart.enabled())
        autostart.refresh()
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, TEST_KEY) as key:
            self.assertEqual(winreg.QueryValueEx(key, autostart.NAME)[0], autostart.command())

    def test_refresh_does_not_turn_it_on(self):
        autostart.refresh()
        self.assertFalse(autostart.enabled())


if __name__ == "__main__":
    unittest.main()
