from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from companion.character import profile_document, read_profile
from companion.characters import CharacterLibrary, ProfileDraft
from companion.config import DEFAULT_MODEL, Settings, with_character
from companion.preferences import Preferences
from test_reference_voice import write_reference


ROOT = Path(__file__).resolve().parent.parent
DEFAULTS = Settings("private-api-key", DEFAULT_MODEL, "Mira", "old prompt", hf_token="private-hf-token")


class CharacterLibraryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.library = CharacterLibrary(self.root)
        self.source = self.root / "source.wav"
        write_reference(self.source)

    def draft(self, **changes):
        return replace(ProfileDraft('Luna "月"', 'Quiet, curious. Say "hmm" sparingly.\nUser: I am stuck.\nCharacter: Show me where.',
                                    str(self.source), "jane", 100, "Take your time."), **changes)

    def test_description_and_audio_round_trip_without_upload_and_survive_source_deletion(self):
        original = self.source.read_bytes()
        path = self.library.save(self.draft())
        character = read_profile(path)
        self.assertEqual(character.name, 'Luna "月"')
        self.assertEqual(character.description, self.draft().description)
        self.assertIn('User: I am stuck.', character.prompt)
        self.assertIn("never memories of this user", character.prompt)
        self.assertNotIn(str(self.source), character.prompt)
        self.assertEqual(Path(character.reference).read_bytes(), original)
        self.assertNotEqual(Path(character.reference), self.source)
        self.source.unlink()
        reopened = CharacterLibrary(self.root)
        self.assertEqual(reopened.draft(path).reference, character.reference)
        self.assertEqual(reopened.profiles()[0][:2], (str(path), character.name))

    def test_duplicate_names_get_independent_profiles_and_no_sample_is_required(self):
        first = self.library.save(self.draft(reference=""))
        second = self.library.save(self.draft(reference=""))
        self.assertNotEqual(first, second)
        self.assertEqual(read_profile(first).reference, "")
        self.assertEqual(len(self.library.profiles()), 2)

    def test_edit_converts_structured_profile_preserving_examples_provenance_and_backup(self):
        path = self.root / "character.toml"
        original = (ROOT / "character.toml").read_bytes()
        path.write_bytes(original)
        draft = self.library.draft(path)
        self.assertIn("Missing shared history", draft.description)
        updated = replace(draft, reference=str(self.source), name="My Jingliu")
        self.library.save(updated, path)
        self.assertEqual(path.with_suffix(".toml.bak").read_bytes(), original)
        character = read_profile(path)
        self.assertEqual(character.name, "My Jingliu")
        self.assertIn("Missing shared history", character.prompt)
        self.assertIn("https://", str(profile_document(path)["reference"]))
        self.assertNotIn("https://", character.prompt)
        self.assertTrue(Path(character.reference).is_relative_to(self.library.directory))
        self.library.save(replace(updated, description="A new direction."), path)
        self.assertEqual(path.with_suffix(".toml.bak").read_bytes(), original)

    def test_invalid_description_or_recording_leaves_existing_profile_unchanged(self):
        path = self.library.save(self.draft(reference=""))
        original = path.read_bytes()
        for changes in ({"description": ""}, {"description": "x" * 24001}, {"name": "a\nb"},
                        {"reference": "missing.wav"}, {"rate": 3}, {"preview": "x" * 6001}):
            with self.subTest(changes=list(changes)):
                with self.assertRaises(ValueError):
                    self.library.save(self.draft(**changes), path)
                self.assertEqual(path.read_bytes(), original)

    def test_failed_atomic_profile_replace_retains_original_and_cleans_temporary_files(self):
        path = self.library.save(self.draft(reference=""))
        original = path.read_bytes()
        with patch("companion.characters.os.replace", side_effect=PermissionError("busy")):
            with self.assertRaises(OSError):
                self.library.save(self.draft(reference="", description="Changed"), path)
        self.assertEqual(path.read_bytes(), original)
        self.assertEqual(list(path.parent.glob("*.tmp")), [])
        self.assertEqual(list(path.parent.glob("*.toml")), [path])

    def test_switch_restores_each_voice_and_startup_reloads_description_without_storing_secrets(self):
        first = read_profile(self.library.save(self.draft()))
        second = read_profile(self.library.save(self.draft(name="Ember", reference="", builtin="alba")))
        preferences = Preferences(self.root / "data" / "preferences.json")
        active = with_character(DEFAULTS, first, use_voice=True)
        active = replace(active, tts_rate=97)
        other = preferences.select(active, second)
        self.assertEqual((other.tts_voice, other.tts_reference), ("alba", ""))
        restored = preferences.select(other, first)
        self.assertEqual((restored.tts_voice, restored.tts_reference, restored.tts_rate), ("reference", first.reference, 97))
        # A newly saved edit intentionally replaces an old voice override.
        edited = replace(self.library.draft(first.path), reference="", rate=102)
        self.library.save(edited, first.path)
        restored = preferences.select(restored, read_profile(first.path), use_profile_voice=True)
        self.assertEqual((restored.tts_voice, restored.tts_rate), ("jane", 102))
        self.library.save(replace(edited, description="A revised personality."), first.path)
        startup = Preferences(preferences.path).load(DEFAULTS)
        self.assertEqual(startup.name, first.name)
        self.assertIn("A revised personality.", startup.system_prompt)
        self.assertEqual(startup.api_key, DEFAULTS.api_key)
        saved = preferences.path.read_text()
        for private in (DEFAULTS.api_key, DEFAULTS.hf_token, "A revised personality."):
            self.assertNotIn(private, saved)
        known = [path for path, _, _ in self.library.profiles(str(first.path), preferences.character_paths())]
        self.assertIn(str(second.path), known)

    def test_description_example_and_previously_selected_external_profiles_are_valid(self):
        example = read_profile(ROOT / "examples" / "character-description.toml")
        self.assertEqual(example.name, "Nara")
        self.assertIn("An ambitious opening", example.prompt)
        first = self.root / "external.toml"
        first.write_bytes((ROOT / "examples" / "character-description.toml").read_bytes())
        active = self.library.save(self.draft(reference=""))
        listed = self.library.profiles(str(active), [str(first)])
        self.assertIn(str(first.resolve()), [path for path, _, _ in listed])

    def test_malformed_saved_profile_does_not_replace_current_preferences(self):
        character = read_profile(self.library.save(self.draft(reference="")))
        preferences = Preferences(self.root / "preferences.json")
        active = preferences.select(DEFAULTS, character)
        original = preferences.path.read_bytes()
        with patch("companion.preferences.os.replace", side_effect=PermissionError("busy")):
            with self.assertRaises(OSError):
                preferences.select(active, replace(character, name="Other", path=self.root / "other.toml"))
        self.assertEqual(preferences.path.read_bytes(), original)
        self.assertEqual(preferences.load(DEFAULTS).name, character.name)
