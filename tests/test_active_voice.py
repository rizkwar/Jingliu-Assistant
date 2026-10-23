from dataclasses import replace
import unittest

from companion.config import DEFAULT_MODEL, Settings, active_character_voice
from companion.reference_voice import VoiceSetupError
from companion.speech_process import PocketSpeaker


class ActiveVoiceTests(unittest.TestCase):
    def setUp(self):
        self.settings = Settings('test-key', DEFAULT_MODEL, 'Jingliu', 'Character prompt',
                                 tts_voice='jane', tts_rate=94,
                                 character_reference='missing-jingliu-reference.wav',
                                 character_voice_rate=100)

    def test_recording_replaces_old_stock_choice_without_changing_other_settings(self):
        selected = active_character_voice(self.settings)
        self.assertEqual(selected, replace(self.settings, tts_voice='reference',
                                          tts_reference=self.settings.character_reference, tts_rate=100))
        # A missing local recording must fail before loading a model, not speak
        # through one of the old stock speakers.
        speaker = PocketSpeaker()
        with self.assertRaises(VoiceSetupError):
            speaker.prepare(selected.tts_reference, lambda *_: None)
        self.assertIsNone(speaker.model)

    def test_current_recording_and_delivery_are_preserved(self):
        current = replace(self.settings, tts_voice='reference', tts_reference='my-recording.wav', tts_rate=97)
        self.assertEqual(active_character_voice(current), current)

    def test_legacy_profile_without_a_recording_keeps_its_existing_voice(self):
        legacy = replace(self.settings, character_reference='')
        self.assertEqual(active_character_voice(legacy), legacy)


if __name__ == '__main__':
    unittest.main()
