# Desktop Companion

A small Windows desktop companion built in Python with PySide6. We are building
this one step at a time, following the character, voice, and memory brief.

## What Jingliu can do

**Talk in character**
- She is **Jingliu**, always in character: reserved, composed, quietly warm. Her profile lives in
  [character.toml](character.toml); you can edit her or add other characters ([guide](docs/character-guide.md)).
- **Models:** Claude through your Claude subscription (the local Claude Code CLI, no API key;
  Sonnet 5.5 by default, also Opus 5.5, Haiku 5.5 and Fable 5.1), Codex with your ChatGPT plan, or
  OpenRouter. Your choice is remembered ([model providers](docs/model-providers.md)).
- **Images and files:** paperclip, paste a screenshot (Ctrl+V) or drag files in: images, PDFs,
  text and code ([details](#share-images-and-files)).
- **She can look at your screen:** ask "what do you think of this?" or "can you see this error?" and she
  takes a screenshot of the monitor you are using and answers about it, or press the monitor button
  in the message box to attach one yourself. Her own windows are left out of it, it always shows in
  the chat, and Settings → App → **Let her look at my screen when I ask her to** turns her asking off.

**Remember, remind, keep history**
- **Memory:** "remember that I take my tea without sugar" — she saves it, and can also keep lasting
  preferences on her own (Settings → App). Every change shows in the chat with **Undo**; manage all in
  **⋯ → Memories** ([details](#asking-her-to-remember)).
- **Reminders:** "remind me at 7 to study", "every weekday at 8, remind me to stretch". She tells
  you herself when one is due, even after a restart; **⋯ → Reminders** lists them ([details](#reminders)).
- **Conversations** are saved locally. **⋯ → History** has search, dates, a glimpse of each chat and
  a delete button on every conversation; **Context** keeps notes for long chats.

**Voice**
- **Speaks her replies** in two voices (Settings → Voice): **Pocket TTS**, quick on the CPU, or
  **Chatterbox**, a more human version of her own voice in a calm delivery (best on the NVIDIA GPU; it
  loads in the background and prepares her next sentences while she speaks) ([details](#try-her-voice)).
- **Talk to her:** hold the microphone or press **Ctrl+Alt+Space**, or turn on hands-free; speech is
  transcribed locally ([details](#talk-through-your-microphone)).
- **Talk over her:** in hands-free mode she stops speaking when you start, and what you say becomes your
  next turn. Her own voice from the speakers is told apart from yours by how loudly each reaches the
  microphone, so with headphones any normal voice works; with speakers, speak up a little. Turn it off
  in Settings → Voice → **Hands-free: talk over her to interrupt**.

**A living desktop avatar** (Live2D, [guide](docs/experimental-live2d.md))
- She **chooses her own expressions** as she talks (smile, blush, shy, laugh, surprised, a one-eye
  wink, nods…), with lip-sync to her voice.
- **She has a life:** greets you, has idle moments, glances at your cursor, grows drowsy and falls
  asleep with drifting "Zzz", and wakes when you come back. **Pet her** by stroking her head.
- **While she works on a task** she looks focused, reads, types and checks the screen, with a small
  panel showing her current step, and a burst of ice crystals when she finishes.
- **Test every animation** in **Settings → Avatar → Animation tester**, or right-click her → **Expression → Test all animations…**.
- Drag to move; the corner grip resizes her in proportion. Smooth and flicker-free, and she uses
  fewer frames (less CPU) while idle or asleep.

**Do things on your computer** ([guide](docs/computer-tasks.md))
- Ask casually ("my desktop is a mess") or type `/do …`. She proposes a plan and waits for your yes —
  click **Yes, do it** or just say so. Files, folders, programs, the web, and the screen, mouse and
  keyboard, through Claude Code on your plan.
- She **asks before** running commands, changing files or clicking and typing — or turn that off in
  Settings → App to let her work without asking. **Stop** cancels at any time.
- **Undo any task:** the task card's **Undo**, "undo that" in chat, `/undo`, or **⋯ → Recent tasks**
  for the last 7 days. You see exactly what will be reversed first.

**The app**
- A moonlit **Jingliu theme** with a matching title bar, few buttons, and everything else in **⋯**.
- In **Windows Search / Start** as **Jingliu**; lives in the **system tray** when closed (Quit from there).
- Settings are remembered as you change them; your data stays on this PC under `data/`.
- **Back up, restore, export:** Settings → App → Your data. A backup is one zip with your conversations,
  memories, reminders, shared files, settings, characters and her profile; restoring first saves what
  you have now to `data/backups`. **Export as text** writes one readable Markdown file.
- **Start with Windows** (quietly, in the tray) and **gentle check-ins** (off by default: a greeting that
  fits the time of day when you arrive or come back after two hours away, and a nudge to rest after
  about three hours at the computer) are in Settings → App.
- **Light in the background:** hidden in the tray with the avatar off, it uses about 11 MB of memory ([details](#running-in-the-background)).

**Chat commands:** `/do <task>` · `/undo` · `/remember <fact>` · `/forget <number>` · `/memories`

**Moonlit window design:** the chat window uses a Jingliu-inspired night-and-frost
theme with message bubbles and formatted replies (bold, lists, code). Where the
older guides below name a button:

| Older name | Now |
| --- | --- |
| **New** | **+** in the top-right corner |
| **History**, **Memories**, **Context**, **Settings**, **Suspend** | the **⋯** menu |
| **Hold to talk** | the microphone in the message box (it turns red while listening) |
| **Hands-free** | the headset button next to the microphone |
| **Speak replies** | the speaker button in the header (also in Settings → Voice) |
| **Stop** | the red stop button, shown only while something can be stopped |

### Share images and files

Click the paperclip, paste a screenshot (Ctrl+V),
or drag files onto the window. Up to six per message: images (PNG, JPG, GIF,
WebP, BMP), PDFs, and text or code files. She sees them with that message;
later messages keep a short "[Attached …]" note, so they are not resent each
turn. Copies are kept locally in `data/attachments/` (Git-ignored) so they still
show in History, and deleting a conversation deletes them too. Large images are
downscaled first. With Claude, images and PDFs are read directly. OpenRouter
needs a vision-capable model. Codex accepts images and text files, not PDFs.

Avatar settings (shown or hidden, animation, size, position, movement, gaze,
hair, doze-off delay) are remembered as soon as you change them, like the model
and character. The mouse wheel scrolls Settings without changing a list or
slider you pass over; click one first to adjust it with the wheel. On Windows 11
the title bar matches the night theme.

Status messages share one line under the message box. Settings is split into
**Companion**, **Voice**, **Avatar** and **App** tabs. **Reload .env + character**
is under **App**.

The natural-animation upgrade is at **checkpoint 5: integrated into the assistant**.
Open **Start Mira.cmd**, enable **Show desktop avatar** and **Animate avatar** in
Settings, then move the cursor while she is idle. She occasionally glances toward
it, returns to rest, and varies small head turns with pauses. Listening and
thinking keep her focused; actual voice playback adds subtle nods. Settings now
include **Occasionally look toward my cursor**, **Gaze intensity** and **Hair
response**. Click **Save defaults** to keep your choices.
See the [integration and verification guide](docs/avatar-motion-checkpoint5.md).
**Preview Head Motion.cmd** remains a separate comparison and rig-review tool;
its pointer tracking stays within the preview page.

**Experimental rigged model:** Jingliu now has a **visual model** selector in
Settings. Choose the imported **Jingliu - Live2D (Bailyovo)** rig to test authored
left/right and up/down head turns, hair physics, blinking and playback lip-sync.
Choose **AI portrait (current)** to restore the existing avatar immediately.
Personality, voice and memories stay with the same character. More local Live2D
models can be added to the selector. See the
[experimental Live2D guide](docs/experimental-live2d.md) for setup, controls and credits.

**She has a life of her own:** on the Live2D model, Jingliu now greets you when
the app opens and has small idle moments: smiles, sighs, gazing at the moon. She
reacts when clicked, and grows drowsy and falls asleep (with drifting "Zzz") when
left alone. Talking to her, clicking her or resting the pointer on her wakes her
up. The AI now chooses her expressions as it replies (blush, shy, smile, laugh,
surprised, sad, pout, nod and more) using silent cues that never appear in the
text or speech. **Pet her** by stroking the pointer back and forth over her head
(no click): she closes her eyes happily, leans into it and slowly blushes. You can also pick one from the avatar's right-click
**Expression** menu. Choose the delay in **Settings → Avatar → Doze off when left alone**. See
[life, sleep and reactions](docs/experimental-live2d.md#life-sleep-reactions-and-idle-moments).

**AI portrait rig experiment:** choose **AI v5 layered rig (experimental)** in
the same selector to try the approved AI avatar with separate head/neck, hair
and earring surfaces, depth-based turns and hair follow-through. Use **Preview
movement** to compare. This is a bounded 2.5D experiment; fine part edges still
need art cleanup. See the [AI layered rig guide](docs/ai-layered-rig.md).

**Avatar artwork tools:** PhotoCraft's local MCP server can edit artwork copies
and layered PSDs in a dedicated authoring folder. See the
[PhotoCraft MCP setup](docs/photocraft-mcp.md) for connection and verification.
The [layer-preparation checkpoint](docs/jingliu-layer-preparation.md) now has an
editable v5 master, a 23-part PSD and real comparison/part previews. This artwork
is prepared separately from the avatar currently running in the assistant.
The [local rig MCP](docs/avatar-rig-mcp.md) adds compact inspection, keyform edits,
rig generation, validation and pose-sheet previews for saved Inochi files.
The [standalone head-rig checkpoint](docs/jingliu-head-rig.md) includes the revised
23-part rig, twelve inspection poses and instructions for testing it in Creator.
The [eye-rig checkpoint](docs/jingliu-eye-rig.md) extends it to 29 parts with
separate irises/lids, independent blinking and clipped gaze. It includes an
editable PSD and twelve close-up poses, still separate from the running assistant.
The [mouth-rig checkpoint](docs/jingliu-mouth-rig.md) adds separate lips, teeth,
tongue, opening/form controls and subtle jaw movement, with rest-image preservation.
The [idle-motion checkpoint](docs/jingliu-idle-motion.md) adds automatic blink
tracks, small head pauses and native hair physics, with short MP4 review clips.
Double-click **Preview Jingliu Rig.cmd** for the separate
[interactive rig viewer](docs/jingliu-interactive-viewer.md): manual head/eye/mouth
controls, animation playback, hair-physics comparison and individual part views.
It implements a validated inspection subset of the saved rig and remains
separate from the running assistant.

**Motion polish:** Settings now has **Calm**, **Natural**, and **Lively** presets,
plus a silent **Preview movement** button. Manual slider changes show **Custom**.
The preview ends on its own or stops when conversation, playback, hiding or
pausing needs priority. See [avatar polish](docs/avatar-polish.md) for details.

## Response model and HD avatar

In **Settings → Response model**, choose **OpenRouter**, **Claude subscription via
Claude Code** or **ChatGPT subscription via Codex**. For Claude, sign in to the
Claude Code CLI (or click **Sign in to Claude**); **Claude Sonnet 5.5** is the
default and no API key is used. Your provider and model choice is remembered
automatically. For Codex, click
**Sign in to ChatGPT**, then **Check connection / models** and choose a model. **Save defaults** keeps the selection. Character,
voice, avatar and the current conversation stay in place when switching models.
See [model providers](docs/model-providers.md) for setup, limits and verification.

**HD rendering** is on by default for a sharper portrait. It preserves the approved
artwork and can be turned off in Settings to reduce graphics load.
See [HD rendering](docs/avatar-hd.md) for before/after pixel sizes and limits.

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
In Settings, scroll to **Avatar size**, **Movement intensity**, **Lip-sync
sensitivity**, **Gaze intensity** and **Hair response**; changes apply immediately
(motion controls ease smoothly), and **Save defaults** keeps them.
The resize grip's actual dimensions are saved too. Hidden avatars stop drawing;
the visible, animated avatar now targets **60 FPS** during idle, previews and
conversation. See the [60 FPS change and measurements](docs/avatar-fps.md).
HD resolution stays the same. See the earlier
[motion integration measurements](docs/avatar-motion-checkpoint5.md) and the earlier
[idle performance comparison](docs/avatar-performance.md) for their test conditions.

See the [Stage 7 guide](docs/avatar-stage7.md) for measured resource use,
verification, and replacing the rig with your own character. The earlier balanced-renderer run
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
- Jingliu's local reference voice, a preview button, automatic speech toggle,
  volume control, and **Read last reply**.
- Streamed audio playback through your Windows default output device.
- A reusable background speech process: models load only when needed and stay
  ready between normal requests. Stop cancels loading and playback; a new
  message also stops the previous voice.
- Hold-to-talk microphone recording, input selection, and an input level meter.
- A Windows global shortcut: **Ctrl+Alt+Space** starts or finishes recording.
- Local English transcription with Faster-Whisper on CPU using INT8 computation.
- Editable transcripts, optional automatic sending, and interruption of current replies.
- Automatic SQLite conversation storage, restart recovery, and a History page with search,
  dates, last-message previews and a delete button on every conversation.
- Memories she keeps when you ask ("remember that…") and, optionally, on her own, each shown
  in the chat with Undo; plus add, edit, pin, and delete controls and local commands.
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
   **8–15 seconds** without music. Existing profiles without a recording retain
   their configured voice; the editor no longer offers alternative stock speakers.
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
4. Optionally double-click **Add Jingliu to Start Menu.cmd**, then type
   "Jingliu" in Windows Search or the Start menu to open her, or pin her from there.
   **Create Desktop Shortcut.cmd** adds the same **Jingliu** shortcut to the desktop.
   Both open the companion directly without a console window. Start Mira.cmd may briefly show one.

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
TTS_VOICE=reference
TTS_ENABLED=true
TTS_VOLUME=70
TTS_RATE=100
TTS_REFERENCE=voices/jingliu-reference.wav
STT_MODEL=base.en
STT_AUTO_SEND=true
STT_MICROPHONE=
```

If `.env` is missing, copy `.env.example` to `.env` first. `.env` is excluded
from Git. Do not paste your key into chat or commit it. Environment variables
take precedence over `.env` values if you already set them in your shell.
The Jingliu recording is local and excluded from Git; restore it at the configured
path or choose your local WAV in Settings. Missing voice audio leaves text chat
usable and reports a voice setup message instead of selecting another speaker.

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
affection, boundaries, and sixteen original conversation examples. Her reserved
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
preferences or developments by asking her to remember them, in **Memories**, or with
`/remember`. She is instructed to acknowledge
missing context and distinguish fictional lore from actual shared conversations.
Ordinary affectionate exchanges stay in character, without unsolicited AI-emotion
disclaimers. Explicit questions about the app's real identity still get an honest answer.

The [editing guide](docs/character-guide.md) covers every profile field, selection,
legacy Markdown support, and memory behavior. The [sample conversations and manual
checks](docs/character-samples.md) cover excitement, frustration, teasing, affection,
disagreement, summaries, and restarts. Exact phrasing is generated by the model.

## Let her do things on your computer

Ask in conversation, even casually ("my desktop is a mess with all these screenshots"),
or type `/do <task>`. She proposes a concrete plan and waits for your yes: click **Yes,
do it**, or just say "yes" or "go ahead", or answer with changes. Turn confirmation off in
**Settings → App** if you'd rather she starts clear requests right away. She works through Claude Code on your Claude plan:
- **Free:** reading files, searching and looking at the screen.
- **Asks you first:** running commands, changing files, and clicking or typing.

You answer each request with **Allow once**, **Allow all … for this task** or **Deny**, and
**Stop** cancels a task. To let her work without asking, turn off **Ask before she runs commands or
uses the mouse and keyboard** in **Settings → App** (or turn tasks off entirely there).

Every task can be **undone**: press **Undo this task** on its card, ask her ("undo that"), type
`/undo`, or open **⋯ → Recent tasks** (the last 7 days, also after a restart). You see exactly what
will be reversed before anything happens. See [computer tasks](docs/computer-tasks.md).

## Try her voice

**Two voice engines.** **Settings → Voice → Voice engine** switches between them,
and the choice is remembered:
- **Pocket TTS** (default): fast and light. It starts speaking almost at once and
  runs on the CPU.
- **Chatterbox** (Resemble AI): more human-sounding, in a calm, composed style
  chosen in listening tests. It runs from its own environment; run
  **Setup Chatterbox.cmd** once (the first use downloads about 3 GB). On this
  laptop's RTX 4060 each sentence takes about 1.5× its length to prepare, so she
  pauses briefly before each one. On the CPU it is much slower.

1. Launch the app, open **Settings**, and click **Preview**. This works without an OpenRouter key.
2. The first preview downloads the English speech model and selected voice from
   Hugging Face into `.cache/huggingface/` in this project. It can take a few
   minutes. Subsequent previews reuse cached files.
3. The voice control shows only **Jingliu's voice**, using her local recording.
   Alternative stock speakers have been removed from Settings and the character
   editor. **Use character voice** restores the profile's recording at 100%
   delivery. **Choose reference WAV** lets you replace the recording deliberately.
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
The character file's `[voice]` section sets its recording and delivery rate.
A selected local recording takes priority over an old stock-speaker preference;
an existing selected recording and its delivery adjustment are preserved. Clearing
a recording leaves reference mode unconfigured instead of switching speakers.
The local Pocket TTS model remains installed to generate speech; removing speaker
choices does not delete shared model weights or your recordings.
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
default. Look for the moon icon, including under the hidden-icons arrow.
Click the icon to reopen the conversation, or right-click for **Show companion**,
**Hide to tray**, **Settings**, **Suspend/Resume**, and **Quit**.

**Light in the background.** While the window is hidden or minimized, the app hands its idle
memory back to Windows after 30 seconds (and again every 10 minutes); it returns by itself when you
open the window. A hidden avatar is fully unloaded after 15 seconds and reloads in a few seconds
when shown. While the window is hidden, the voice and microphone engines close once they have
gone unused for 10 minutes; while it is open they stay loaded. The voice loads in the background
when the app starts and when you open the window (Pocket takes about 20 seconds from cold), so a
reply rarely waits for it. Measured: about 1.7 GB in use with the window and avatar open, about
11 MB with both hidden. Reminders still arrive.

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

### Reminders

Ask her in your own words: "remind me at 7 to study", "in 20 minutes tell me to take a break",
"every weekday at 8, remind me to stretch". She knows the current date and time, works out when,
and confirms in character; a line such as **Reminder set: "Study" · Today, 19:00** appears with
**Cancel**. Repeats can be daily, weekdays or weekly. If the time is unclear, she asks.

When one is due she tells you herself, in the chat and aloud, as soon as she is not busy with a
reply or a task; a Windows notification appears too when the window is hidden in the tray.
Reminders are saved, so ones that came due while the app was closed are delivered when it opens
(those missed by more than 12 hours are only listed). "Cancel my stretching reminder" works in
chat, and **⋯ → Reminders** lists everything upcoming with a remove button.

### Asking her to remember

Tell her in your own words, as with other assistants: "remember that I take my tea
without sugar", "don't forget my exam is on the 3rd", "keep in mind I'm vegetarian".
She answers in character and saves a short note through a silent `[[remember: …]]`
cue; "forget that" or "the exam got cancelled, forget it" removes the closest match
through `[[forget: …]]`. Every change appears in the chat as a small line, such as
**Memory saved: "Takes tea without sugar."**, with **Undo**. Nothing is saved if the
reply fails, and she declines to store passwords, PINs and card numbers.

**Settings → App → Let her remember important things on her own** (on by default,
remembered immediately) also lets her save lasting preferences, life facts, goals
and how you like her to behave when you mention them, sparingly and never small
talk or moods. Turn it off and she saves only when asked. Memories she saves are
pinned, like `/remember`, and can be edited in **Memories**.

Use **Memories** to add, inspect, edit, pin, and delete individual facts or
preferences. A memory is limited to 1,000 characters. Pinned memories
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
feat: add experimental layered depth rig for AI Jingliu
```
