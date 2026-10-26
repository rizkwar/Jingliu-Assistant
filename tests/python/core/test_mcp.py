"""MCP servers: what can be saved and imported, what Claude Code receives, and the connection test."""

import asyncio
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from companion.core import mcp

FAKE_SERVER = r'''
import json, sys
print("starting up (servers may log before speaking JSON-RPC)", flush=True)
for line in sys.stdin:
    message = json.loads(line)
    if message.get("method") == "initialize":
        result = {"protocolVersion": "2025-06-18", "capabilities": {"tools": {}}, "serverInfo": {"name": "fake"}}
    elif message.get("method") == "tools/list":
        if message.get("params", {}).get("cursor"):
            result = {"tools": [{"name": "add_note", "description": "Add a note.\nMore detail."}]}
        else:
            result = {"tools": [{"name": "search_notes", "description": "Search notes."}], "nextCursor": "2"}
    else:
        continue
    print(json.dumps({"jsonrpc": "2.0", "id": message["id"], "result": result}), flush=True)
'''


class ConfigTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.folder = Path(folder.name)

    def test_pasted_json_in_every_common_form(self):
        claude = mcp.parse('{"mcpServers": {"notes": {"command": "npx", "args": ["-y", "notes-mcp"], "env": {"K": "v"}}}}')
        self.assertEqual((claude[0].name, claude[0].command, claude[0].args, claude[0].env),
                         ("notes", "npx", ["-y", "notes-mcp"], {"K": "v"}))
        vscode = mcp.parse('{"servers": {"web": {"type": "http", "url": "https://x.test/mcp", "headers": {"A": "b"}}}}')
        self.assertEqual((vscode[0].transport, vscode[0].url, vscode[0].headers), ("http", "https://x.test/mcp", {"A": "b"}))
        single = mcp.parse('{"command": "uvx", "args": "calendar-mcp --read-only"}')
        self.assertEqual((single[0].name, single[0].args), ("server", ["calendar-mcp", "--read-only"]))
        with self.assertRaises(ValueError):
            mcp.parse("not json")

    def test_names_and_fields_are_checked(self):
        mcp.validate(mcp.Server(name="notes", command="npx"))
        for server in (mcp.Server(name="has space", command="npx"), mcp.Server(name="jingliu", command="npx"),
                       mcp.Server(name="web", transport="http", url="ftp://x"), mcp.Server(name="empty", command=" "),
                       mcp.Server(name="where", command="npx", scope="sometimes")):
            with self.assertRaises(ValueError):
                mcp.validate(server)
        with self.assertRaises(ValueError):
            mcp.validate(mcp.Server(name="Notes", command="a"), [mcp.Server(name="notes", command="b")])

    def test_saved_and_loaded_unchanged(self):
        servers = [mcp.Server(name="notes", command="npx", args=["-y", "x"], scope="everywhere", ask=False),
                   mcp.Server(name="web", transport="http", url="https://x.test/mcp", enabled=False)]
        mcp.save(servers, self.folder / "servers.json")
        self.assertEqual(mcp.load(self.folder / "servers.json"), servers)
        self.assertEqual(mcp.load(self.folder / "missing.json"), [])
        (self.folder / "broken.json").write_text("{", encoding="utf-8")
        with self.assertRaises(ValueError):
            mcp.load(self.folder / "broken.json")

    def test_what_claude_code_receives(self):
        servers = [mcp.Server(name="notes", command="uvx", args=["notes"], scope="everywhere", ask=False),
                   mcp.Server(name="github", transport="http", url="https://x.test/mcp", headers={"Authorization": "t"}),
                   mcp.Server(name="off", command="uvx", enabled=False, scope="everywhere")]
        tasks = mcp.claude_config(servers)["mcpServers"]
        self.assertEqual(set(tasks), {"notes", "github"})
        self.assertEqual(tasks["github"], {"type": "http", "url": "https://x.test/mcp", "headers": {"Authorization": "t"}})
        self.assertEqual(set(mcp.claude_config(servers, conversation=True)["mcpServers"]), {"notes"})
        self.assertEqual(mcp.trusted_tools(servers), ["mcp__notes"])

    @unittest.skipUnless(os.name == "nt", "Windows batch launchers")
    def test_batch_launchers_run_through_cmd_on_windows(self):
        with patch("companion.core.mcp.shutil.which", return_value=r"C:\nodejs\npx.cmd"):
            entry = mcp.Server(name="notes", command="npx", args=["-y", "notes"]).entry()
        self.assertEqual(entry, {"command": "cmd", "args": ["/c", "npx", "-y", "notes"]})

    def test_servers_set_up_for_claude_can_be_imported(self):
        (self.folder / ".claude.json").write_text(json.dumps({
            "mcpServers": {"notes": {"command": "npx", "args": ["notes"]}},
            "projects": {"C:/work": {"mcpServers": {"db": {"type": "http", "url": "https://db.test/mcp"}}}}}))
        desktop = self.folder / "Claude"
        desktop.mkdir()
        (desktop / "claude_desktop_config.json").write_text(json.dumps({"mcpServers": {"notes": {"command": "other"},
                                                                                       "calendar": {"command": "cal"}}}))
        with patch("companion.core.mcp.Path.home", return_value=self.folder), \
                patch.dict(os.environ, {"APPDATA": str(self.folder)}):
            found = {server.name: (label, server) for label, server in mcp.import_candidates()}
        self.assertEqual(set(found), {"notes", "db", "calendar"})
        self.assertEqual(found["notes"], ("Claude Code", mcp.Server(name="notes", command="npx", args=["notes"])))
        self.assertEqual(found["calendar"][0], "Claude Desktop")


class ConnectionTests(unittest.TestCase):
    def test_a_command_server_lists_its_tools_across_pages(self):
        with tempfile.TemporaryDirectory() as folder:
            script = Path(folder) / "server.py"
            script.write_text(FAKE_SERVER, encoding="utf-8")
            server = mcp.Server(name="fake", command=sys.executable, args=["-u", str(script)])
            tools = asyncio.run(mcp.list_tools(server))
        self.assertEqual(tools, [("search_notes", "Search notes."), ("add_note", "Add a note.")])

    def test_a_missing_command_is_explained(self):
        server = mcp.Server(name="fake", command="surely-not-installed-mcp-9271")
        with self.assertRaisesRegex(ValueError, "was not found"):
            asyncio.run(mcp.list_tools(server))

    def test_a_server_that_exits_is_explained(self):
        server = mcp.Server(name="fake", command=sys.executable, args=["-c", "print('bye')"])
        with self.assertRaisesRegex(ValueError, "stopped before answering"):
            asyncio.run(mcp.list_tools(server))


if __name__ == "__main__":
    unittest.main()
