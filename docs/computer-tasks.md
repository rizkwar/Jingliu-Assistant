# Computer tasks

Jingliu can do things on this computer when you ask: make or tidy files and folders,
run programs and commands, look things up on the web, and use apps on screen with the
mouse and keyboard.

## Asking her

- **In conversation, even casually:** "can you make me a folder for my college notes?" or "ugh,
  my desktop is such a mess with all these screenshots". She recognises a job being handed to her,
  improvises a concrete plan (where, how it's organised, what she leaves alone), and asks whether to
  go ahead. A **Proposed task** card shows the plan with **Yes, do it** and **Not now**.
- **Confirming:** click **Yes, do it**, or just say or type "yes", "go ahead" or "sure, do it". A
  plain yes starts the plan immediately, including through the microphone and hands-free mode.
  Say "not now" to decline. Answer with changes ("yes, but put them in Pictures instead") and she
  starts the task with your change included.
- **Directly:** `/do make a folder called Trips on my desktop` starts at once, with no proposal.
- **Without confirmation:** turn off **Settings → App → Confirm with me before she starts a task**.
  She then starts clear, specific requests right away and only proposes when a request is unclear.

She only treats clear requests as tasks. Questions ("what's the difference between RAM and
storage?") and passing remarks ("I should clean my Downloads someday") stay conversation;
in a live check she offered to help with the second one instead of acting on her own.
When she's done, she reports in her own voice, and the report is spoken and saved with the
conversation.

## What needs your approval

| She can do freely | She asks first |
| --- | --- |
| Read files, list and search folders | Run a command or program (PowerShell, Bash) |
| Search the web, open web pages | Create, change or delete a file |
| Look at the screen (screenshots) | Click, type, press keys or scroll on screen |

Each request opens a window showing the full command, file contents or action, with:
- **Allow once:** only this step.
- **Allow all … for this task:** the same kind of step (commands, file changes, or mouse and
  keyboard) for the rest of this task only.
- **Deny:** she skips the step, won't try it another way, and tells you what she couldn't do.

Closing the window counts as Deny. To skip these questions, turn off **Settings → App → Ask
before she runs commands or uses the mouse and keyboard** (remembered immediately): every step
then runs at once, still listed in the chat as it happens. **Stop** cancels a task at any time. Tasks also stop after
80 steps or 20 minutes, or when the app closes. She works anywhere on the computer, but is
told to stop and explain instead of guessing when something is ambiguous, needs a password,
spends money, messages other people, changes system settings, or deletes a lot.

Turn the feature off in **Settings → App → Let her do tasks on this computer**.

## Undoing a task

Every task keeps a record of the file changes it makes. To undo one:

- press **Undo this task** on its card in the chat;
- ask her ("undo that", "put it back the way it was"): she answers and the confirmation appears;
- type `/undo` for the latest task; or
- open **⋯ → Recent tasks**, which lists the last 7 days of tasks that changed files, also after a
  restart, each with **Undo**.

Undo first lists what it will do and asks you to confirm, then reverses the changes, newest first:

- Files she **edited or overwrote** get their original content back (the original is copied just
  before the change is allowed).
- Files and folders she **created or copied** are removed. They are set aside in the task's undo
  folder rather than destroyed.
- Items she **moved or renamed** go back where they were.
- Items she **deleted** come back. Her delete tool keeps them in the undo folder instead of erasing them.

She is told to use her own `move_path`, `copy_path`, `delete_path` and `make_folder` tools for
these operations, which is what makes them reversible. Shell **commands** and **clicks or typing in
other apps** cannot be reversed automatically; the confirmation says so when a task used them.
Undo never overwrites something that has changed since: if you created a file where one used to
be, or put your own files into a folder she made, that part is skipped and reported. If the
original of a file cannot be saved, that edit is refused rather than made unrecoverable.

Undo records live in `data/task_undo/` (with what you asked and how it ended) and are removed after
7 days. She is told when you undo, so later replies don't assume the work is still there.

## How it works

Conversation stays tool-free, exactly as before. A task is a separate Claude Code run
(`claude -p`, your Claude plan, model from Settings) with real tools. Each run is isolated:
- **Tools:** only Bash, PowerShell, Read, Write, Edit, Glob, Grep, WebSearch, WebFetch, plus the
  app's own server (`companion/task_tools.py`) for screenshots, clicks, typing, keys, scroll and wait.
- **No personal setup:** your Claude Code settings, skills and slash commands are not loaded
  (`--setting-sources ""`, `--disable-slash-commands`), and no other MCP servers are allowed
  (`--strict-mcp-config`). `--safe-mode` is not used because it also drops the approval server.
- **No API billing:** API keys are removed from its environment, so it uses your subscription.
- **Approval routing:** Claude Code sends steps that need approval to the app's
  `--permission-prompt-tool`, which asks the chat window over a loopback-only connection
  protected by a per-task secret token. Anything that cannot reach you is denied.

Screen coordinates use the latest screenshot (downscaled to 1366 px wide) and are mapped back
to your physical screens. Mouse and keyboard input goes through Windows `SendInput`; Windows
blocks input into windows running as administrator.

## Verified

- Real Claude Code: the approval hook's input (`tool_name`, `input`, `tool_use_id`) and replies
  (`allow` with `updatedInput`, `deny` with a message). A denied file write was not made; an
  allowed one was.
- A real task created a folder and file and listed them, asking before its command.
- Screenshot capture and coordinate mapping (centre to centre) on this 1920×1080 screen, with
  no input sent and no image sent to the model during development.
- Live conversation: she cued tasks for three clear requests and none for a question or a
  passing remark.
- Tests cover the tool server protocol, token-protected approvals, isolated run settings, the
  task card, approve/deny/allow-for-task, `/do`, Stop, and turning the feature off.

Not yet tried end to end: a full mouse-and-keyboard task in a real app. Try something small
first, like "open Notepad and type hello", and watch the approvals.
