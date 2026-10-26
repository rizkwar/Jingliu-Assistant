import asyncio
from dataclasses import replace
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import httpx

from companion.character import MAX_PROFILE_BYTES, read_profile
from companion.config import load_settings
from companion.llm import stream_reply
from companion.prompts import reply_prompt
from companion.storage import Store


ROOT = Path(__file__).resolve().parent.parent
PROFILE = ROOT / "character.toml"


class CharacterTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.profile = self.root / "character.toml"
        self.profile.write_bytes(PROFILE.read_bytes())
        environment = patch.dict(os.environ, {}, clear=True)
        environment.start()
        self.addCleanup(environment.stop)

    def test_profile_sets_identity_despite_legacy_name_and_rereads_edits(self):
        (self.root / ".env").write_text("COMPANION_NAME=Jinger\nTTS_VOICE=vera\n", encoding="utf-8")
        settings = load_settings(self.root)
        self.assertEqual(settings.name, "Jingliu")
        self.assertEqual(settings.tts_voice, "vera")  # Character does not silently choose a voice.
        self.assertIn("You have my attention", settings.voice_preview)
        self.assertEqual((settings.character_voice, settings.character_voice_rate), ("jane", 100))
        self.assertEqual(Path(settings.character_reference).name, 'jingliu-reference.wav')
        self.assertNotIn("[voice]", settings.system_prompt)
        self.assertEqual(Path(settings.character_path), self.profile.resolve())
        self.profile.write_text(self.profile.read_text(encoding="utf-8").replace('name = "Jingliu"', 'name = "Luna"'), encoding="utf-8")
        self.assertEqual(load_settings(self.root).name, "Luna")

    def test_selection_is_root_relative_and_explicit_missing_profile_does_not_fallback(self):
        profiles = self.root / "profiles"
        profiles.mkdir()
        self.profile.replace(profiles / "other.toml")
        (self.root / ".env").write_text("CHARACTER_PROFILE=profiles/other.toml\n", encoding="utf-8")
        self.assertEqual(load_settings(self.root).name, "Jingliu")
        (self.root / ".env").write_text("CHARACTER_PROFILE=absent.toml\n", encoding="utf-8")
        with self.assertRaises(OSError):
            load_settings(self.root)

    def test_invalid_profile_reports_safe_actionable_errors_without_silent_character_change(self):
        for text in ('schema_version = 9', 'schema_version = 1\n[identity]\nname = 4',
                     'schema_version = 1\n[unknown]\nvalue = "x"', 'private_unterminated_value = "secret'):
            with self.subTest(text=text):
                self.profile.write_text(text, encoding="utf-8")
                with self.assertRaises(ValueError) as error:
                    read_profile(self.profile)
                self.assertNotIn("secret", str(error.exception))
        self.profile.write_bytes(b"x" * (MAX_PROFILE_BYTES + 1))
        with self.assertRaisesRegex(ValueError, "32 KiB"):
            read_profile(self.profile)

    def test_profile_examples_are_labeled_demonstrations_and_reference_metadata_is_omitted(self):
        character = read_profile(self.profile)
        self.assertIn("never memories of this user", character.prompt)
        self.assertIn("Continuity after summarization", character.prompt)
        self.assertIn("Missing shared history", character.prompt)
        self.assertIn("not canon", self.profile.read_text(encoding="utf-8"))
        self.assertNotIn("https://", character.prompt)

    def test_voice_preset_rejects_unknown_voices_and_invalid_rates(self):
        original = self.profile.read_text(encoding="utf-8")
        for text in (original.replace('builtin = "jane"', 'builtin = "invented"'),
                     original.replace("rate = 100", "rate = 12"),
                     original.replace("rate = 100", "rate = true")):
            self.profile.write_text(text, encoding="utf-8")
            with self.assertRaises(ValueError):
                read_profile(self.profile)

    def test_profile_survives_database_reopen_summary_and_fresh_conversation_requests(self):
        # Verify actual request composition at the HTTP boundary, without provider calls.
        database = self.root / "test.sqlite3"
        store = Store(database)
        conversation = store.create_conversation()
        store.save_memory("The user's current project is a lunar garden planner", True)
        store.save_summary(conversation, "We chose the violet layout; the user asked for less teasing while debugging.")
        store.close()
        reopened = Store(database)
        self.addCleanup(reopened.close)
        settings = replace(load_settings(self.root), api_key="test-key", llm_provider="openrouter")
        requests = []
        def handler(request):
            requests.append(json.loads(request.content))
            return httpx.Response(200, text='data: {"choices":[{"delta":{"content":"One concrete step."},"finish_reason":"stop"}]}\n\ndata: [DONE]\n\n')
        async def send(summary):
            prompt = reply_prompt(settings.system_prompt, reopened.relevant_memories("garden"), summary)
            async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
                return [part async for part in stream_reply(client, replace(settings, system_prompt=prompt),
                                                            [{"role": "user", "content": "What comes next?"}])]
        self.assertEqual(asyncio.run(send(reopened.summary(conversation)["content"])), ["One concrete step."])
        fresh = reopened.create_conversation()
        self.assertIsNone(reopened.summary(fresh))
        asyncio.run(send(None))
        for request in requests:
            prompt = request["messages"][0]["content"]
            self.assertTrue(prompt.startswith(settings.system_prompt))
            self.assertIn("lunar garden planner", prompt)
            self.assertIn("Fictional identity and background are roleplay", prompt)
            self.assertIn("Only claim shared history supported", prompt)
        self.assertIn("violet layout", requests[0]["messages"][0]["content"])
        self.assertNotIn("violet layout", requests[1]["messages"][0]["content"])

    def test_retrieval_disabled_does_not_insert_private_memories_into_contract(self):
        prompt = reply_prompt(read_profile(self.profile).prompt)
        self.assertIn("Saved memory records (JSON):\n[]", prompt)
        self.assertIn("Memory retrieval may be disabled", prompt)
