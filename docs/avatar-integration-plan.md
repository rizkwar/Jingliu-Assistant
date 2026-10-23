# Jingliu mesh avatar: Stage 2 integration plan

Status: inspection and planning complete. This document does not implement the
renderer, install dependencies, create a rig, or connect animation to speech.

## Approved artwork

Use **v5**, as explicitly selected by the user. The local source is
`artifacts/avatar-stage1/jingliu-portrait-final.png`; its selection record is
`artifacts/avatar-stage1/selected-portrait.json`. The final copy's SHA-256 matches
the approved v5 file:

```text
4d032f53e7c5a5f3667009a67d6f566bd408a2728c5f3ba9d9c8b92e23fa695c
```

Later v6 and intermediate drafts are not the approved source. A PNG is source
artwork, not an animated avatar. V5 has fine bangs near the eye outlines; Stage 3
must inspect those areas during blinking and mouth/head tests, preserving this
choice rather than silently substituting another portrait.

## What exists in this project

| Area | Inspected implementation | Integration consequence |
| --- | --- | --- |
| Desktop UI | `CompanionWindow(QMainWindow)` in `companion/ui.py`; native Qt Widgets, `PySide6-Essentials==6.12.0` | Add a rendering surface to the existing app; no UI framework rewrite. |
| Desktop avatar | `DesktopAvatar` and `AvatarController` in `companion/avatar.py` | Reuse visibility, tray controls, click-to-open, dragging, monitor-safe position and shutdown. Current artwork is drawn with `QPainter`. |
| Existing geometry | Fixed 168 x 174 widget with an ellipse-and-badge window mask | A portrait needs a larger host and a different mask/input treatment. Putting it under the current ellipse would crop it. |
| Speech generation | `SpeechController` starts a reusable `QProcess` running `companion.speech_process` | Keep local Pocket TTS, reference recordings, phrase queueing and cancellation. |
| Actual audio output | `PocketSpeaker.speak()` generates PCM chunks and writes volume-adjusted samples to `sounddevice.OutputStream` | Measure lip-sync at this boundary, using the effective playback rate. |
| Conversation/state | `activity_state()` in `avatar.py`, emitted as `CompanionWindow.activity_changed(str)` | Reuse the existing state source rather than infer activity from text or run a second state machine. |
| Character switching | `_activate_character()` / `_apply_settings()` in `ui.py`; the latter calls `avatar.refresh()` | Swap the associated avatar and clear the old visual state when the character changes. |
| Continuity | `reply_prompt()`, existing profiles, SQLite chats/summaries and explicit Memories | The renderer needs no changes to prompts, model requests, memories or conversation storage. |

The speech subprocess reports `loading`, `preparing`, `speaking`, completion and
errors through a JSON line protocol. Its current `speaking` status is emitted
before the first blocking audio write, so it is an activity hint rather than a
sample-accurate playback clock. It sends no PCM levels or output timestamps today.
`spoken` confirms a completed phrase and supports existing interruption context;
that behavior must remain correct.

`SpeechController.stop()` clears pending work and active IDs, then kills its busy
child. New messages, Stop, recording, suspension and shutdown already use this
path. Future animation updates must be invalidated there too.

The existing visual states are `ready`, `opening_mic`, `listening`, `transcribing`,
`thinking`, `replying`, `summarizing`, `preparing_voice`, `speaking`, `suspended`,
`error` and `closing`. The current mascot's opening mouth is a timer-driven drawing;
it does not measure audio amplitude.

## Verified upstream capabilities

Research was pinned to Mesh Avatar Studio commit
`195ec284d3f7ae181782bf449069cb77e0650964`, verified against upstream HEAD during
this inspection. Its packages are `mesh-avatar` **0.2.1** and
`mesh-avatar-element` **0.1.1**. This pin prevents a later setup from silently
using a different API.

The renderer is a **browser WebGL2 runtime**, not a Python/Qt image rig. Its loader
is `loadMeshAvatar(canvas, source, options)` and accepts a `.mavatar` or an unpacked
avatar folder. React, camera tracking and microphone capture are not required.
[Runtime documentation](https://github.com/shinshin86/mesh-avatar-studio/blob/195ec284d3f7ae181782bf449069cb77e0650964/packages/runtime/README.md).

The custom element's standalone build is `dist/standalone.js`. A
`<mesh-avatar src="..." fit="contain">` element provides a `ready` promise,
`avatar`, `setVoiceLevel(value)`, `paused`, and `load` / `error` events. Its own
animation loop pauses when hidden/offscreen or explicitly paused, and disconnecting
it destroys its renderer. Set `src` before connecting it: its default source is an
online Miko sample, which is not the selected character.
[Element documentation](https://github.com/shinshin86/mesh-avatar-studio/blob/195ec284d3f7ae181782bf449069cb77e0650964/packages/element/README.md),
[element implementation](https://github.com/shinshin86/mesh-avatar-studio/blob/195ec284d3f7ae181782bf449069cb77e0650964/packages/element/src/index.ts).

The actual runtime exposes `setSpeaking(boolean)`, `setVoiceLevel(0..1)`,
`setExpression(name)`, `setEmotion(tag, {playMotion:false})`, `setAutoIdle`,
`setAutoMotion`, `setSwayGain`, `setTalkGain`, `stopLipSync` and `destroy`.
`manual:true` with caller-owned `advance()` supports real render pausing;
`setAutoIdle(false)` alone does not stop rendering.
[Public interface](https://github.com/shinshin86/mesh-avatar-studio/blob/195ec284d3f7ae181782bf449069cb77e0650964/packages/runtime/src/engine/index.ts).

A `.mavatar` is an archive containing `avatar.json`, `rig.json`, `built/layers.json`
and built images, with optional drawn sprites. Keep a source-inclusive working
export for editing; playback can use an export without `source.png`. Neither a
valid archive nor a successful load proves that the animation looks good.
[Format and validation guide](https://github.com/shinshin86/mesh-avatar-studio/blob/195ec284d3f7ae181782bf449069cb77e0650964/docs/format.md).

## Chosen integration approach

Add a **locally bundled web renderer inside Qt WebEngine**, managed by the existing
`AvatarController`. Keep the floating desktop companion placement, with a larger
portrait canvas and the existing native app controls. The HTML content renders
the avatar; the Qt host owns window movement, app actions and lifetime.

This is a compatibility decision based on the inspected APIs, not a claim that
the combination has already run here. In Stage 4, first prove loading and resizing
in a simple embedded view, then verify the transparent floating host, input and
monitor behavior on this Windows machine. If floating transparency or WebGL2 fails,
retain a readable error and the current mascot fallback; report the limitation.

Proposed components, to implement only in their later stages:

- A lazy `MeshAvatarView` using `QWebEngineView`, with a local HTML host and a
  pinned standalone component bundle. Guard optional imports and initialization:
  missing Addons, GPU/WebGL failure or an invalid assigned rig must leave chat
  and the current mascot usable. Keep third-party license notices.
- A narrow `QWebChannel` bridge publishing only visual state, bounded loudness,
  model selection and lifecycle messages. Do not expose the main window, keys,
  conversations, memories, raw microphone audio or arbitrary file operations.
- A loopback-only, read-only asset server on an allocated port. Serve an explicit
  avatar/web asset directory, never the workspace root or `.env`. This avoids
  assuming that JavaScript modules and model fetches will work under `file://`.
- A nonsecret character-to-avatar association keyed by existing `character_key()`.
  Only a character with an assigned rig gets that rig; other characters retain
  the normal fallback. No chat database migration is needed.

Qt documents an embeddable web widget, transparent page backgrounds, and a
QObject/JavaScript channel. Actual transparent WebGL composition remains a native
verification item. Production startup should use local assets, with no CDN,
Node/Vite server, camera permissions or second audio player.
[QWebEngineView](https://doc.qt.io/qtforpython-6/PySide6/QtWebEngineWidgets/QWebEngineView.html),
[page background](https://doc.qt.io/qtforpython-6/PySide6/QtWebEngineCore/QWebEnginePage.html#PySide6.QtWebEngineCore.QWebEnginePage.setBackgroundColor),
[QWebChannel](https://doc.qt.io/qtforpython-6/PySide6/QtWebChannel/QWebChannel.html).

Do not add an arbitrary `[avatar]` section to the existing TOML today: the loader
rejects unknown sections, and the character editor reconstructs its supported
fields. A separate map initially avoids changing that schema or losing metadata
on an edit. Size, motion and lip-sync controls belong to Stage 7.

## Dependencies and setup boundaries

| Dependency | Current check | Planned use |
| --- | --- | --- |
| Node.js / npm / Git | Available; Node v24.11.1 | Isolated Studio setup/build in Stage 3. Upstream requires Node 22.17+. |
| `uv` | Not on PATH | Stage 3 Python tools for grids, layers and coordinate calibration, isolated from the assistant environment. |
| Playwright Chromium | Not verified | Check/install with Studio's documented setup in Stage 3 for pose rendering. |
| Qt WebEngine / WebChannel | Both unavailable; Addons not installed | Add version-matched `PySide6-Addons==6.12.0` in Stage 4, then verify native imports/rendering. |
| Mesh web bundle | Not installed | Pin and bundle the inspected component/runtime for Stage 4; no React or MediaPipe dependency. |

Studio work should live in an isolated ignored checkout, with the approved source
copied into its own `projects/jingliu/` working directory. Follow its current
`AGENTS.md` and agent guide, including coordinate calibration and visual checks.
The editor/build tools are preparation tools; they should not run during everyday
chat. WebEngine adds browser processes and resource cost; measure that in Stage 7.

## Later stages and acceptance checks

### Stage 3: create and review separately

Set up the pinned Studio checkout and its tools; run doctor and coordinate
calibration. Create a project from the approved v5 source, place the rig using
zoomed grids, validate it, build layers and inspect fixed-pose renders. Review
closed eyes, mouth opening, head turns, neck seams and hair motion. Generate
matching drawn eyelids/mouths only through the supported variant workflow, explain
any external image-generation step, and preserve the selected character. Export
and validate `.mavatar`; show a working preview and remaining limitations.
Do not connect it to the assistant in this stage.
[Creation guide](https://github.com/shinshin86/mesh-avatar-studio/blob/195ec284d3f7ae181782bf449069cb77e0650964/docs/agent-guide.md).

### Stage 4: display and idle only

Add the local web surface and asset lifecycle. Verify load, resize, hide/show,
blinking/breathing/hair idle behavior, renderer failure, model reload and shutdown.
Keep the current mascot as a fallback. Recheck chat, voice preview, recording,
tray/hotkey actions, summaries and character switching. No mouth animation from
reply text or the current `speaking` flag in this stage.

### Stage 5: mouth movement from actual playback

Keep Pocket TTS and sounddevice. Extend only the audio output boundary to compute
levels from post-volume PCM that is actually delivered for playback. Account for
the existing delivery-rate adjustment; generated chunks alone are not a playback
clock. Prefer output callback/DAC timing, with bounded telemetry passed outside
the real-time callback to the existing JSON protocol and Qt bridge. The current
blocking writer may need a bounded producer/playback queue inside the speech child;
preserve streamed phrase order and completed-phrase acknowledgements.

`sounddevice` exposes the output buffer's DAC timestamp in callback time data.
Use it to schedule the mouth envelope, then measure real audio/visual offset.
Callback code must avoid blocking I/O; do not write JSON from the audio callback.
[sounddevice 0.5.6 stream API](https://python-sounddevice.readthedocs.io/en/0.5.6/api/streams.html).

Send `setSpeaking(true)` with bounded voice levels during audible playback. On
silence, buffering gaps, mute, cancellation, failure, model switch or shutdown,
clear scheduled updates, reject stale session/job IDs, and return the mouth to
rest with `setSpeaking(false)` and `setVoiceLevel(0)`. Clear any explicit lip-sync
preview state too. Do not use the microphone, generated text, or `speakKana()`.

This is **amplitude-based lip-sync**. The runtime's loudness-driven vowel changes
are not English phoneme recognition, so no phoneme-accuracy claim is planned.
[Mouth-motion implementation](https://github.com/shinshin86/mesh-avatar-studio/blob/195ec284d3f7ae181782bf449069cb77e0650964/packages/runtime/src/engine/motion.js).

### Stage 6: conversation states and restrained expressions

Reuse `activity_changed`, mapping existing states to subtle supported visual
behavior. Start with neutral/half-lidded/restraint rather than frequent gestures.
Keep expression commands separate from dialogue and TTS. Pause motion when
suspended and close/reset the mouth on interrupted audio. Leave the character's
personality profile, memory and spoken wording under the existing conversation
system.

### Stage 7: controls and measurement

Add visibility/size/motion/sensitivity controls, explicit hidden/suspended render
pause and orderly disposal. Measure idle/speech CPU and memory, frame behavior
and synchronization on this machine. Exercise repeated replies, Stop, microphone
interruption, resizing, character/model reload, tray use and quit. Document how
to replace the rig with another locally prepared character.

## What Stage 2 verified

Read the current app and regression tests, inspected pinned upstream docs/source,
checked installed modules and tool availability, and verified the approved source
hash. No `.env` contents were printed, app/hardware capture started, package
installed, rig built, runtime executed, or performance measurement claimed.
Only this planning document changes the tracked project. Next action requires
the user's **next**, and is Stage 3 only.
