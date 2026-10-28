"""Skills: her own folder of Claude Code skills, added, switched, removed and installed, and loaded only when she has some."""

from dataclasses import replace
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent

from companion.chat import skills
from companion.chat.claude import reply_command
from tests.qt_test_support import application


def skill(folder, name, description="Use it for tests."):
    path = Path(folder) / name
    path.mkdir(parents=True, exist_ok=True)
    (path / "SKILL.md").write_text(f"---\nname: {name}\ndescription: {description}\n---\n\nDo the thing.\n", encoding="utf-8")
    return path


class SkillStoreTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        root = Path(self.folder.name) / "skills"
        for name, value in (("ROOT", root), ("PLUGIN", root / "plugin"), ("OFF", root / "off")):
            patcher = patch.object(skills, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.source = Path(self.folder.name) / "source"

    def test_a_folder_of_skills_is_added_switched_and_removed(self):
        self.assertIsNone(skills.plugin_dir())  # None yet: replies keep safe mode.
        skill(self.source / "pack" / "one", "study-notes", "Make study notes.")
        skill(self.source / "pack" / "two", "quiz-maker")
        self.assertEqual(sorted(skills.add(self.source)), ["quiz-maker", "study-notes"])
        found = {item["name"]: item for item in skills.installed()}
        self.assertEqual(found["study-notes"]["description"], "Make study notes.")
        plugin = Path(skills.plugin_dir())
        self.assertTrue((plugin / ".claude-plugin" / "plugin.json").is_file())
        skills.set_enabled("quiz-maker", False)
        self.assertFalse({item["name"]: item for item in skills.installed()}["quiz-maker"]["enabled"])
        self.assertFalse((plugin / "skills" / "quiz-maker").exists())
        skills.set_enabled("quiz-maker", True)
        skills.remove("study-notes")
        self.assertEqual([item["name"] for item in skills.installed()], ["quiz-maker"])
        with self.assertRaises(skills.SkillError):
            skills.add(Path(self.folder.name) / "nothing-here")

    def test_github_links_of_every_shape(self):
        self.assertEqual(skills.parse_github("https://github.com/emilkowalski/skills"), ("emilkowalski", "skills", None, ""))
        self.assertEqual(skills.parse_github("https://github.com/o/r/tree/main/skills/animate"), ("o", "r", "main", "skills/animate"))
        self.assertEqual(skills.parse_github("https://github.com/o/r/blob/dev/x/SKILL.md"), ("o", "r", "dev", "x"))
        self.assertEqual(skills.parse_github("o/r"), ("o", "r", None, ""))
        with self.assertRaises(skills.SkillError):
            skills.parse_github("https://example.com/not-github")

    def zipped(self, files):
        data = io.BytesIO()
        with zipfile.ZipFile(data, "w") as archive:
            for name, text in files.items():
                archive.writestr(name, text)
        return data.getvalue()

    def test_installing_from_github_takes_the_skills_in_the_folder_asked_for(self):
        archive = self.zipped({
            "repo-main/skills/animate/SKILL.md": "---\nname: animate\ndescription: Motion.\n---\nBody",
            "repo-main/skills/review/SKILL.md": "---\nname: review-animations\ndescription: Review.\n---\nBody",
            "repo-main/README.md": "hi"})
        seen = []

        def get(url, limit=0):
            seen.append(url)
            return b'{"default_branch": "main"}' if "api.github.com" in url else archive
        with patch.object(skills, "_get", get):
            self.assertEqual(skills.install("https://github.com/o/repo/tree/main/skills/animate"), ["animate"])
            self.assertEqual(sorted(skills.install("o/repo")), ["animate", "review-animations"])
        self.assertIn("https://codeload.github.com/o/repo/zip/refs/heads/main", seen)

    def test_an_archive_that_writes_outside_its_folder_is_refused(self):
        archive = self.zipped({"../evil/SKILL.md": "---\nname: evil\n---\n"})
        with patch.object(skills, "_get", lambda url, limit=0: archive if "codeload" in url else b"{}"):
            with self.assertRaises(skills.SkillError):
                skills.install("o/repo")
        self.assertEqual(skills.installed(), [])

    def test_your_claude_code_skills_are_offered_until_she_has_them(self):
        home = Path(self.folder.name) / "claude"
        skill(home / "skills", "ui-ux-pro-max", "UI help.")
        with patch.dict(os.environ, {"CLAUDE_CONFIG_DIR": str(home)}):
            offered = skills.claude_code_skills()
            self.assertEqual([name for name, _, _ in offered], ["ui-ux-pro-max"])
            skills.add_folder(offered[0][2])
            self.assertEqual(skills.claude_code_skills(), [])

    def test_replies_load_only_her_skills_and_keep_safe_mode_without_any(self):
        with patch("companion.chat.claude.claude_executable", lambda: "claude"):
            plain = reply_command("p.txt", "m")
            with_skills = reply_command("p.txt", "m", skills="C:/her/plugin")
        self.assertIn("--safe-mode", plain)
        self.assertNotIn("--plugin-dir", plain)
        self.assertNotIn("--safe-mode", with_skills)
        self.assertEqual(with_skills[with_skills.index("--setting-sources") + 1], "")  # None of your setup.
        self.assertEqual(with_skills[with_skills.index("--plugin-dir") + 1], "C:/her/plugin")
        self.assertIn("Skill", with_skills[with_skills.index("--tools") + 1])
        self.assertIn("Skill", with_skills[with_skills.index("--allowedTools") + 1:])

    def test_tasks_get_her_skills(self):
        from companion.tasks.runner import ComputerTask
        from tests.python.tasks.test_computer_tasks import SETTINGS
        skill(self.source, "study-notes")
        skills.add(self.source)
        with patch("companion.tasks.runner.UNDO_ROOT", Path(self.folder.name) / "undo"):
            task = ComputerTask("Make notes", [], SETTINGS)
        arguments = task.process.arguments()
        self.assertEqual(arguments[arguments.index("--plugin-dir") + 1], str(skills.PLUGIN))
        self.assertNotIn("--disable-slash-commands", arguments)
        self.assertIn("Skill", arguments[arguments.index("--tools") + 1])
        task.folder.cleanup()


class SkillCueTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = application()

    def test_her_install_cue_asks_you_first(self):
        from companion.core.storage import Store
        from companion.ui.window import CompanionWindow
        from tests.python.ui.test_ui import SETTINGS, FakeMicrophone, FakeSpeech
        window = CompanionWindow(replace(SETTINGS, llm_provider="claude"), speech=FakeSpeech(),
                                 microphone=FakeMicrophone(), store=Store(":memory:"))
        try:
            asked, installs = [], []
            with patch("companion.ui.window.ask", lambda *args, **kwargs: asked.append(args)), \
                    patch.object(window.skills_panel, "install", lambda source: installs.append(source) or True):
                window._queue_cues([(0, "installskill:https://github.com/o/r")])
                window._apply_memory_actions()
                self.app.processEvents()
                self.assertEqual(len(asked), 1)
                self.assertIn("https://github.com/o/r", asked[0][2])
                self.assertEqual(installs, [])  # Nothing until you say yes…
                asked[0][4]()
                self.assertEqual(installs, ["https://github.com/o/r"])  # …then it installs.
        finally:
            window.close()
            window.deleteLater()
            self.app.sendPostedEvents(None, QEvent.Type.DeferredDelete)


if __name__ == "__main__":
    unittest.main()
