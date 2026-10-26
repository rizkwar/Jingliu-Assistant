"""The Codex-style window: sidebar conversations, search, pins, message style, model picker and reply actions."""

import os
import unittest
from dataclasses import replace
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent, Qt
from PySide6.QtWidgets import QMessageBox

from companion.core.storage import Store
from companion.ui.chat_view import Bubble
from companion.ui.window import CompanionWindow
from tests.python.ui.test_ui import SETTINGS, FakeMicrophone, FakeSpeech
from tests.qt_test_support import application


def conversation(store, title, pinned=False):
    identifier = store.create_conversation("")
    store.rename_conversation(identifier, title)
    turn = store.start_turn(identifier, "Hello")
    store.save_turn(turn, "Hello.", "Hello.", "complete")
    if pinned:
        store.pin_conversation(identifier)
    return identifier


class SidebarLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = application()

    def setUp(self):
        self.store = Store(":memory:")
        self.older = conversation(self.store, "Study plan for finals")
        self.pinned = conversation(self.store, "Practising sword forms", pinned=True)
        self.speech = FakeSpeech()
        self.window = CompanionWindow(replace(SETTINGS, llm_provider="claude"), speech=self.speech,
                                      microphone=FakeMicrophone(), store=self.store)
        self.window.resize(1200, 800)
        self.window.show()
        self.app.processEvents()

    def tearDown(self):
        self.window.close()
        self.window.deleteLater()
        self.app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.app.processEvents()

    def titles(self):
        sidebar = self.window.sidebar.list
        return [sidebar.item(row).text() for row in range(sidebar.count())
                if sidebar.item(row).data(Qt.ItemDataRole.UserRole)]  # Date headings are not chats.

    def test_sidebar_lists_pinned_first_and_hides_other_empty_chats(self):
        titles = self.titles()
        self.assertEqual(titles[0], "Practising sword forms")  # Pinned, with a crescent.
        self.assertIn("Study plan for finals", titles)
        self.window._new_conversation()
        self.window._new_conversation()  # The first empty one leaves the list again.
        self.assertEqual(self.titles().count("New conversation"), 1)

    def test_search_filters_conversations(self):
        self.window._search_conversations()
        self.window.sidebar.search.setText("sword")
        self.assertEqual(self.titles(), ["Practising sword forms"])
        self.assertEqual(self.window.sidebar.list_title.text(), "Results")

    def test_clicking_a_conversation_opens_it_and_pins_persist(self):
        item = self.window.sidebar.list.findItems("Study plan for finals", Qt.MatchFlag.MatchExactly)[0]
        self.window.sidebar.list.itemClicked.emit(item)
        self.assertEqual(self.window._conversation_id, self.older)
        self.assertEqual(self.window.conversation_title.text(), "Study plan for finals")
        self.window._pin_conversation(self.older, True)
        self.assertTrue(self.store.conversation(self.older)["pinned"])
        self.window._pin_conversation(self.pinned, False)
        self.assertEqual(self.titles()[0], "Study plan for finals")

    def test_deleting_the_open_conversation_moves_to_another(self):
        self.window._switch_conversation(self.older)
        with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes):
            self.window._delete_conversation(self.older)
        self.assertIsNone(self.store.conversation(self.older))
        self.assertNotEqual(self.window._conversation_id, self.older)
        self.assertNotIn("Study plan for finals", self.titles())

    def test_message_style_switches_between_plain_text_and_bubble(self):
        self.window._switch_conversation(self.older)
        replies = [item for item in self.window.transcript._items if isinstance(item, Bubble) and item.role != "user"]
        self.assertTrue(replies and replies[0].property("plain"))  # Plain by default, like Codex.
        self.window.message_style.setCurrentIndex(self.window.message_style.findData("bubble"))
        self.assertFalse(replies[0].property("plain"))
        self.assertEqual(self.window.settings.message_style, "bubble")

    def test_model_picker_shows_and_changes_the_model(self):
        self.assertEqual(self.window.model_picker.text(), "Sonnet 5.5")
        self.window._fill_model_menu()
        opus = next(action for action in self.window.model_menu.actions() if action.text() == "Claude Opus 5.5")
        opus.trigger()
        self.assertEqual(self.window.settings.claude_model, "claude-opus-5-5")
        self.assertEqual(self.window.model_picker.text(), "Opus 5.5")

    def test_approve_chip_mirrors_the_ask_before_acting_setting(self):
        self.assertFalse(self.window.approve_chip.isChecked())  # She asks first by default.
        self.window.approve_chip.click()
        self.assertFalse(self.window.approve_steps.isChecked())
        self.assertFalse(self.window.settings.approve_steps)
        self.window.approve_steps.setChecked(True)
        self.assertFalse(self.window.approve_chip.isChecked())

    def test_quote_and_read_aloud_from_her_reply(self):
        self.window.input.setPlainText("And then?")
        self.window._quote("Examples first.\nThen the reasoning.")
        self.assertEqual(self.window.input.toPlainText(), "> Examples first.\n> Then the reasoning.\n\nAnd then?\n")
        self.window._read_aloud("Examples first.")
        self.assertEqual(self.speech.calls[-1][0], "Examples first.")

    def test_opening_a_chat_keeps_its_place_and_is_reopened_next_time(self):
        before = self.titles()
        bottom = self.window.sidebar.list.findItems(before[-1], Qt.MatchFlag.MatchExactly)[0]
        chosen = bottom.data(Qt.ItemDataRole.UserRole)
        self.window.sidebar.list.itemClicked.emit(bottom)
        self.assertEqual(self.titles(), before)  # Only a new message moves a chat up.
        self.assertEqual(self.window.settings.last_conversation, chosen)
        again = CompanionWindow(self.window.settings, speech=FakeSpeech(), microphone=FakeMicrophone(), store=self.store)
        self.addCleanup(again.deleteLater)
        self.assertEqual(again._conversation_id, chosen)

    def test_folders_show_a_chevron_and_open_with_their_chats(self):
        from companion.ui.sidebar import ICONS
        project = self.window._new_project()
        self.window._new_chat_in_project(project)
        self.window.store.start_turn(self.window._conversation_id, "Hello")
        self.window._refresh_sidebar()
        tree = self.window.sidebar.trees["project"]
        item = tree.topLevelItem(0)
        self.assertEqual(tree.indentation(), 0)  # No indentation area to paint in another blue.
        self.assertTrue(item.isExpanded())
        self.assertEqual(item.text(1), ICONS["chevron"])  # A symbol, not a number.
        tree.itemClicked.emit(item, 1)  # The chevron only folds…
        self.assertFalse(item.isExpanded())
        self.assertEqual(item.text(1), ICONS["chevron_right"])
        self.assertIs(self.window.pages.currentWidget(), self.window.chat_page)  # …it doesn't open the page.

    def test_rows_offer_buttons_on_hover(self):
        sidebar = self.window.sidebar
        chat = sidebar.list.findItems("Study plan for finals", Qt.MatchFlag.MatchExactly)[0]
        self.assertEqual([glyph for glyph, _, _ in sidebar._buttons_for(chat)], ["pin", "more"])
        heading = next(sidebar.list.item(row) for row in range(sidebar.list.count())
                       if not sidebar.list.item(row).data(Qt.ItemDataRole.UserRole))
        self.assertEqual(sidebar._buttons_for(heading), [])
        dict(((glyph, callback) for glyph, _, callback in sidebar._buttons_for(chat)))["pin"](chat, None)
        self.assertTrue(self.store.conversation(self.older)["pinned"])
        project = self.window._new_project("study")
        folder = sidebar.trees["study"].topLevelItem(0)
        self.assertEqual([glyph for glyph, _, _ in sidebar._buttons_for(folder)], ["compose", "more"])
        dict(((glyph, callback) for glyph, _, callback in sidebar._buttons_for(folder)))["compose"](folder, None)
        self.assertEqual(self.store.conversation(self.window._conversation_id)["project_id"], project)

    def test_sidebar_hides_on_a_narrow_window_and_comes_back(self):
        self.window.resize(600, 700)
        self.app.processEvents()
        self.assertFalse(self.window.sidebar.isVisible())
        self.assertTrue(self.window.show_sidebar.isVisible())
        self.window.resize(1200, 800)
        self.app.processEvents()
        self.assertTrue(self.window.sidebar.isVisible())


if __name__ == "__main__":
    unittest.main()
