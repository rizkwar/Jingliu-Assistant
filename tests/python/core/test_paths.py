"""Saved paths and character keys survive moving or renaming the project folder."""

import json
from pathlib import Path
import tempfile
import unittest

from companion.avatar.models import AvatarModels
from companion.character.profile import character_key
from companion.core.config import DEFAULT_MODEL, PROJECT_ROOT, Settings
from companion.core.paths import portable, resolve
from companion.core.preferences import Preferences
from companion.core.storage import Store

# A real file in the project, saved under the folder's old name.
OLD = r"D:\Projects\OldName\requirements.txt"


class PathTests(unittest.TestCase):
    def test_paths_in_the_project_are_saved_relative_to_it(self):
        self.assertEqual(portable(PROJECT_ROOT / "voices" / "her.wav"), "voices/her.wav")
        self.assertEqual(portable("voices/her.wav"), "voices/her.wav")
        outside = Path(tempfile.gettempdir()) / "elsewhere.wav"
        self.assertEqual(portable(outside), str(outside))
        self.assertEqual(resolve("requirements.txt"), PROJECT_ROOT / "requirements.txt")

    def test_a_full_path_from_before_the_folder_moved_is_found_again(self):
        self.assertEqual(resolve(OLD), PROJECT_ROOT / "requirements.txt")
        missing = r"D:\Music\never-there-1234.wav"
        self.assertEqual(resolve(missing), Path(missing))  # Nothing matches: left alone.

    def test_character_keys_are_the_same_before_and_after_a_move(self):
        self.assertEqual(character_key(str(PROJECT_ROOT / "requirements.txt")), character_key(OLD))
        self.assertEqual(character_key(OLD), "requirements.txt")
        self.assertEqual(character_key(""), "")


class MovedFolderTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.folder = Path(folder.name)

    def test_conversations_follow_their_character(self):
        path = self.folder / "chats.sqlite3"
        store = Store(path)
        store.create_conversation(OLD.lower())
        store.create_conversation("named-in-a-test")
        store.close()
        reopened = Store(path)
        self.addCleanup(reopened.close)
        self.assertEqual(len(reopened.conversations(character_key(OLD))), 1)
        self.assertEqual(len(reopened.conversations("named-in-a-test")), 1)  # Relative keys are untouched.

    def test_avatar_model_choices_follow_their_character(self):
        (self.folder / "data").mkdir()
        entry = {"models": [], "selected": "current"}
        (self.folder / "data/avatar_models.json").write_text(
            json.dumps({"version": 1, "characters": {OLD.lower(): dict(entry, selected="old"),
                                                       "requirements.txt": entry}}), encoding="utf-8")
        characters = AvatarModels(self.folder)._load()["characters"]
        self.assertEqual(list(characters), ["requirements.txt"])
        self.assertEqual(characters["requirements.txt"]["selected"], "current")  # The newer entry wins.

    def test_preferences_find_the_voice_again_and_save_it_relative(self):
        path = self.folder / "preferences.json"
        path.write_text(json.dumps({"version": 1, "settings": {"tts_reference": OLD},
                                    "character_voices": {OLD: {"tts_reference": OLD}}}), encoding="utf-8")
        preferences = Preferences(path)
        loaded = preferences.load(Settings("", DEFAULT_MODEL, "Aria", "Hi"))
        self.assertEqual(Path(loaded.tts_reference), PROJECT_ROOT / "requirements.txt")
        self.assertIn("requirements.txt", preferences.character_paths())
        preferences.save(loaded)
        saved = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(saved["settings"]["tts_reference"], "requirements.txt")
        self.assertEqual(saved["character_voices"]["requirements.txt"]["tts_reference"], "requirements.txt")


if __name__ == "__main__":
    unittest.main()
