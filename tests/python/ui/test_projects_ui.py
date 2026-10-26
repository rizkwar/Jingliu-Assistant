"""Projects and MCP servers in the window: creating, chatting in, moving, deleting; servers in Settings."""

import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from dataclasses import replace
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent
from PySide6.QtWidgets import QMessageBox

from companion.core import mcp
from companion.core.storage import Store
from companion.ui.tools import ServerDialog
from companion.ui.window import CompanionWindow
from tests.python.ui.test_ui import SETTINGS, FakeMicrophone, FakeSpeech
from tests.qt_test_support import application


class ProjectWindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = application()

    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.folder = Path(folder.name)
        self.store = Store(":memory:")
        mcp.save([mcp.Server(name="notes", command="uvx", scope="everywhere", ask=False),
                  mcp.Server(name="github", transport="http", url="https://x.test/mcp")], self.folder / "mcp.json")
        self.window = CompanionWindow(replace(SETTINGS, llm_provider="claude"), speech=FakeSpeech(),
                                      microphone=FakeMicrophone(), store=self.store,
                                      mcp_config=self.folder / "mcp.json", projects_root=self.folder / "projects")
        self.window.resize(1200, 800)
        self.window.show()
        self.app.processEvents()

    def tearDown(self):
        self.window.close()
        self.window.deleteLater()
        self.app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.app.processEvents()

    def make_project(self, name="Calculus exam"):
        project = self.window._new_project()
        self.window.project_page.name.setText(name)
        self.window.project_page._save_name()
        return project

    def test_a_new_project_opens_its_page_and_appears_in_the_sidebar(self):
        project = self.make_project()
        self.assertIs(self.window.pages.currentWidget(), self.window.project_page)
        self.assertEqual(self.window.conversation_title.text(), "Calculus exam")  # The header names the page.
        tree = self.window.sidebar.tree
        self.assertEqual(tree.topLevelItem(0).text(0), "Calculus exam")
        self.assertEqual(self.store.project(project)["name"], "Calculus exam")

    def test_chats_in_a_project_carry_its_instructions_and_files(self):
        project = self.make_project()
        page = self.window.project_page
        page.instructions.setPlainText("Worked examples first.")
        page._save_instructions()
        notes = self.folder / "limits.md"
        notes.write_text("A limit is what a function approaches.", encoding="utf-8")
        page.add_files([str(notes)])
        self.assertEqual(len(self.store.project_files(project)), 1)
        self.assertIn("She reads 1 of 1 files", page.knowledge.text())
        page.start.click()
        self.assertIs(self.window.pages.currentWidget(), self.window.chat_page)
        self.assertEqual(self.store.conversation(self.window._conversation_id)["project_id"], project)
        self.assertTrue(self.window.crumb.isVisible())
        self.assertIn("Calculus exam", self.window.crumb.text())
        context = self.window._project_context()
        self.assertIn("Worked examples first.", context)
        self.assertIn("A limit is what a function approaches.", context)

    def test_materials_can_be_updated(self):
        from companion.chat import projects as knowledge
        from companion.core.paths import resolve
        project = self.make_project()
        page = self.window.project_page
        notes = self.folder / "lecture.md"
        notes.write_text("Week 1: the mean.", encoding="utf-8")
        page.add_files([str(notes)])
        item = self.store.project_files(project)[0]
        self.assertFalse(knowledge.newer_at_source(item))
        notes.write_text("Week 1: the mean. Week 2: the variance.", encoding="utf-8")
        os.utime(notes, (time.time() + 60, time.time() + 60))  # Edited later.
        item = self.store.project_files(project)[0]
        self.assertTrue(knowledge.newer_at_source(item))
        old_copy = resolve(item["path"])
        page._replace_file(item, item["source"])  # Refresh
        updated = self.store.project_files(project)
        self.assertEqual(len(updated), 1)
        self.assertFalse(knowledge.newer_at_source(updated[0]))
        self.assertFalse(old_copy.exists())  # The old version is gone, not kept alongside.
        self.window._new_chat_in_project(project)
        self.assertIn("Week 2: the variance.", self.window._project_context())
        other = self.folder / "slides.md"
        other.write_text("Slides: distributions.", encoding="utf-8")
        page._replace_file(updated[0], str(other))  # Replace with another file
        self.assertEqual(self.store.project_files(project)[0]["name"], "slides.md")

    def test_moving_a_chat_in_and_out_of_a_project(self):
        project = self.make_project()
        self.window._leave_pages()
        conversation = self.window._conversation_id
        self.window._move_conversation(conversation, project)
        self.assertEqual(self.store.conversation(conversation)["project_id"], project)
        self.window._move_conversation(conversation, "")
        self.assertEqual(self.store.conversation(conversation)["project_id"], "")
        self.window._move_conversation(conversation, "+")  # Into a new project named after the chat.
        moved = self.store.conversation(conversation)["project_id"]
        self.assertTrue(moved and self.store.project(moved))

    def test_deleting_a_project_can_keep_its_chats(self):
        project = self.make_project()
        self.window._new_chat_in_project(project)
        conversation = self.window._conversation_id
        self.window._open_project(project)
        with patch.object(QMessageBox, "exec", lambda box: setattr(box, "_choice", box.buttons()[0])), \
                patch.object(QMessageBox, "clickedButton", lambda box: box._choice):
            self.window.project_page._delete()
        self.assertIsNone(self.store.project(project))
        self.assertEqual(self.store.conversation(conversation)["project_id"], "")
        self.assertIs(self.window.pages.currentWidget(), self.window.chat_page)

    def test_conversation_tools_only_for_claude_and_allowed_servers(self):
        self.assertEqual(set(json.loads(self.window._chat_tools())["mcpServers"]), {"notes"})
        self.window.settings = replace(self.window.settings, llm_provider="openrouter")
        self.assertEqual(self.window._chat_tools(), "")
        self.window._tool_used("mcp__notes__search_notes")
        self.assertIn("Used search notes from notes", self.window.transcript.toPlainText())

    def test_servers_are_managed_in_settings(self):
        panel = self.window.tools_panel
        self.assertEqual([server.name for server in panel.servers], ["notes", "github"])
        dialog = ServerDialog(others=panel.servers)
        dialog.paste.setPlainText('{"mcpServers": {"calendar": {"command": "uvx", "args": ["calendar-mcp"]}}}')
        dialog._from_json()
        self.assertEqual(dialog.name.text(), "calendar")
        dialog._save()
        panel.servers.append(dialog.result_server)
        panel._save()
        self.assertEqual([server.name for server in mcp.load(self.folder / "mcp.json")], ["notes", "github", "calendar"])
        self.assertEqual([server.name for server in self.window.mcp_servers], ["notes", "github", "calendar"])


if __name__ == "__main__":
    unittest.main()
