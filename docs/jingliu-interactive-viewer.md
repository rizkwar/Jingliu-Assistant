# Jingliu: standalone interactive rig viewer

This checkpoint makes the saved 34-part rig interactive outside the assistant.
It uses the actual saved meshes, deformation keyforms, opacity tracks, eye/mouth
clipping masks and configured hair pendulum. It does not create new artwork or
change the working assistant, voice, memories or selected model.

## Start it

Double-click **Preview Jingliu Rig.cmd** in the project folder. Keep its console
open while testing; closing it stops the local server. The launcher chooses an
available loopback port and opens the viewer in your normal browser. No API key
or additional package installation is needed: it uses Node.js and the project's
existing Python/PySide6 environment.

From the project folder, the equivalent command is:

```powershell
node scripts/preview_inochi_avatar.mjs --open
```

If a browser does not open, use the local URL printed in the console. For a
specific port, add `--port 8769`. For another supported saved checkpoint, add
`--model authoring/your-rig.inx`. Paths must remain inside the local authoring
root. Missing rigs, unsupported features and occupied ports produce readable
console messages. A missing texture produces an error inside the viewer.

The default source is:

`.cache/avatar-authoring/jingliu/authoring/jingliu-v5-idle-test-v2.inx`

## What to try

1. Choose **Manual controls**. Move Head X/Y, Head tilt, Gaze, eye opening and
   mouth opening/form. All eight saved parameters are available as ten sliders.
2. Leave **Hair follow-through** on while moving the head. Turn it off to test
   **Hair sway** manually. **Settle hair now** resets the pendulum at the current
   head pose; gravity can retain an offset when the head is tilted.
3. Select **Idle - blink and hair**, **Blink only**, or **Hair response test**,
   then **Play**. Animation owns the pose sliders. **Pause** freezes the current
   pose and physics. Scrubbing the timeline pauses playback and reconstructs the
   pendulum from the beginning, making repeated seeks reproducible.
4. Use **Visible part** to inspect a separated bang, iris, lid or mouth piece.
   Zoom helps check edges. Invisible-at-rest parts need their relevant eye or
   mouth control before they can be seen.
5. **Reset to rest** stops animation, clears the pose and restores manual
   control. It preserves the inspection zoom, selected part and physics toggle.
   Select **Whole model** if you were inspecting one piece.

The viewer is silent. It has no microphone, speech, conversation-state or global
cursor connection. Rendering pauses when its document is hidden. On return,
playback continues from the held position without replaying hidden time. The fps
counter is a rolling observation of that browser's animation callbacks, not a
benchmark or a promised frame rate.

## Runtime and export decision

| Item | What was established |
| --- | --- |
| Current native source | Inochi 0.8 TRNSRTS container; v2 previously opened and played in Creator 0.8.6 |
| Native SDK 0.8.6 | Local source requires an OpenGL context; not a browser module |
| C ABI route | Official `inochi2d-c` documents loading, parameter access and timing callbacks; no compatible compiled binding was tested here |
| TypeScript route | Official `inochi2d-ts` documents a Three.js loader/renderer; full support for this rig's physics and animation was not established |
| Viewer bundle | Our own JSON plus ordinary PNG textures, for the explicitly validated subset; **not an exported INP** |
| Viewer renderer | Small WebGL implementation in `scripts/inochi-viewer/`; **not the official Inochi SDK** |

Sources inspected: [SDK v0.8.6 README](https://github.com/Inochi2D/inochi2d/blob/v0.8.6/README.md),
[official C ABI](https://github.com/Inochi2D/inochi2d-c),
[official TypeScript implementation](https://github.com/Inochi2D/inochi2d-ts), and
[SDK releases](https://github.com/Inochi2D/inochi2d/releases).
The current SDK's newer bindings must be checked separately before adoption;
their APIs should not be assumed interchangeable with 0.8.6.

The exporter rejects unsupported features rather than silently dropping them:
nested transforms, composites, non-Normal blending, extra material textures,
unsupported masks, unset keyforms, other physics modes and animation mixing.
This is a scoped inspection tool for our rig, not a general Inochi viewer.

## Verification

- The browser loaded all 34 parts and eight controls with no console errors after
  correcting a vertex/fragment uniform-precision mismatch in the initial shader.
- Real controls were used for left/right turns, closed eyelids, rounded open
  mouth, manual hair, clip play/pause, blink seeking, rest reset, part isolation,
  zoom, a 540-pixel-wide layout and page reload.
- A separate temporary test server withheld a texture. The viewer displayed its
  missing-texture message and disabled the controls.
- Numerical comparison covered all three clips at 120 Hz: **4,803 samples**.
  The largest parameter difference from the prior Python inspection evaluator
  was about `6.7e-12`. Two combined poses compared all 10,384 vertices; the largest
  Float32 difference was about `0.000062` artwork pixels.
- Numerical agreement compares our two inspection evaluators. It does not prove
  pixel-identical or trajectory-identical rendering against the native SDK.
- Focused checks cover playback ownership, pause/seek/reset, stable pendulum
  settling, alpha conversion, source preservation, unsupported features and HTTP
  access restrictions. Source `.inx` and original texture sections remain intact.

```powershell
& .venv/Scripts/python.exe -m unittest tests.test_inochi_viewer tests.test_inochi_idle_motion tests.test_inochi_preview -v
node --test tests/inochi-viewer.test.mjs
& .venv/Scripts/python.exe scripts/check_inochi_viewer.py
```

New inspection bundles and source-hash reports are stored in
`.cache/avatar-authoring/jingliu/viewer/`. They use new directories on each
launch. Screenshots and numerical evidence are under `review-viewer-v1/` in the
same authoring root. Artwork and generated files stay ignored by Git. The
exported bundle omits author metadata and PSD source-layer paths. The HTTP
server exposes only its explicit viewer/model/texture allowlist, supports only
GET/HEAD, and binds exclusively to `127.0.0.1`.

Fine fringe/lash remnants, a shared hair/earring pendulum and the existing small
head-turn range remain. There are no new profile paintings or independently
simulated strands in this checkpoint.

Next: test this renderer in a separate PySide6 WebEngine window, including its
shutdown and failure behavior, before adding an opt-in assistant model option.
A native SDK-backed renderer remains a separate compatibility task.

Suggested commit: `feat: add standalone interactive Jingliu rig viewer`
