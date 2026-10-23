# Motion presets and a silent preview

Settings now includes **Motion preset** and **Preview movement**, below the avatar
visibility controls. This polish step makes it easier to choose and check movement
inside the assistant, using the existing portrait and renderer.

## Try it

1. Restart **Start Mira.cmd** and open Settings.
2. Enable **Show desktop avatar** and **Animate avatar**.
3. Choose a **Motion preset**, then click **Preview movement**.
4. Watch the floating avatar settle, look left and right, tilt gently, and return
   to rest. The sample lasts about 12 seconds and produces no sound.
5. Use **Stop preview**, the main **Stop** button, or wait for normal completion.
6. Adjust individual sliders if needed, then click **Save defaults**.

The preview requires a loaded, visible mesh avatar with movement above zero and
an idle conversation. It is unavailable while a request, recording, speech,
suspension or Hands-free session is active. It does not automatically enable the
avatar, animation or microphone, and it does not request a response from a model.
If the button is unavailable, the nearby status text explains the reason.

## Presets and saved choices

| Preset | Movement | Gaze | Hair response | Effect |
| --- | ---: | ---: | ---: | --- |
| Calm | 45% | 55% | 30% | Smaller head/gaze motion and firmer hair. |
| Natural | 100% | 100% | 45% | The previous default movement settings. |
| Lively | 100% | 100% | 65% | More hair follow-through within the same head/gaze limits. |
| Custom | Your values | Your values | Your values | Shown when the sliders do not match a named preset. |

Presets change only those three controls. Cursor opt-in, avatar visibility, size,
HD rendering, lip sensitivity, voice, character and conversation settings retain
their independent controls. Lively does not increase the reviewed head-turn range
or add new expressions. Changing sliders during a preview still works.

The preset name is derived from the existing numeric values. There is no second
saved preset field to become inconsistent with them. Save defaults persists those
same numeric preferences; startup and settings reload preserve custom values.

## Preview behavior and ownership

`MotionPreview` is a finite posture/gaze sequence used by `AssistantMotion`.
It starts from the current posture, with eyes anticipating the head and smaller
shoulder motion following. The final hold gives the body time to settle. It stays
inside the head/gaze ranges reviewed during the earlier animation checkpoints.
Movement and gaze intensity scale the sample, and hair uses its selected spring
response. Settings changes continue to ease smoothly.

The preview writes head, body and gaze only. The existing runtime still owns
blink, breath, hair physics and the mouth. The demo never supplies synthetic
speech levels, changes the app's conversation state, or calls TTS or microphone
APIs. It uses the existing rendering loop rather than a second avatar instance.

Desktop cursor polling pauses during the demo so it cannot compete with the
scripted glances. Normal idle and cursor eligibility resume after completion.
Any of these actions cancels the sample rather than queuing it for later:

- Starting a conversation, recording, actual playback, or Hands-free session.
- Stop, Stop preview, suspension, movement set to zero, or animation disabled.
- Hiding, minimizing, reloading, disposing or closing the avatar.
- The embedded renderer document becoming hidden.

Cancellation keeps the current posture as the starting point for the next normal
transition. Hiding or pausing also stops rendering. Restore/show does not resume a
cancelled demo. The native host and renderer exchange sequence-numbered completion
messages, so a late acknowledgment cannot stop a newer preview.

Minimized and hidden renderer pages also stop native cursor polling. The renderer
reports document visibility to the host in addition to the existing Qt window
visibility checks, covering a hidden embedded page inside an otherwise visible
widget. Loading a new renderer is asynchronous; checks wait for its first rendered
frame before inspecting animation parameters.

## Verification and local preview

The regression checks passed **269 Python tests** and **51 JavaScript tests**:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests
node --test tests/*.test.mjs
```

New checks cover presets and custom-value persistence, preview controls and gates,
Stop/playback cancellation, a bounded finite sequence, eye anticipation/body lag,
20/30/60 FPS timing, invalid elapsed time, live tuning, repeated starts and normal
idle after completion. Existing character, memory, voice and conversation tests
remain in that suite.

The opt-in native check uses the real local renderer and temporary settings/chat
data. It captures only the avatar canvas and its isolated test Settings window:

```powershell
.\.venv\Scripts\python.exe scripts/check_avatar_polish.py
```

It passed completion, preset values, manual stopping, custom settings persistence,
conversation-state cancellation, output-playback signals, the main Stop button,
pause/hide/zero movement, minimizing, a hidden renderer page, reload and shutdown.
No script errors, speech requests, microphone requests or model requests were
observed. Parameters stayed finite and breath remained bounded. This check uses
controlled playback signals to verify cancellation; it does not play or record
audio. Actual local speech and interruption were checked in
[the integration stage](avatar-motion-checkpoint5.md).

The native sample and Settings layout were visually inspected. No obvious new
gross neck/hair gaps or invisible frames appeared in the sampled poses. This is
still a modest 2D mesh turn range, with the previously documented half-eye drawing
limitation. No new art, layers, dependencies or performance claims are introduced.

Ignored local artifacts are under `.cache/avatar-polish/`: `verification.json`,
`samples.json`, `left.png`, `right.png`, `tilt.png`, `settings.png`, and
`movement-preview.webm`. The optional MP4 copy was converted at 30 FPS with even
frame dimensions for playback compatibility; it contains only the avatar.

Suggested commit: `feat: add avatar motion presets and silent preview`
