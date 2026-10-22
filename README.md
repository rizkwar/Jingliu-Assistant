# Desktop Companion

A small Windows desktop companion built in Python with PySide6. We are building
this one step at a time, following the character, voice, and memory brief.

## Step 7: inspectable conversation summaries

Implemented:

- A desktop chat window with streaming OpenRouter responses.
- Nemotron 3 Ultra (free) as the default model.
- An editable character in [character.md](character.md), provisionally named Mira.
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

The latest opened conversation resumes when you launch the app. **New** starts
another conversation and keeps the previous one in **History**. Summaries are
generated on request and saved explicitly after review.

## Run on Windows

Use Python 3.11 or 3.12. From PowerShell in this folder:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Open `.env` in your editor and fill in your key locally:

```dotenv
OPENROUTER_API_KEY=your_key_here
OPENROUTER_MODEL=nvidia/nemotron-3-ultra-550b-a55b:free
COMPANION_NAME=Mira
TTS_VOICE=alba
TTS_ENABLED=true
TTS_VOLUME=70
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
edit `.env` or `character.md` while the app is open and choose **Settings →
Reload .env + character**.
Use **New** when testing a changed personality from a clean conversation.
Saved memories can still apply to new conversations; manage them in **Memories**.

The API model ID includes the `nvidia/` prefix. `#providers` is part of the model
webpage URL and must not be included in the API request.

**Try it:** say “Explain recursion using a tiny example,” then “Make that simpler.”
The second reply should refer to the first. Try **Stop** during a reply as well.
Only the visible portion of an interrupted answer is used in later context.
Failed turns with no answer stay visible but are excluded from later context.

## Try her voice

1. Launch the app, open **Settings**, and click **Preview**. This works without an OpenRouter key.
2. The first preview downloads the English speech model and selected voice from
   Hugging Face into `.cache/huggingface/` in this project. It can take a few
   minutes. Subsequent previews reuse cached files.
3. Choose a voice and preview it again. The available voices are `alba`, `anna`,
   `azelma`, `cosette`, `eponine`, `fantine`, `jane`, and `vera`.
4. Leave **Speak replies** checked to hear answers as phrases become available. Use **Stop** at
   any time, or **Read last reply** to hear an answer again.

The selected voice, toggle, and volume controls apply immediately. Click **Save
defaults** in Settings to keep them after restarting. Saved preferences override
audio defaults in `.env`; reloading keeps the saved preferences while refreshing
your API key, model, name, and character. Existing `.env` files do not need
updating; defaults apply when entries are absent. Volume changes stop current playback; the new
volume applies to the next preview or reply. A volume of zero skips synthesis.
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
   Mira's window forward so you can see the recording status.
2. Recording stops after 60 seconds. Starting a recording stops Mira's current
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

Audio stays in memory, is limited to one minute, and is never written to a recording
file or uploaded. Only the resulting text is sent to the language model when
you send a message. Cancelling transcription terminates its process; the next
turn reloads the model from the disk cache. Normal turns keep it ready in RAM.

## Running in the background

Closing the main window keeps Mira running in the Windows notification area by
default. Look for the purple face icon, including under the hidden-icons arrow.
Click the icon to reopen the conversation, or right-click for **Show companion**,
**Hide to tray**, **Settings**, **Suspend/Resume**, and **Quit**.

Hiding the window cancels recording or transcription and clears any pending
automatic send. An existing text reply and its speech can continue in the
background. The global recording shortcut brings the window forward again.

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
preferences. Save is explicit: Mira does not silently extract a profile from
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
initializes CUDA for speech. Recording only occurs after you press the talk
button or use the recording shortcut; there is no always-on listening.

Free endpoints can be rate limited or temporarily unavailable. The app uses
only the configured model and does not switch to a paid model. Stop cancels the
local request and closes its connection; upstream cancellation depends on the
provider. The app does not display or retain separate reasoning fields.

## Next steps

1. **Natural interaction** — speech detection and echo handling.
2. **Character presence** — an optional desktop avatar and activity states.

## Verification

Tests use mocked HTTP streams, fake microphone capture, and small fake local
processes. They do not require an API key, access your microphone, download
models, or play audio. Storage tests use isolated in-memory or temporary databases:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

API integration follows OpenRouter's
[quickstart](https://openrouter.ai/docs/quickstart) and
[streaming reference](https://openrouter.ai/docs/api_reference/streaming).

Speech follows the [Pocket TTS Python API](https://kyutai-labs.github.io/pocket-tts/API%20Reference/python-api/).
Local recognition follows [Faster-Whisper](https://github.com/SYSTRAN/faster-whisper).

Suggested commit for this step:

```text
feat: add reviewable conversation summaries and bounded continuity
```
