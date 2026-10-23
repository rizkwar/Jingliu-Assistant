# Natural motion in the assistant: checkpoint 5

The reviewed head/gaze experiment now runs in the floating desktop avatar. The
approved v5 portrait, rig, eye drawings, hair mask and character assignments are
unchanged. The existing voice, character, model selection, memory and conversation
systems continue to supply their original behavior. There are no new dependencies
or per-frame model requests.

## Try it

1. Restart using **Start Mira.cmd**. In Settings, enable **Show desktop avatar**
   and **Animate avatar**.
2. Leave her idle and move the mouse to either side of the avatar, including in
   another application. Give her several seconds: she chooses occasional short
   glances rather than continuously following the mouse. She returns to rest
   between gestures, with a 9–14 second eligibility cooldown and some skipped
   opportunities.
3. Try **Preview voice** at a nonzero volume, then **Stop** during speech. Her mouth
   follows the audio you hear; small head nods use that same playback envelope.
4. Try a normal conversation. Listening greatly reduces wandering, thinking uses
   the existing focused half-eye drawing, and speaking restores open eyes.
5. Adjust the controls below, then click **Save defaults**. Hide/show or reload the
   avatar to check the behavior. Settings also survive an application restart.

The separate **Preview Head Motion.cmd** still provides the earlier comparison,
fixed head-turn sequence and rig inspection. It shares the idle controller with
the assistant, while retaining page-local pointer events and temporary controls.
It never starts the assistant or changes its saved settings.

## Controls

| Setting | Behavior |
| --- | --- |
| Occasionally look toward my cursor | Enables brief desktop cursor attention while idle. Turning it off cancels the target and eases back. |
| Movement intensity | Scales head, shoulder and gaze movement. Zero centers these transforms; blinking, breathing, lip-sync and hair physics remain separate. |
| Gaze intensity | Independently scales eye movement. Zero keeps gaze centered while allowing head turns. |
| Hair response | 20–80%, default 45%. Lower values make the existing springs firmer; higher values allow more follow-through. It does not add new separated hair layers or freeze the built-in breeze. |
| Lip-sync sensitivity | Scales mouth response to actual playback. It does not change speech volume or head nod strength. |
| Animate avatar | Pauses the renderer and cursor polling, and clears speech animation. |
| Show desktop avatar | Hiding stops rendering and cursor polling and clears pending attention and speech animation. |

Movement, gaze and hair settings ease over several frames to avoid a sudden
pose change. Save defaults persists only the settings through the existing local
preferences mechanism. Older preference files acquire the new defaults.

## Coordinated motion and state ownership

`companion/avatar_web/assistant-motion.js` owns head, body, gaze and a small brow
cue. It composes the shared `IdleAttention` controller with restrained activity
postures. Eyes anticipate the idle target, the head eases toward it, and smaller
shoulder motion follows. The controller chooses targets and resting intervals
rather than continuously oscillating every part.

Listening keeps her nearly centered and attentive. Thinking uses the approved
half-eye patches with centered gaze: those patches contain their own irises and
cannot support independent pupil tracking. Listening, idle attention and speech
use the open-eye rig. Related activity states share a 180 ms hold to avoid
flickering expressions during short preparation transitions. State cues describe
application activity; they do not infer the user's emotions.

Only idle admits cursor attention. Starting a conversation clears its cursor
target immediately, while the pose returns smoothly. Speaking permits reduced
idle movement and small nods driven by actual output loudness. A speaking state
or generated text alone cannot produce a speech nod or animate the mouth.

Runtime text-driven talk nods are disabled to avoid two competing head controllers.
The runtime retains ownership of blink, breath, mouth sprites and hair springs.
Posture parameters never include mouth, eyelid or breath overrides. Head/gaze
limits remain within the checkpoint 3 review range: yaw ±12, pitch ±4, roll ±8
in rig parameter units, with smaller body and gaze limits. These are not physical
degrees or a full 3D rotation. Another rig still needs its own visual review.

## Desktop cursor coordinates and lifecycle

The native host samples `QCursor.pos()` every 100 ms while the avatar is visible,
animated, ready, idle, cursor-enabled and has nonzero movement intensity. It uses
`QWebEngineView.mapFromGlobal()` to convert Qt logical desktop coordinates, then
sends fractions of the view's size through the existing local WebChannel. The
renderer maps these into CSS canvas coordinates. Device-pixel backing resolution
is not used for cursor placement.

The eye center, image dimensions and contain-fit margins come from the loaded
avatar's actual `package.rig` metadata. They are not silently calibrated to the
1254-pixel Jingliu portrait for every character. Invalid metadata produces no
cursor target. Geometry tests cover translation, negative origins, scale changes,
different image sizes and malformed values.

Only changed cursor samples cross the bridge. A glance snapshots its target;
later mouse movements do not tug it around. Old samples expire. Dragging the
avatar clears attention. The first poll after show/state changes occurs on a
later timer turn, after the visibility and activity signals. Hide, suspension,
animation pause, renderer failure and disposal stop polling and clear attention.
Resuming starts a fresh frame clock, discarding hidden elapsed time.

Cursor positions stay in local transient memory. They are not saved in chat,
preferences or diagnostics, and are not sent to the response provider. There is
no camera, microphone listener or global input hook for this feature.

## Playback and rendering stability

Existing DAC-timed post-volume playback levels still reach the renderer through
`SpeechController.playback_level`. The mouth uses its existing amplitude-based
lip-sync, not phoneme recognition. Head emphasis receives the original bounded
level, independently of the mouth-sensitivity slider. Stop, interruption, hidden
rendering and the playback watchdog clear the audio level and pending nod. The
mouth returns to rest; the visible head pose settles smoothly.

The stable stepping repair from checkpoint 4 is now a reproducible production
runtime patch. `advanceStable(seconds)` advances springs in steps no larger than
20 ms, then deforms and draws once. Each outer frame simulates at most 100 ms;
sprite fading receives that total elapsed time once. This avoids the unstable
large spring step observed in the earlier recording without multiplying mesh
draws during a stall. Idle targets 20 FPS and active states 30 FPS at the existing
HD resolution.

`scripts/patch_avatar_runtime.py` accepts only the known pinned pristine,
HD-only or current bundles. The optional stable API preserves the original
`advance()` API and license notices. See [runtime provenance](../companion/avatar_web/vendor/README.md)
for hashes and reproduction instructions. The loopback asset service still
serves an explicit allowlist; credentials, preferences and source files are not
exposed by adding the three browser modules.

## Verification

The regression suite passed **256 Python tests** and **42 JavaScript tests**:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests
node --test tests/*.test.mjs
```

The normal tests use isolated data and fake services, without real microphone
capture, speech playback or model requests. The runtime test also reconstructs
the original bundle hash and verifies exact patch reproduction, including Windows
line endings and rejection of unknown source versions.

The opt-in native check exercises the real assistant and renderer, using a
temporary conversation store and preference file:

```powershell
.\.venv\Scripts\python.exe scripts/check_avatar_motion.py
# Also play a short cached local Alba voice sample and interrupt actual playback:
.\.venv\Scripts\python.exe scripts/check_avatar_motion.py --audio
```

The audio run stays offline and does not change the chosen character voice. It
needs the model and stock voice already cached. This check passed cursor mapping
and disabling, activity expressions, smooth controls, saving preferences,
resizing, pausing, suspension, actual mouth/nod activity, Stop, three mocked
conversation turns, three avatar reloads, hidden rendering and shutdown. No
renderer script errors were observed. It verifies finite parameters and bounded
breath throughout. Qt deferred deletions are processed during its manual event
loop so reload measurements include normal page cleanup.

The isolated QA renderer installs deterministic randomness before controller
creation so deliberately skipped glances do not make the check flaky. Normal
assistant sessions keep their varied randomness. Native cursor inputs are
controlled `QCursor.pos()` samples through the real
coordinate conversion, without moving the operating-system pointer. This run
used one display at 125% scaling. Physical mixed-DPI/multiple-monitor cursor
behavior still needs a manual check on that hardware; mathematical geometry
coverage is not a substitute for that check.

Avatar-only PNGs for cursor, listening, thinking and actual speech were inspected.
The portrait stayed visible, with no obvious new gross neck/hair gaps in those
samples. This is a small mesh-based turn range, not a fully reconstructed side
view or a guarantee of perfect motion. No new artwork was generated.

Local evidence is ignored under `.cache/head-motion-checkpoint5/`, including
`verification.json` and pose PNGs. It contains no desktop capture, personal chat,
API credentials or voice recordings. Resource measurements below describe this
single local run, not a before/after benchmark or a performance guarantee.

On this 16-logical-CPU Windows machine, with a 320 ? 350 logical-pixel avatar,
HD enabled and 125% display scaling, the final audio run observed:

| Phase | Seconds | Whole-machine CPU | Summed working set | Draws/sec |
| --- | ---: | ---: | ---: | ---: |
| Visible idle, before loading voice | 6.09 | 4.28% | 601.0 MiB | 20.51 |
| Actual local speech playback | 5.25 | 22.51% | 1461.1 MiB | 29.14 |
| Hidden, after Stop and reloads | 6.11 | 0.85% | 665.6 MiB | 0.0 |

Counters cover the Python/Qt/Chromium process tree plus the local voice process
when present, including the verification polling. Speech uses the cached stock
Alba voice and includes CPU inference. Stop terminates that speech process, so
the hidden row is not a voice-model-loaded measurement. Working sets sum shared
pages too; they are not private allocated RAM. GPU use was not measured.
The 5?6 second samples are too short to imply a guaranteed resource budget or
a speedup over earlier stages. Hidden rendering and cursor polling stopped.


Suggested commit: `feat: integrate natural avatar motion and desktop cursor attention`
