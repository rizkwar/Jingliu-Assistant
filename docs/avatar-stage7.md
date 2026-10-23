# Stage 7: controls, lifecycle checks and observed resource use

The seven-stage avatar integration is complete. The approved local Jingliu rig
now has display, idle animation, output-driven lip-sync, conversation cues and
practical controls. Existing chat, local voice, character profiles and memory
remain in the same application.

## Controls and a quick check

Restart **Start Mira.cmd**. In **Settings**, scroll down to the desktop avatar:

| Control | Behavior |
| --- | --- |
| Show desktop avatar | Shows/hides it; hidden avatars stop drawing. |
| Animate avatar | Pauses/resumes all animation, including the mouth. |
| Avatar size | Sets width from 220–640 logical pixels, with a proportional initial height. |
| Bottom-right resize grip | Changes width/height freely within 220×240 and 640×700; contain-fit preserves the portrait's proportions. |
| Movement intensity | 0–100%; reduces head/body/gaze offsets, speech nods and hair sway. At zero those movements stop; blinking, breathing, facial cues and lip-sync can continue. |
| Lip-sync sensitivity | 25–200%; scales the playback envelope, without changing audible volume. Increase it for a quiet mouth; decrease it for excessive opening. |
| Save defaults | Keeps visibility, animation, actual width/height, position, movement and sensitivity after restart. |

Changes apply immediately. Dragging the resize grip updates the size label and
saved dimensions. Controls set while hidden apply when the portrait returns.
The mesh controls do not stretch the simple fallback mascot.

Try Preview voice, Stop during playback, a few messages, hiding/showing the
portrait, resizing and **right-click → Reload avatar**. Check saved defaults after
restarting. Visibility and reduced motion also remain available through the
existing app controls. There is no new microphone or camera access.

## Rendering and lifecycle

The original Stage 7 renderer capped WebGL draws near 30 FPS. The subsequent
[idle optimization](avatar-performance.md) uses 20 FPS while waiting and 30 FPS
during conversation, retaining HD resolution. Elapsed-time stepping still handles
different display refresh rates. The loop stops when hidden, reduced motion is
enabled, suspended, closing or disposed. Hidden voice resets, state/control
updates and resize notifications do not trigger extra draws. A visible static
portrait can redraw once for a size/control change. Keeping a hidden renderer
loaded saves reload time; it does not free its allocated memory.

Settings validation rejects out-of-range dimensions, movement and sensitivity,
including booleans passed as numbers. Older preference files receive the new
defaults without migration. Reloads reuse the current dimensions and controls,
dispose the old page, close its allowlisted asset service and invalidate its
animation loop. Normal application teardown releases shared Chromium children
as well as the app's local voice process.

## Measurements on this machine

Observed on **2026-10-23**, Windows, **16 logical processors** (Intel Family 6,
Model 154), at **320×350 logical pixels**, full movement and 100% lip sensitivity.
The cached local reference TTS voice was warmed before every measured phase;
the same loaded model remained in memory for hidden and idle measurements.

| Phase | Sample duration | CPU, whole-machine equivalent | Mean summed working sets | Draws/sec |
| --- | ---: | ---: | ---: | ---: |
| Hidden, local voice loaded | 8.16 s | 0.57% | 1,447.3 MiB | 0.00 |
| Visible idle, local voice loaded | 8.09 s | 9.11% | 1,442.8 MiB | 28.05 |
| Local speech generation/playback | 8.23 s | 19.53% | 1,486.7 MiB | 28.18 |

Each phase included **five owned processes**: the application, its Chromium
helpers and its local voice child. CPU was calculated from their combined user
and kernel CPU-time deltas, divided by elapsed time and 16 logical processors.
Before normalization, those CPU values were 9.20%, 145.75% and 312.54% of one core.
Working sets were sampled about every 200 ms and summed across the process tree;
shared pages can be counted more than once. These numbers are **not avatar-only
memory**, private memory, GPU memory, or a long-duration leak test. GPU usage and
physical audio/display synchronization were not measured.

The visible renderer has a noticeable CPU cost on this machine. Hiding it stops
all measured draws and substantially reduces CPU use, while leaving the loaded
voice/renderer memory available. Local TTS inference adds further CPU and memory
cost during speech. These short, observed samples are not performance guarantees
for other machines, larger portraits, voices or background workloads.

## Reproduce the check

The opt-in Windows tool plays short local test lines. Close extra assistant
instances and first confirm **Preview voice** works with the cached voice. Then:

```powershell
.\.venv\Scripts\python.exe scripts/measure_avatar.py
```

It uses temporary empty chat storage, the selected local voice and mocked HTTP
replies, with Hugging Face offline mode enabled. It makes no model API requests
and never records the microphone. The Windows helper reads only process IDs,
parent relationships, CPU times and working sets; no process command lines are
collected. Missing counters or a missing offline voice fail the check instead
of inventing results. Initial model loading/inference warmup is excluded from the
phase averages.

The report stays local at `.cache/avatar-performance.json`, with a settings
screenshot at `.cache/stage7-controls.png`. The tool does not save changes to your
normal preferences or conversations.

## Verification

- **244 Python regression tests** and **7 JavaScript policy tests** passed.
- Native Windows controls were inspected: resizing and labels, zero movement,
  higher/lower mouth sensitivity, saving/reloading, and hidden control updates.
- Live cached TTS playback and interruption passed, followed by three mocked
  conversation turns through the actual worker and storage.
- Five avatar reloads retained dimensions and controls. Hidden drawing stayed at
  zero, including after reloads. The shutdown check confirmed that all owned
  child processes exited after QApplication teardown.
- The original approved artwork remains unchanged. No new online model, audio
  service, telemetry service or application dependency was added in this stage.

The earlier Windows breakpoint dialog has not been reproduced in native entry
point and lifecycle checks; its original cause remains unconfirmed. The measured
checks do not establish an arbitrary-length session or every GPU/driver setup.

## Replace Jingliu with your own character

1. Use **Settings → Add character** to create/edit the personality and optional
   local reference voice. This makes a profile and voice choice; it does not rig
   a portrait automatically. Note the profile path shown in Settings.
2. Prepare a front-facing transparent portrait and create a separate Mesh Avatar
   Studio project. Follow the pinned [creation guide](https://github.com/shinshin86/mesh-avatar-studio/blob/195ec284d3f7ae181782bf449069cb77e0650964/docs/agent-guide.md)
   and the [Stage 3 notes](avatar-stage3.md): trace the rig, review head/hair/eye
   motion, and supply supported blink and mouth drawings where needed. Keep the
   editable source/working export separately.
3. Validate and export a playback `.mavatar`. Store it locally, for example at
   `data/avatars/my-character.mavatar`, which is already excluded from Git.
4. Add an entry to the existing `data/avatars.json`, preserving other entries:

   ```json
   {
     "characters": {
       "character.toml": ".cache/mesh-avatar-studio/projects/jingliu/exports/jingliu-playback.mavatar",
       "data/characters/my-character.toml": "data/avatars/my-character.mavatar"
     }
   }
   ```

   Use the actual generated profile filename. Paths resolve from the project
   root, and assignments match profile paths, not display names.
5. Select the new character and use **Reload avatar**. Test blinking, thinking,
   lip-sync, interruptions and saved size. An invalid/missing rig shows a readable
   fallback; it does not replace the character's voice or memory. Restore the
   correct archive and reload to recover.

Back up profiles, recordings, mapping and rig files privately. The bundled web
runtime carries its license, but character artwork and locally generated assets
are not included in a fresh Git checkout. There is no automatic portrait-to-rig
generation step in the assistant.

Suggested commit: `feat: add avatar controls and verify performance`
