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
  herself when one is due, even after a restart, in her own **Reminders** session at the top of your chats,
  never in the chat you are in: she says it aloud, and the session shows a count until you open it, where you
  can answer her. **⋯ → Reminders** lists the upcoming ones.
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
  when you come back. **Pet her** by stroking her head with the pointer. Asleep she is never a still
  picture: her head lolls and nods with her breath, she shifts to the other side, nuzzles, sighs and murmurs,
  dreams (a little bubble rises: ☾, ❄ or ♪), "z"s drift up, frost motes fall, and petting her makes small
  hearts float up. Settings → Avatar → Animation tester has Dream to see one.
- While she works on a task she looks focused, and a small panel shows her current step.
- Drag to move; drag her bottom-right corner to resize her. **Settings → Avatar → Animation tester** plays every animation.
- **Accessories** (Settings → Accessories, Live2D models): **glasses** rigged like a Live2D art mesh in her face's
  deformer: pinned to her face mesh, they turn, tilt and look up and down exactly as her face does, sit under
  her fringe, and stay put when she blinks: Teacher (reading glasses), Round, Rectangle, Oval or Half-rim, in silver, gold, black, glacial
  blue or crimson, with clear, moonlit-blue, rose or dark lenses.

**Three kinds of conversation**, each with its own tab above Settings: **Chats** (everyday, grouped by
Pinned / Today / Yesterday / Previous 7 days / Older), **Projects** and **Study**. Opening a conversation
shows its tab; New chat is an everyday chat.

**Study**
- A **subject** is a folder of study sessions that **share her memory**: in a new session she remembers what
  you covered in the others (your saved notes, or their last exchanges) and picks up from there.
- **Materials** she teaches and quizzes from (text and PDFs are read) and **how she teaches you**.
  **Link folder…** uses a folder of course materials where it is (PDF, Word, PowerPoint, text and code; nothing
  is copied, new files are picked up): each message she sees its list of files and only the passages related
  to it, which keeps replies fast and light. Or add files one by one, and update one any time: **Replace…** with a newer version, or when the original file changes, **Refresh** (or
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
- **Never silently stuck:** the card shows what she is doing between steps ("Thinking…", "Writing guide.md · 84
  lines…") with a timer. If she repeats a step, goes quiet for 4 minutes or one step runs over 5, she is
  stopped mid-step and told to try another way; stuck again, she reports what she finished. Type in the
  card's **Tell her something…** box to steer her while she works ("use the venv python").

**The app**
- **A Codex-style window** under the moonlit sky: a sidebar with New chat, Memories, Reminders, Recent tasks, Usage
  and your conversations (right-click to **pin** one under a crescent, rename or delete it), **search**
  (Ctrl+K), a model picker and an **Approve for me** switch in the message box, and copy / read aloud under
  each reply. Select part of a reply and right-click → **Quote in reply**. Her messages can be plain text
  or bubbles (Settings → App → Window). Shortcuts: Ctrl+N new chat, Ctrl+B sidebar, Ctrl+, settings.
- **Replies set like ChatGPT's**: smooth greyscale text (Settings → Window → Text rendering), roomy lines,
  `inline code` in rounded pills, files she cites shown with a file icon that **open the file** from your
  subject's materials, centred tables, links that open in your browser, and **math** from LaTeX
  (`$…$` in a line, `$$…$$` centred), drawn with a real math font, e.g. relational algebra like
  `R_1 \bowtie_{c} R_2 = \sigma_{c}(R_1 \times R_2)`. Scrolling up while she writes stays put; a round ↓
  brings you back to her latest words.
- **Code in its own box**: `</>` and the language or file name, icon buttons to **wrap long lines** and
  **copy** (it turns into a check), and colours for keywords, strings, comments and numbers.
- **No Windows title bar**, like Claude's app: her header is the title bar (drag it, double-click to maximize,
  drag to a screen edge to snap, hover maximize for Snap Layouts), with thin minimize, maximize and close
  buttons in its corner; the shadow, rounded corners and animations stay.
- **Light on your limits:** with your Claude subscription each chat continues its own session, so a reply processes
  only your new message and reads the rest from the prompt cache (about a tenth of the cost; in a test, replies after
  the first reused 93-96%). Her instructions stay the same from message to message; the time, reminders, memories
  and study passages travel with your message, and passages she already has are not sent again. A chat starts a
  fresh session when you edit or delete a message, change model, after a long pause, or when it grows large.
  **One mind, like Claude Code:** computer tasks run in the chat's own session, so what you discussed is in front of
  the task, and what the task read and found is in front of her when you talk afterwards. Typing in that chat while
  she works reaches her as you type it ("use the PDF folder too"). **Compacting:** when a chat grows long, her
  older exchanges become the chat's notes (on Haiku; see and edit them under Context) and she carries on from the
  notes and recent messages, with a small "Compacted" note in the chat. Reminders out of view, check-ins and
  summaries run on Haiku. Usage shows how much came from the cache.
- **Coding mode** (the **Coding** chip in the message box, per chat; on by itself in a project's chats): she reads
  your files herself, read-only and without asking, with search first and big files in parts, and a note lists
  what she looked at. It keeps more of the conversation in mind before compacting. Changing files and running
  commands still go through a task. Needs your Claude subscription.
- **Effort** (beside the model in the message box, or Settings): how hard she thinks. **Auto** (the default)
  keeps small talk light and thinks harder for code, maths, study and contest problems; or choose Low, Medium,
  High, Extra high or Max. Computer tasks have their own level (Medium by default). Reminders, check-ins and
  summaries always use Low.
- **Usage** in the sidebar: how much of her plan is left, as moons that wane as you use it (Claude's 5-hour
  session and week, ChatGPT's windows via Codex, or your OpenRouter credit), each with when it resets. The
  sidebar shows the window closest to running out ("62% left", amber below 20%). The page also has 14 days of
  tokens split into input, output and cached (hover a day for its numbers) and the chats that used the most
  today, this week or this month (click one to open it). Token counts stay on this computer.
- **Smooth to use:** math formulas are drawn once and kept, so chats with them open faster; Settings and pages
  crossfade; new messages fade in; her words appear at an even pace
  as she writes; the mouse wheel glides; menus fade in and hovers ease. All of it follows Windows' "Show animations"
  setting. Icons are Lucide's (2 px strokes, bundled under its ISC licence), with medium-weight labels and soft fills
  instead of hairline outlines.
- **No popups**: rename a chat, project or subject right where its name is (double-click it, or the title above the chat); questions like "Delete …?" and notices appear in a bar inside the window.
- **Fonts**: Inter (bundled, like ChatGPT; the default), Segoe UI Variable, Sitka, Bahnschrift or Calibri, in four text sizes.
- **Themes** (Settings → App → Window → Theme): Moonlit frost, Crimson moon, Jade grove, Lunar gold, Violet
  dusk, Midnight ink, Graphite (ChatGPT's neutral greys, with her crimson kept), and two light ones, Snowfield and
  Blossom day. The whole window changes at once.
- **Laid out like ChatGPT:** a light frame (a top bar with the sidebar toggle, search and the window's buttons, and a
  rail with Chats, Projects, Study, Usage and Settings) around a darker rounded panel that holds the sidebar and the
  conversation, with a line between them. The conversation is a centred reading column, with pill-shaped messages
  of yours, her replies as plain text, and a large rounded message box.
- Lives in the **system tray** when closed (Quit from there); in Windows Search / Start as **Jingliu**.
- **Start with Windows** (quietly, in the tray) and **gentle check-ins** (off by default: a greeting
  that fits the time of day, and a nudge to rest after about three hours) in Settings → App. Like
  reminders, check-ins arrive in her Reminders session, not in the chat you are in.
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
- **Sessions:** Claude Code keeps a transcript of each chat's session (tasks included) under `~/.claude/projects`
  on this computer, in a folder of the app's own. The app deletes it with the chat, when a session is replaced or
  compacted, and after 30 days.
- **Usage** keeps only token counts per reply (with the chat and model) and the latest limits each service
  reported, in `data/usage-limits.json`; never what was said.

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
