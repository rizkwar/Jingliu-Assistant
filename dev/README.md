# Development tools

Tools used while building the avatar. The app itself does not need any of them. Run them from the
project folder (the `.cmd` previews do that themselves). Some need Node.js; the MCP servers have
their own requirements in `requirements-avatar-mcp.txt`.

| Tools | What they are for |
| --- | --- |
| **Preview Jingliu Avatar.cmd**, `preview_mesh_avatar.mjs`, `avatar-preview/` | The mesh portrait in a browser, outside the app. |
| **Preview Jingliu Rig.cmd**, `preview_inochi_avatar.mjs`, `inochi-viewer/`, `prepare_inochi_viewer.py` | Interactive viewer for the layered Inochi rig: head, eyes, mouth, hair physics. |
| **Preview Head Motion.cmd**, `preview_head_motion.mjs`, `head-motion-study/` | Head-turn and idle-attention motion study. |
| `build_layered_jingliu.py`, `build_inochi_*.py`, `build_inochi_jingliu.mjs`, `jingliu_inochi_keyforms.mjs`, `inochi_idle_motion.py`, `avatar_rig_data.py` | Build the layered (AI portrait) rig and its eye, mouth and idle-motion parts. |
| `render_inochi_rig.py`, `render_inochi_motion.py` | Render pose sheets and motion clips of a rig. |
| `avatar_rig_mcp.py`, `call_avatar_rig_mcp.py`, `check_avatar_rig_mcp.py` | A local MCP server for inspecting and editing saved rigs ([guide](avatar-rig-mcp.md)). |
| [photocraft-mcp.md](photocraft-mcp.md) | Editing avatar artwork with PhotoCraft's MCP server. |
| `check_live2d.py`, `check_live2d_physics.js`, `check_layered_avatar.py`, `check_avatar_motion.py`, `check_avatar_polish.py`, `check_inochi_viewer.*` | Checks that drive the real avatar and capture screenshots. |
| `measure_avatar*.py`, `windows_process_metrics.py` | Frame rate, CPU and memory measurements. |
| `patch_avatar_runtime.py` | Re-applies the stability patch to the vendored avatar runtime. |

Prepared artwork and rig files stay local and Git-ignored, under `.cache/` and `data/`.
