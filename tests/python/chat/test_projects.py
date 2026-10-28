"""Projects: storage, the files she knows, what she is told, and how tasks and replies use them."""

import asyncio
from dataclasses import replace
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from companion.chat import projects as knowledge
from companion.chat.llm import ChatError, stream_reply
from companion.chat.prompts import reply_prompt
from companion.core import mcp
from companion.core.storage import Store
from companion.tasks.runner import ComputerTask
from tests.python.chat.test_claude_backend import SETTINGS as CLAUDE, Process, delta, result
from tests.python.tasks.test_computer_tasks import SETTINGS as TASK_SETTINGS


class ProjectStorageTests(unittest.TestCase):
    def setUp(self):
        self.store = Store(":memory:")
        self.addCleanup(self.store.close)

    def test_a_project_keeps_its_details_and_chats(self):
        project = self.store.create_project("  Calculus   exam ")
        self.assertEqual(self.store.project(project)["name"], "Calculus exam")
        self.store.update_project(project, description="Finals", instructions="Examples first.", color="amber",
                                  folder="C:/Study")
        saved = self.store.project(project)
        self.assertEqual((saved["description"], saved["instructions"], saved["color"], saved["folder"]),
                         ("Finals", "Examples first.", "amber", "C:/Study"))
        inside, outside = self.store.create_conversation("me"), self.store.create_conversation("me")
        self.store.set_conversation_project(inside, project)
        self.assertEqual([row["id"] for row in self.store.conversations("me", project=project)], [inside])
        self.assertEqual([row["id"] for row in self.store.conversations("me", project="")], [outside])
        self.assertEqual(self.store.projects()[0]["conversation_count"], 1)

    def test_bad_details_are_refused(self):
        project = self.store.create_project("Exam")
        for fields in ({"name": "  "}, {"color": "pink"}, {"instructions": "x" * 8001}, {"owner": "me"}):
            with self.assertRaises(ValueError):
                self.store.update_project(project, **fields)
        with self.assertRaises(ValueError):
            self.store.set_conversation_project(self.store.create_conversation(), "gone")

    def test_deleting_keeps_or_removes_its_chats(self):
        kept, removed = self.store.create_project("Kept"), self.store.create_project("Removed")
        first, second = self.store.create_conversation(), self.store.create_conversation()
        self.store.set_conversation_project(first, kept)
        self.store.set_conversation_project(second, removed)
        self.store.add_project_file(kept, "notes.md", "data/projects/x/notes.md", "text", 10)
        files = self.store.delete_project(kept)
        self.assertEqual([item["name"] for item in files], ["notes.md"])
        self.assertEqual(self.store.conversation(first)["project_id"], "")  # Back in Recents.
        self.store.delete_project(removed, delete_conversations=True)
        self.assertIsNone(self.store.conversation(second))
        self.assertEqual(self.store.projects(), [])


class KnowledgeTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.folder = Path(folder.name)

    def store_file(self, name, text):
        source = self.folder / name
        source.write_text(text, encoding="utf-8")
        return knowledge.store_file(source, "p1", self.folder / "projects")

    def test_files_are_copied_and_same_names_both_kept(self):
        first = self.store_file("notes.md", "Limits.")
        second = self.store_file("notes.md", "Limits.")
        self.assertEqual(first[0], "notes.md")
        self.assertNotEqual(first[1], second[1])
        self.assertEqual(first[2], "text")

    def test_context_carries_instructions_and_file_contents_within_budget(self):
        project = {"name": "Exam", "description": "Finals", "instructions": "Examples first.", "folder": "C:/Study"}
        name, path, kind, size = self.store_file("notes.md", "A limit is what a function approaches.")
        image = self.folder / "board.png"
        image.write_bytes(b"\x89PNG not really")
        files = [{"name": name, "path": path, "kind": kind}, {"name": "board.png", "path": str(image), "kind": "image"}]
        text = knowledge.context(project, files)
        self.assertIn('"Exam"', text)
        self.assertIn("Examples first.", text)
        self.assertIn("A limit is what a function approaches.", text)
        self.assertIn("not readable here (ask the user to share one in the chat if you need it): board.png", text)
        with patch.object(knowledge, "KNOWLEDGE_CHARS", 10):
            self.assertLess(len(knowledge.context(project, files[:1])), len(text))
        prompt = reply_prompt("Profile.", project=text, tools=["notes"])
        self.assertIn("Examples first.", prompt)
        self.assertIn("connected MCP servers\n(notes)", prompt)

    def test_pdfs_are_read_as_text(self):
        from pypdf import PdfWriter
        writer = PdfWriter()
        writer.add_blank_page(200, 200)
        path = self.folder / "blank.pdf"
        with path.open("wb") as output:
            writer.write(output)
        self.assertIsNone(knowledge.file_text({"name": "blank.pdf", "path": str(path), "kind": "pdf"}))  # No text: listed.


class TaskAndReplyTests(unittest.TestCase):
    def test_tasks_get_the_servers_and_start_in_the_project_folder(self):
        with tempfile.TemporaryDirectory() as folder:
            servers = [mcp.Server(name="notes", command="uvx", args=["notes"], ask=False),
                       mcp.Server(name="github", transport="http", url="https://x.test/mcp")]
            project = {"name": "Exam", "folder": folder, "instructions": "Use the past papers."}
            # Its journal goes in the temporary folder too, never in the person's real task history.
            task = ComputerTask("Make a revision sheet", [], TASK_SETTINGS, servers=servers, project=project,
                                undo_root=Path(folder) / "undo")
            try:
                arguments = task.process.arguments()
                config = json.loads((Path(task.folder.name) / "mcp.json").read_text(encoding="utf-8"))
                self.assertEqual(set(config["mcpServers"]), {"jingliu", "notes", "github"})
                allowed = arguments[arguments.index("--allowedTools") + 1:arguments.index("--append-system-prompt-file")]
                self.assertIn("mcp__notes", allowed)  # Trusted: runs without asking.
                self.assertNotIn("mcp__github", allowed)  # Asks first, through the approval hook.
                self.assertEqual(Path(task.process.workingDirectory()), Path(folder))
                prompt = (Path(task.folder.name) / "prompt.txt").read_text(encoding="utf-8")
                self.assertIn('project "Exam"', prompt)
                self.assertIn("Use the past papers.", prompt)
            finally:
                task.folder.cleanup()

    def collect(self, lines, settings):
        process, seen = Process(lines), {}

        async def fake_run(command, stdin_text=None, cwd=None):
            seen["command"] = command
            if "--mcp-config" in command:
                seen["config"] = json.loads(Path(command[command.index("--mcp-config") + 1]).read_text(encoding="utf-8"))
            return process

        async def gather():
            return [part async for part in stream_reply(None, settings, [{"role": "user", "content": "Hi"}])]

        with patch("companion.chat.claude.run", fake_run), patch("companion.chat.claude.claude_executable", lambda: "claude"):
            return asyncio.run(gather()), seen

    def test_conversation_tools_reach_claude_and_are_reported(self):
        tools = json.dumps(mcp.claude_config([mcp.Server(name="notes", command="uvx", scope="everywhere")],
                                             conversation=True))
        start = {"type": "stream_event", "event": {"type": "content_block_start",
                                                   "content_block": {"type": "tool_use", "name": "mcp__notes__search"}}}
        parts, seen = self.collect([delta("Let me look."), start, delta("Found it."), result()],
                                   replace(CLAUDE, chat_tools=tools))
        self.assertEqual(parts, ["Let me look.", {"tool": "mcp__notes__search"}, "\n\n", "Found it."])
        command = seen["command"]
        self.assertEqual(command[command.index("--allowedTools") + 1:], ["mcp__notes"])
        self.assertEqual(set(seen["config"]["mcpServers"]), {"notes"})
        self.assertEqual(command[command.index("--tools") + 1], "")  # Still no built-in tools.

    def test_other_tools_still_stop_the_reply(self):
        start = {"type": "stream_event", "event": {"type": "content_block_start",
                                                   "content_block": {"type": "tool_use", "name": "Bash"}}}
        with self.assertRaises(ChatError):
            self.collect([start, result()], CLAUDE)


if __name__ == "__main__":
    unittest.main()
