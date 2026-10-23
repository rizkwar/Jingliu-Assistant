# Jingliu avatar: Stage 3 preparation and review

The approved **v5** portrait now has a separate Mesh Avatar Studio rig, drawn blink
and mouth frames, validated exports, and a working local browser preview. The
assistant's Python code, voice, character profile, memories and settings are unchanged.
Qt integration and audio synchronization have not been implemented or tested here.

## Open the preview

Double-click **`Preview Jingliu Avatar.cmd`** in the project root. It starts a local
server and opens `http://127.0.0.1:8765` in your browser. Use Chrome or Edge with
WebGL2 available. Keep its console open; close it or press Ctrl+C to stop the server.
If a preview is already running, open that address directly.

The controls show idle motion, a blink, a gentle closed-eye smile, head turns,
four mouth shapes, pause/resume, and a checkerboard for transparency inspection.
**The mouth test is silent.** It tests the drawings and does not simulate speech
synchronization. The page never accesses the microphone, camera, TTS or chat.

Only the explicitly allowlisted web files, runtime bundle/license and playback
archive are served. The server binds to `127.0.0.1`; it does not serve the project
root, original portrait, `.env`, conversations, or arbitrary paths.

## Local working files

Studio is isolated at `.cache/mesh-avatar-studio/`, pinned to commit
`195ec284d3f7ae181782bf449069cb77e0650964`. Its runtime is `mesh-avatar` 0.2.1.
No creation dependencies were added to the assistant's Python environment.

The private project is `.cache/mesh-avatar-studio/projects/jingliu/`:

| File or folder | Purpose |
| --- | --- |
| `source.png` | Exact approved v5, 1254 × 1254 with transparency. |
| `rig.draft.json`, `rig.json` | Traced draft and built complete rig. |
| `built/` | Eye layers, base image, refined hair influence mask, and 10 drawn sprites. |
| `variants/` | Seven full-size generated animation frames; the source is unchanged. |
| `variant-requests/` | Studio's edit masks and instructions; optional expression requests are prepared but not generated. |
| `review/` | 21 fixed poses, eye/mouth crops, preview screenshots and browser-check results. |
| `exports/jingliu-playback.mavatar` | Validated playback archive, source omitted; 1,805,766 bytes. |
| `exports/jingliu-working.mavatar` | Validated source-inclusive editing archive; 3,347,785 bytes. |
| `stage3-verification.json` | Hashes, calibration result and review evidence. |
| `work/` | Grids, overlays, generation prompts, mask refinement, QA scripts and tool logs. |

These artwork and derived files stay in Studio's ignored `projects/` directory,
following its project instructions. They are **not included in a Git commit**.
Keep the private working folder/source-inclusive archive when backing up this work.
A fresh checkout needs those local assets restored before this preview can run.

Source SHA-256 (also matches `artifacts/avatar-stage1/jingliu-portrait-final.png`):

```text
4d032f53e7c5a5f3667009a67d6f566bd408a2728c5f3ba9d9c8b92e23fa695c
```

## Preparation and visual corrections

The coordinate-reading calibration passed with median error **0.46 px** and maximum
**1.02 px**. Full and enlarged 5/10/20/25/50 px grids were inspected before tracing.
Approximate source landmarks: crown `(630,180)`, face centre `(630,650)`, chin
`(633,800)`, neck pivot `(631,811)`, shoulders `(325,1000)` and `(976,1008)`.
There are long side locks and a hanging earring; no hand obscures the face.

The rig uses a neck pivot, conservative head displacement/roll, nine hair strands,
two eye openings/ROIs, a fitted mouth line, chest and shoulder breathing regions,
and a finer face/hair mesh. Every overlay was inspected. The long hair is handled
by strand regions rather than enlarging the head ellipse into the shoulders.

The first render exposed a patchy procedural blink around the overlapping fringe.
Seven variants were created using the built-in **imagegen** tool: `eyes_closed`,
`eyes_half`, `eyes_smile`, `mouth_a`, `mouth_a_half`, `mouth_i` and `mouth_o`.
The exact prompts are recorded in `work/blink-generation-prompts.md` and
`work/generated-variant-prompts.json`; the Studio masks are in `variant-requests/`.
The generator received the source and corresponding mask. Studio accepted each
alignment/edge check and imported only the masked pixels with small tint correction.

All four mouth drawings are needed at this runtime pin: loading any drawn sprites
disables its procedural mouth. The preview and export therefore contain a complete
core eye/mouth set, not an eyes-only sprite folder.

The automatic hair mask included silver shoulder ornaments. The project-local
`work/refine-hair-mask.py` removes the traced ornament and earring regions from
the **deformation mask**, without editing the approved portrait. Run this after
each layer rebuild. It also updates the layer build fingerprint.

## Verification and limits

- Studio doctor passes: Node 24.11.1, uv 0.13.5, Python 3.11.6 and Playwright Chromium.
- Draft/complete rigs, project folder and both exported archives validate.
- Three review rounds produced 21 fixed poses each. The final contact sheet,
  individual turns/tilts, closed/half eyes, open mouth, expressions and hair sequence
  were visually inspected. No obvious mesh tearing, cut chin or exposed neck seam
  was seen in the tested range. Final blink frames contain no visible iris/white.
- In the hair-sway sequence, a sampled hair patch changes while sampled face-core
  and central-clothing patches remain pixel-identical; see the verification JSON.
- Standalone browser checks pass for loading, animation, all seven drawings,
  controls/reset, pause/resume, resizing, invalid-file errors and asset isolation,
  with no browser errors or outside network requests. Screenshots are in `review/`.
  A high-refresh timing issue in the preview loop was caught and corrected.
- Upstream lint and all four builds pass (the React build emits its upstream
  `use client` warning). Both Python tool suites pass, 6 tests each.
- The initial upstream unit run had 190 passing and 11 failing tests, plus one
  failed suite: Windows symlink permissions, time-sensitive/timeout assertions,
  archive endpoint expectations, and a doctor-module transform error. Runtime
  format/CLI tests pass separately with one worker and a longer timeout: **25/25**.
  Numerical deformation and sprite regression remains **0 px**; physics differs
  only by floating-point tolerance. This is not a claim that the full upstream
  test suite passes on this machine.
- The upstream browser run finished with **97 passed, 3 failed, 1 skipped**, at
  its configured three-failure limit. Two sample/editor mouth-pixel checks failed;
  one editor layout exceeded a 900 px viewport by 1.5 px. These are recorded in
  `work/upstream-e2e.log`; the run also reports its early-stop error. The separate
  Jingliu preview's drawing/control checks pass. Do not infer that Studio's kana
  demo or all editor layouts are verified by this avatar's successful preview.

The review uses full Playwright Chromium with Direct3D11. The default headless
shell selected software SwiftShader here, so `work/render-jingliu.mjs` wraps the
upstream pose runner with the verified hardware backend and progress logging.
It does not modify the runtime or its deformation rules.

This is a 2D warp, not a reconstructed 3D head. Hidden parts cannot be revealed.
The silver earring follows the head without independent swing; the small hair
twist is part of the head. Fringe/eye transitions remain the first area to check
after any source or rig edits. Optional sad/surprised eyes and angry/sad closed
mouth drawings were not generated. No assistant audio/visual offset or resource
use measurements are claimed at this stage.

## Open and rebuild in Studio

From the assistant's root, open PowerShell and configure only that terminal:

```powershell
$env:Path = (Resolve-Path '.cache/avatar-tooling/bin').Path + ';' + $env:Path
$env:UV_CACHE_DIR = (Resolve-Path '.cache').Path + '\uv-avatar-cache'
$env:UV_PYTHON = (Resolve-Path '.venv/Scripts/python.exe').Path
$env:PLAYWRIGHT_BROWSERS_PATH = (Resolve-Path '.cache').Path + '\avatar-browsers'
Set-Location '.cache/mesh-avatar-studio'
npm.cmd run dev
```

Open the address Studio prints, choose **Open project**, and select **jingliu**.
After editing eye outlines, save the draft and rebuild the layers before export:

```powershell
npm.cmd run validate-rig -- projects/jingliu/rig.draft.json
uv run --offline --with numpy --with pillow --with opencv-python-headless tools/build-layers.py projects/jingliu --rig rig.draft.json
uv run --offline projects/jingliu/work/refine-hair-mask.py
uv run --offline tools/variant-requests.py projects/jingliu
uv run --offline tools/build-sprites.py projects/jingliu
node --experimental-strip-types work/render-jingliu.mjs projects/jingliu
```

Inspect overlays/layers/poses again after geometry changes; existing drawings may
need updating if their edit regions change. Exports are snapshots, so repack to a
new filename and validate it after edits. Restart the standalone preview server
after updating its playback archive or web files.

Next, **Stage 4** will display the verified avatar inside the existing assistant,
including the native transparency/fallback checks. Wait for the user's `next`.
