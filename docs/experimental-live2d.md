# Experimental rigged models

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

1. Restart **Start Mira.cmd** to load the new code.
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
checkout, run **Setup Live2D.cmd** once. It downloads the pinned PixiJS 6.5.10,
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
.\.venv\Scripts\python.exe scripts/check_live2d.py
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
.\.venv\Scripts\python.exe scripts/check_live2d.py --physics
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
