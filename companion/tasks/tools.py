"""Local MCP server for computer tasks: the approval hook and screen, mouse and keyboard tools.

Claude Code starts this over stdio for a task run. Risky steps reach `approve`, which asks
the companion window (over a loopback socket with a per-task token) and waits for the
person's answer. Plain newline-delimited JSON-RPC; no MCP SDK needed.
"""

import base64
import json
import os
import socket
import sys
import tempfile
import time
from pathlib import Path

PROTOCOLS = ("2026-07-28", "2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05")
OBJECT = {"type": "object", "additionalProperties": True}
POINT = {"x": {"type": "number", "description": "x in the latest screenshot's pixels"},
         "y": {"type": "number", "description": "y in the latest screenshot's pixels"}}
TOOLS = [
    {"name": "approve", "description": "Permission prompt for the companion app.", "inputSchema": OBJECT},
    {"name": "screenshot", "description": "See the whole screen (all monitors). Take one before clicking; "
     "coordinates for other tools are in this image's pixels.", "inputSchema": {"type": "object", "properties": {}}},
    {"name": "click", "description": "Click at a point in the latest screenshot.", "inputSchema": {
        "type": "object", "required": ["x", "y"], "properties": {**POINT,
            "button": {"type": "string", "enum": ["left", "right", "middle"]},
            "count": {"type": "integer", "description": "2 for a double-click"}}}},
    {"name": "type_text", "description": "Type text into the focused window (click it first).", "inputSchema": {
        "type": "object", "required": ["text"], "properties": {"text": {"type": "string"}}}},
    {"name": "press_keys", "description": 'Press a key or combination, e.g. "enter", "ctrl+s", "alt+tab", "win+r".',
     "inputSchema": {"type": "object", "required": ["keys"], "properties": {"keys": {"type": "string"}}}},
    {"name": "scroll", "description": "Scroll at a point: positive amount scrolls up, negative down (notches).",
     "inputSchema": {"type": "object", "required": ["x", "y", "amount"], "properties": {
         **POINT, "amount": {"type": "integer"}}}},
    {"name": "wait", "description": "Wait for something on screen to finish (0.2 to 10 seconds).",
     "inputSchema": {"type": "object", "required": ["seconds"], "properties": {"seconds": {"type": "number"}}}},
    # File operations that the person can undo afterwards; prefer them to shell commands.
    {"name": "move_path", "description": "Move or rename a file or folder (undoable). If destination is an "
     "existing folder, the item goes inside it.", "inputSchema": {"type": "object", "required": ["source", "destination"],
         "properties": {"source": {"type": "string"}, "destination": {"type": "string"}}}},
    {"name": "copy_path", "description": "Copy a file or folder (undoable).", "inputSchema": {
        "type": "object", "required": ["source", "destination"],
        "properties": {"source": {"type": "string"}, "destination": {"type": "string"}}}},
    {"name": "delete_path", "description": "Delete a file or folder (undoable: it is kept so it can be restored).",
     "inputSchema": {"type": "object", "required": ["path"], "properties": {"path": {"type": "string"}}}},
    {"name": "make_folder", "description": "Create a folder, with any missing parents (undoable).",
     "inputSchema": {"type": "object", "required": ["path"], "properties": {"path": {"type": "string"}}}},
]
FILE_TOOLS = {"move_path", "copy_path", "delete_path", "make_folder"}
state = {"factor": None}


def log(entry):
    path = os.environ.get("JINGLIU_TASK_LOG")
    if path:
        with open(path, "a", encoding="utf-8") as output:
            output.write(json.dumps(entry, ensure_ascii=False)[:4000] + "\n")


def ask_companion(arguments):
    """Wait for the person's decision in the companion window. Any failure denies."""
    automatic = os.environ.get("JINGLIU_APPROVAL_AUTO")
    if automatic in {"allow", "deny"}:  # Only for offline checks without the window.
        return automatic == "allow", "Denied by the offline check."
    port, token = os.environ.get("JINGLIU_APPROVAL_PORT"), os.environ.get("JINGLIU_APPROVAL_TOKEN")
    if not port or not token:
        return False, "No one is available to approve this step."
    try:
        with socket.create_connection(("127.0.0.1", int(port)), timeout=5) as connection:
            connection.settimeout(600)  # The person may take their time.
            connection.sendall((json.dumps({"token": token, "request": arguments}) + "\n").encode())
            reply = b""
            while not reply.endswith(b"\n"):
                chunk = connection.recv(65536)
                if not chunk:
                    break
                reply += chunk
        answer = json.loads(reply or b"{}")
        return bool(answer.get("allow")), answer.get("message") or "The person declined this step."
    except (OSError, ValueError):
        return False, "The approval window is not available, so this step was not allowed."


def text(value, error=False):
    return {"content": [{"type": "text", "text": value}], **({"isError": True} if error else {})}


def call(name, arguments):
    if name == "approve":
        allowed, message = ask_companion(arguments)
        decision = ({"behavior": "allow", "updatedInput": arguments.get("input", {})} if allowed
                    else {"behavior": "deny", "message": message})
        log({"approve": arguments, "decision": decision["behavior"]})
        return text(json.dumps(decision))
    if name in FILE_TOOLS:
        return file_operation(name, arguments)
    from . import desktop
    if name == "screenshot":
        path = Path(tempfile.gettempdir()) / f"jingliu-screen-{os.getpid()}.png"
        width, height, factor = desktop.screenshot(path)
        state["factor"] = factor
        data = base64.b64encode(path.read_bytes()).decode("ascii")
        path.unlink(missing_ok=True)
        return {"content": [{"type": "image", "data": data, "mimeType": "image/png"},
                            {"type": "text", "text": f"Screenshot {width}x{height}. Use these pixel coordinates."}]}
    if name == "wait":
        time.sleep(max(.2, min(10., float(arguments.get("seconds", 1)))))
        return text("Waited.")
    if name in {"click", "scroll"} and state["factor"] is None:
        return text("Take a screenshot first, so points match what you see.", error=True)
    if name == "click":
        desktop.click(float(arguments["x"]), float(arguments["y"]), state["factor"],
                      arguments.get("button", "left"), int(arguments.get("count", 1)))
        return text("Clicked. Take a screenshot to see the result.")
    if name == "scroll":
        desktop.scroll(float(arguments["x"]), float(arguments["y"]), state["factor"], int(arguments["amount"]))
        return text("Scrolled.")
    if name == "type_text":
        desktop.type_text(str(arguments["text"]))
        return text("Typed.")
    if name == "press_keys":
        desktop.press(str(arguments["keys"]))
        return text("Pressed.")
    return text(f"Unknown tool: {name}", error=True)


def file_operation(name, arguments):
    from .journal import Journal
    folder = os.environ.get("JINGLIU_JOURNAL")
    if not folder:
        return text("File tools are unavailable in this run.", error=True)
    journal = Journal(folder)
    if name == "move_path":
        moved = journal.move(arguments["source"], arguments["destination"])
        return text(f"Moved to {moved}.")
    if name == "copy_path":
        copied = journal.copy(arguments["source"], arguments["destination"])
        return text(f"Copied to {copied}.")
    if name == "delete_path":
        journal.delete(arguments["path"])
        return text("Deleted (kept for undo).")
    made = journal.make_folder(arguments["path"])
    return text(f"Folder ready: {made}.")


def main():
    from .desktop import dpi_aware
    dpi_aware()
    for line in sys.stdin:
        try:
            message = json.loads(line)
        except ValueError:
            continue
        method, ident = message.get("method"), message.get("id")
        if ident is None:
            continue  # Notifications, such as notifications/initialized, need no reply.
        if method == "initialize":
            asked = message.get("params", {}).get("protocolVersion")
            result = {"protocolVersion": asked if asked in PROTOCOLS else PROTOCOLS[2],
                      "capabilities": {"tools": {}}, "serverInfo": {"name": "jingliu", "version": "1.0"}}
        elif method == "tools/list":
            result = {"tools": TOOLS}
        elif method == "tools/call":
            params = message.get("params", {})
            try:
                result = call(params.get("name"), params.get("arguments") or {})
            except Exception as exc:  # A failed action is reported to the agent, never fatal.
                result = text(f"That did not work: {type(exc).__name__}: {str(exc)[:200]}", error=True)
        elif method == "ping":
            result = {}
        else:
            sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": ident,
                                         "error": {"code": -32601, "message": "Method not found"}}) + "\n")
            sys.stdout.flush()
            continue
        sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": ident, "result": result}) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
