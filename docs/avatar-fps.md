# Smoother avatar rendering at 60 FPS

The visible, animated desktop avatar now targets **60 FPS** during idle,
movement previews, listening, thinking and speaking. Previously it was capped at
20 FPS idle and 30 FPS during activity. Restart **Start Mira.cmd** to load the
change, then try **Settings → Preview movement**.

Frame deadlines retain their phase through small display jitter instead of
restarting the schedule after each late frame. Slower displays remain limited by
their actual animation callbacks. Motion still follows elapsed time: raising the
frame rate adds intermediate poses rather than making gestures run faster.
Stalls get one bounded update, without a burst of catch-up draws, and resuming
discards hidden time. Existing stable spring stepping remains in use.

The speech watchdog now resets the mouth within the current animation frame
without drawing the same frame twice. Explicit Stop and playback reset still
draw the closed mouth immediately. Hidden, paused and minimized avatars continue
to stop rendering and cursor polling.

## Observed native results

These short Windows checks used the actual assistant renderer, HD enabled,
125% display scaling and no voice model, microphone or online requests. The
normal window was 320 x 350 logical pixels, with a 600 x 623 backing canvas.

At that same resolution, idle rendering rose from **20.02 to 60.06 draws/sec**.
The observed 95th-percentile spacing between draw updates fell from **50.1 ms to
16.7 ms**. Whole-machine CPU rose from **3.69% to 10.45%** on this 16-logical-CPU
machine. More frequent rendering has a real CPU cost.

| Normal-size phase | Draws/sec after change | 95th-percentile spacing |
| --- | ---: | ---: |
| Idle | 60.06 | 16.7 ms |
| Movement preview | 60.24 | 16.8 ms |
| Thinking | 59.90 | 16.8 ms |
| Hidden | 0 | No draws |

The largest supported window, 640 x 700 logical pixels with a 1200 x 1279 HD
canvas, measured 59.73 draws/sec idle, 54.57 during the movement preview and 57.45
while thinking. Its preview still missed some frame deadlines: 95th-percentile
spacing was 33.3 ms. The new target is not a guarantee of 60 FPS under every
window size, GPU or background workload. HD resolution and artwork were not
reduced to obtain these results.

Measurements count renderer draws and observe draw-count changes at browser
animation callbacks. They are not GPU presentation timings. Each visible phase
lasted about six seconds, and the hidden phase about three seconds. CPU and
working-set counters include the verification process and Chromium children;
the monitoring probe adds some overhead. Background workloads can affect the
comparison. The baseline thinking phase used a different canvas size, so it is
not used as a CPU comparison here. There is no new measurement of GPU utilization
or concurrent TTS inference.

## Verification

All **53 JavaScript tests** passed, including cadence at 30–165 Hz, small vsync
jitter, bounded stalls, invalid timestamps, elapsed motion time, previews and
stable physics. The native polish check passed normal completion, Stop, output
playback cancellation, conversation states, pause/hide/minimize, hidden-page
visibility, reload and shutdown at the new rate. The silent preview capture now
requests 60 FPS. It does not supply synthetic mouth movement or start audio.

```powershell
node --test tests/*.test.mjs
.\.venv\Scripts\python.exe scripts/check_avatar_polish.py

# Measure the current renderer with isolated settings:
.\.venv\Scripts\python.exe scripts/measure_avatar_fps.py --label after
.\.venv\Scripts\python.exe scripts/measure_avatar_fps.py --label after --width 640
```

For future comparisons, run `--label before` before editing the renderer. The
harness fixes the test window size, uses a temporary conversation store and
preferences, and opens windows without taking keyboard focus. Reports stay
ignored under `.cache/avatar-fps/`. It does not read API keys, saved chats or
normal preferences.

Suggested commit: `perf: raise avatar rendering to 60 fps`
