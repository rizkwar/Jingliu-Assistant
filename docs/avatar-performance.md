# Lower idle rendering cost

The avatar now targets **20 FPS while waiting** and **30 FPS while listening,
thinking or speaking**. The higher rate also continues for one second after a
state, control, visibility or size change so transitions can settle. Actual
playback levels raise the rate even if the conversation state arrives later.
This applies to both HD and balanced rendering; pixel sizes and artwork stay
the same. No additional setting or dependency is needed.

Frame deadlines tolerate display jitter without steadily losing frames. Animation
uses elapsed time rather than a frame counter, bounded to 100 ms after a stall.
Resume starts a fresh clock, so hidden time cannot produce a burst of catch-up
draws. Existing playback resets, sequence checks and the silence watchdog remain
in place. Hidden, suspended and paused avatars still stop their animation loop.

## Observed comparison

Measured on 2026-10-23 on this Windows machine with 16 logical processors,
320 by 350 logical pixels, HD enabled, and a **600 by 623** backing canvas.
Each phase ran for approximately eight seconds. These runs used no voice model,
microphone or online inference; they measure the test application's process tree.

| Phase | Before CPU | After CPU | Before draws/sec | After draws/sec |
| --- | ---: | ---: | ---: | ---: |
| Idle, first sample | 9.63% | 5.22% | 29.44 | 20.01 |
| Thinking | 9.90% | 6.31% | 29.48 | 30.04 |
| Idle, second sample | 9.31% | 5.40% | 29.61 | 20.07 |
| Hidden | 0.44% | 0.16% | 0 | 0 |

CPU percentages use the entire machine as 100%. The two idle samples averaged
about **9.5% before and 5.3% after**. CPU frequency, graphics scheduling and
background workloads vary; the unchanged-rate thinking sample also used less
CPU, so the entire observed reduction cannot be attributed to fewer idle draws.
The directly verified change is roughly one-third fewer idle draws at the same
resolution. These short samples are not a guaranteed percentage improvement.

Working sets did not decrease: idle samples were approximately 573–582 MiB before
and 600–609 MiB after. This sums process working sets, potentially counting shared
pages more than once; it is neither private memory nor GPU memory. This change
reduces rendering work, rather than unloading the renderer or cached voice.

Before/after native screenshots were inspected for sharpness. The original
portrait and texture sampling are unchanged. The compromise is fewer idle motion
frames; conversation animation retains the higher rate.

## Verification and reproduction

The deterministic JavaScript tests cover idle versus active rates, delayed state
delivery, interaction holds, 60/144 Hz display jitter, elapsed time, stalls and
resume. Native checks cover every activity group, expression changes, mouth
reset, stale state rejection, suspension and reload. The existing local-speech
benchmark checks real playback and interruption, three mocked conversation turns,
resizing, saved controls, five reloads, zero hidden draws and child-process exit.
All native checks passed for this change, along with 19 focused Python tests
and 12 JavaScript tests covering conversation states, quality and frame cadence.

To compare a future renderer change, run this before editing, then again after:

```powershell
.\.venv\Scripts\python.exe scripts/measure_avatar_rendering.py --label before
.\.venv\Scripts\python.exe scripts/measure_avatar_rendering.py --label after
```

Close extra assistant instances first. Each command opens a temporary native
window and uses empty in-memory chat storage and temporary preferences. Counters,
canvas dimensions and screenshots stay in `.cache/avatar-rendering-*.json/png`.
It does not change your normal conversations, preferences or credentials.

The broader cached-voice check remains:

```powershell
.\.venv\Scripts\python.exe scripts/measure_avatar.py
```

It explicitly selects the mocked OpenRouter transport for its synthetic turns,
regardless of your saved provider. It does not use your Codex subscription.
Its report identifies HD mode, so newer measurements can be distinguished from
the older balanced-renderer figures in the Stage 7 guide.

Suggested commit: `perf: reduce avatar idle rendering cost`
