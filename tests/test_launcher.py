from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from companion.doctor import Check
from companion.launcher import launch, record_failure


class LaunchTests(unittest.TestCase):
    def test_fatal_preflight_shows_actionable_error_without_starting_app(self):
        with patch("companion.doctor.run_checks", return_value=[Check("error", "httpx", "Run Setup Jinger.cmd.")]), \
             patch("companion.launcher.notify") as notify, patch("companion.launcher.record_failure"), \
             patch("companion.__main__.main") as app:
            self.assertEqual(launch(), 1)
        app.assert_not_called()
        self.assertIn("Setup Jinger.cmd", notify.call_args.args[0])

    def test_warnings_allow_offline_startup(self):
        with patch("companion.doctor.run_checks", return_value=[Check("warning", "API configuration", "No key")]), \
             patch("companion.launcher.notify") as notify, patch("companion.__main__.main", return_value=0) as app:
            self.assertEqual(launch(), 0)
        notify.assert_not_called()
        app.assert_called_once()

    def test_unexpected_startup_error_is_redacted_in_popup_and_log(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            def log(stage, exception=None):
                record_failure(stage, exception, root)
            with patch("companion.doctor.run_checks", return_value=[]), \
                 patch("companion.__main__.main", side_effect=RuntimeError("secret-key and private transcript")), \
                 patch("companion.launcher.record_failure", side_effect=log), patch("companion.launcher.notify") as notify:
                self.assertEqual(launch(), 1)
            contents = (root / "data" / "startup-error.log").read_text()
            self.assertIn("RuntimeError", contents)
            self.assertNotIn("secret-key", contents + str(notify.call_args))
            self.assertNotIn("private transcript", contents + str(notify.call_args))

    def test_failure_logging_is_bounded_and_handles_a_read_only_project(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "data").mkdir()
            (root / "data" / "startup-error.log").write_text("x" * 70000)
            record_failure("startup", ValueError("do not log this"), root)
            self.assertLess((root / "data" / "startup-error.log").stat().st_size, 200)
            self.assertEqual((root / "data" / "startup-error.previous.log").stat().st_size, 70000)
            with patch("companion.launcher.Path.mkdir", side_effect=PermissionError):
                record_failure("startup", root=root)  # Must not hide the original startup failure.
