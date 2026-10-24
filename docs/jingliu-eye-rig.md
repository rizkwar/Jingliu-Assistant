# Jingliu: separate eyes, blinking and gaze

The standalone Inochi experiment now has **29 drawable parts and six controls**.
Each eye has an independent iris, white aperture, upper lid, lower lid and closed
lash drawing. The iris keeps its shape during a blink; an Inochi clipping mask
keeps it inside the moving aperture. Both eyes can blink together or wink.

This checkpoint is separate from the assistant. Its existing avatar options,
voice, character and memory are unchanged.

## Try it

Open the previously installed Inochi Creator 0.8.6 and use **File > Open**:

`.cache/avatar-authoring/jingliu/authoring/jingliu-v5-eyes-test-v4d.inx`

Enable **View > Parameters** if necessary. The new controls are:

| Control | Range and behavior |
| --- | --- |
| Eye L open | 1 = open, 0 = closed; left side of the image |
| Eye R open | 1 = open, 0 = closed; right side of the image |
| Eye gaze XY | -1..1 on both axes; positive X looks right, positive Y looks down |

Try intermediate eye openings, a wink, and small gaze shifts while changing
**Head XY - small turn** or **Head tilt**. Use the toolbar's **Reset parameters**
button to return to rest. Collapse the Head XY section or scroll the parameter
panel to expose the entire gaze control. These are authored controls, with no
automatic blinking or cursor driver yet.

## Editable artwork and review files

Paths below are relative to `.cache/avatar-authoring/jingliu/`. They remain local
and ignored by Git. The original portrait is still the approved **v5**; suffixes
such as v4d identify this authoring checkpoint.

| File | Purpose |
| --- | --- |
| `authoring/jingliu-v5-eye-parts-v4d.psd` | 31 editable pixel layers, including two hidden original-eye references |
| `authoring/jingliu-v5-eye-parts-v4d.pcraft` | Native PhotoCraft document |
| `authoring/jingliu-v5-eyes-test-v4d.inx` | Current rig to open in Creator |
| `review-eyes-v4/eyes-verified.png` | Twelve close-up poses: gaze directions, blink stages, wink and combined head turns |
| `review-eyes-v4/verification.json` | Final-file evidence and remaining limits |
| `authoring/eye-parts-v4b.json` | Maps the ten exported eye parts used by the builder |
| `authoring/crown-clean-v4c.png` | Reduced stray crown overlap over the right eye |
| `authoring/eye-r-closed-v4d.png` | Revised right closed-lash texture |

PhotoCraft MCP performed the cuts, white-eye underpainting, iris-top extension
and local cleanup. The original complete eye drawings remain hidden references.
The PSD was saved and reopened with all 31 layers. The rig uses 29 drawables
because those two references are excluded.

The local rig MCP gained `rig_build_jingliu_eyes`. Start from the 23-part head
checkpoint and pass the manifest to produce a new eye rig. The final checkpoint
also imports the crown and right closed-lash cleanup with `rig_replace_texture`.
All keyforms and the other parts are preserved by those texture replacements.
The [MCP guide](avatar-rig-mcp.md) describes the tools and constraints.

## Verification and limits

- Reviewed twelve close-up poses rendered from the final saved meshes and
  keyforms. These are software inspection renders, not runtime screenshots.
- Loaded the rig in official Creator 0.8.6. Tested a wink, both eyes closed,
  closed eyes with a head-turn corner, gaze in both horizontal directions and
  reset. Reopened the final texture-cleanup file and checked the right blink
  before returning it to rest.
- Sampled 25 head poses x 3 tilts x 10 eye openings for the eye meshes:
  **2,104,500 triangle instances**, with zero inversions. Rigid iris translation
  does not change triangle area. Hair sway has zero eye offsets.
- The head source is preserved. The original 23 texture slots remain in the eye
  build; the final crown cleanup changes one of those slots. Ten appended slots
  hold the new eye artwork. Other original textures stay byte-identical.
- Seventeen Python tests and three JavaScript tests passed. The real MCP STDIO
  integration check discovered eleven tools and passed seventeen calls.

```powershell
& .venv/Scripts/python.exe -m unittest tests.test_avatar_rig_data tests.test_inochi_preview tests.test_inochi_eyes -v
node tests/inochi-keyforms.test.mjs
& .cache/tooling/avatar-rig-mcp/venv/Scripts/python.exe scripts/check_avatar_rig_mcp.py
```

This remains a small-turn authoring experiment. Fine cut edges, including tiny
fringe/lash remnants visible in close-ups, still need polish. Near closure blends
into a closed-lash drawing over the last tenth of the blink. Gaze is limited to
six source pixels horizontally and three vertically to suit the available iris
paint. This is not a finished professional VTuber model.

The next [mouth-rig checkpoint](jingliu-mouth-rig.md) is now available, with
separate mouth parts, opening/form controls and speaking-pose tests. Playback
and automatic motion remain separate work.

Suggested commit: `feat: add separate eye rigs with blinking and gaze`
