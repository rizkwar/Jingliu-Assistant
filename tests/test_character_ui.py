import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import httpx
from PySide6.QtCore import QEvent, QTimer
from PySide6.QtWidgets import QApplication

from companion.character import read_profile
from companion.character_ui import CharacterDialog
from companion.characters import CharacterLibrary, ProfileDraft
from companion.config import with_character
from companion.library_ui import HistoryDialog
from companion.preferences import Preferences
from companion.storage import Store
from companion.ui import CompanionWindow
from qt_test_support import application
from test_reference_voice import write_reference
from test_ui import FakeMicrophone, FakeSpeech, SETTINGS, REAL_CLIENT


class CharacterWindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = application()

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.library = CharacterLibrary(self.root)
        self.first = self.library.save(ProfileDraft("Nara", "Calm, dry wit; interested in astronomy.", builtin="jane", rate=95))
        self.preferences = Preferences(self.root / "data" / "preferences.json")
        self.store = Store(":memory:")
        self.speech = FakeSpeech()
        settings = with_character(SETTINGS, read_profile(self.first), use_voice=True)
        self.window = CompanionWindow(settings, store=self.store, speech=self.speech,
                                      microphone=FakeMicrophone(), preferences=self.preferences, characters=self.library)
        self.window.show()

    def tearDown(self):
        self.window.request_quit()
        self.window.deleteLater()
        self.app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.app.processEvents()
        self.store.close()

    def run_editor(self, callback, edit=False):
        errors = []
        def fill():
            dialog = QApplication.activeModalWidget()
            try:
                self.assertIsInstance(dialog, CharacterDialog)
                callback(dialog)
            except BaseException as exc:
                errors.append(exc)
                dialog.reject()
        QTimer.singleShot(0, fill)
        self.window._edit_character() if edit else self.window._add_character()
        if errors:
            raise errors[0]

    def test_describe_attach_preview_save_and_restart_restores_character_and_local_voice(self):
        source = self.root / "sample.wav"
        write_reference(source)
        self.window.input.setPlainText("Keep my unsent thought")
        def fill(dialog):
            dialog.name.setText("Ember")
            dialog.description.setPlainText("Warm and playful, speaks concisely, likes old films. No exaggerated praise.")
            with patch("companion.character_ui.QFileDialog.getOpenFileName", return_value=(str(source), "")):
                dialog.choose_audio.click()
            dialog.preview_text.setText("You have my attention.")
            dialog.preview.click()
            self.assertEqual(self.speech.calls[-1][1], str(source.resolve()))
            dialog.save.click()
            if dialog.saved_path is None:
                self.fail(dialog.feedback.text())
        self.run_editor(fill)
        self.assertEqual(self.window.settings.name, "Ember")
        self.assertEqual(self.window.input.toPlainText(), "Keep my unsent thought")
        managed = self.window._speech_voice()
        self.assertNotEqual(managed, str(source))
        source.unlink()
        self.assertTrue(Path(managed).is_file())
        loaded = Preferences(self.preferences.path).load(SETTINGS)
        self.assertEqual((loaded.name, loaded.tts_reference), ("Ember", managed))
        self.assertIn("likes old films", loaded.system_prompt)
        self.assertIsNone(self.window._worker)

    def test_legacy_profile_can_be_selected_again_after_creating_a_character(self):
        legacy = self.root / "character.md"
        legacy.write_text("You are {name}, an old friend.", encoding="utf-8")
        with patch("companion.ui.load_settings", return_value=SETTINGS):
            self.assertTrue(self.window._activate_character(legacy))
            legacy_conversation = self.window._conversation_id
            self.assertEqual(self.window.settings.name, "Mira")
            self.assertFalse(self.window.edit_character.isEnabled())
            self.assertTrue(self.window._activate_character(self.first))
            available = [self.window.character_select.itemData(i) for i in range(self.window.character_select.count())]
            self.assertIn(str(legacy.resolve()), available)
            self.assertTrue(self.window._activate_character(legacy))
        self.assertEqual(self.window._conversation_id, legacy_conversation)
        self.assertIn("You are Mira, an old friend.", self.window.settings.system_prompt)

    def test_switch_keeps_histories_summaries_and_voice_separate_at_http_boundary(self):
        original_id = self.window._conversation_id
        turn = self.store.start_turn(original_id, "Our telescope project")
        self.store.save_turn(turn, "Use a blue lens.", "Use a blue lens.", "complete")
        self.store.save_summary(original_id, "We chose a blue lens.")
        self.store.save_memory("I prefer short replies.")
        second = self.library.save(ProfileDraft("Ember", "Cheerful, likes films.", builtin="alba"))
        self.assertTrue(self.window._activate_character(second))
        second_id = self.window._conversation_id
        self.assertNotEqual(original_id, second_id)
        self.assertNotIn("blue lens", self.window.transcript.toPlainText())
        self.assertEqual(self.window._speech_voice(), "alba")
        history = HistoryDialog(self.store, self.window)
        self.assertEqual(history.items.count(), 1)
        history.deleteLater()
        requests = []
        def handler(request):
            requests.append(json.loads(request.content))
            return httpx.Response(200, text='data: {"choices":[{"delta":{"content":"Tell me about the film."},"finish_reason":"stop"}]}\n\ndata: [DONE]\n\n')
        with patch("companion.worker.httpx.AsyncClient", side_effect=lambda **kwargs: REAL_CLIENT(
                transport=httpx.MockTransport(handler), trust_env=False, **kwargs)):
            self.window.input.setPlainText("What interests you?")
            self.window._send()
            import time
            deadline = time.monotonic() + 3
            while self.window._worker and time.monotonic() < deadline:
                self.app.processEvents()
                time.sleep(0.005)
        self.assertIsNone(self.window._worker)
        self.assertIn("Cheerful, likes films", requests[0]["messages"][0]["content"])
        self.assertIn("I prefer short replies", requests[0]["messages"][0]["content"])
        self.assertNotIn("blue lens", json.dumps(requests))
        self.assertTrue(self.window._activate_character(self.first))
        self.assertEqual(self.window._conversation_id, original_id)
        self.assertEqual((self.window._speech_voice(), self.window.delivery_rate.value()), ("jane", 95))
        self.assertIn("blue lens", self.window.transcript.toPlainText())
        self.assertEqual(self.store.summary(original_id)["content"], "We chose a blue lens.")

    def test_edit_renames_same_profile_without_losing_chat_and_cancel_writes_nothing(self):
        conversation = self.window._conversation_id
        original = self.first.read_bytes()
        self.run_editor(lambda dialog: (dialog.name.setText("Discard this"), dialog.reject()), edit=True)
        self.assertEqual(self.first.read_bytes(), original)
        def edit(dialog):
            dialog.name.setText("Nara Moon")
            dialog.description.setPlainText("Reserved and curious; gentle wit.")
            dialog.builtin.setCurrentText("vera")
            self.assertEqual(dialog.builtin.count(), 1)
            self.assertTrue(dialog.builtin.isHidden())
            dialog.save.click()
            if dialog.saved_path is None:
                self.fail(dialog.feedback.text())
        self.run_editor(edit, edit=True)
        self.assertEqual(self.window.settings.name, "Nara Moon")
        self.assertEqual(self.window._conversation_id, conversation)
        self.assertEqual(self.window._speech_voice(), "jane")
        self.assertIn("Reserved and curious", self.window.settings.system_prompt)

    def test_failed_selection_keeps_current_character_and_draft(self):
        second = self.library.save(ProfileDraft("Ember", "Cheerful."))
        previous = self.window.settings
        conversation = self.window._conversation_id
        self.window.input.setPlainText("A thought")
        with patch.object(self.preferences, "save", side_effect=PermissionError("Not writable")), \
                patch("companion.ui.QMessageBox.warning"):
            self.assertFalse(self.window._activate_character(second))
        self.assertIs(self.window.settings, previous)
        self.assertEqual(self.window._conversation_id, conversation)
        self.assertEqual(self.window.input.toPlainText(), "A thought")
