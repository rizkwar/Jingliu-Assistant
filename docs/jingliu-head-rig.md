# Jingliu: standalone head-rig checkpoint

The PhotoCraft artwork now has a saved Inochi Creator **0.8.6** rig with 23
drawable meshes and three controls: **Head XY - small turn**, **Head tilt**, and
**Hair sway - manual test**. This checkpoint remains separate from the avatar
running in the assistant.

The subsequent [eye-rig checkpoint](jingliu-eye-rig.md) adds separate iris/lid
parts, blinking and gaze. Use that guide for the latest standalone rig; this
page records the earlier head-and-hair checkpoint.

## Review and test

All generated artwork, rig files and inspection figures are local and ignored
by Git under `.cache/avatar-authoring/jingliu/`:

| Relative file | Purpose |
| --- | --- |
| `authoring/jingliu-v5-parts-v3.psd` | Updated editable 23-layer artwork |
| `authoring/torso-clean-v3.png` | Torso with stray upper outlines removed in PhotoCraft |
| `authoring/jingliu-v5-head-test-v3.inx` | Current standalone rig to open in Creator |
| `review-rig-v2/poses-final.png` | Twelve rendered poses, including the corners and combined controls |
| `review-rig-v2/before.png` | Earlier six-pose inspection sheet |
| `review-rig-v2/verification.json` | Checkpoint evidence and remaining limitations |

The `v3` suffix is the rig/artwork iteration. The approved source portrait is
still Jingliu **v5**. The intermediate v2 cleanup was superseded because it cut
too far into a shoulder.

In Creator, open the current INX file using **File > Open**. Enable
**View > Parameters** if needed. Drag the point in the Head XY control to test
small left/right and up/down poses, then try Head tilt and Hair sway. The toolbar
**Reset parameters** button returns to rest. Changing a control does not create
an automatic idle animation or connect it to conversation state.

## What changed

The first test revealed stationary blue hair outlines in the torso texture and
gaps between adjoining hair cuts. PhotoCraft MCP was used to remove the stray
upper outlines while keeping the collar and shoulders. The cleaned PSD was
saved separately and reopened with all 23 pixel layers and both hidden closed-eye
alternatives intact.

The mesh authoring fields now give adjoining hair pieces a shared spatial
deformation. This reduces gaps caused by inconsistent offsets at cut edges.
Lower hair blends toward the stationary bust, and manual sway bends the hair
with a continuous field that varies across the portrait. Crown roots and the
bottom crop stay fixed during sway. Facial features retain separate keyforms,
including asymmetric eye widths and different nose/jaw travel during turns.

Most inspection and editing used the [local MCP server](avatar-rig-mcp.md).
Two tools were added: pose-sheet rendering from saved meshes/keyforms, and
importing a PhotoCraft PNG into a part's texture. The renderer decodes Inochi's
premultiplied TGA/PNG textures and renders actual mesh triangles. It is a limited
software inspection tool, not the Inochi runtime.

## Verification

- Rendered and visually reviewed 12 poses covering both directions, vertical
  corners, tilt, hair sway and combined extremes.
- Loaded the saved v3 file in the official Creator. Dragged from the up-left
  corner to down-right, tested down-right with hair sway, then reset to rest.
- Tested 225 combinations of head XY, tilt and sway for each mesh: **3,017,700
  triangle instances**, with **zero inverted triangles** in those samples.
- The original PSD import hash is unchanged. Exactly the torso texture slot
  changed; all 22 other embedded texture slots stayed byte-identical.
- Eleven focused Python tests and three JavaScript tests passed. The updated
  real MCP integration check passed 13 calls across 10 discovered tools.

```powershell
& .venv/Scripts/python.exe -m unittest tests.test_avatar_rig_data tests.test_inochi_preview -v
node tests/inochi-keyforms.test.mjs
& .cache/tooling/avatar-rig-mcp/venv/Scripts/python.exe scripts/check_avatar_rig_mcp.py
```

These checks establish a working small-turn experiment. They do not establish
professional-quality wide turns or production readiness. The eyes remain whole
drawings with hidden closed alternatives; separate iris and eyelid authoring is
next. Fine cut edges and shoulder hair remnants still need refinement. Hair
sway is manual, with no physics driver, and this rig has no speech connection.

Suggested commit: `feat: refine Jingliu head rig and add MCP pose previews`
