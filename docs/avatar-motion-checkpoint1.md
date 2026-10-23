# Natural animation: checkpoint 1 inspection

Checkpoint 1 is complete. The recommendation is a small, isolated head-turn and
gaze experiment using the existing rig. Application code and approved artwork
remain at the baseline. The unfinished trial begun before the five-checkpoint
request is preserved locally in `.cache/motion-experiment-checkpoint2/` and has
been removed from the active application.

## What was inspected and reproduced

- PySide6 desktop host, the playback/state WebChannel bridge, the actual vendored
  Mesh Avatar 0.2.1 runtime, and its pinned source at
  `195ec284d3f7ae181782bf449069cb77e0650964`.
- Approved 1254 by 1254 portrait, neck pivot, head/body influence bands, eye
  openings, nine strand paths, refined hair mask, mesh spacing, built layers,
  ten eye/mouth sprite PNGs, shader eye clipping, sprite draw order and physics.
- Existing pose contact sheet and enlarged rest/left-turn eye crops were viewed.
  Those older separate-pose images show usable deformation, but do not establish
  good combined turns or natural timing.
- A new 21.6-second native canvas recording reproduced idle, thinking, speaking
  and return to idle. Speaking used synthetic output envelopes, without audible
  TTS, microphone capture or API requests. Test storage/preferences were temporary.

Local baseline evidence:

- `.cache/avatar-motion-baseline/baseline.webm`: actual canvas capture, with
  timing retained by the browser's MediaRecorder. It contains only the avatar.
- `sequence.png`: frames sampled every three seconds, inspected for visible
  head/body changes and expression transitions.
- `samples.json` and `summary.json`: timestamped numeric renderer parameters.
- `rest.png`: final native portrait capture.

The decoded frame sequence confirms little visible head change while the mouth
and expressions change. Across the sampled recording, head yaw was approximately
**-2.70 to +1.70**, pitch **-2.17 to +0.83**, and roll **-0.97 to -0.20** in
runtime parameter units. These are not physical degrees. Static frames cannot
establish animation quality; the video and samples provide the timing baseline
for the next comparison. No new motion-quality claim is made for the set-aside
trial. Its earlier PNG recording used a heavy capture path and is unsuitable as
a real-time comparison.

## Main limitations

### The app suppresses most available motion

`companion/avatar_web/conversation-state.js` sends a near-fixed head/body/gaze
pose every frame, blended at 0.75 when Movement intensity is 100%. Thus only 25%
of runtime wandering survives. Body targets are both zero. State yaw offsets
reach just 2 units; the speaking nod has gain 0.12 and is diluted by the same
blend. Random authored motions are also disabled.

The rig already supports yaw, pitch, roll, gaze and body controls. In
`rig.json`, `head.maxRoll=0.12` radians is reached at roll parameter 30; a state
roll of 1.2 represents only about 0.28 physical degrees even before blending.
Simply increasing a rotation on the whole window would miss the actual issue.

The runtime deforms facial features at different rates: nose/mouth shift,
near/far eye width changes, head/neck weighted rotation and a depth-like head
offset. This can suggest a modest turn without moving the whole portrait as one
flat card. It cannot reveal the hidden side of a single drawing.

### Hair is rigged, but is not fully separated artwork

Nine four-node strand regions and a refined mask already drive spring motion.
Roots are attached to transformed head anchors; tips lag behind. Neighboring
fringe strands are coupled to reduce splitting. Most hair is still pixels in
the base portrait deformed through weights, rather than separate front/back
hair cutouts. Face and ornaments are mostly excluded from the hair mask.

The head ellipse and neck pivot are plausible, and the fine mesh covers the
face/hair with a 7-pixel cell size. Current evidence points first to under-driven
parameters, rather than a missing rig. The long locks over shoulders, fringe
crossing eyes, collar boundary and attached earring are the highest-risk areas
for combined movement. A complete separate-layer reconstruction would require
unseen face/neck/clothing pixels behind the hair; those should not be invented
unless a demonstrated defect requires a small repair.

`setSwayGain(0)` does not guarantee completely frozen hair: the upstream physics
still contains breeze and minimum displacement limits. Hair response should be
evaluated through rendered settling tests, rather than inferred from that name.

### Gaze works differently during drawn expressions

Open eyes have separate eyeball, lash, lower-lid and crease layers. The shader
moves the eyeball texture within sampled lid boundaries; both eyes receive a
shared gaze target with slightly different scaling. This is a suitable starting
point for restrained gaze, but extreme clipping still needs a fresh test.

Drawn half-closed/smiling/closed eyes are complete image overlays. Their irises
are not independently controlled like the open-eye layers. In particular, the
thinking half-closed drawing may hide a gaze shift. Test open eyes and transitions
first; decide at checkpoint 3 whether the smallest useful improvement is to
limit gaze during that expression or separate its iris/lid assets. No replacement
drawings have been generated.

## References and tool choices

The supplied [YouTube reference](https://www.youtube.com/watch?v=Nxd1BVrg49w)
could not be loaded through the available web reader, so it was not watched.
[Live2D's motion guidance](https://docs.live2d.com/en/cubism-editor-tutorials/motion-hint/)
was accessible: coordinate head and body with a delay, ease starts/stops and
retain periods of stillness. These principles inform the recommendation.

The current [Mesh Avatar Studio documentation](https://github.com/shinshin86/mesh-avatar-studio)
describes head turns, strand motion, layer rebuilds and pose review. The app's
pinned implementation was inspected directly; an upstream feature is not assumed
available merely because newer documentation mentions it.

| Candidate | Expected benefit and preparation | Fit, availability and Windows | Ongoing cost and terms |
| --- | --- | --- | --- |
| **Existing Mesh runtime plus one coordinated motion controller — recommended** | Visible bounded head turns, eyes leading, delayed shoulders and settling hair. Uses current rig and images. | Existing Qt WebEngine host and actual `setParameters`, `setVoiceLevel` and physics APIs are available locally and already run on Windows. | Keep 20 FPS idle / 30 FPS active and current HD canvas. A small numeric controller adds no model inference or new texture layers; incremental CPU/GPU/RAM cost is unmeasured until checkpoint 5. Existing code is MIT, with notices retained. |
| **Refine Mesh masks/weights and rebuild layers if the experiment exposes defects** | Improve fringe/shoulder isolation or pivots. Rebuild offline using Studio's Python tools, then render poses with Playwright. Full independent front/back hair is not a drop-in option in the current loader; it could need hidden-region artwork and layer/draw-order changes. | Installed Studio editor, builder and review tools work with the current asset format. Native assistant integration can stay in place. | One-time preparation and review cost. Mask/weight fixes need not add layers; extra textures/meshes would add upload memory, vertices and draws and must be measured. Studio tools are MIT; artwork rights remain separate. |
| **Live2D Cubism Web migration — reserve for a proven asset limitation** | Potentially more elaborate authored head perspectives and independently rigged parts, requiring a new layered character model and keyforms. Existing `.mavatar` is not a ready Cubism model. | Official Web sample/framework code exists and lists Windows browser support; Qt embedding would still need verification. The Core library is downloaded separately. No compatible Jingliu Cubism assets are present. | Entire new runtime and asset workload, unmeasured CPU/GPU/RAM. One-time model preparation is substantially greater. Core/SDK use and redistribution have separate Live2D terms; do not assume a blanket free release exemption for an app importing user models. |

Live2D availability details come from its
[official sample README](https://github.com/Live2D/CubismWebSamples/blob/develop/README.md);
release categories are explained on its [SDK license page](https://www.live2d.com/en/sdk/license/).
No new tools, runtimes or models were installed for this checkpoint. The local
Studio builder and Playwright suit preparation; Qt canvas recording and FFmpeg
suit repeatable previews. Neither needs to run continuously in the assistant.

## Recommended checkpoint 2 experiment

Create a separate preview using the approved rig and the exact app runtime:

1. Compare the recorded baseline with a short sequence: center, left, center,
   right, center, up/down, a combined turn/tilt, and settled rest.
2. Start around yaw +/-12, pitch +/-4 and roll +/-8 **parameter units**, then
   reduce the range if cheeks, fringe, eye overlays or collar distort. These
   are initial test inputs, not a verified safe range or physical angles.
3. Let the eyes reach a modest shared target first, ease the head over roughly
   1.5–2 seconds, and let a smaller body motion follow. Hold each pose briefly.
4. Keep runtime blinking, breathing and hair physics; one controller owns posture
   and gaze. Preserve the existing output-driven mouth owner. Include blink and
   synthetic speaking overlap to reveal visual conflicts without online calls.
5. Capture matched video and enlarged eye/neck frames before changing any assets.
   Judge silhouette/parallax, lid clipping, doubled edges, texture stretch and
   hair settling. Report defects rather than treating numeric tests as proof.

Checkpoint 3 decides any minimal rig/layer repair from that evidence. Occasional
cursor attention belongs to checkpoint 4: use Qt global logical coordinates
relative to the avatar, bounded targets, a brief attention window and cooldown,
with an off switch. Display scaling/negative monitor positions need explicit
checks. Continuous chasing or per-frame LLM calls are unnecessary.

Checkpoint 5 will connect/tune conversation behavior and measure the completed
path. Earlier HD renderer-only idle samples averaged about 5.3% whole-machine
CPU on this 16-thread machine, with roughly 600–609 MiB summed working sets and
no voice model loaded; see [performance notes](avatar-performance.md). Those are
historical baseline figures, not measurements of the proposed controller.

Only this inspection document and its README link are intended for this step.
Say **next** to begin the separate checkpoint 2 experiment.

Suggested commit: `docs: inspect avatar motion and plan head-turn experiment`
