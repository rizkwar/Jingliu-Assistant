# Varied idle and cursor attention: checkpoint 4

The separate preview now starts in **Free idle**. Double-click
**Preview Head Motion.cmd**, then move the mouse around that page. The right
portrait varies small glances, tilts and comfortable resting periods. Eyes
arrive first, the head eases toward the pose, and the smaller shoulder movement
follows later. Hair uses the existing attached strand springs.

The controller deliberately spends several seconds settled between gestures.
It chooses discrete targets and varied hold times rather than running a separate
repeating sine wave on every body part. Head/gaze/body limits stay inside the
checkpoint 3 review range. Blinking, breathing and the mouth keep their runtime
owners. No model calls, camera, microphone, new drawings or new dependencies are
needed for this motion.

## Cursor attention

A recent meaningful cursor movement can attract a brief glance at an available
resting moment. The target is sampled once: moving the mouse during the gesture
does not continually tug her head. After a short hold she returns, with a
9–14 second cooldown before another notice is eligible. Some opportunities are
skipped, so a moving cursor does not command her constantly. Tiny accumulated
movements are recognized; stale cursor samples and invalid geometry are ignored.

Turning **Cursor attention** off, leaving the page, losing focus or hiding it
clears that target. An active glance returns smoothly. Pausing/hiding stops the
loop; returning starts a fresh frame clock without replaying hidden time.

This stage reads **page-local pointer events only**. It cannot observe the cursor
in other applications or on another monitor. Client coordinates and the canvas
rectangle are measured in the same CSS space, accounting for its contain-fit
portrait and eye position. Translation/scaling tests pass, including negative
origins, but this is not a physical multi-monitor desktop test. Qt global cursor
sampling and real monitor/DPI checks belong to checkpoint 5. The preview geometry
is calibrated to this Jingliu rig and must not silently be reused for another
character's portrait.

## Controls

| Control | Behavior |
| --- | --- |
| Free idle | Runs the varied idle/attention controller. Uncheck for the earlier finite head-turn sequence. |
| Rig inspection | Selects checkpoint 3's diagnostic sequence instead. |
| Cursor attention | Enables/disables occasional glances in Free idle; disabled in fixed review modes. |
| Movement | Scales head, body and gaze. At zero they are pinned to center; blink/breath/hair are separate. |
| Gaze | Scales pupil movement independently within the movement limit. |
| Hair response | Uses the existing sway gain from 0.20–0.80. Lower values make springs firmer; the built-in breeze is retained. |
| Silent speech test | Sends a synthetic output envelope to both mouths for visual overlap checks; it produces no audio. |

These preview settings are temporary and take effect immediately. They do not
change assistant preferences. Smooth settings transitions and persistence belong
to integration. Live attention uses neutral/open eyes because the approved
half-closed drawings contain their irises; their limitation remains visible in
Rig inspection. Conversation-dependent expression/nod behavior is checkpoint 5.

## A rendering defect caught during review

The first recorded test exposed an actual failure: large individual time steps
under capture load made the upstream explicit spring integrator unstable. Breath
grew far outside its intended range, and the portrait moved out of view even
though the initial numeric/control checks passed. That failed recording was not
accepted as visual verification.

An initial fix used the runtime's existing multi-step `advance()` call, but that
also deformed and drew the mesh repeatedly, increasing work during a stall.
The finished preview uses a **preview-only stepping adapter** instead:

- Motion/lip/physics updates use steps no larger than 20 ms.
- Mesh deformation, sprite fading and rendering happen once per outer frame.
- Sprite fading receives the total elapsed time once. No duplicate mouth timing
  is added. Stalls are bounded to 100 ms; hidden time is discarded.
- The adapter verifies the pinned HD bundle's hash and exact patch locations.
  An unexpected runtime version fails rather than being patched speculatively.

The optional method exists only in the module served by the preview. Production
`companion/avatar_web/vendor/mesh-avatar.js`, its original `advance()` method,
the assistant host and the approved rig/assets are untouched. Both comparison
portraits use the same adapted stepping; the left retains the current assistant
posture policy. The preview is consequently not a measurement of production
runtime cost. This adapter must receive integration review at checkpoint 5.

## Verification and visual evidence

**19 JavaScript tests** pass across idle/attention, the original pose study,
rig review and stable stepping:

```powershell
node tests/idle-attention.test.mjs
node tests/head-motion-study.test.mjs
node tests/rig-review.test.mjs
node tests/stable-preview.test.mjs
```

They cover long bounded idle runs with stillness, equivalent timing at
20/30/60 FPS, eye anticipation/body lag, frozen cursor targets, cooldowns,
stale and slowly moving inputs, smooth disable, geometry translation/scaling,
invalid/stalled time and preservation of runtime spring stability with one draw.

The corrected native recording covers roughly 32 seconds of simulation in
32.4 seconds of video. It contains two cursor notices, subsequent disengagement,
an off-switch interval, idle variation, and synthetic mouth overlap/release.
Frame sequences and the final native screenshot were inspected: the portrait
remains visible, with bounded breath and no obvious new gross neck/hair tearing
in those samples. This is not a claim that all animation is perfect or all frame
timing/GPU combinations are covered.

Native checks also passed movement/gaze controls, pause/resume, resizing, replay,
hidden drawing, review-mode switching and zero JavaScript console errors.
Controlled page pointer events were used, without moving the operating-system
cursor. No user conversations or credentials were recorded.

Local evidence stays ignored in `.cache/head-motion-checkpoint4/`:
`idle-cursor.mp4`, `idle-cursor.webm`, `sequence.png`, `controls.png`,
`samples.json` and `verification.json`. The recording contains only the two
avatar canvases and captions. It does not show the desktop or cursor itself.
Labels identify attention phases.

Two renderers plus capture add work; CPU/GPU/RAM have not been measured for the
new production path because it has not been integrated. No performance numbers
from earlier stages are presented as new results.

After **next**, checkpoint 5 connects the reviewed controller to the assistant's
states, actual output audio, global cursor position and saved controls, then
measures and verifies the single-avatar path. The assistant continues using its
existing animation until that step.

Suggested commit: `feat: add varied idle and occasional cursor attention preview`
