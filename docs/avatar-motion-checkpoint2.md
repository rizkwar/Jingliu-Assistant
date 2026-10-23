# Head and gaze experiment: checkpoint 2

The separate preview is ready. Double-click **Preview Head Motion.cmd** from the
project folder. It starts a read-only local server on port 8766 and opens the
comparison in your browser. Close its console to stop it. Node.js is required
for this development preview; no new packages or models are installed.

The left portrait runs the assistant's current `ConversationVisual` policy. The
right portrait runs a finite head/gaze study. Both use the approved playback
`.mavatar`, the exact vendored app runtime, HD texture sampling, equivalent
canvas sizes, the same draw cadence and the same synthetic speech levels. The
browser may give their natural blinks different timing.

## What to review

The 38.2-second animation sequence includes rest, left/right turns, returns to
center, up/down looks, combined turns/tilts, half-closed eyes and settled rest.
The sequence stops advancing at its end while normal breathing/blinking continue.

- **Replay sequence** starts the study again.
- **Pause** freezes elapsed animation time; Resume starts a fresh frame clock.
- **Silent speech test** drives both mouths with a synthetic envelope. It has no
  audio and does not test physical audio/display synchronization.
- **Check edges** uses a checker background to make silhouette defects clearer.

The head uses yaw +/-12, pitch +/-4 and roll +/-8 **rig parameter units**, not
physical degrees. Eye targets reach their destination over about 0.45 seconds;
head movement eases over 1.8–2.1 seconds, then holds. The smaller shoulder motion
follows with an exponential lag. The sequence uses the existing facial
deformation and hair physics, rather than rotating the whole portrait element.

Only head/body/gaze parameters are owned by the experiment. Blinking, breathing,
hair and mouth retain their existing runtime paths. This is a controlled pose
experiment, not the finished variable idle or conversational behavior. Cursor
attention remains checkpoint 4; app integration remains checkpoint 5.

## Inspection results and limitations

Native Qt WebEngine recording captured the two canvases together with their
timing preserved. Frames sampled through the recording and enlarged eye/face
crops were inspected. The experiment produces modest visible turns and tilts;
the inspected poses keep the neck/collar connected, without an obvious gross
mesh tear or open silhouette gap. This small range is suitable for further
review, not proof that every combined pose is artifact-free.

The half-closed eye asset still contains its iris, so gaze is less independent
during that expression. The frontal drawing also limits perspective and the
amount of genuinely new silhouette a turn can reveal. Hair follow-through is
restrained in this existing rig; the earring follows the head as an attached
part. These are checkpoint 3 review targets, rather than reasons to increase
motion until the portrait distorts.

No rig, masks, drawing, voice, memory or application response code was changed.
The earlier unfinished random-motion trial remains separate under `.cache/`;
this study intentionally uses predictable poses so visual comparisons are easier.

## Verification

Five JavaScript tests check both-direction/vertical coverage and bounds, eye
anticipation, body lag, consistent timing at 20/30/60 FPS, bounded stall recovery,
returns to rest and isolation from mouth/breath/eyelid controls:

```powershell
node tests/head-motion-study.test.mjs
```

Native checks passed for reaching planned poses, mouth overlap and release,
pause/resume, resizing, replay, hidden drawing stopping and resume. The renderer
reported no JavaScript console errors. HTTP checks verified that the preview
does not serve `.env`, chat files or arbitrary paths. It uses only allowlisted
assets, refuses writes and does not connect to a microphone or model provider.

Local review evidence lives in `.cache/head-motion-checkpoint2/`: a comparison
video, timestamped renderer samples, full preview screenshot, extracted frame
sequence and enlarged crops. These generated files and the rig remain ignored
by Git. Native recording may run longer than 38.2 wall-clock seconds under load:
individual simulation steps are capped at 100 ms to avoid unstable catch-up.
The video preserves that timing rather than speeding up PNG frames.

The preview targets 30 draws/second for the paired study. Two renderers and video
capture add work; their cost is not representative of one production avatar.
No new CPU/GPU/RAM savings or performance guarantee is claimed. Measurements of
the final single-avatar path belong to checkpoint 5.

Next: after **next**, checkpoint 3 reviews the combined poses, gaze and hair
more closely and makes only the rig/layer repairs justified by visible defects.

Suggested commit: `feat: add isolated head and gaze motion study`
