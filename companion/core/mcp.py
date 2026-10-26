"""MCP servers the person connects: saved settings, importing them from Claude, the configuration Claude Code
receives, and a connection test that lists a server's tools."""

import asyncio
from dataclasses import asdict, dataclass, field
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import tempfile

from .config import PROJECT_ROOT

CONFIG = PROJECT_ROOT / "data" / "mcp_servers.json"
RESERVED = {"jingliu"}  # The app's own screen and file tools during computer tasks.
NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,39}$")
SCOPES = ("tasks", "everywhere")
PROTOCOL = "2025-06-18"


@dataclass
class Server:
    name: str
    transport: str = "stdio"          # "stdio" (a command) or "http" (a URL)
    command: str = ""
    args: list = field(default_factory=list)
    env: dict = field(default_factory=dict)
    url: str = ""
    headers: dict = field(default_factory=dict)
    enabled: bool = True
    scope: str = "tasks"              # "tasks", or "everywhere": conversations too
    ask: bool = True                  # In tasks: ask before each of its tools

    def summary(self):
        if self.transport == "http":
            return self.url
        return " ".join([self.command, *map(str, self.args)]).strip()

    def entry(self):
        """This server as Claude Code expects it in --mcp-config."""
        if self.transport == "http":
            return {"type": "http", "url": self.url, **({"headers": dict(self.headers)} if self.headers else {})}
        command, args = self.command, list(map(str, self.args))
        resolved = shutil.which(command) or ""
        if os.name == "nt" and resolved.lower().endswith((".cmd", ".bat")):
            command, args = "cmd", ["/c", command, *args]  # npx and friends are batch files on Windows.
        return {"command": command, "args": args, **({"env": dict(self.env)} if self.env else {})}


def validate(server, others=()):
    if not NAME.match(server.name or ""):
        raise ValueError("A server name uses letters, numbers, - and _ (up to 40), starting with a letter or number.")
    if server.name.lower() in RESERVED:
        raise ValueError(f"“{server.name}” is used by the app itself. Choose another name.")
    if any(other.name.lower() == server.name.lower() for other in others if other is not server):
        raise ValueError(f"There is already a server called “{server.name}”.")
    if server.transport == "http":
        if not re.match(r"^https?://\S+$", server.url or ""):
            raise ValueError("Enter the server's address, starting with http:// or https://.")
    elif server.transport == "stdio":
        if not (server.command or "").strip():
            raise ValueError("Enter the command that starts the server, such as npx.")
    else:
        raise ValueError("A server is reached by a command or a URL.")
    if server.scope not in SCOPES:
        raise ValueError("Choose where the server is used.")
    if not all(isinstance(value, str) for value in (*server.env.values(), *server.headers.values(), *server.args)):
        raise ValueError("Arguments, variables and headers must be text.")
    return server


def load(path=CONFIG):
    path = Path(path)
    if not path.exists():
        return []
    try:
        document = json.loads(path.read_text(encoding="utf-8-sig"))
        servers = [Server(**{key: value for key, value in item.items() if key in Server.__dataclass_fields__})
                   for item in document.get("servers", [])]
    except (ValueError, TypeError, AttributeError) as exc:
        raise ValueError("The saved MCP servers could not be read (data/mcp_servers.json).") from exc
    for server in servers:
        validate(server, servers)
    return servers


def save(servers, path=CONFIG):
    for server in servers:
        validate(server, servers)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, suffix=".tmp", delete=False) as output:
        json.dump({"version": 1, "servers": [asdict(server) for server in servers]}, output, indent=2)
    os.replace(output.name, path)


def from_entry(name, entry):
    """A server from the usual JSON form ({"command", "args", "env"} or {"type": "http", "url", "headers"})."""
    if not isinstance(entry, dict):
        raise ValueError(f"“{name}” is not a server description.")
    if entry.get("url") or entry.get("type") in {"http", "sse", "streamable-http"}:
        return Server(name=name, transport="http", url=str(entry.get("url", "")),
                      headers={str(k): str(v) for k, v in (entry.get("headers") or {}).items()})
    args = entry.get("args") or []
    if isinstance(args, str):
        args = shlex.split(args, posix=False)
    return Server(name=name, command=str(entry.get("command", "")), args=[str(a) for a in args],
                  env={str(k): str(v) for k, v in (entry.get("env") or {}).items()})


def parse(text):
    """Servers from pasted JSON: {"mcpServers": {...}}, {"name": {...}}, or one {"command": ...}."""
    try:
        document = json.loads(text)
    except ValueError as exc:
        raise ValueError("That isn't valid JSON. Paste the server's configuration snippet.") from exc
    if not isinstance(document, dict):
        raise ValueError("Paste a JSON object describing the server.")
    if "mcpServers" in document:
        document = document["mcpServers"]
    elif "servers" in document and isinstance(document["servers"], dict):
        document = document["servers"]  # VS Code's form.
    if {"command", "url"} & document.keys():
        return [from_entry("server", document)]
    return [from_entry(str(name), entry) for name, entry in document.items()]


def import_candidates():
    """Servers already set up for Claude Code or Claude Desktop on this computer: (source, server) pairs."""
    found = []
    home = Path.home()
    sources = [("Claude Code", home / ".claude.json")]
    if os.environ.get("APPDATA"):
        sources.append(("Claude Desktop", Path(os.environ["APPDATA"]) / "Claude" / "claude_desktop_config.json"))
    for label, path in sources:
        try:
            document = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError):
            continue
        groups = [document.get("mcpServers") or {}]
        groups += [(project or {}).get("mcpServers") or {} for project in (document.get("projects") or {}).values()]
        for group in groups:
            for name, entry in group.items():
                try:
                    found.append((label, from_entry(str(name), entry)))
                except ValueError:
                    continue
    unique = {}
    for label, server in found:
        unique.setdefault(server.name.lower(), (label, server))
    return list(unique.values())


def claude_config(servers, conversation=False):
    """--mcp-config contents: enabled servers (only those allowed in conversation, when `conversation`)."""
    chosen = [s for s in servers if s.enabled and (not conversation or s.scope == "everywhere")]
    return {"mcpServers": {server.name: server.entry() for server in chosen}}


def trusted_tools(servers):
    """Servers whose tools run in tasks without asking: allowed as whole servers."""
    return [f"mcp__{server.name}" for server in servers if server.enabled and not server.ask]


# Connection test -------------------------------------------------------------------------------

def _request(identifier, method, params=None):
    return {"jsonrpc": "2.0", "id": identifier, "method": method, **({"params": params} if params is not None else {})}


INITIALIZE = {"protocolVersion": PROTOCOL, "capabilities": {}, "clientInfo": {"name": "jingliu-companion", "version": "1.0"}}


async def list_tools(server, timeout=30):
    """[(tool name, description)] from the server, or ValueError with a reason the person can act on."""
    try:
        async with asyncio.timeout(timeout):
            return await (_http_tools(server) if server.transport == "http" else _stdio_tools(server))
    except TimeoutError:
        raise ValueError("The server did not answer within 30 seconds.") from None


def _tools(result):
    return [(str(tool.get("name", "")), str(tool.get("description") or "").strip().split("\n")[0][:200])
            for tool in result.get("tools", []) if isinstance(tool, dict)]


async def _stdio_tools(server):
    entry = server.entry()
    executable = shutil.which(entry["command"])
    if not executable:
        raise ValueError(f"“{server.command}” was not found on this computer. Is it installed?")
    environment = {**os.environ, **server.env}
    try:
        process = await asyncio.create_subprocess_exec(
            executable, *entry["args"], stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL, env=environment, limit=2**22,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    except OSError as exc:
        raise ValueError(f"The server could not be started: {exc.strerror or exc}.") from None

    async def send(message):
        process.stdin.write((json.dumps(message) + "\n").encode("utf-8"))
        await process.stdin.drain()

    async def answer(identifier):
        while True:
            line = await process.stdout.readline()
            if not line:
                raise ValueError("The server stopped before answering. Check its command and arguments.")
            try:
                message = json.loads(line)
            except ValueError:
                continue  # Servers may log to stdout before speaking JSON-RPC.
            if message.get("id") == identifier:
                if "error" in message:
                    raise ValueError("The server reported an error: " + str((message["error"] or {}).get("message", "")))
                return message.get("result") or {}

    try:
        await send(_request(1, "initialize", INITIALIZE))
        await answer(1)
        await send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        tools, cursor, identifier = [], None, 2
        while True:
            await send(_request(identifier, "tools/list", {"cursor": cursor} if cursor else {}))
            result = await answer(identifier)
            tools += _tools(result)
            cursor, identifier = result.get("nextCursor"), identifier + 1
            if not cursor or identifier > 12:
                return tools
    finally:
        if process.returncode is None:
            process.kill()
            await process.wait()


async def _http_tools(server):
    import httpx
    headers = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json",
               "MCP-Protocol-Version": PROTOCOL, **server.headers}

    def result_of(response, identifier):
        if response.status_code in (401, 403):
            raise ValueError("The server refused access. Check the authorization header or sign-in it needs.")
        if response.status_code >= 400:
            raise ValueError(f"The server answered with HTTP {response.status_code}.")
        messages = []
        if "text/event-stream" in response.headers.get("content-type", ""):
            for line in response.text.splitlines():
                if line.startswith("data:"):
                    try:
                        messages.append(json.loads(line[5:].strip()))
                    except ValueError:
                        continue
        else:
            messages.append(response.json())
        for message in messages:
            if isinstance(message, dict) and message.get("id") == identifier:
                if "error" in message:
                    raise ValueError("The server reported an error: " + str((message["error"] or {}).get("message", "")))
                return message.get("result") or {}
        raise ValueError("The server's answer was not understood as MCP.")

    try:
        async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
            response = await client.post(server.url, headers=headers, json=_request(1, "initialize", INITIALIZE))
            result_of(response, 1)
            if response.headers.get("mcp-session-id"):
                headers["Mcp-Session-Id"] = response.headers["mcp-session-id"]
            await client.post(server.url, headers=headers, json={"jsonrpc": "2.0", "method": "notifications/initialized"})
            tools, cursor, identifier = [], None, 2
            while True:
                response = await client.post(server.url, headers=headers,
                                             json=_request(identifier, "tools/list", {"cursor": cursor} if cursor else {}))
                result = result_of(response, identifier)
                tools += _tools(result)
                cursor, identifier = result.get("nextCursor"), identifier + 1
                if not cursor or identifier > 12:
                    return tools
    except httpx.HTTPError as exc:
        raise ValueError(f"Could not reach the server: {type(exc).__name__}.") from None
