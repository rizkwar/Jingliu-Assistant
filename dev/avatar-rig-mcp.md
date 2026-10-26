# Local MCP for saved avatar rigs

`avatar-rig` is a small project-owned MCP server for authoring **saved Inochi
0.8 INX/INP files**. It complements PhotoCraft's artwork MCP. It does not control
the Inochi Creator desktop window or take screenshots. It can now render pose
contact sheets with a limited software inspection renderer.

Routine work uses concise part/parameter summaries and explicit mesh edits.
Visual review remains necessary to judge likeness, overlaps and motion. This
checkpoint makes no measured claim about token savings or animation quality.

## Tools

| Tool | Purpose |
| --- | --- |
| `rig_status` | Check supported capabilities and Node availability |
| `rig_list_files` | List saved rigs in the permitted folder |
| `rig_inspect` | Inspect part IDs, mesh counts, parameter ranges and defaults |
| `rig_validate` | Validate the container, references, meshes and saved keyforms |
| `rig_build_jingliu` | Generate the small head/tilt/hair test from the 23-part PSD import |
| `rig_build_jingliu_eyes` | Add separate iris/lid parts, clipping masks, blinks and gaze from exported PhotoCraft PNGs |
| `rig_build_jingliu_mouth` | Add separate lips, cavity, teeth and tongue, mouth opening/form and subtle jaw keyforms |
| `rig_add_idle_motion` | Add native blink/head clips and a head-driven hair pendulum to the mouth checkpoint |
| `rig_render_motion_preview` | Export a bounded MP4 inspection of saved tracks and configured pendulum data |
| `rig_get_keyform` | Read up to 64 rest vertices and deformation offsets |
| `rig_edit_keyform` | Replace offsets for up to 128 vertices in one keyform |
| `rig_set_defaults` | Save a separate pose checkpoint to view in Creator |
| `rig_render_preview` | Render up to 12 poses to a new PNG; optional artwork region gives close-up inspections |
| `rig_replace_texture` | Import one full-canvas PNG edited in PhotoCraft into an unshared part texture |

All paths are relative to the configured authoring root. Only `.inx` and `.inp`
files are accepted for rig operations; preview and texture tools also accept
PNG paths inside that root. The eye builder accepts a JSON manifest mapping
`L`/`R` to `sclera aperture`, `iris`, `upper lid`, `lower lid` and `closed alternate`
PNG paths, all scoped to the same root. The mouth builder takes the 29-part eye
checkpoint and a manifest of `cavity`, `tongue`, `teeth`, `lower lip` and
`upper lip` PNG paths. Every rig write requires a new output filename. Existing
files cannot be overwritten. Embedded textures and vendor extension bytes are
preserved when editing offsets or defaults. The fixed rig builder also retains
the original texture section.

Validation checks saved keyforms for collapsed or inverted triangles. It does
not decode texture images or establish that combined poses, hair roots, shoulder
underpainting, alpha edges or animation look correct. The builder separately
samples combined head/tilt/hair deformation for triangle inversion. The hair
control is currently a manual test parameter, not a physics simulation.

Previews use the project Python environment with PySide6, while the MCP server
itself uses its separate tooling environment. The renderer supports flat parts,
Normal blending, premultiplied PNG/TGA textures, linear additive deformation
bindings, multiplicative part opacity and a single positive clipping mask per
part. Mask thresholds use the source's alpha, independent of its visibility and
opacity, matching Inochi 0.8's stencil shader. Unsupported mask combinations,
composites, drivers, tinting and transforms fail
with an error. Its images are inspection renders, not screenshots of Inochi.
The separate motion preview evaluates the project's global `Pendulum` /
`AngleLength` driver and Linear/Bezier animation lanes, then renders the resulting
poses. It requires an existing local FFmpeg executable. Other physics types are
not simulated. It accepts 2..12 seconds, 12..60 fps and even sizes of 256..640px.

## Install separately from the assistant

Run from the repository root in PowerShell:

```powershell
python -m venv .cache/tooling/avatar-rig-mcp/venv
& .cache/tooling/avatar-rig-mcp/venv/Scripts/python.exe -m pip install -r dev/requirements-avatar-mcp.txt
$rigPython = (Resolve-Path '.cache/tooling/avatar-rig-mcp/venv/Scripts/python.exe').Path
$rigServer = (Resolve-Path 'dev/avatar_rig_mcp.py').Path
$rigRoot = (Resolve-Path '.cache/avatar-authoring/jingliu').Path
$rigNode = (Get-Command node).Source
codex mcp add avatar-rig -- $rigPython $rigServer --root $rigRoot --node $rigNode
codex mcp get avatar-rig --json
```

The SDK and its dependencies live in an isolated, ignored tooling environment.
The companion's requirements and runtime are unchanged. The server needs no API
key, login or network listener; it communicates over local STDIO. Do not put
private recordings, credentials, chats or memories inside its artwork root.

After registration, restart the Codex IDE extension through its MCP settings,
then confirm that `avatar-rig` is connected. Registering a server does not prove
that an existing conversation has loaded its tools. See the
[official OpenAI MCP configuration guide](https://learn.chatgpt.com/docs/extend/mcp?surface=cli).

## Working files

These remain under `.cache/avatar-authoring/jingliu/` and out of Git:

- `authoring/jingliu-v5-parts-v1.psd`: prepared 23-part artwork.
- `authoring/jingliu-v5-import-v1.inx`: original import saved by Creator 0.8.6.
- `authoring/jingliu-v5-head-test-v1.inx`: exploratory mesh rig with head XY,
  tilt and manual hair sway.
- `authoring/jingliu-v5-head-test-v3.inx`: revised hair joins and cleaned torso;
  see the head-rig checkpoint.
- `authoring/jingliu-v5-eyes-test-v4d.inx`: separated eyes, blink and gaze;
  see the eye-rig checkpoint.
- `authoring/jingliu-v5-mouth-test-v1.inx`: layered mouth and speaking controls;
  see the mouth-rig checkpoint.
- `authoring/jingliu-v5-idle-test-v2.inx`: native blink/head clips and hair physics;
  see the idle-motion checkpoint.
- `mcp-checks/`: generated test copies and MCP verification reports.

Use the names returned by `rig_list_files`. Inspect a rig before choosing node
UUIDs or parameter/keyform indices. Offsets are in node-local pixels relative
to the rest mesh. After an edit, inspect a rendered pose before accepting it.
Open a saved pose checkpoint in Creator to view its parameter defaults.

The first head-test file exposed hair-root and shoulder seams. The revised file
has now been opened in Creator and checked at opposite head-turn corners and
with manual hair sway. The later eye checkpoint was also checked in Creator.
Automatic physics, speech and assistant integration remain separate work.

## Verification on 2026-10-24

At initial setup, seven file-authoring tests passed. A real MCP STDIO client discovered
all eight tools and completed eleven calls, including generating a rig, reading
and editing an eye keyform, saving a pose and validating the saved result.
Negative calls rejected an escaping path, an overwrite and an invalid vertex.
The source rig hash and the embedded artwork bytes were unchanged.

After adding preview and texture tools, the updated check discovered **10 tools**
and passed **13 MCP calls**. It also rendered a two-pose sheet and confirmed that
replacing the torso changed exactly one embedded texture slot. The original
file and all 22 other texture slots stayed unchanged. Four additional Python
tests cover TGA orientation/alpha, pose interpolation and triangle rendering.

The eye checkpoint expands this to **11 tools and 17 MCP calls**. It generates
29 parts with six controls, validates masks, renders a blink/gaze close-up and
confirms the original 23 embedded texture slots survive the eye build unchanged.
Focused tests also cover scalar opacity, stencil clipping and non-collapsing
lid keyforms.

The mouth checkpoint expands the check to **12 tools and 25 MCP calls**. It
builds 34 parts with eight controls and verifies that closed-mouth rest renders
are byte-identical before/after the upgrade, even if the form slider stays wide.
It also confirms all input texture slots and original parts/bindings are retained.

```powershell
& .venv/Scripts/python.exe -m unittest tests.test_avatar_rig_data -v
& .cache/tooling/avatar-rig-mcp/venv/Scripts/python.exe dev/check_avatar_rig_mcp.py
```

The second check requires the local PSD-import checkpoint and Node.js. It
creates new test copies and prints the relative verification-report path.
It now also requires `authoring/torso-clean-v3.png` from the revised artwork
checkpoint and the project environment with PySide6.
The eye checks additionally require the local `authoring/eye-parts-v4b.json`
manifest and its exported PhotoCraft PNGs. These private authoring assets are
not bundled in the repository.
Mouth checks require `authoring/mouth-parts-v1.json` and its five PhotoCraft PNGs.

The idle-motion check now discovers **14 tools** and completes **33 calls**. It
adds the driver and three clips, verifies preservation of the input artwork and
bindings, encodes a short MP4 and rejects bad paths, overwrites, unknown clips
and excessive export frame rates. Animation validation checks references, axes,
key ordering, ranges and interpolation names. Physics validation checks target
references, native enum spellings and finite constants.

If an existing conversation has not reloaded its native tool catalogue, the
same server can be called through the real STDIO client helper:

```powershell
'[{"tool":"rig_status","arguments":{}}]' | & .cache/tooling/avatar-rig-mcp/venv/Scripts/python.exe dev/call_avatar_rig_mcp.py
```

This performs MCP initialization, discovery and tool calls; it does not dispatch
directly to server functions or automate desktop input.

The [community live-control MCP](https://github.com/ozekimasaki/inochi-creator-mcp)
is a different project: it requires a patched editor build and excludes mesh
vertex editing and detailed parameter bindings. It is not installed by this
setup. The file format and binding layout here were checked against the
[Inochi2D 0.8.6 source](https://github.com/Inochi2D/inochi2d/tree/v0.8.6).

Suggested commit: `feat: add local MCP tools for avatar rigging`
