# Rig and layer review: checkpoint 3

The existing rig is suitable for the small head-motion range tested so far.
**No source-art, rig, mask or sprite repair was justified by the inspected
results.** The source image, nine strand definitions and approved eye/mouth
drawings remain intact. This checkpoint adds an isolated diagnostic preview,
not integration into the assistant.

## Review it

Double-click **Preview Head Motion.cmd**, then enable **Rig inspection**.
The ordinary checkpoint 2 sequence is still available when it is unchecked.
The inspection runs for 39.6 seconds of animation time:

- Open-eye gaze sweeps: horizontal +/-0.6 and vertical +/-0.3.
- Combined head corners: yaw +/-12, pitch +/-4, roll +/-8, with small body follow.
- A brief drawn blink at each turned position, followed by reopening.
- Left/right gaze commands with the same half-closed expression, exposing its
  current limitation.
- Return to neutral and six seconds of settling.

Angles above are rig control values, not physical degrees. Gaze sweeps are
diagnostic limits, not the intended continuous idle movement. The silent speech
checkbox lets you inspect mouth drawings during turns. No microphone or online
model calls are used.

## Observations and decision

Fourteen full-resolution canvas captures, enlarged eye/neck crops and frame
sequences from a native video recording were inspected. At these tested poses:

| Area | Observed result | Decision |
| --- | --- | --- |
| Open eyes | Both eyes respond to the shared gaze direction, with irises retained inside the inspected eye openings. | Keep the existing layered eyeball and clipping path. |
| Blink and mouth overlap | The turned closed-eye captures contain closed lash lines without an obvious remaining iris. Mouth drawings continue to appear during the turn sequence. | Keep the approved drawings and existing runtime owners. |
| Head/neck/collar | No obvious open collar gap or gross mesh fold in the inspected combined poses. Perspective remains modest. | Keep the neck pivot and current bounded head range. |
| Fringe and side locks | Motion remains restrained, with roots effectively attached and no obvious major splitting in the inspected frames. | Keep the current mask/strand deformation; separate cutouts are not needed for this range. |
| Earring | Follows the head as an attached part; does not have independent swing. | Retain this limitation rather than add unreviewed accessory motion. |
| Half-closed eyes | Gaze values change, but the drawing includes its iris and does not provide the independent movement of the open-eye layer. | Record this capability limit; preserve the drawing. |

These observations do not establish artifact-free behavior at larger angles or
all possible combinations. Fine outlines and the fringe crossing the eyes remain
areas to inspect when tuning later motion.

### Why not separate the half-eye artwork now?

The half-eye PNGs include iris, lashes, skin and foreground hair in one opaque
patch. The runtime hides the underlying open-eye layers when that patch covers
them. Moving the whole patch would move skin/lashes too; unhiding the open iris
over it would duplicate content. Removing the drawing would return to procedural
lid deformation, which previously produced seams near this character's fringe.

A genuinely independent half-eye iris would require either prepared iris/lid
layers with the covered background completed, or a separately calibrated interior
aperture mask and an optional shader path. Existing full-open eye curves are not
valid masks for this half-eye drawing. That is a larger asset/rendering experiment
without a demonstrated need for the planned neutral-eye cursor glances.

For checkpoint 4, prefer open-eye attention during a deliberate glance and retain
the relaxed half-eye expression for focused/resting moments. Do not claim that a
gaze parameter alone fixes the drawn half-eye. Any future aperture experiment
should begin with just 1–2 source pixels of horizontal displacement and its own
close-up review, preserving the original assets.

## Numerical checks

A read-only check imported the pinned rig/physics implementation and approved
rig, using eight combinations of the head bounds above, body yaw +/-1.2 and body
roll +/-1.12. Each trajectory warmed up, eased into the pose for two seconds,
held, returned over two seconds and settled. Simulation used 60 Hz, sway gain 1
and breath 0. Values below are **1254 by 1254 source-image pixels**, not screen
pixels or resource-use measurements.

- Maximum secondary drift at portrait hair-root coordinates: about **0.0031 px**.
  Physics root nodes themselves remain exactly anchored; these are distinct tests.
- Peak secondary difference versus a stationary rig with the same breeze:
  **4.32 px**, with fringe difference below **3.02 px**.
- Extra motion versus that breeze baseline fell below **0.00014 px** one second
  after returning to rest. The built-in breeze continues; this is not literal
  zero hair motion.
- Sampled neck deformation Jacobians stayed positive, approximately
  **0.922–1.078**, with finite results. Sampling is not proof about every mesh
  triangle or visible alpha boundary.

Rig and engine hashes matched before/after. Reproduction and the full report
remain local under `.cache/head-motion-checkpoint3/rig-numerical-review.mjs`
and `numerical-results.json`. These checks support the visual review; they do
not replace it or measure the native 20/30 FPS rendering path's performance.

## Verification and evidence

All **eight** focused JavaScript tests passed:

```powershell
node tests/head-motion-study.test.mjs
node tests/rig-review.test.mjs
```

The native Qt preview captured fourteen poses and passed checks for head/gaze
coverage, mouth overlap/release, pause/resume, resizing, replay, hidden drawing
and return. It reported no JavaScript console errors. The review server retains
its explicit asset allowlist and write/Host restrictions.

Local evidence in `.cache/head-motion-checkpoint3/` includes `rig-review.mp4`,
`comparison.webm`, `eye-neck-sheet.png`, `blink-sequence.png`, numbered pose PNGs
with diagnostic JSON and `samples.json`. The paired preview/video are heavier
than one production avatar; no new CPU/GPU/RAM claims are made here.

The running assistant, character, voice, memory, lip-sync and asset assignment
have not been modified. After **next**, checkpoint 4 adds varied idle behavior,
occasional cursor attention and coordinated hair response in the separate study.
Application integration and final measurements remain checkpoint 5.

Suggested commit: `test: add avatar rig and layer inspection preview`
