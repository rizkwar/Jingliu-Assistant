# Jingliu: speaking-mouth authoring checkpoint

The standalone Inochi rig now has **34 drawable parts and eight controls**.
The mouth uses separate upper/lower lips, a shaded cavity, teeth and tongue.
Two new parameters control opening and rounded-to-wide shaping. Teeth and tongue
are clipped by the opening. A small local face deformation gives the jaw up to
two source pixels of movement while the mouth opens.

This checkpoint remains separate from the assistant. It does not yet consume
TTS playback, microphone audio or phonemes.

## Try the controls

In the installed **Inochi Creator 0.8.6**, use **File > Open** and choose:

`.cache/avatar-authoring/jingliu/authoring/jingliu-v5-mouth-test-v1.inx`

Enable **View > Parameters** and scroll the panel down to the mouth controls.

| Control | Use |
| --- | --- |
| Mouth open | 0 returns to the original resting mouth; 1 fully opens the authored shape |
| Mouth form | -1 narrows/rounds the opening, 0 is neutral, +1 widens it |

Try openings around 0.2 and 0.5, then a larger opening. Combine a rounded form
with opening around 0.8, or a wide form with opening around 0.35. These give
O-like and E-like drawing variations; they are not phoneme recognition.
Move **Head XY - small turn** and **Head tilt**, and try a blink while the mouth
is open. The toolbar's **Reset parameters** button restores the original rest.

## Editable artwork

All paths below are relative to `.cache/avatar-authoring/jingliu/` and ignored
by Git. Portrait **v5** is still the approved character; `mouth-v1` identifies
this authoring experiment.

| File | Purpose |
| --- | --- |
| `authoring/jingliu-v5-mouth-parts-v1.psd` | 36 editable pixel layers; new mouth parts hidden at rest |
| `authoring/jingliu-v5-mouth-parts-v1.pcraft` | Native PhotoCraft document |
| `authoring/mouth-parts-v1.json` | Maps the five mouth components to their full-canvas PNG exports |
| `authoring/jingliu-v5-mouth-test-v1.inx` | Current standalone mouth rig |
| `review-mouth-v1/first.png` | Twelve inspected poses, including head turns and a combined blink |
| `review-mouth-v1/verification.json` | Final checkpoint evidence and limits |

PhotoCraft MCP authored smooth paths and shading for the opening, tooth strip,
tongue and lips. The original resting mouth remains intact. The PSD was saved
and reopened with all 36 pixel layers.

The new `rig_build_jingliu_mouth` tool accepts the 29-part eye checkpoint and a
JSON manifest with `cavity`, `tongue`, `teeth`, `lower lip` and `upper lip` PNG
paths. It adds detailed meshes and opening/form keyforms. Saved head offsets are
extended onto the larger mouth meshes only after checking that the source field
is affine; sculpted fields are rejected rather than silently approximated.

## Verification and limits

- Reviewed twelve poses rendered from the saved meshes and keyforms.
- Opened the saved rig in official Creator 0.8.6 and tested the opening and form
  controls, including closing while a rounded form remains selected, then reset
  to rest. The native runtime draws the clipped teeth and tongue with the lips.
- Geometry checks sampled 25 head poses x 3 tilts x 7 openings x 3 forms for the
  mouth components and face/jaw: **6,470,100 triangle instances**, zero inversions.
- All 33 input texture slots and the original 29 parts remain unchanged. Five
  new texture slots contain the mouth artwork. Existing head/eye bindings remain.
- The real MCP test compares rendered rest images before/after the upgrade,
  including leaving the form slider wide while the mouth is closed. The PNGs
  are byte-identical.
- Twenty Python tests and three JavaScript tests passed. The real MCP STDIO
  check discovers twelve tools and completes twenty-five calls, including the
  mouth build, preview, original-art preservation and rejected overwrites.

```powershell
& .venv/Scripts/python.exe -m unittest tests.test_avatar_rig_data tests.test_inochi_preview tests.test_inochi_eyes tests.test_inochi_mouth -v
node tests/inochi-keyforms.test.mjs
& .cache/tooling/avatar-rig-mcp/venv/Scripts/python.exe scripts/check_avatar_rig_mcp.py
```

The artwork is a first speaking-mouth pass. The resting drawing crossfades into
the articulated parts below 12% opening; tiny lips and tooth/tongue details can
lose definition at desktop scale. Existing fringe/lash cut remnants still need
polish. Static pose checks and sampled geometry do not prove natural continuous
speech animation or phoneme-accurate lip-sync.

The subsequent [idle-motion checkpoint](jingliu-idle-motion.md) adds automatic
blink tracks and damped hair follow-through. Runtime and playback integration
remain separate work.

Suggested commit: `feat: add layered mouth shapes and speaking controls`
