# Jinger

A Windows desktop companion built with Python and PySide6: a character who chats with you, speaks
with her own voice, listens through your microphone, lives on your desktop as an animated Live2D
avatar, remembers what matters, reminds you of things, and can do tasks on your computer. The
current character is **Jingliu**, always in character: reserved, composed, quietly warm.

## What she can do

**Talk in character**
- Her profile lives in [character.toml](character.toml); you can edit her or add other characters
  ([character guide](docs/character-guide.md)).
- **Models:** Claude through your Claude subscription (the local Claude Code CLI, no API key;
  Sonnet 5.5 by default, also Opus 5.5, Haiku 5.5 and Fable 5.1), Codex with your ChatGPT plan, or
  OpenRouter. Your choice is remembered ([model providers](docs/model-providers.md)).
- **Images and files:** paperclip, paste a screenshot (Ctrl+V) or drag files in: up to six images,
  PDFs, text or code files per message.
- **She can look at your screen:** ask "what do you think of this?" or "can you see this error?" and
  she takes a screenshot of the monitor you are using (her own windows left out) and answers about
  it. The monitor button in the message box attaches one yourself.

**Remember, remind, keep history**
- **Memory:** "remember that I take my tea without sugar". She saves it, and can also keep lasting
  preferences on her own. Every change shows in the chat with **Undo**; manage them in **⋯ → Memories**.
- **Reminders:** "remind me at 7 to study", "every weekday at 8, remind me to stretch". She tells you
  herself when one is due, even after a restart; **⋯ → Reminders** lists them.
- **Conversations** are saved locally. **⋯ → History** has search, dates, rename and delete;
  **⋯ → Context** keeps notes for long chats.

**Voice**
- **Speaks her replies** with **Pocket TTS** (quick, on the CPU) or **Chatterbox** (more human, best
  on an NVIDIA GPU), both from her own reference recording ([reference voice](docs/reference-voice.md)).
- **Talk to her:** the microphone button, **Ctrl+Alt+Space** from anywhere, or hands-free mode
  (the headset button), which listens for a pause to end your turn. Speech is transcribed locally.
- **Talk over her:** in hands-free mode she stops speaking when you start. Works best with headphones;
  with speakers, speak up a little. Switch it off in Settings → Voice.

**A living desktop avatar** ([Live2D avatar guide](docs/live2d-avatar.md))
- She **chooses her own expressions** as she talks (smile, blush, laugh, wink, nods…), with lip-sync.
- She greets you, has idle moments, glances at your cursor, falls asleep when left alone and wakes
  when you come back. **Pet her** by stroking her head with the pointer.
- While she works on a task she looks focused, and a small panel shows her current step.
- Drag to move; the corner grip resizes her. **Settings → Avatar → Animation tester** plays every animation.

**Three kinds of conversation**, each with its own tab above Settings: **Chats** (everyday, grouped by
Pinned / Today / Yesterday / Previous 7 days / Older), **Projects** and **Study**. Opening a conversation
shows its tab; New chat is an everyday chat.

**Study**
- A **subject** is a folder of study sessions that **share her memory**: in a new session she remembers what
  you covered in the others (your saved notes, or their last exchanges) and picks up from there.
- **Materials** she teaches and quizzes from (text and PDFs are read) and **how she teaches you**. Update a
  material any time: **Replace…** with a newer version, or when the original file changes, **Refresh** (or
  **Refresh all**) brings the new version in. She tutors in its sessions: explains step by step, checks
  your understanding and grounds answers in your materials.
- Above the message box: **Quiz me** (one question at a time, scored: *Quiz 4/5*), **Make flashcards**,
  **Explain simpler**, **Summarize**, and a **Focus timer** (25 minutes, or ask her: "let's focus for 40
  minutes"). When it ends she tells you herself and the minutes count toward the subject.
- **Flashcards** she makes are saved to the subject (Undo removes them). **Review** them with spaced
  repetition: Show answer (Space), then Again / Hard / Good / Easy (1–4), each showing when the card returns.
  The subject page shows progress: cards due, focus time this week, recent quiz accuracy.

**Projects**
- Keep ongoing work together: a project has its own **chats**, **instructions** she follows in every chat of
  it ("I'm a beginner, examples first"), **files** she knows (text, code and PDFs are read for her) and an
  optional **folder** where computer tasks start. Start one with **+** next to Projects in the sidebar.
- Right-click any chat → **Move to project**. The header shows *Project › Chat*; click the project to open
  its page. Deleting a project can keep its chats (they return to Recents).

**Tools from MCP servers** (Settings → Tools)
- Connect MCP servers (your notes, a calendar, GitHub, a database…): by command or URL, by pasting the JSON
  snippet from a server's instructions, or **Import from Claude** (Claude Code and Claude Desktop). **Test**
  shows a server's tools.
- Computer tasks can use every enabled server; its steps show in the task card and ask first unless you turn
  that off per server. Servers set to **Conversations and tasks** are also available while she replies with
  your Claude subscription, and each tool she uses shows as a small note in the chat.

**Do things on your computer** ([computer tasks](docs/computer-tasks.md))
- Ask casually ("my desktop is a mess") or type `/do …`. She proposes a plan and waits for your yes.
- She **asks before** running commands, changing files, or clicking and typing, unless you turn that
  off in Settings → App. **Stop** cancels at any time.
- **Undo any task:** the task card's **Undo**, "undo that", `/undo`, or **⋯ → Recent tasks** (7 days).

**The app**
- **A Codex-style window** under the moonlit sky: a sidebar with New chat, Memories, Reminders, Recent tasks
  and your conversations (right-click to **pin** one under a crescent, rename or delete it), **search**
  (Ctrl+K), a model picker and an **Approve for me** switch in the message box, and copy / read aloud under
  each reply. Select part of a reply and right-click → **Quote in reply**. Her messages can be plain text
  or bubbles (Settings → App → Window). Shortcuts: Ctrl+N new chat, Ctrl+B sidebar, Ctrl+, settings.
- Lives in the **system tray** when closed (Quit from there); in Windows Search / Start as **Jingliu**.
- **Start with Windows** (quietly, in the tray) and **gentle check-ins** (off by default: a greeting
  that fits the time of day, and a nudge to rest after about three hours) in Settings → App.
- **Back up, restore, export** in Settings → App → Your data.
- **Light in the background:** hidden in the tray with the avatar off, it uses about 11 MB of memory.

**Chat commands:** `/do <task>` · `/undo` · `/remember <fact>` · `/forget <number>` · `/memories`

## Get started

1. Install **64-bit Python 3.11 or 3.12** from [python.org](https://www.python.org/downloads/windows/).
2. Double-click **Setup Jinger.cmd**. It creates `.venv` and installs everything (internet needed;
   voice and speech-recognition models download on first use). It never overwrites an existing `.env`.
3. Double-click **Start Jinger.cmd**.
4. In **Settings → Response model**, sign in to Claude or ChatGPT, or put an OpenRouter key in `.env`.

The **More** folder has the other helpers:

| File | What it does |
| --- | --- |
| **Add to Start Menu.cmd** | Adds her to Start, so you can search for "Jingliu" and pin her to the taskbar. |
| **Create Desktop Shortcut.cmd** | The same shortcut, on the desktop. |
| **Setup Chatterbox.cmd** | Installs the Chatterbox voice engine (about 3 GB on first use). |
| **Setup Live2D.cmd** | Downloads the Live2D runtime used by the avatar. |
| **Check Setup.cmd** | Checks Python, packages, settings and engines, without network or microphone. |

Run setup again (with the app closed) to repair or update dependencies.

### Configuration

Most things are set in **Settings** and remembered as you change them (in `data/preferences.json`).
`.env` holds the rest; copy [.env.example](.env.example) if it is missing:

| Setting | Meaning |
| --- | --- |
| `OPENROUTER_API_KEY`, `OPENROUTER_MODEL` | Only needed for OpenRouter. |
| `CHARACTER_PROFILE` | The active character file (default `character.toml`). |
| `TTS_REFERENCE` | Her voice recording, e.g. `voices/jingliu-reference.wav` (kept out of Git). |
| `TTS_ENABLED`, `TTS_VOLUME`, `TTS_RATE` | Startup voice defaults. |
| `HF_TOKEN` | Optional Hugging Face token for the full Pocket TTS model. |
| `STT_MODEL`, `STT_AUTO_SEND`, `STT_MICROPHONE` | Speech recognition model, auto-send, and input device. |

Edit `.env` or `character.toml` while she is running, then **Settings → App → Reload .env + character**.

## Your data

Everything stays on this computer, in `data/` (conversations, memories, reminders, shared files,
settings, characters) and `voices/`. Neither is ever committed to Git.

- **Back up everything** writes one zip; **Restore from a backup** first saves what you have now to
  `data/backups`; **Export as text** writes every conversation as one readable Markdown file.
- What you send goes to the model provider you chose, with her profile, recent context, relevant
  memories and conversation notes. Speech synthesis and recognition are local.
- Audio from the microphone stays in memory and is never saved to a file.

## Troubleshooting

- **She does not start:** run **More\Check Setup.cmd**. A failed start writes a short record (no
  message text or keys) to `data/startup-error.log`. For full output, run
  `.\.venv\Scripts\python.exe -m companion` in this folder.
- **Avatar unavailable:** run **More\Setup Live2D.cmd**, check that the model files are in place
  ([Live2D avatar guide](docs/live2d-avatar.md)), and that graphics drivers are up to date.
- **No voice:** check the recording at `TTS_REFERENCE` and your Windows output device. Chatterbox
  needs **More\Setup Chatterbox.cmd** first.
- **Microphone does not open:** Windows Settings → Privacy & security → Microphone → allow desktop apps.
- **Moved the project folder:** recreate `.venv` (run **Setup Jinger.cmd** after renaming the old
  `.venv`), then run **More\Add to Start Menu.cmd** again. Start with Windows repairs itself.

## Project layout

```
companion/          the app
  app/              startup, tray, Start with Windows, hotkey, setup checks
  core/             settings, saved preferences, the database, backups
  chat/             model providers, prompts, memory notes, reminders, check-ins
  character/        character profiles and the saved-character library
  voice/            speech, the microphone, transcription, talk-over
  avatar/           the desktop avatar and its web renderer (web/)
  tasks/            computer tasks: runner, tools, undo journal, screen capture
  ui/               the main window, chat view, settings pages, theme
docs/               guides, and an example character (docs/examples/)
More/               extra launchers: shortcuts, voice and avatar setup, setup check
scripts/            what the launchers run, plus the publishing safety check
dev/                avatar development tools: rig/, qa/, previews/ (see dev/README.md)
tests/python/       Python tests, in the same folders as the app
tests/js/           tests for the avatar's JavaScript
data/, voices/, .cache/   your local data, voice recordings and model caches (Git-ignored)
```

## Development

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -t .
node --test tests/js/*.test.mjs
```

Tests use fake network streams, fake microphones and temporary folders: no API key, microphone,
model downloads or audio playback. Before publishing, the pre-push hook checks that no personal
data, secrets or local paths are in the history ([publishing safely](docs/publishing-safely.md)).
