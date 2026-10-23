from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

CHECK = Path(__file__).resolve().parents[1] / "scripts/check_publish_safety.py"
NO_REPLY = "123+example@users.noreply.github.com"


class PublishSafetyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.git("init", "-q")
        self.git("config", "user.name", "example")
        self.git("config", "user.email", NO_REPLY)
        self.git("config", "core.autocrlf", "false")

    def git(self, *args):
        return subprocess.run(["git", *args], cwd=self.root, check=True,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    def write(self, path, value):
        file = self.root / path
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(value, encoding="utf-8")
        self.git("add", "--", path)

    def commit(self, message="Add sample"):
        self.git("commit", "-qm", message)

    def scan(self, history=False):
        arguments = [sys.executable, str(CHECK)] + (["--history"] if history else [])
        return subprocess.run(arguments, cwd=self.root, capture_output=True, text=True)

    def test_safe_source_and_no_reply_history_pass(self):
        self.write("app.py", 'print("hello")\n')
        self.commit()
        self.assertEqual(self.scan(history=True).returncode, 0)

    def test_public_github_system_identity_is_allowed(self):
        self.git("config", "user.name", "GitHub Actions")
        self.git("config", "user.email", "noreply@github.com")
        self.write("app.py", "pass\n")
        self.commit()
        self.assertEqual(self.scan(history=True).returncode, 0)

    def test_env_and_private_recordings_are_blocked(self):
        for path in (".env", "clip.wav", "chat.sqlite3", "data/conversation.json", "old.bundle"):
            with self.subTest(path=path):
                self.write(path, "private content")
        result = self.scan()
        self.assertEqual(result.returncode, 1)
        self.assertIn("Private local file", result.stdout)
        self.assertNotIn("private content", result.stdout)

    def test_history_catches_a_deleted_secret_without_printing_it(self):
        credential = "sk-or-v1-" + "x7Z5q9" * 8
        self.write("config.txt", credential)
        self.commit()
        self.git("rm", "config.txt")
        self.commit("Remove credential")
        self.assertEqual(self.scan().returncode, 0)
        result = self.scan(history=True)
        self.assertEqual(result.returncode, 1)
        self.assertNotIn(credential, result.stdout + result.stderr)

    def test_deleted_private_files_are_still_blocked_in_history(self):
        self.write("voices/sample.wav", "dummy recording")
        self.commit()
        self.git("rm", "voices/sample.wav")
        self.commit("Remove sample")
        self.assertEqual(self.scan(history=True).returncode, 1)

    def test_personal_author_identity_is_blocked_without_printing_it(self):
        email = "person" + "@" + "private.invalid"
        self.git("config", "user.name", "Private Person")
        self.git("config", "user.email", email)
        self.write("app.py", "pass\n")
        self.commit()
        result = self.scan(history=True)
        self.assertEqual(result.returncode, 1)
        self.assertIn("Commit identity", result.stdout)
        self.assertNotIn(email, result.stdout)
        self.assertNotIn("Private Person", result.stdout)

    def test_personal_paths_and_email_in_source_are_blocked(self):
        home = "C:" + "/Users/" + "PrivatePerson/project"
        email = "contact" + "@" + "private.invalid"
        self.write("notes.txt", home + "\n" + email)
        result = self.scan()
        self.assertEqual(result.returncode, 1)
        self.assertIn("Absolute user-home path", result.stdout)
        self.assertIn("Personal/contact email", result.stdout)
        self.assertNotIn(home, result.stdout)
        self.assertNotIn(email, result.stdout)

    def test_examples_are_allowed_and_ignored_local_files_are_not_published(self):
        self.write(".gitignore", ".env\n")
        (self.root / ".env").write_text("local-only", encoding="utf-8")
        self.write(".env.example", "OPENROUTER_API_KEY=\nHF_TOKEN=\n")
        self.write("example.txt", "user@example.com")
        self.commit()
        self.assertEqual(self.scan(history=True).returncode, 0)

    def test_secret_in_commit_message_is_blocked(self):
        credential = "hf_" + "pR8sT6uV9wX4yZ2" * 3
        self.write("app.py", "pass\n")
        self.commit(credential)
        result = self.scan(history=True)
        self.assertEqual(result.returncode, 1)
        self.assertNotIn(credential, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
