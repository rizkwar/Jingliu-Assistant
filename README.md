# Desktop Companion

A small Windows desktop companion built in Python with PySide6. We are building
this one step at a time, following the character, voice, and memory brief.

## Step 3: push-to-talk conversations

Implemented:

- A desktop chat window with streaming OpenRouter responses.
- Nemotron 3 Ultra (free) as the default model.
- An editable character in [character.md](character.md), provisionally named Mira.
- Recent conversation context (up to 12 exchanges, bounded to 48,000 characters).
- Stop, new conversation, and reload settings controls.
- Background API work so the window stays responsive, including during cancellation.
- Clear messages for missing keys, rate limits, network failures, and interrupted streams.
- Local Pocket TTS speech on CPU, starting after a complete text reply arrives.
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

Tray operation and saved memory are future steps. Conversations are held in RAM
and disappear when you close the app or start a new conversation.

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
edit `.env` or `character.md` while the app is open and click **Reload settings**.
Use **New conversation** when testing a changed personality from a clean context.

The API model ID includes the `nvidia/` prefix. `#providers` is part of the model
webpage URL and must not be included in the API request.

**Try it:** say “Explain recursion using a tiny example,” then “Make that simpler.”
The second reply should refer to the first. Try **Stop** during a reply as well.
Only the visible portion of an interrupted answer is used in later context.
Failed turns with no answer stay visible but are excluded from later context.

## Try her voice

1. Launch the app and click **Preview**. This works without an OpenRouter key.
2. The first preview downloads the English speech model and selected voice from
   Hugging Face into `.cache/huggingface/` in this project. It can take a few
   minutes. Subsequent previews reuse cached files.
3. Choose a voice and preview it again. The available voices are `alba`, `anna`,
   `azelma`, `cosette`, `eponine`, `fantine`, `jane`, and `vera`.
4. Leave **Speak replies** checked to hear completed answers. Use **Stop** at
   any time, or **Read last reply** to hear an answer again.

The selected voice, toggle, and volume controls apply during the current app
session. To set startup defaults, edit the `TTS_*` values in `.env` and click
**Reload settings**. Existing `.env` files do not need updating; defaults apply
when these entries are absent. Volume changes stop current playback; the new
volume applies to the next preview or reply. A volume of zero skips synthesis.

Fenced code blocks and raw URLs are omitted from speech. Very long answers are
spoken as a short preview of up to about 2,400 characters; the full text stays
visible. Speech currently starts after the language model finishes. Speaking
sentences while the language model is still writing belongs to the next step.

**Stop** terminates the speech process, so the next spoken request reloads the
model into RAM from its disk cache. Normal completed requests keep the model
and voice states loaded. Closing the window releases the speech process too.
Voice playback failures are shown beside the voice controls; text chat remains
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

Choose **Refresh** to list input devices, then select a microphone if the Windows
default is not the one you want. The level meter should move while you speak.
If the microphone cannot open, check **Settings > Privacy & security > Microphone**
in Windows and allow desktop apps to use it. A conflicting global shortcut is
reported in the window; the hold button remains available.

The default `STT_MODEL=base.en` balances size and English recognition quality.
Use `tiny.en` for a smaller model or `small.en` for a larger one. `STT_AUTO_SEND`
sets the startup checkbox. Leave `STT_MICROPHONE` blank for the Windows default,
or set it to an input device index or a name accepted by sounddevice. Device
indices can change after reconnecting hardware. Existing `.env` files continue
working without these settings; reload settings to apply edited startup defaults.

Audio stays in memory, is limited to one minute, and is never written to a recording
file or uploaded. Only the resulting text is sent to the language model when
you send a message. Cancelling transcription terminates its process; the next
turn reloads the model from the disk cache. Normal turns keep it ready in RAM.

## Data and provider behavior

Typed or submitted transcribed messages, character instructions, and recent context are sent to
OpenRouter and the selected model provider. Local conversation storage is not
implemented yet. The free Nemotron endpoint's provider notice says requests
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

1. **Faster spoken replies** — speak sentences as the language model streams them.
2. **Persistent companion** — SQLite history, manageable memory, and tray support.
3. **Natural interaction** — speech detection, echo handling, and optional avatar.

## Verification

Tests use mocked HTTP streams, fake microphone capture, and small fake local
processes. They do not require an API key, access your microphone, download
models, or play audio:

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
feat: add push-to-talk with local Whisper transcription
```
