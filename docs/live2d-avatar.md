# The Live2D avatar

Jingliu can now have several visual models under the same character profile.
**Settings > Jingliu visual model** switches immediately between the current AI
portrait and imported Live2D rigs. Selection is saved separately for each character.
Voice, response model, personality, memories and the current conversation continue
to use the same systems.

This workspace has two choices:

| Visual model | What it uses |
| --- | --- |
| AI portrait (current) | The approved v5 illustration and existing Mesh Avatar renderer. Choose this to turn the experiment off. |
| Jingliu - Live2D (Bailyovo) | The ready-made model downloaded by the user from the creator's BOOTH page, with its own artwork, head keyforms and physics. |

The Live2D option is an existing artist-created rig. It is **not a conversion of
the AI portrait**. Rigging that portrait is a separate future model option.

## Try it

1. Restart **Start Jinger.cmd** to load the new code.
2. Open **Settings**, enable **Show desktop avatar**, then choose
   **Jingliu - Live2D (Bailyovo)** under **Jingliu visual model**.
3. Enable **Animate avatar**. Click **Preview movement** for a roughly 20-second
   silent demonstration of left/right turns, looking up/down, and a diagonal tilt.
4. Choose **Portrait** or **Full model** framing. The **Blindfold** checkbox
   controls the imported Jingliu rig's authored accessory parameter.
5. Try cursor attention, a voice reply, **Stop**, and switching models. Mouth
   movement uses the assistant's existing playback levels, including cancellation.
6. Select **AI portrait (current)** to return to the previous avatar. No restart
   or profile change is needed when switching models.

Use **Add Live2D model** to import another local ZIP or `.model3.json` for the active
character. Keep a model file beside its textures, moc3 and physics resources. A ZIP
with several model entries needs to be extracted first so you can choose one.
Repeated imports of identical rig resources reuse the installed asset set.

## Local setup and files

The optional runtime has already been installed in this workspace. On a fresh
checkout, run **More\Setup Live2D.cmd** once. It downloads the pinned PixiJS 6.5.10,
pixi-live2d-display 0.4.0, Pixi's CSP compatibility plugin and Cubism Core 5.1.0
into `.cache/avatar-runtimes/live2d/`. The installer checks SHA-256 hashes and
retains notices. It does not change the assistant's Python dependencies.

Imported model resources live under `data/avatar_models/<model-id>/`. Per-character
choices, names, framing and credits live in `data/avatar_models.json`. Keep the
original downloads in `ext_sources/`. All three locations are excluded from Git;
the publishing check also rejects `ext_sources/` if it is force-added.

The importer reads only the rig, textures, physics, pose and display metadata.
It does not import prerecorded sounds or idle motion files that could compete
with conversation control. Legacy Chinese ZIP filenames are resolved against
the manifest, then copied to safe local resource names. Relative path traversal,
external resource URLs and oversized packages are rejected. The avatar service
exposes an explicit resource list on loopback, with remote requests blocked.
Pixi's compatibility plugin keeps JavaScript `unsafe-eval` disabled; the Live2D
page permits WebAssembly compilation for Cubism Core.

## Life: sleep, reactions and idle moments

The Live2D rig now has a life layer (`companion/avatar/web/avatar-life.js`) on top
of the head and gaze controller. The model package has no motion files, so every
animation is procedural. Each one drives the rig's own expression parameters,
checked by rendering them: eyelids and eye-smile, mouth shape, blush, brows, body
lift (`Param114`), arms (`Param13`) and shoulders. Offsets go in before physics,
so her hair and ribbons follow every movement.

| When | What she does |
| --- | --- |
| App opens | A small hello: a stretch in the morning, a soft smile and nod in the day, a yawn late at night |
| Left alone (default 5 minutes) | Grows drowsy at 60%: a yawn, heavy lids, slow blinks, nodding off and catching herself |
| Then | Falls asleep: eyes closed, head bowed, slow visible breathing, "Zzz" drifting beside her head |
| You talk, she speaks, or the mic opens | Wakes at once with a small start, ready to listen |
| You click her, or rest the pointer on her | Wakes gently: eyelids flutter, a small yawn, then a smile |
| Click her while awake | A blink, a little bounce and a smile; three quick clicks fluster her (blush, pout, looking away) |
| Idle, awake | Every 20–45 seconds: a content smile, gazing up at the moon, a sigh, a double blink, a stretch or a yawn |
| Listening / thinking | Small acknowledging nods / glances up and aside while she considers |
| Speaking | Brows lift on emphasis, with a slight warmth; playback lip-sync always keeps the mouth |
| Needs attention (error) | A concerned brow and mouth |

### The AI controls her expressions

While the desktop avatar is shown, the reply model may add silent cues such as
`[[blush]]` where a feeling changes. A streaming filter
(`companion/avatar/cues.py`) removes them before anything is displayed, spoken
or saved, including cues split across chunks. Bracketed text that is not a known
cue, such as code like `matrix[[0]]`, is left alone. If she is speaking aloud,
each cue fires when her voice reaches it; otherwise it fires at once.

| Cue | Effect |
| --- | --- |
| `smile`, `happy` | Warm smile with smiling eyes (happy adds a small nod) |
| `blush` | Blush, a soft smile, eyes lowered |
| `shy` | Blush while looking away and down |
| `laugh` | Closed, smiling eyes and a little bounce |
| `wink` | A one-eye wink with a small smile and tilt (see below) |
| `surprised` | Wide eyes, raised brows, a small "oh" and a hop |
| `sad`, `pout`/`annoyed`, `worried` | Lowered gaze and frown / pout turning away / concerned brows |
| `think`, `nod`, `shake`, `tilt` | Glance up and aside / nod / head shake / curious tilt |
| `sigh`, `yawn`, `stretch`, `moon` | The matching idle gestures |
| `neutral` (or `calm`) | Returns to her usual composed face at once |

Moods last 7–10 seconds, then fade back. A cue also wakes her if she was asleep.
The instructions ask her to use cues sparingly and in character. In a live check,
she used one cue for a compliment (shy), a fall (smile) and bad news (calm), and
none for a technical answer. You can also trigger any of them yourself:
right-click the avatar → **Expression**.

### Petting

Move the pointer back and forth (or up and down) over her head: no click needed.
Pressing and dragging still moves the avatar. While you pet her:
- **How she reacts:** she closes her eyes in a smile, leans toward your hand and
  bobs gently with each stroke. Her blush builds over about five seconds. When you
  stop, a content smile lingers.
- **Cursor:** a palm-down hand appears while you are petting.
- **Asleep:** petting doesn't wake her (even with the pointer resting on her head).
  She smiles and blushes in her sleep. If she's drowsy, petting lets her drift off.
- **What counts:** strokes are counted by direction changes (two within 1.5
  seconds, each after at least 8 px), so passing the pointer across her once is
  not petting. Only strokes over her head count: from the top of her hair down to
  her eyes, measured from her eye positions, so it follows her as she moves.

The Animation tester's **Being petted** button plays a 3.5-second demonstration.

### Working on a task

While she does a computer task, her idle glances and cursor-watching pause and she works.
The base is a composed, focused face: eyes slightly narrowed, brows drawn in, lips set,
head a little lowered. Each kind of step has its own motion:

| Step | How she looks |
| --- | --- |
| Thinking (start, after a denied step) | A glance up and aside |
| Reading files, searching, opening pages | Her eyes sweep along a line, flick back and step down, like reading a page |
| Writing files, typing | Eyes lowered, small rhythmic bursts and tiny nods, an occasional glance up |
| Running a command | The same rhythm with a slight tilt |
| Using the screen (screenshots, clicks) | Looking off to the side, with a small nod at each click |
| Waiting for your approval | She looks at you: brows lifted, head tilted, leaning in a little |

Every 6–12 seconds a small human moment keeps long tasks alive: concentrating harder, a
quick check-in glance at you with a faint smile, or pressing her lips together. She doesn't
doze off while working.

A frosted moonlight panel in her window shows the current step, typed out as it happens,
with a turning crescent and a shimmer line. It turns amber while she waits for you, and
green when she's done. On success, ice crystals and snowflakes scatter from beside her
head as she nods with a satisfied smile; on failure she sighs, looks worried, and the panel
says "Stopped". The Animation tester's **Working on a task** group plays each state.

### A visible blush

Rendering the rig showed that `ParamCheek` changes no pixels at all: the blush is
painted into the face. A visible blush is therefore added on top: a soft pink glow
under each eye, placed from the eyes' own drawables so it follows head turns. Its
strength follows the expression: up to about a third opacity for blush and shy,
fainter for a smile, and a hint while she sleeps.

### How the one-eye wink works

This rig has no per-eye eyelid. Pixel comparisons of the real model showed that
`ParamEyeLOpen` closes both eyes and `ParamEyeROpen` changes nothing. The "EYE"
parameters only nudge an iris or highlight, or (`Param102`) drop both lids. So the
wink is composited:
- **Drawn twice:** while winking, the frame is drawn normally, then again with the
  eyelids closed, using the same pose and physics.
- **Masked:** the second drawing shows only through a soft elliptical mask over her
  visible eye (her left; her right is under her fringe).
- **Tracked:** the mask follows that eye's actual drawables, which were found by
  comparing open and closed geometry at load, so it stays in place during head turns.
- **Seamless:** closing the eyes moves nothing outside the eyes, so the blend has no seam.
- **Cost:** the second drawing only happens during a wink (about one second).
- **Fallback:** if the eye drawables can't be found, a warning is logged and the
  avatar keeps working.

### Animation tester

**Settings → Avatar → Animation tester** (or right-click the avatar →
**Expression → Test all animations…**) has a button for every animation:

- **Expressions:** neutral, smile, blush, shy, sad, pout, worried.
- **Gestures:** happy, laugh, wink, surprised, nod, head shake, tilt, think, sigh, yawn, stretch, moon gaze.
- **Reactions:** greeting, poke, flustered.
- **Sleep cycle:** get drowsy, nod off, fall asleep, wake gently, wake startled. "Wake" replays
  the full wake-up even if she is already awake.

It needs **Show desktop avatar**, **Animate avatar** and the Live2D visual model,
and says which one is missing. Tester commands use a separate channel that reply
cues cannot reach, so the model cannot put her to sleep.

**Settings → Avatar → Doze off when left alone** chooses Never or 2/5/10/20 minutes
(late at night, 23:00–05:00, she dozes off 30% sooner). The tooltip shows
"Drowsy" or "Sleeping". Movement intensity scales her body movement; facial
expressions stay whole. Only the Live2D model has this layer. The AI portrait and
layered rig are unchanged.

Verification: `node --test tests/js/*.test.mjs` covers the sleep timeline, wake
triggers, hover dwell, pokes, lip-sync priority and long seeded runs within rig
bounds. A native check of the real widget, with a 20-second delay, observed the
greeting, a yawn into drowsiness, sleep with the "Sleeping" tooltip and the Zzz
overlay, and a click waking her gently and opening chat, with no renderer
console errors. Pose sheets of every gesture were rendered from the real rig and
inspected, and expression values were tuned from those images.

## Smoothness, flicker and CPU

- **Frame rate follows what she is doing.** She draws at 60 FPS while anything lively happens:
  conversation (listening, thinking, speaking), a gesture or expression changing, petting, a task,
  a preview, or the cursor moving near her in the last 1.5 s. While she only breathes and blinks
  she draws at 30 FPS, and at 24 FPS asleep. Measured on this laptop with the app idle: about
  1.0 → 0.5 of a CPU core for the avatar and its web process.
- **OpenGL, not Direct3D 11.** With Qt's default Direct3D 11 backend, the see-through avatar
  window occasionally showed a frame with the page missing (a visible flicker, about once a minute
  during tasks). The app sets `QSG_RHI_BACKEND=opengl`, which hands every frame over intact; set the
  variable yourself to override it. Destroying the web view under OpenGL stalls in the driver for
  about 15 seconds, so on quit the app saves and closes everything, then ends its process directly.
- **The task panel is drawn by Qt**, in its own click-through window above her, not in the page:
  Chromium sometimes presented a frame without that panel's layer while its text typed out.

## Rig controls

The existing posture controller feeds the model's real `ParamAngleX`, `ParamAngleY`,
`ParamAngleZ`, body, iris, eyelid and mouth parameters. The model's authored head
keyforms change facial contours and feature placement as the head turns. This is
a layered 2D rig with a bounded turn range, not a reconstructed 3D head.

Head and gaze updates happen before the rig's physics evaluation. This lets the
authored hair and accessory groups respond to the head turn. Hair response scales
the identified hair physics outputs inside their actual limits. Blinking is
paired, breathing is subtle, and head movements retain the existing eye lead and
delayed body response. Preview movement is silent and cancels for conversation,
voice playback, hiding or pausing. Hidden avatars stop drawing.

Physics advances at fixed intervals using the rig's exported rate (60 Hz for this
Jingliu rig). Frame remainders stay in an accumulator rather than being passed to
the particle solver as tiny steps. Output interpolation and retained raw state
keep redraws and high-refresh frames from resetting ribbons to rest or feeding
display scaling back into the simulation. Redraw-only updates do not advance
physics. This fixes intermittent rapid back-ribbon flipping without disabling
idle head movement or the authored ribbon motion.

Playback lip-sync remains amplitude-based. No phoneme recognition was added.
The rig cannot animate drawings or angles that its creator did not author. The
downloaded package contains runtime exports rather than editable PSD/Cubism
project files. Its artwork and rig limits remain the creator's work.

## Verification

The full suites passed **284 Python tests** and **57 JavaScript tests** during
integration. The opt-in native check also passed:

```powershell
.\.venv\Scripts\python.exe dev/qa/check_live2d.py
```

It uses temporary model assignments, preferences and conversations. No response
provider, microphone capture or speech generation is used. It verifies the actual
imported Jingliu model and production renderer:

- 142 parameters, 236 drawable parts, authored physics and 28 identified hair outputs.
- Left/right, up/down and diagonal poses, with finite parameters and a closed mouth
  during the silent preview.
- Changing hair outputs during turns, framing, the blindfold and renderer reload.
- Synthetic playback-envelope mouth movement and Stop returning it to rest.
- Hide, pause, resume, repeated switching to the original renderer, and shutdown.
- No renderer console errors in that run.

Avatar-only pose images, a silent `rig-preview.webm`, and `verification.json` are
saved under ignored `.cache/live2d-qa/`. These images were visually inspected.
The automated playback check uses synthetic levels; listen to a real voice reply
to judge audiovisual timing on your setup. Resource usage has not been benchmarked
for this experiment, and no measured frame-rate claim is made.

### Ribbon timing regression

```powershell
.\.venv\Scripts\python.exe dev/qa/check_live2d.py --physics
```

This additional check runs the real pinned Cubism solver and imported rig through
2,400 synthetic frames (about 40 seconds of pose input), including tiny redraws
and frame intervals close to an exact physics step. The old timing produced
full-range ribbon jumps and 1,495 limit hits across 14 ribbon parameters. Fixed
timing reduced the largest consecutive change to about **0.95% of parameter range**,
with **zero limit hits** in the same inputs. These are simulation measurements,
not display-frame-rate measurements or a guarantee about every possible model.
The native check also observes 12 seconds of idle rendering before the existing
turn, playback-reset, hide/resume and model-switch checks. The JavaScript suite
now includes six timing regressions, with **63 JavaScript tests** passing.

## Credits and usage terms

The [creator's Jingliu model page](https://booth.pm/en/items/5175544) credits the
art to **八爷** and the rig to **Bailyovo / 白狸Baily**, with character copyright
belonging to miHoYo. Its posted terms prohibit secondary distribution and streaming
for profit, and refer users to the game's fan-creation rules. Keep the model local;
it is not included in the source repository or releases.

[PixiJS](https://github.com/pixijs/pixijs/tree/v6.5.10) and
[pixi-live2d-display](https://github.com/guansss/pixi-live2d-display/tree/v0.4.0)
use MIT licenses. Cubism Core has the separate
[Live2D Proprietary Software License](https://www.live2d.com/eula/live2d-proprietary-software-license-agreement_en.html).
Downloading optional runtime files does not relicense them or the model artwork.
