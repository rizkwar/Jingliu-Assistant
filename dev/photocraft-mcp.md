# PhotoCraft MCP for avatar artwork

Use the MCP server bundled with the installed PhotoCraft application to prepare
Jingliu's editable artwork. This is an authoring tool for Codex; the companion
does not need PhotoCraft running during normal conversations.

## Connection

- Server name: `photocraft`
- Transport: local STDIO
- Executable: `C:\Program Files\PhotoCraft\photocraft-cli.exe`
- Mode: `mcp` (headless document editor)
- Read and write root: this project's `.cache/avatar-authoring/jingliu/`
- Credentials: none; this mode does not open a TCP listener

The MCP file-access roots grant access to the dedicated artwork folder, rather
than the repository root. Keep `.env`, recordings, conversations and other
private files outside that folder. The folder and the user-level Codex
configuration are excluded from this repository.

Headless editing does **not** change the document currently open in the desktop
PhotoCraft window. Save the PSD through MCP, then open that file in PhotoCraft
to inspect it. A live desktop bridge is a separate setup and is not configured
by these instructions.

## Register on this Windows installation

From PowerShell in the project root:

```powershell
$artRoot = Join-Path (Get-Location).Path '.cache/avatar-authoring/jingliu'
New-Item -ItemType Directory -Path $artRoot -Force | Out-Null
codex mcp add photocraft -- 'C:\Program Files\PhotoCraft\photocraft-cli.exe' mcp --automation-read-root $artRoot --automation-write-root $artRoot
codex mcp get photocraft --json
```

This records the absolute local artwork path in the user's Codex configuration;
do not paste that configuration into tracked files. Adjust the executable path
if PhotoCraft is installed elsewhere. The `mcp` subcommand is included with
PhotoCraft; no additional server package or API key is needed.

After registration, use **Codex Settings > MCP servers > Restart extension** in
the IDE, or restart the Codex desktop client if using that client. Confirm that
`photocraft` is connected before relying on its tools. Registration alone does
not add tools to an already running conversation.

## Authoring workflow

1. Put working artwork copies inside the permitted folder. The initial input is
   `inputs/portrait-v5.png`; the approved source portrait remains in its original
   location.
2. Use `doc_open` with a path relative to the artwork folder, then `doc_inspect`
   to inspect the dimensions and layer tree.
3. Use `command_list` to look up the installed commands and parameter schemas
   before editing with `command_run` or `command_batch`.
4. Save editable `.psd` or `.pcraft` documents with `doc_save`. Use a new filename
   for a checkpoint before substantial edits.
5. Inspect `doc_render_preview` and reopen the saved file to verify its layers.

The input portrait remains a single-layer image. The subsequent
Jingliu layer-preparation checkpoint provides
an editable master and a 23-part PSD. Rigging remains a separate step.

## Verified locally

On 2026-10-24, PhotoCraft **0.15.1** passed a real MCP STDIO check:

- Initialization and discovery of **25 tools**.
- Opening the **1254 x 1254** portrait and inspecting its document tree.
- Rendering and visually inspecting a **512 x 512** preview.
- Saving a separate PSD, reopening it, and checking dimensions and layer count.
- Rejecting a path that attempted to leave the permitted artwork folder.
- Leaving the input portrait unchanged.

The check outputs are local and ignored by Git:
`.cache/photocraft-mcp/verification.json` and
`.cache/avatar-authoring/jingliu/checks/`.

Sources: [PhotoCraft control and MCP documentation](https://github.com/storytold/photocraft/blob/main/docs/control-protocol.md),
[official OpenAI MCP configuration guide](https://learn.chatgpt.com/docs/extend/mcp).

Suggested commit: `docs: add PhotoCraft MCP authoring setup`
