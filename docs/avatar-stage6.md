# Stage 6: conversation states and restrained expressions

The existing assistant activity signal now drives a small set of visual cues.
These describe what the app is doing, rather than inferring emotion from user
messages. Character profiles, prompts, conversation history, summaries, memories
and speech text are unchanged. No animation tags enter TTS.

## Try it

Quit the running assistant and reopen **Start Mira.cmd**, then enable **Show
desktop avatar** and **Animate avatar** in Settings.

| What you do | What the portrait shows |
| --- | --- |
| Wait between turns | Neutral face, restrained breathing and hair movement. |
| Hold Talk, or start Hands-free | Attentive gaze and a small head inclination. |
| Wait for transcription, a reply, a summary, or voice preparation | A focused half-lidded expression and slight gaze shift. |
| Play Preview voice or receive a spoken reply | Neutral face with a trace of warmth and very small voice-driven head movement. The mouth still follows actual playback. |
| Stop or interrupt speech | Mouth returns to rest; the face follows the new activity. |
| Suspend | Mouth resets and the portrait freezes. Resume restores movement. |
| Encounter a conversation error | A calm neutral expression; read the actual error in the chat window. |

Brief preparation states may finish before an expression appears. This is
intentional: a 180 ms hold prevents flickering, and related states share a style.
Expressions blend through the pinned runtime's overlay; posture targets approach
their values smoothly. The cues are deliberately subtle for this portrayal of
Jingliu. No automatic winks, exaggerated surprise, blush, or broad grins are added.

Reduced motion keeps the current portrait static. Hiding, suspending or closing
the avatar stops its loop; returning to an active view uses the latest activity.
The existing simple mascot fallback retains its own activity cues.

## Implementation

- `CompanionWindow.activity_changed` remains the only conversation state source.
  `AvatarController` already forwards it to the active widget; the mesh host now
  publishes the normalized state through an `activityChanged` WebChannel signal.
  Each update has a sequence number, so older updates cannot overwrite a new one.
  When a renderer finishes loading, the host publishes its current state, covering
  activity changes that happened during loading or avatar replacement.
- `companion/avatar_web/conversation-state.js` contains the visual policy and
  transition logic separately from the playback code. It maps all existing states
  into idle, listening, thinking, speaking, attention and paused groups. Unknown
  states safely default to idle. Latest activity replaces a pending cue; there
  are no delayed expression callbacks that can fire after a reload or disposal.
- Only the pinned runtime's supported `neutral` and `halfLidded` expressions are
  used. Thinking reuses the approved half-closed eye artwork. Pose offsets are at
  most two degrees, with small gaze/brow offsets. A 0.75 parameter blend retains
  some natural idle movement; blinking and breathing still come from the runtime.
  Automatic random motions are disabled so they cannot introduce unrelated
  gestures. No artwork or voice has been replaced.
- `setTalkGain(0.12)` allows a small speaking nod only while actual nonzero playback
  levels set `setSpeaking(true)`. The activity cue alone cannot open the mouth.
  Visual poses contain no mouth parameters, leaving Stage 5 lip-sync in control.
  Pausing freezes the existing pose instead of jumping to another face.

## Verification

**242 Python tests** and **6 JavaScript policy tests** passed. Python tests cover
the existing conversation, memory, summary, recording, playback and avatar paths.
The JavaScript checks cover all states, unknown state names, transition holding,
rapid reversal, pose smoothing, bounds, expression names and mouth isolation.

Run the policy checks with the development machine's Node installation:

```powershell
node tests/avatar-state.test.mjs
```

Node is for this development check; the installed assistant does not start Node
or Studio to render the avatar.

A native Windows Qt check sent controlled activities through the actual window
signal and inspected renderer diagnostics for each group. Screenshots of idle,
listening, thinking, speaking and attention states were inspected, along with an
open-mouth preview driven by playback-level signals. Native assertions passed for
expression selection, resting mouth without audio, output-level lip-sync, stale
state rejection, rapid reversal, suspension/resume and state restoration on reload.
These checks used temporary empty storage and no microphone or API requests.

Local evidence stays ignored in `.cache/stage6-*.png`,
`.cache/stage6-verification.json` and `.cache/stage6-native-check.py`. The native
state check used controlled playback levels, rather than a new live TTS run;
Stage 5 records the live local TTS and interruption checks. Hardware resource
measurements and broader usability tuning remain Stage 7 work.

Suggested commit: `feat: add restrained avatar conversation expressions`

Next, after the user's **next**: Stage 7 controls, practical polish and measured
resource use.
