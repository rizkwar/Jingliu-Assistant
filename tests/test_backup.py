import tempfile
import unittest
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from companion import backup
from companion.storage import Store


class BackupTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.project, self.data = self.root / "project", self.root / "project" / "data"
        (self.data / "attachments" / "2026").mkdir(parents=True)
        (self.data / "attachments" / "2026" / "photo.png").write_bytes(b"png")
        (self.data / "preferences.json").write_text('{"version": 1}', encoding="utf-8")
        (self.project / "character.toml").write_text('name = "Jingliu"', encoding="utf-8")
        self.store = Store(self.data / "companion.sqlite3")
        conversation = self.store.create_conversation()
        turn = self.store.start_turn(conversation, "Hello there")
        self.store.save_turn(turn, "Good evening.", "Good evening.", "complete")
        self.store.save_memory("Takes tea without sugar.")
        self.store.add_reminder("Study", datetime.now(timezone.utc) + timedelta(hours=2))

    def tearDown(self):
        self.store.close()

    def test_a_backup_holds_everything_and_restores_it(self):
        archive = backup.backup(self.store, self.root / "backup.zip", self.data, self.project)
        with zipfile.ZipFile(archive) as zipped:
            names = set(zipped.namelist())
        for name in ("data/companion.sqlite3", "data/preferences.json", "data/attachments/2026/photo.png",
                     "project/character.toml", backup.MANIFEST):
            self.assertIn(name, names)
        self.assertEqual(backup.check(archive)["app"], "Jingliu")
        # Things change after the backup...
        self.store.save_memory("Something new.")
        (self.data / "attachments" / "2026" / "photo.png").unlink()
        (self.data / "preferences.json").write_text('{"changed": true}', encoding="utf-8")
        safety = backup.restore(archive, self.data / "backups", self.data, self.project, store=self.store)
        self.assertTrue(safety.is_file())  # What was there before is kept.
        restored = Store(self.data / "companion.sqlite3")
        try:
            self.assertEqual([m["content"] for m in restored.memories()], ["Takes tea without sugar."])
            self.assertEqual([r["text"] for r in restored.reminders()], ["Study"])
        finally:
            restored.close()
        self.assertTrue((self.data / "attachments" / "2026" / "photo.png").is_file())
        self.assertEqual((self.data / "preferences.json").read_text(encoding="utf-8"), '{"version": 1}')
        self.store = Store(":memory:")  # The real one was closed by the restore.

    def test_only_jingliu_backups_with_safe_paths_are_accepted(self):
        bad = self.root / "bad.zip"
        with zipfile.ZipFile(bad, "w") as zipped:
            zipped.writestr("hello.txt", "hi")
        with self.assertRaises(ValueError):
            backup.check(bad)
        evil = self.root / "evil.zip"
        with zipfile.ZipFile(evil, "w") as zipped:
            zipped.writestr(backup.MANIFEST, "{}")
            zipped.writestr("data/companion.sqlite3", "")
            zipped.writestr("data/../../outside.txt", "no")
        with self.assertRaises(ValueError):
            backup.check(evil)
        (self.root / "notzip.zip").write_text("x")
        with self.assertRaises(ValueError):
            backup.check(self.root / "notzip.zip")

    def test_export_is_a_readable_text_file(self):
        target = backup.export_text(self.store, self.root / "export.md", "Jingliu")
        text = target.read_text(encoding="utf-8")
        for expected in ("# Conversations with Jingliu", "- Takes tea without sugar. (pinned)", "- Study —",
                         "## Hello there", "**You:** Hello there", "**Jingliu:** Good evening."):
            self.assertIn(expected, text)


if __name__ == "__main__":
    unittest.main()
