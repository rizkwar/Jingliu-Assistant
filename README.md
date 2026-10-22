# Desktop Companion

A small Windows desktop companion built in Python with PySide6. We are building
this one step at a time, following the character, voice, and memory brief.

## Step 1: character + text conversation

Implemented:

- A desktop chat window with streaming OpenRouter responses.
- Nemotron 3 Ultra (free) as the default model.
- An editable character in [character.md](character.md), provisionally named Mira.
- Recent conversation context (up to 12 exchanges, bounded to 48,000 characters).
- Stop, new conversation, and reload settings controls.
- Background API work so the window stays responsive, including during cancellation.
- Clear messages for missing keys, rate limits, network failures, and interrupted streams.

Voice, microphone input, tray operation, and saved memory are future steps.
Nothing records your microphone in this version. Conversations are held in RAM
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

## Data and provider behavior

Typed messages, the character instructions, and recent context are sent to
OpenRouter and the selected model provider. Local conversation storage is not
implemented yet. The free Nemotron endpoint's provider notice says requests
are logged for security and product improvement, and asks users not to send
confidential or personal data. See the
[model page](https://openrouter.ai/nvidia/nemotron-3-ultra-550b-a55b:free).

Free endpoints can be rate limited or temporarily unavailable. The app uses
only the configured model and does not switch to a paid model. Stop cancels the
local request and closes its connection; upstream cancellation depends on the
provider. The app does not display or retain separate reasoning fields.

## Next steps

1. **Next: Pocket TTS** — audition a voice and speak typed replies locally.
2. **Microphone conversations** — push-to-talk and Faster-Whisper transcription.
3. **Persistent companion** — SQLite history, manageable memory, and tray support.
4. **Natural interaction** — speech detection, interruption handling, and optional avatar.

## Verification

Tests use mocked HTTP streams and do not require an API key or make API calls:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

API integration follows OpenRouter's
[quickstart](https://openrouter.ai/docs/quickstart) and
[streaming reference](https://openrouter.ai/docs/api_reference/streaming).
