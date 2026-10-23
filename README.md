# Desktop Companion

A small Windows desktop companion built in Python with PySide6. We are building
this one step at a time, following the character, voice, and memory brief.

## Jingliu desktop avatar (Stage 7 complete)

The approved v5 portrait now displays in the assistant's floating desktop window,
with idle blinking, breathing and hair motion. Open **Start Mira.cmd**, then
**Settings → Show desktop avatar**. Drag to move, use the bottom-right grip to
resize, or right-click for chat and reload controls. **Animate avatar** pauses
idle motion. Her mouth now follows actual local TTS playback, including silence
and Stop. This uses audio amplitude. Listening now shows an attentive posture;
thinking uses a focused half-lidded expression, with smooth transitions.

To check lip-sync, leave **Animate avatar** enabled and click **Preview voice**
at a nonzero volume, then try **Stop** during speech. See the
[Stage 5 guide](docs/avatar-stage5.md) for timing, tests and limitations.
See the [Stage 6 guide](docs/avatar-stage6.md) for conversation cues and checks.
In Settings, scroll to **Avatar size**, **Movement intensity**, and **Lip-sync
sensitivity**; changes apply immediately, and **Save defaults** keeps them.
The resize grip's actual dimensions are saved too. Hidden avatars stop drawing;
visible rendering is capped near 30 FPS.

See the [Stage 7 guide](docs/avatar-stage7.md) for measured resource use,
verification, and replacing the rig with your own character. The native run
observed about **9.1% whole-machine CPU while visibly idle**, **19.5% during local
speech**, and **0.6% while hidden** on this 16-thread machine, including the loaded
TTS process. These are short measurements, not performance guarantees.

See the [Stage 4 guide](docs/avatar-stage4.md) for setup, local character
assignments, fallback behavior and native verification. A fresh environment needs
the updated `requirements.txt` (or run **Setup Mira.cmd**) and restored local rig.
The separate **Preview Jingliu Avatar.cmd** remains available for rig review.

See the [Stage 3 guide](docs/avatar-stage3.md) for the local exports, visual review,
test results and Studio editing instructions. Artwork and rig files remain local
and Git-ignored under `.cache/mesh-avatar-studio/projects/jingliu/`.

## Step 14: create and switch characters

Implemented:

- A desktop chat window with streaming OpenRouter responses.
- Nemotron 3 Ultra (free) as the default model.
- An editable [Jingliu character profile](character.toml), with restrained warmth,
  dry humor, and a gradual romantic interest in the user.
- A character editor: describe a personality, attach a local voice recording,
  preview the voice, and save. Add or edit characters without application code.
- A saved character selector with separate chat histories and voice preferences.
- Recent conversation context (up to 12 exchanges, bounded to 48,000 characters).
- Stop, new conversation, and reload settings controls.
- Background API work so the window stays responsive, including during cancellation.
- Clear messages for missing keys, rate limits, network failures, and interrupted streams.
- Local Pocket TTS speech on CPU, with phrases queued while the text reply streams.
- Voice preparation overlaps language-model generation; queued phrases play in order.
- Eight built-in English voices, a preview button, automatic speech toggle,
  volume control, and **Read last reply**.
- Streamed audio playback through your Windows default output device.
- A reusable background speech process: models load only when needed and stay
  ready between normal requests. Stop cancels loading and playback; a new
  message also stops the previous voice.
- Hold-to-talk microphone recording, input selection, and an input level meter.
- A Windows global shortcut: **Ctrl+Alt+Space** starts or finishes recording.
- Local English transcription with Faster-Whisper on CPU using INT8 computation.
- Editable transcripts, optional automatic sending, and interruption of current replies.
- Automatic SQLite conversation storage, restart recovery, and a History manager.
- Explicit memories with add, edit, pin, and delete controls, plus local commands.
- Bounded memory retrieval: up to 6 relevant or pinned records, totaling at most
  3,000 characters, accompany each model request.
- System tray controls to show, hide, suspend, resume, open settings, and quit.
- A compact conversation window with a separate Settings window.
- Saved audio, microphone, memory retrieval, and close-to-tray preferences.
- Single-instance protection so launching again does not create another hidden companion.
- Conversation-specific continuity notes: write, generate, inspect, edit, save, or clear.
- Incremental summary drafts from older exchanges using the configured OpenRouter model.
- Saved summaries accompany future replies while recent exchanges remain full messages.
- An opt-in Hands-free button with local speech detection and pause-based turn endings.
- Turn-based listening: microphone closed during replies and playback, with a quiet delay before listening resumes.
- Adjustable pause duration, bounded audio buffers, and automatic idle timeout.
- An optional floating desktop mascot with local animation and visible activity states.
- Click to reopen chat, drag to reposition, and a context menu for existing app controls.
- Saved avatar visibility, animation, and monitor position, with a reset control.
- Double-click launch, setup, diagnostic, and desktop shortcut scripts for Windows.
- Offline startup checks and minimal error logs that omit credentials and conversations.
- Structured personality, reactions, relationship preferences, and original dialogue examples.
- Stable character instructions alongside memories and summaries, with explicit fictional/real continuity rules.
- Suppression of common marked action cues during streaming speech and replay.

The selected character and their latest opened conversation resume when you launch the app. **New** starts
another conversation and keeps the previous one in **History**. Summaries are
generated on request and saved explicitly after review.

### Add your own character

1. Restart the app, then open **Settings > Add character**.
2. Enter a name and describe their personality, background, speaking style,
   relationship with you, and reactions. Include sample dialogue if you like.
3. Choose a clean **3–30 second PCM WAV** of one English speaker, ideally
   **8–15 seconds** without music. A recording is optional; you can use a built-in voice.
4. Click **Preview voice**, then **Save and use character**.

Use the character dropdown in **Settings** to switch, or **Edit character** to
change the active description and recording. Each character keeps its own chats,
summaries, and voice settings. Explicit **Memories** are shared user-managed records.
Your existing chats are assigned to the active character on the first upgraded launch.

Profiles and copied recordings live in `data/characters/`, excluded from Git.
Creating and editing needs no API call; the description accompanies your normal
online chat requests. Recordings and speech synthesis stay local. Voice resemblance
depends on the sample and model; an exact actor match is not guaranteed.
See the [character guide](docs/character-guide.md) and an editable
[description example](examples/character-description.toml). The
[reference-voice guide](docs/reference-voice.md) covers first-time model access.

## Run on Windows

**Already installed?** Double-click **Start Mira.cmd**. It uses this project's
`.venv` without activating Python. Your existing `.env`, settings, and history
continue to work.

For a new installation:

1. Install **64-bit Python 3.11 or 3.12** from [python.org](https://www.python.org/downloads/windows/).
2. Double-click **Setup Mira.cmd**. It creates `.venv`, installs CPU PyTorch and
   the required packages, and checks native engine imports. Internet is needed
   for installation; voice and recognition models download when first used.
3. Add your OpenRouter key to `.env` locally, then double-click **Start Mira.cmd**.
   Setup copies `.env.example` only when `.env` is missing. It preserves an
   existing `.env`, your `data` folder, preferences, and model caches.
4. Optionally double-click **Create Desktop Shortcut.cmd**. The shortcut opens
   the companion directly without a console window. Start Mira.cmd may briefly show one.

Quit the companion before rerunning setup to repair or update dependencies. Setup refuses
to delete a broken or incomplete `.venv`; rename that folder and rerun setup.
These scripts run from the source folder; this is not yet a standalone executable.
Keep the folder in its final location. If you move it, recreate the virtual
environment ([Python's guidance](https://docs.python.org/3/library/venv.html)),
then remove or rename the old desktop shortcut before creating a new one. The
shortcut creator refuses to overwrite a shortcut pointing somewhere else.

For manual installation, use PowerShell in this folder:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install torch --index-url https://download.pytorch.org/whl/cpu
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Open `.env` in your editor and fill in your key locally:

```dotenv
OPENROUTER_API_KEY=your_key_here
OPENROUTER_MODEL=nvidia/nemotron-3-ultra-550b-a55b:free
CHARACTER_PROFILE=character.toml
TTS_VOICE=alba
TTS_ENABLED=true
TTS_VOLUME=70
TTS_RATE=100
TTS_REFERENCE=
STT_MODEL=base.en
STT_AUTO_SEND=true
STT_MICROPHONE=
```

If `.env` is missing, copy `.env.example` to `.env` first. `.env` is excluded
from Git. Do not paste your key into chat or commit it. Environment variables
take precedence over `.env` values if you already set them in your shell.

Then launch:

```powershell
.\.venv\Scripts\python.exe -m companion
```

Type a message and press **Enter**. Use **Shift+Enter** for a new line. You can
edit `.env` or `character.toml` while the app is open and choose **Settings →
Reload .env + character**.
Use **New** when testing a changed personality from a clean conversation.
Saved memories can still apply to new conversations; manage them in **Memories**.

The API model ID includes the `nvidia/` prefix. `#providers` is part of the model
webpage URL and must not be included in the API request.

### Check setup or troubleshoot startup

Double-click **Check Setup.cmd** to inspect Python, pinned packages, configuration,
saved preferences, storage access, database schema compatibility, and native engine
imports. The report never prints your API key or conversation contents. Checks
run offline without model downloads, microphone access, or API requests. A configured
key still needs a real chat request to verify its validity and provider availability.

Warnings allow launch, including offline use without a key. Errors must be fixed
before the windowed launcher proceeds. Normal launches run the quick checks;
Check Setup.cmd adds isolated native engine imports. Equivalent terminal commands:

```powershell
.\.venv\Scripts\python.exe -m companion.doctor
.\.venv\Scripts\python.exe -m companion.doctor --engines --json
```

Unexpected launcher failures produce a message box and a minimal record in
`data/startup-error.log`: timestamp, stage, and exception class only. It omits
exception messages, tracebacks, keys, and chat text. Logs rotate after about
64 KiB, retaining one previous file. For terminal output, use the existing
`.\.venv\Scripts\python.exe -m companion` command.

**Try it:** say “Explain recursion using a tiny example,” then “Make that simpler.”
The second reply should refer to the first. Try **Stop** during a reply as well.
Only the visible portion of an interrupted answer is used in later context.
Failed turns with no answer stay visible but are excluded from later context.

## Talk with Jingliu

The active [character.toml](character.toml) contains her identity, fictional
background, traits, interests, likes/dislikes, opinions, speaking style, reactions,
affection, boundaries, and fourteen original conversation examples. Her reserved
manner draws on the [official trailer](https://www.youtube.com/watch?v=fMiYAEj46Rc)
and [game dialogue](https://honkai-star-rail.fandom.com/wiki/Jingliu/Voice-Overs).
Her warmer romantic interest in you is an editable companion adaptation.

Open **Settings > Edit character**, change the description or recording, then
**Save and use character**. To edit TOML directly, use **Open profile file**,
save your edits, then **Reload .env + character**. A TOML profile's name takes precedence over the old `COMPANION_NAME`
entry, so an existing `.env` naming Mira needs no changes. The existing launcher
filenames also continue to work. Choose and preview a voice in Settings, then
**Save defaults** to keep later adjustments to that character's voice.

Every reply receives the profile separately from conversation notes and relevant
memories. A restart keeps the current conversation; **New** starts with the same
character and selected memories, without the previous chat's notes. Save real
preferences or developments in **Memories** or with `/remember`; automatic
personal-memory extraction has not been added. She is instructed to acknowledge
missing context and distinguish fictional lore from actual shared conversations.

The [editing guide](docs/character-guide.md) covers every profile field, selection,
legacy Markdown support, and memory behavior. The [sample conversations and manual
checks](docs/character-samples.md) cover excitement, frustration, teasing, affection,
disagreement, summaries, and restarts. Exact phrasing is generated by the model.

## Try her voice

1. Launch the app, open **Settings**, and click **Preview**. This works without an OpenRouter key.
2. The first preview downloads the English speech model and selected voice from
   Hugging Face into `.cache/huggingface/` in this project. It can take a few
   minutes. Subsequent previews reuse cached files.
3. Choose a voice and preview it again. The available voices are `alba`, `anna`,
   `azelma`, `cosette`, `eponine`, `fantine`, `jane`, and `vera`.
   **Use character voice** applies Jingliu's recommended **Jane at 94% delivery**.
   This aims for a calmer, slightly lower English delivery using a stock voice;
   it does not reproduce her game's actor. Preview it and adjust to your taste.
   For a voice conditioned on a recording instead, use **Choose reference WAV**.
   See the [reference-voice setup guide](docs/reference-voice.md) for recording
   requirements and access to the full Pocket TTS model. This workspace has a
   [prepared local Jingliu reference](docs/jingliu-reference.md), excluded from Git.
   The full model and local CPU reference synthesis are verified here, including
   an offline check. Listen to the generated previews to judge the voice match.
4. Leave **Speak replies** checked to hear answers as phrases become available. Use **Stop** at
   any time, or **Read last reply** to hear an answer again.

The selected voice, toggle, and volume controls apply immediately. Click **Save
defaults** in Settings to keep them and the delivery rate after restarting. Saved preferences override
audio defaults in `.env`; reloading keeps the saved preferences while refreshing
your API key, model, name, and character. Existing `.env` files do not need
updating; defaults apply when entries are absent. Volume changes stop current playback; the new
volume applies to the next preview or reply. A volume of zero skips synthesis.
The **Delivery** slider ranges from 80% to 115%. Below 100% slows playback and
lowers pitch together; 100% restores the original voice. It applies consistently
to Preview, streamed replies, and Read last reply. Changing it stops current
playback and discards queued phrases. `TTS_RATE` sets the unsaved startup default.
The character file's optional `[voice]` section recommends a voice and rate;
the button applies it explicitly, without automatically replacing a saved choice.
Changing the voice, volume, or turning speech off stops the current reply's
speech queue. Enabling speech again applies to the next response; use **Read
last reply** after generation finishes to replay the current answer.

Fenced code blocks and raw URLs are omitted from speech. Very long answers are
spoken as a short preview of up to about 2,400 characters; the full text stays
visible. Complete sentences are queued as text arrives, and long paragraphs
can break at a shorter phrase boundary. The final unfinished phrase is queued
once the text stream finishes. Common abbreviations, decimals, inline code,
links, and code fences are handled across text chunks.

The voice begins preparing when you send a message. The first spoken phrase can
play before the language model finishes writing; first-use downloads, loading,
or a very short response can still make audio begin after all the text arrives.
There is no promise of a fixed response time. One speech process keeps the voice
loaded and plays each phrase once, in order.

To check streaming, leave **Speak replies** on and ask for a detailed explanation
in several sentences. Watch the text continue while earlier sentences play.
Then start recording or click **Stop**: current playback and queued phrases
should stop, and none of them should resume in the next turn. Speech errors
leave the text stream running. **Read last reply** deliberately replays the answer.

The app tracks fully played phrases. If speech is interrupted, recent context
includes those completed phrases and a note that part of the current phrase
may also have played; it does not claim you heard the complete answer. The full
visible text remains available in the conversation.

**Stop** terminates the speech process, so the next spoken request reloads the
model into RAM from its disk cache. Normal completed requests keep the model
and voice states loaded. **Suspend** or **Quit** releases the speech process too.
Voice playback failures are shown above the talk button; text chat remains
available. Check your Windows default output device if you hear nothing.

## Talk through your microphone

1. Hold **Hold to talk**. Wait for **Listening** before you speak, then release
   the button to finish. You can also press **Ctrl+Alt+Space** once to start
   recording and again to finish, even while using another app. This brings
   the companion's window forward so you can see the recording status.
2. Recording stops after 60 seconds. Starting a recording stops the companion's current
   voice and interrupts any response she is still generating.
3. The microphone closes before local transcription starts. The first spoken
   turn downloads the English model into `.cache/whisper/`; later turns reuse it.
4. The recognized text appears in the input box and is sent automatically when
   **Send transcription automatically** is checked. Uncheck it to edit each
   transcript before sending. If you already have a draft, transcription is
   appended and always waits for you to press **Send**.
5. **Stop** cancels recording or transcription and discards pending recognition.
   Silent or very short recordings do not send a message.

In **Settings**, choose **Refresh** to list input devices, then select a microphone if the Windows
default is not the one you want. The level meter should move while you speak.
If the microphone cannot open, check **Settings > Privacy & security > Microphone**
in Windows and allow desktop apps to use it. A conflicting global shortcut is
reported in the window; the hold button remains available.

The default `STT_MODEL=base.en` balances size and English recognition quality.
Choose `tiny.en` in Settings for a smaller model or `small.en` for a larger one. `STT_AUTO_SEND`
sets the startup checkbox. Leave `STT_MICROPHONE` blank for the Windows default,
or set it to an input device index or a name accepted by sounddevice. Device
indices can change after reconnecting hardware. Existing `.env` files continue
working without these settings. Use **Save defaults** to retain your current selections.

Audio stays in memory, is limited to one minute for manual recording, and is never written to a recording
file or uploaded. Only the resulting text is sent to the language model when
you send a message. Cancelling transcription terminates its process; the next
turn reloads the model from the disk cache. Normal turns keep it ready in RAM.

## Hands-free turns

Click **Hands-free** beside **Hold to talk** to start an explicit listening session.
Wait for **Hands-free listening** before speaking. Speech detection runs locally
using the Silero VAD model bundled with Faster-Whisper; it needs no extra download.
The level meter and status text show when the microphone is active and when speech
has been detected.

1. Say one sentence, then pause. By default, a pause of about **1.2 seconds** finishes
   the turn. In **Settings**, choose **0.8**, **1.2**, or **1.8 seconds** and click
   **Save defaults** to retain the setting. A little leading audio is kept in memory
   to preserve the beginning of speech.
2. The microphone closes before local transcription starts. With **Send transcription
   automatically** checked, the recognized text follows the normal chat flow.
3. The microphone stays closed while the companion generates or speaks. After the reply and
   playback both finish, the app waits another **0.8 seconds** before listening again.
   This avoids recording the companion's own reply; it does not implement acoustic echo cancellation.
4. Click **End hands-free** to end the listening session. An existing reply can finish.
   Click **Stop** to end the session and cancel current recording, transcription,
   generation, or playback too. Stop also cancels a queued return to listening.

For an offline check, uncheck automatic sending in Settings first. Hands-free will
capture one turn and leave the transcript editable, then turn itself off. This
review mode needs no API key once the recognition model is cached. An existing draft
must be sent or cleared before starting hands-free. A new typed draft while waiting
for a reply also prevents automatic listening from resuming.

Hands-free is **off on launch** and never starts automatically from saved preferences.
Hiding or minimizing the main window, opening Settings or a conversation manager,
Suspend, and Quit turn it off. Resume does not restart it. Microphone, transcription,
voice, or API failures also turn it off without retrying. No speech for **30 seconds**
ends the session; a detected utterance is limited to **30 seconds**. Empty recognition
does not send a message. The audio callback queue is bounded; capture overruns fail
the turn rather than sending incomplete audio.

Use a quiet room: nearby people, a TV, or other apps' audio can trigger speech
detection. It has no wake word or speaker identification. You cannot interrupt the companion
by speaking while the microphone is closed. **Hold to talk** or **Ctrl+Alt+Space**
exits hands-free, starts a manual recording, and interrupts the current reply.
Voice activity detection is local; only submitted transcript text goes to OpenRouter.

## Running in the background

Closing the main window keeps the companion running in the Windows notification area by
default. Look for the purple face icon, including under the hidden-icons arrow.
Click the icon to reopen the conversation, or right-click for **Show companion**,
**Hide to tray**, **Settings**, **Suspend/Resume**, and **Quit**.

Hiding the window cancels recording or transcription and clears any pending
automatic send. An existing text reply and its speech can continue in the
background. Hands-free is turned off and must be started again explicitly. The
global recording shortcut brings the window forward for manual recording again.

**Suspend** stops generation, recording, transcription, and playback, and releases
the local audio model processes. While suspended, sending, previews, and the
recording shortcut do nothing. **Resume** re-enables them; interrupted work does
not restart automatically. Suspension lasts for the current session.

Choose **Quit** to save the latest reply and fully exit. Alternatively, uncheck
**Keep running in the system tray when I close the window** in Settings. If Windows
does not provide a tray, closing the window exits normally. Launching a second
copy displays a reminder to use the existing tray icon.

**Check it:** open Settings, change volume, and click **Save defaults**. Close
the main window and reopen it through the tray. Try Suspend and Resume, then
choose Quit and launch again: your saved volume and conversation should return.

Settings changes apply immediately; **Done** closes the settings window. **Save
defaults** writes only nonsecret preferences to `data/preferences.json`, which
is excluded from Git. Your API key remains in `.env`. To return to `.env` audio
defaults, quit the app, delete `data/preferences.json`, and relaunch. A damaged
preferences file produces a warning and falls back to `.env`; Save defaults
replaces it with valid settings.

## Desktop avatar

Open **Settings**, check **Show desktop avatar**, and click **Save defaults** if
you want it to appear after restarting. The avatar is off by default. Its graphics
are rendered locally; enabling it works without an API key, does not load audio
models, and does not start recording.

- **Click** the mascot to open the existing chat window. Your draft and conversation
  stay intact, and clicking it does not start listening.
- **Drag** it to move it around the desktop. Use **Settings → Save defaults** after
  dragging to keep the position across restarts. Unsaved movement lasts for the session.
- **Right-click** for Open chat, Settings, Stop, Suspend/Resume, Reset position,
  Hide avatar, and Quit. Stop and Suspend use the same controls as the chat window.
- **Show desktop avatar** in the tray menu also toggles visibility. Closing the
  avatar itself hides it; choose **Quit** to exit the whole app.

The simple fallback mascot's badge distinguishes Ready, Opening mic, Listening, Transcribing, Thinking,
Writing, Summarizing, Loading voice, Speaking, Suspended, Needs attention, and Closing.
The mouth follows levels from actual speaker output, with no movement during voice
preparation. Colors and text distinguish activity; detailed errors remain
in the chat window. The avatar uses your configured companion name in its tooltip.

The mesh portrait shows idle motion and mouth movement from actual local speaker
playback. Loading a voice or generating text alone does not open its mouth. Its
tooltip reflects activity. Listening and thinking have restrained visual cues;
expression controls stay separate from the text sent to TTS.

Uncheck **Animate avatar** for a static portrait. The fallback mascot's timer also stops while
the avatar is hidden, suspended, closing, or showing an error. Save defaults retains
your animation choice. The avatar stays available when chat is hidden in the tray;
the existing rule that hiding chat ends hands-free listening still applies.

Saved coordinates are kept inside an available monitor if displays change. **Reset
position**, in Settings or the avatar menu, returns it to the lower-right corner of
the chat window's monitor. Quit removes the floating window and its animation timer.

**Quick check without an API key:** enable the avatar, drag it, and save defaults.
Close chat into the tray, click the avatar to reopen it, then try Suspend and Resume.
Quit and relaunch to check that its position and animation preference return.

## Saved conversations and memory

Messages, memories, and conversation summaries are stored in `data/companion.sqlite3`. The database is
local SQLite storage, is not encrypted, and is excluded from Git. The app does
not put your API key or microphone recordings into this database.

Use **History** to reopen or delete an earlier conversation. The full visible
conversation is restored. Model requests include up to 12 recent answered exchanges
and any summary you have saved for that conversation. Recent exchanges occupy at
most 32,000 characters, reserving 16,000 for your next message within the existing
48,000-character budget. Character instructions, memories, and the summary are
additional system context. Large exchanges can reduce the number of recent pairs.
The assistant cannot independently search the archive; reopen a conversation
to discuss its context. Merely reopening it does not make an API call
or play its audio again.

Streaming replies are checkpointed about every half-second and finalized at the
end of a turn. After an unexpected exit, the latest saved partial reply appears
as interrupted; up to the most recent half-second may be missing. Failed turns
remain visible in History, and unanswered failures are excluded from model
context. A save failure is reported in the window; a failed final save can be
retried before the next message or when closing.

Use **Memories** to add, inspect, edit, pin, and delete individual facts or
preferences. Save is explicit: the companion does not silently extract a profile from
ordinary conversation. A memory is limited to 1,000 characters. Pinned memories
are preferred across topics; unpinned memories are selected by word overlap with
your current message and recent user messages. Retrieval is deliberately simple
and does not use embeddings. If many memories are pinned, only a bounded subset
fits in each request.

Uncheck **Include relevant saved memories in online replies** in Settings to
skip memory retrieval for future requests. This keeps the saved records available
in Memories; click **Save defaults** to retain the choice. Facts already present
in recent conversation context still accompany that conversation. Start **New**
for a conversation without that previous context. The toggle does not retract
an active request or remove anything already sent to a provider.

These commands also work without an API key:

```text
/remember I prefer intuition and examples before formal explanations.
/memories
/forget 1
```

`/remember` saves a pinned memory and displays its number. `/memories` opens the
manager. `/forget` deletes the memory with that number. Command confirmations
are local and are not included in subsequent model context. Deleting a memory
does not delete the original conversation or messages containing that fact;
delete the conversation from History if you also want those removed. Neither
deletion retracts data already sent to an online provider.

**Check persistence:** save a preference with `/remember`, open **Memories** to
confirm it, start a new conversation, and ask a question where that preference
matters. Quit through the tray and relaunch: the conversation and memory should remain.
Then edit or delete the memory and check that the next response uses the changed
record. No new API request is made by the memory manager itself.

For a backup, **Quit** through the tray and copy the `data` folder. Keep it separate from
source-code commits. Quitting first ensures pending writes and SQLite's temporary
transaction files have settled.

## Keep older conversation context

Open **Context** to inspect or write continuity notes for the selected conversation.
Notes can hold earlier decisions, constraints, or unfinished tasks after their
original messages fall outside recent context. They apply only to this conversation;
**Memories** remains the separate place for preferences shared across conversations.

1. For a quick check in a short chat, open **Context**, write “We chose Python and
   local voice for this project,” and click **Save**. Ask what you chose earlier.
   Writing, editing, and clearing notes work without an API key.
2. In a longer chat, watch the context hint above the toolbar. When older exchanges
   fall outside recent context, **Generate draft** becomes available. It makes one
   online request using your configured model and key. It sends the current notes
   plus a batch of older answered exchanges; it does not send independent saved
   memories, local memory commands, or unanswered failed turns.
3. Review and edit the generated notes, then click **Save**. Generation alone does
   not change the saved summary. Drafts are not spoken or inserted into the chat
   transcript. Closing Context discards unsaved draft changes.
4. If older exchanges remain, generate another draft. Each batch merges the current
   notes with the next unsummarized exchanges. You can review several batches before
   saving; the saved summary remains unchanged until you click Save.
5. Use **Clear saved** to remove the summary. Original messages and explicit memories
   remain. Start **New** to confirm the summary does not follow you into another chat.

Summaries are limited to 6,000 characters. Each source batch contains at most 24,000
characters of serialized older exchanges, plus the previous notes. An oversized
exchange uses marked beginning/end excerpts, reported in the Context window; some
details will be omitted. Generated notes can also contain mistakes, so keep exact
details that matter by editing the draft. Later corrections and recent messages take
precedence in the model instructions.

**Cancel**, **Stop**, **Suspend**, starting a recording, or closing a generating
Context window cancels the summary request. API failures and oversized output keep
your saved notes, draft edits, and coverage unchanged. Quitting waits for cancellation.
There are no automatic summary requests during normal chat.

Saved summaries accompany online replies even when saved memory retrieval is off;
that toggle controls the separate Memories collection. Clear the summary to stop
including those notes. This does not retract data already sent to a provider.
Summaries survive restarts, and deleting a conversation from History deletes its
summary too. Existing databases upgrade automatically while preserving chats and memories.

## Data and provider behavior

Typed or submitted transcribed messages, character instructions, and recent context are sent to
OpenRouter and the selected model provider. Selected saved memories and the current
conversation's saved summary are included with those requests too. Generating a
summary sends its source exchanges and current notes to that same provider.
The free Nemotron endpoint's provider notice says requests
are logged for security and product improvement, and asks users not to send
confidential or personal data. See the
[model page](https://openrouter.ai/nvidia/nemotron-3-ultra-550b-a55b:free).

Speech synthesis and playback happen locally. Initial model and voice downloads
need internet access; generated reply text is not sent to a speech service.
Model caches are excluded from Git. Speech uses a CPU model; the app never
initializes CUDA for speech. Recording occurs after you press the talk button,
use the recording shortcut, or explicitly start a Hands-free session. Hands-free
listens between turns while the window is visible; it starts off each launch.

Free endpoints can be rate limited or temporarily unavailable. The app uses
only the configured model and does not switch to a paid model. Stop cancels the
local request and closes its connection; upstream cancellation depends on the
provider. The app does not display or retain separate reasoning fields.

## Publishing privacy

Local credentials, conversations, recordings and generated working assets stay
Git-ignored. A publishing check also reviews tracked history and commit identities;
the included push hook and GitHub workflow help catch accidental exposure.
See [publishing safely](docs/publishing-safely.md) for the commands and limits.

## Next steps

1. **Voice interruption** — acoustic echo cancellation for speaking during playback.
2. **Distribution** — a standalone Windows build without a separate Python installation.

## Verification

Tests use mocked HTTP streams, fake microphone capture, and small fake local
processes. They do not require an API key, access your microphone, download
models, or play audio. Storage tests use isolated in-memory or temporary databases:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Windows launcher tests use temporary project folders and shortcut files inside
`artifacts`; they do not create a shortcut on your Desktop or install packages.

API integration follows OpenRouter's
[quickstart](https://openrouter.ai/docs/quickstart) and
[streaming reference](https://openrouter.ai/docs/api_reference/streaming).

Speech follows the [Pocket TTS Python API](https://kyutai-labs.github.io/pocket-tts/API%20Reference/python-api/).
Local recognition follows [Faster-Whisper](https://github.com/SYSTRAN/faster-whisper).
Voice activity detection uses its [bundled Silero VAD implementation](https://github.com/SYSTRAN/faster-whisper/blob/v1.2.1/faster_whisper/vad.py).

Suggested commit for this step:

```text
feat: add avatar controls and verify performance
```
