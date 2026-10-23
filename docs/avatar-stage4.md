# Stage 4: local avatar display inside the assistant

The approved Jingliu v5 rig now runs in the existing floating desktop window.
This stage adds display and idle movement only. Voice generation/playback,
personality, memories, summaries and model requests keep their existing paths.
The mesh mouth rests during speech; Stage 5 will connect actual output audio.
Conversation expressions belong to Stage 6.

## Try it

1. Close an older running copy from its tray menu. Start **Start Mira.cmd**.
2. Open **Settings**, enable **Show desktop avatar**. Save defaults to restore
   visibility next time. No API key or microphone is needed to display her.
3. Watch for blinking, breathing and restrained hair movement. Drag the portrait
   to move it. The bottom-right grip resizes it without changing its proportions.
4. Click to reopen chat; right-click for the existing controls and **Reload avatar**.
   **Animate avatar** pauses/resumes idle motion. Hiding the avatar stops its
   animation loop; the avatar remains available when only chat is hidden in tray.

Setup now installs `PySide6-Addons==6.12.0` and `PySide6-WebEngine==6.12.0.140`.
Qt 6.12 split WebEngine into a separate package; Addons alone is insufficient.
See the [official Qt release notes](https://www.qt.io/blog/qt-for-python-release-6.12-is-here).
Run **Setup Mira.cmd** on another environment, or install the updated requirements
using the project's virtual environment.

## Local assignments

`data/avatars.json` is a local, Git-ignored mapping from profile paths to playback
archives. Relative paths resolve from the project root. This machine is assigned:

```json
{
  "characters": {
    "character.toml": ".cache/mesh-avatar-studio/projects/jingliu/exports/jingliu-playback.mavatar"
  }
}
```

To replace or add a rig, prepare/validate a `.mavatar` separately, add its profile
and archive paths to this file, then reload the avatar or switch characters.
**Reload .env + character** also refreshes changed assignments. A character with
no explicit assignment retains the simple mascot, even if its display name is the
same. Source artwork and exports remain local; a fresh Git checkout does not
contain them. Back up the Stage 3 working files separately.

## Implementation and failure handling

`AvatarController` still owns placement, visibility, chat actions and shutdown.
`MeshDesktopAvatar` embeds a transparent `QWebEngineView`; its off-the-record
profile uses the bundled `mesh-avatar` 0.2.1 runtime. No Node server, Studio editor,
CDN or external renderer request is needed at startup. Vendor provenance and
licenses are in `companion/avatar_web/vendor/`.

A loopback service on a dynamically allocated port serves only explicit in-memory
assets under a random path. It checks the Host header, denies other paths/methods,
and never serves the workspace or data directories. The renderer's requests are
restricted to its own assets; camera and microphone permissions are denied. The
WebChannel exposes only lifecycle reports and a pause signal, with no assistant
object, chat content, credentials, microphone or audio API.

Missing dependencies, unreadable assignments, missing/invalid archives, loading
timeout, graphics context loss and renderer termination show a readable fallback
message. The normal mascot and chat remain usable. Check dependencies, restore the
local playback archive, then right-click **Reload avatar**. Hardware WebGL2 must
be available; no sandbox-disabling or GPU flags are added to the application.

Hide/show and reduced motion cancel/restart the manual animation loop; resizing
keeps contain-fit rendering. Reload/profile changes dispose the old page and
close its asset service. Shutdown disposes the independent desktop window too.
Mesh activity expressions and audio-driven mouth controls are deliberately absent.

## Verification

Native Windows Qt rendering was exercised with temporary empty storage and no
API calls or audio capture/playback. The approved rig loaded in the actual
`CompanionWindow`; screenshots were inspected at 320×350 and 440×470 logical
window sizes, and the transparent corner had alpha 0. Checks passed for advancing
idle frames, resize, reduced motion, hidden-frame pause, resume, resting mouth
during a speaking activity, reload, tray/open-chat behavior and orderly shutdown.
A simulated renderer failure and missing/invalid archive checks exercised the
native fallback, including its visible error message.

All **230** project regression tests passed in the final serial run. This includes
avatar assignment/service security checks, widget reload/profile switching,
dependency fallback, and the existing voice, microphone, chat and continuity
tests. The restricted sandbox initially blocked fake audio subprocesses; outside
it, a transient microphone-state timing failure passed in isolation and then the
entire suite passed serially. No speech or microphone code was changed.

Local evidence is in ignored `.cache/stage4-*.png` and
`.cache/stage4-integration-check.py`. These are verification artifacts, not files
required by the app. Existing UI regression tests use fake audio and mocked model
streams; live conversation/TTS listening quality and synchronization are not
claimed by these display checks. No performance measurements are claimed here.

Suggested commit: `feat: display local mesh avatar in desktop companion`

Next stage, after approval: synchronize the mouth with actual TTS audio playback,
including pauses and interruptions.
