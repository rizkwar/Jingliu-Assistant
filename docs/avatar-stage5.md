# Stage 5: mouth movement from local speech playback

The mesh avatar now follows the assistant's actual speaker output. This is
**amplitude-based lip-sync**, using the existing drawn mouth shapes. It is not
English phoneme recognition. Personality, memory, text generation and voice
selection are unchanged; TTS still runs locally with Pocket TTS.

## Try it

1. Quit an older app instance from its tray menu and reopen **Start Mira.cmd**.
2. In **Settings**, enable **Show desktop avatar** and **Animate avatar**, select
   your usual voice, and choose a nonzero volume.
3. Click **Preview voice**. The mouth should rest during voice loading, move
   with the spoken line, and close after it ends. The first inference can take
   longer than subsequent lines.
4. Preview again and press **Stop** during speech. The audio stops and the mouth
   returns to rest. Also try ordinary spoken replies, silence between phrases,
   and starting a recording to interrupt a reply.

No new service, API key, model, voice recording or dependency is needed for this
stage. Reduced motion keeps the portrait static, including its mouth. Hiding or
reloading the avatar resets its mouth while preserving normal audio behavior.

## Audio and timing

`PocketSpeaker` still generates mono PCM with the selected local voice. The new
`audio_playback.play_chunks()` applies volume and clipping and prepares 20 ms
blocks at the **effective playback sample rate**, including the existing delivery
rate adjustment. Each prepared block carries a bounded RMS-derived level. A
bounded queue holds about half a second of PCM; generation can continue while the
output callback consumes it. Empty generation gaps output zeros, with zero levels.

The sounddevice callback fills the buffer from those prepared blocks. It appends
minimal bounded telemetry for the block it actually submits, using
`outputBufferDacTime - currentTime` to translate PortAudio's output schedule into
the shared monotonic clock. It does no JSON output, model inference, RMS analysis,
file access or waiting. A separate reporting thread sends level/timestamp events
through the existing speech subprocess protocol. No microphone input is used.

This follows [sounddevice's callback and DAC timing API](https://python-sounddevice.readthedocs.io/en/0.5.6/api/streams.html).
The stream's finished callback acknowledges that buffered samples have drained;
only then does the phrase report completion, preserving interruption context and
the existing streamed phrase order.

`SpeechController` validates telemetry, rejects other job IDs, and schedules
levels with a precise Qt timer. A busy UI skips obsolete frames instead of
replaying a backlog. Stop, failure, completion and replacement clear its timers
and pending levels. A watchdog closes the mouth if telemetry disappears.

The existing avatar controller forwards levels to the narrow WebChannel bridge.
The simple fallback mascot uses the same output levels instead of its old
timer-driven speaking mouth.
The renderer uses `setVoiceLevel()` and `setSpeaking()`, with the runtime's mouth
smoothing. Silence allows a short natural release; explicit cancellation resets
lip-sync and mouth parameters. Sequence numbers reject obsolete bridge updates.
Hide, reduced motion, disposal and reload also clear the mouth. No future mouth
animation is queued in JavaScript. Voice-driven head gestures remain disabled in
this stage; conversation expressions belong to Stage 6.

## Verified here

- All **242** offline regression tests passed, including new checks for post-volume
  RMS, clipping, sample order, padding, silent generation gaps, DAC scheduling,
  malformed telemetry, stale jobs, cancellation, completion and watchdog reset.
- A native Windows test generated and played a short line with the configured,
  cached local TTS voice in offline mode. The actual avatar opened its mouth during
  playback and rested afterward. A second live line was interrupted with Stop;
  its mouth returned to rest and a queued future update could not reopen it.
- Native visual checks also passed for mouth shapes, stale bridge sequence
  rejection, reduced motion and hide/show resets. The open-mouth preview was
  inspected in `.cache/stage5-mouth-preview.png`.
- The final live check observed 198 level events and 415 visual samples, with
  maximum mouth opening 0.914. The first sampled mouth opening above 0.1 followed
  the first delivered nonzero level by **78 ms**. This is a sampled software
  observation including bridge/render/smoothing delay; it is **not a measured
  physical speaker-to-display synchronization error**. Hardware/device differences
  and UI load can affect alignment; further tuning belongs to Stage 7.
- The `pythonw` application entry-point check loaded the avatar and exited normally
  using temporary empty storage. The earlier Windows breakpoint dialog was **not
  reproduced**, so its cause is still unconfirmed. No crash fix is claimed.

Local evidence remains Git-ignored: `.cache/stage5-verification.json`,
`.cache/stage5-launch-check.json`, screenshots and native check scripts. These
checks make no language-model requests and do not record microphone audio.

Suggested commit: `feat: sync avatar mouth with local speech playback`

Next, after the user's **next**: connect conversation states and restrained
expressions in Stage 6. Do not include expression tags in spoken text.
