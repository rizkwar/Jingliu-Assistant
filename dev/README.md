# Development tools

Tools used while building the avatar. The app itself does not need any of them. Run them from the
project folder (the `.cmd` previews do that themselves). Some need Node.js; the MCP servers have
their own requirements in `rig/requirements-avatar-mcp.txt`. Tools import their neighbours in the
same folder, so keep each group together.

## rig/: the layered (AI portrait) rig

| Tools | What they are for |
| --- | --- |
| `build_layered_jingliu.py`, `build_inochi_*.py`, `build_inochi_jingliu.mjs`, `jingliu_inochi_keyforms.mjs`, `inochi_idle_motion.py`, `avatar_rig_data.py` | Build the rig and its eye, mouth and idle-motion parts. |
| `render_inochi_rig.py`, `render_inochi_motion.py` | Render pose sheets and motion clips. |
| **Preview Jingliu Rig.cmd**, `preview_inochi_avatar.mjs`, `inochi-viewer/`, `prepare_inochi_viewer.py`, `check_inochi_viewer.*` | Interactive rig viewer (head, eyes, mouth, hair physics) and its check. |
| `avatar_rig_mcp.py`, `call_avatar_rig_mcp.py`, `check_avatar_rig_mcp.py` | A local MCP server for inspecting and editing saved rigs ([guide](rig/avatar-rig-mcp.md)). |
| [photocraft-mcp.md](rig/photocraft-mcp.md) | Editing avatar artwork with PhotoCraft's MCP server. |

## qa/: checks and measurements on the real avatar

| Tools | What they are for |
| --- | --- |
| `check_live2d.py`, `check_live2d_physics.js`, `check_layered_avatar.py`, `check_avatar_motion.py`, `check_avatar_polish.py` | Drive the real avatar and capture screenshots. |
| `measure_avatar*.py`, `windows_process_metrics.py` | Frame rate, CPU and memory measurements. |

## previews/: the avatar outside the app

| Tools | What they are for |
| --- | --- |
| **Preview Jingliu Avatar.cmd**, `preview_mesh_avatar.mjs`, `avatar-preview/` | The mesh portrait in a browser. |
| **Preview Head Motion.cmd**, `preview_head_motion.mjs`, `head-motion-study/` | Head-turn and idle-attention motion study. |

`patch_avatar_runtime.py` re-applies the stability patch to the vendored avatar runtime in
`companion/avatar/web/vendor/`.

Prepared artwork and rig files stay local and Git-ignored, under `.cache/` and `data/`.
