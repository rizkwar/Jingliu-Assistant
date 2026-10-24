# Jingliu v5: editable artwork checkpoint

The PhotoCraft MCP connection now has a prepared artwork document for the next
rigging experiment. This checkpoint edits artwork only; it does not change the
assistant's selected model, renderer, voice, character profile or conversations.

## Open the result

All artwork stays in the local, Git-ignored folder
`.cache/avatar-authoring/jingliu/`.

| File beneath that folder | Purpose |
| --- | --- |
| `authoring/jingliu-v5-layered-v1.psd` | Grouped editable master for PhotoCraft |
| `authoring/jingliu-v5-layered-v1.pcraft` | Native PhotoCraft master |
| `authoring/jingliu-v5-parts-v1.psd` | 23 raster parts, with their original canvas positions |
| `exports-v1/parts/` | 23 transparent PNG exports on a shared 1254 x 1254 canvas |
| `review-v1/comparison.png` | Approved v5 beside the prepared composite |
| `review-v1/parts-review.png` | Labelled inspection sheet of the actual exported parts |
| `review-v1/layer-manifest.json` | Part order, rest visibility, bounds and feature/hair cut notes |
| `review-v1/verification.json` | Measured checks for the saved artwork |

In PhotoCraft, choose **File > Open** and open the grouped master. Expand the
front hair, face, body and rear hair groups in the Layers panel. Toggle individual
parts to inspect them. Left/right in the part names mean the viewer's left/right.

The master also keeps a hidden approved-v5 reference and a hidden clean torso
completion. Those two helper layers are excluded from the 23-part PSD and PNG
exports. The closed-eye alternatives are hidden at rest in both documents.

## What was prepared

- Separate left and right eyes and brows, nose, resting mouth, and a clean face
  base without a second pair of eyes or a second mouth underneath.
- Separate left, center and right fringe, left/right side bangs, left/right long
  front locks, crown, rear hair and the earring.
- Independent neck and torso surfaces, with a torso crop that retains the collar.
- Completed eye and brow paint where the original bangs obscured the drawing.

The first automatic cuts contained feature remnants and hair fragments in the
face. The face base was cleaned with PhotoCraft's content-aware fill and clone
stamp. Complete eyes and brows were cut from the existing hidden completion
painting, positioned against the approved portrait, and checked with the hair
hidden. The right fringe and left side bang were recut from the crown, keeping
overlap at their roots. No new image-generation call was used for this checkpoint.

The artwork uses the approved AI-assisted Jingliu v5 fan portrait and the two
previously generated hidden completion paintings. Their earlier generation
notes remain in `.cache/avatar-rigs/jingliu-layered/prompts.json`. The original
portrait remains separate from these working files.

## Verification on 2026-10-24

PhotoCraft **0.15.1** was driven through the connected MCP tools. The saved
23-part PSD was reopened through MCP and inspected again:

- All 23 parts survived as pixel layers, without unresolved Smart Objects or
  layer masks. Both hidden closed-eye alternatives retained their visibility.
- Each exported PNG has transparency, visible pixels, and a 1254 x 1254 canvas.
- The grouped master and the 23-part document rendered identically: maximum
  premultiplied RGBA channel difference **0**.
- Saving and reopening the parts PSD also produced maximum channel difference
  **0**, measured against its pre-save composite.
- The cleaned face base, isolated facial features, assembled portrait and
  closed-eye drawing were visually inspected. The review figures show the actual
  saved parts, not a mockup of a proposed rig.
- The working portrait copy still matches the original source by SHA-256.

These are artwork checks. They do not measure animation quality, runtime frame
rate or Inochi compatibility. No application code changed during this checkpoint.

## Next: a small rigging test

The next checkpoint is to test the PSD import into the chosen rigging editor,
then build meshes and small left/right and up/down head poses. Use those poses
to refine overlaps before increasing the turn range.

The eyes currently have complete open drawings and closed alternatives; iris
and eyelid meshes still need separate authoring. The original torso paint also
retains some hair-edge detail, and the hidden clean torso completion needs
alignment at the shoulders and hair roots before it can replace that paint.
Check those areas during deformation rather than assuming the neutral composite
proves that every hidden area is ready for wide turns.

This artwork has no authored motion parameters or physics yet and is not an
Inochi puppet or a Cubism model. Assistant integration remains a later checkpoint.

That describes the original artwork checkpoint. The subsequent
[standalone head rig](jingliu-head-rig.md) now has an Inochi import, revised torso
paint, head-turn keyforms and a manual hair-sway test, with verification and
remaining limitations recorded separately.

Suggested commit: `docs: record Jingliu layered artwork checkpoint`
