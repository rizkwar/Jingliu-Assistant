# Jingliu: automatic blinking and hair follow-through

The standalone Inochi file now includes three native animation clips and a
**SimplePhysics pendulum**. The rig still has 34 drawable parts and eight
parameters. Head movement carries the pendulum's anchor; its damped output
drives the existing hair and earring keyforms, so the motion can lag and settle.
The blink track closes quickly, briefly holds, and opens more slowly, with varied
pauses and one double blink in the idle cycle.

This stage does not connect the rig to the assistant or voice playback.

## Try it in Creator

Open **Inochi Creator 0.8.6**, then **File > Open**:

`.cache/avatar-authoring/jingliu/authoring/jingliu-v5-idle-test-v2.inx`

Use the top-right **Edit Animation** button. Enable **View > Animation List** and
**View > Timeline** if they are hidden. Select a clip and press the Timeline's
Play button. Playback loops; opening the file alone does not start animation.

| Clip | Purpose |
| --- | --- |
| Idle - blink and hair | An 18-second idle cycle with small head changes, pauses and blinks |
| Blink only | Check automatic blinks while the head remains still |
| Hair response test | Turn, hold, reverse, then stop; watch the hair settle |

The main toolbar's **Enable physics** button toggles the pendulum for comparison.
With physics enabled, it owns **Hair sway - manual test**, which keeps its older
label for compatibility. Disable physics to inspect that slider manually.
**Reset physics** returns the pendulum to equilibrium. Stop the timeline, then
use **Reset parameters** and **Reset physics** to restore rest.

## Review files

Paths are relative to `.cache/avatar-authoring/jingliu/` and remain ignored by Git.

| File | Purpose |
| --- | --- |
| `authoring/jingliu-v5-idle-test-v2.inx` | Current native rig with animation tracks and pendulum |
| `review-idle-v2/idle.mp4` | Six-second software inspection of idle motion and blinks |
| `review-idle-v2/hair-response.mp4` | Ten-second software inspection of turns and settling |
| `review-idle-v2/idle.frames.png` | Selected frames, including a blink and hair extrema |
| `review-idle-v2/verification.json` | Final checkpoint evidence |

Videos render the saved meshes and tracks with an evaluator for this configured
pendulum subset. They are **not recordings of the Inochi runtime**. Their
verification files include the source rig hash. Video frame rate is an export
setting, not a measured application-performance result.

The original mouth-stage PSD remains the editable artwork master; this stage
does not repaint or replace any texture or mesh. The initial idle v1 file was
rejected by Creator because physics enums require the member names `Pendulum`
and `AngleLength`. Use **v2**; the validator now rejects the incorrect spellings.

## Verification and limitations

- Creator 0.8.6 opened v2 and listed all three clips. Native playback was checked:
  the head changed pose, the hair driver's value changed and returned to zero,
  and both eye-open controls reached zero during a visible blink. Stopping the
  timeline and resetting parameters/physics restored the resting pose.
- All 38 texture slots, all 34 original drawable parts and all original
  deformation keyforms remain unchanged. The additions are one driver, its head
  input bindings and three animation clips.
- Focused tests cover blink timing/bounds, loop seams, pendulum response,
  length preservation, settling, frame-rate stability and invalid references.
- Twenty-six Python tests and three JavaScript tests passed. The real MCP STDIO
  check discovers fourteen tools and completes thirty-three calls, including
  native-motion authoring, MP4 rendering and rejected invalid requests.
- The offline 12-second hair test sampled at 120 Hz remained within the existing
  hair keyform range and settled to approximately zero after the head stopped.
  This is simulation evidence, not a measurement of Creator's exact trajectory.

```powershell
& .venv/Scripts/python.exe -m unittest tests.test_avatar_rig_data tests.test_inochi_preview tests.test_inochi_eyes tests.test_inochi_mouth tests.test_inochi_idle_motion -v
node tests/inochi-keyforms.test.mjs
& .cache/tooling/avatar-rig-mcp/venv/Scripts/python.exe scripts/check_avatar_rig_mcp.py
```

There is one shared hair/earring pendulum, rather than independent strand
simulation. Fine fringe/lash cut remnants still need artwork polish. These are
authored loops; a later runtime driver can vary timing and react to conversation
state. Cursor tracking, audio synchronization and assistant integration remain
separate stages.

The [interactive-viewer checkpoint](jingliu-interactive-viewer.md) now provides
manual controls, clip playback, physics comparison and part isolation separately
from the assistant. It documents the supported renderer subset and the native
runtime compatibility work that remains.

Suggested commit: `feat: add native idle blinks and damped hair physics`
