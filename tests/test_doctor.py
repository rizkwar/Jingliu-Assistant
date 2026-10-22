from dataclasses import asdict
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from companion.doctor import engine_check, run_checks


class DoctorTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        (self.root / "requirements.txt").write_text("PySide6-Essentials==1.0\nhttpx==1.0\npython-dotenv==1.0\npocket-tts==1.0\n")
        (self.root / "character.md").write_text("Private character instructions for {name}.")
        self.environment = patch.dict(os.environ, {}, clear=True)
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.versions = patch("companion.doctor.metadata.version", return_value="1.0")
        self.versions.start()
        self.addCleanup(self.versions.stop)

    def test_missing_key_is_only_a_warning_and_report_contains_no_secrets(self):
        checks = run_checks(self.root)
        self.assertFalse(any(item.status == "error" for item in checks))
        self.assertEqual(next(item for item in checks if item.name == "API configuration").status, "warning")
        (self.root / ".env").write_text("OPENROUTER_API_KEY=private-key-value\n")
        report = json.dumps([asdict(item) for item in run_checks(self.root)])
        self.assertNotIn("private-key-value", report)
        self.assertNotIn("Private character", report)
        self.assertFalse((self.root / "data" / "companion.sqlite3").exists())

    def test_missing_core_dependency_blocks_launch_but_voice_dependency_does_not(self):
        from importlib.metadata import PackageNotFoundError
        for missing, expected in (("httpx", "error"), ("pocket-tts", "warning")):
            with self.subTest(missing=missing):
                def version(package):
                    if package == missing:
                        raise PackageNotFoundError(package)
                    return "1.0"
                with patch("companion.doctor.metadata.version", side_effect=version):
                    result = next(item for item in run_checks(self.root) if item.name == missing)
                self.assertEqual(result.status, expected)

    def test_invalid_saved_reference_warns_without_blocking_text_chat(self):
        from companion.config import load_settings
        from companion.preferences import Preferences
        from dataclasses import replace
        Preferences(self.root / "data" / "preferences.json").save(
            replace(load_settings(self.root), tts_voice="reference", tts_reference="missing-private-reference.wav"))
        checks = run_checks(self.root)
        result = next(item for item in checks if item.name == "Reference audio")
        self.assertEqual(result.status, "warning")
        self.assertNotIn("missing-private-reference.wav", str(checks))

    def test_invalid_configuration_and_unwritable_data_are_errors_without_raw_exception_text(self):
        with patch("companion.config.load_settings", side_effect=ValueError("private-key-value")), \
             patch("companion.doctor.tempfile.TemporaryFile", side_effect=PermissionError("private-key-value")):
            checks = run_checks(self.root)
        self.assertGreaterEqual(sum(item.status == "error" for item in checks), 2)
        self.assertNotIn("private-key-value", str(checks))

    def test_bad_preferences_warn_without_overwriting_the_file(self):
        data = self.root / "data"
        data.mkdir()
        path = data / "preferences.json"
        path.write_text("{broken")
        result = next(item for item in run_checks(self.root) if item.name == "Saved preferences")
        self.assertEqual(result.status, "warning")
        self.assertEqual(path.read_text(), "{broken")

    def test_database_probe_is_read_only_and_does_not_migrate_history(self):
        (self.root / "data").mkdir()
        path = self.root / "data" / "companion.sqlite3"
        with closing(sqlite3.connect(path)) as db:
            db.executescript("PRAGMA user_version=1; CREATE TABLE private(value TEXT); INSERT INTO private VALUES ('a private conversation');")
        original = path.read_bytes()
        checks = run_checks(self.root)
        self.assertEqual(path.read_bytes(), original)
        self.assertNotIn("a private conversation", str(checks))
        with closing(sqlite3.connect(path)) as db:
            self.assertEqual(db.execute("PRAGMA user_version").fetchone()[0], 1)
            db.execute("PRAGMA user_version=99")
        result = next(item for item in run_checks(self.root) if item.name == "Conversation database")
        self.assertEqual(result.status, "error")

    def test_engine_probe_removes_key_and_never_reports_native_stderr(self):
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "private-key-value"}), \
             patch("companion.doctor.subprocess.run", return_value=subprocess.CompletedProcess([], 1)) as run:
            result = engine_check("Voice", "torch")
        self.assertEqual(result.status, "warning")
        self.assertNotIn("OPENROUTER_API_KEY", run.call_args.kwargs["env"])
        self.assertEqual(run.call_args.kwargs["env"]["HF_HUB_OFFLINE"], "1")
        self.assertEqual(run.call_args.kwargs["stderr"], subprocess.DEVNULL)
        with patch("companion.doctor.subprocess.run", side_effect=subprocess.TimeoutExpired("import", 30)):
            self.assertEqual(engine_check("Qt", "PySide6.QtWidgets", required=True).status, "error")
