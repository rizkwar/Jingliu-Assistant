# Choose a model without changing your character

Open **Settings → Response model**. Choose **OpenRouter (API key)** or **ChatGPT
subscription via Codex**. Click **Save defaults** to keep the choice after restart.

## Subscription setup

1. Select **ChatGPT subscription via Codex**.
2. Click **Sign in to ChatGPT** and finish in your browser. Sign in once for this
   assistant even if another Codex installation is already signed in.
3. Use **Check connection / models**, select a model or keep **Codex default
   model**, then Save defaults and send a message.

Codex CLI must be installed; this project was checked with 0.155.1. The app finds
it on PATH or in the standard Windows Codex installation. This option requires
ChatGPT authentication, rather than API-key authentication. It uses your plan's
Codex access and limits. It does not expose every model on the ChatGPT website
or provide unrestricted API credit. The catalog does not confirm entitlement:
only a completed inference verifies access to the chosen model. Errors never
trigger another provider or a paid API fallback.

See the official [authentication guide](https://learn.chatgpt.com/docs/auth) and
[app-server documentation](https://learn.chatgpt.com/docs/app-server).

For OpenRouter, enter a model ID and keep `OPENROUTER_API_KEY` in `.env`.
Model availability and cost depend on that provider and your account.

## Continuity and privacy

Model selection is separate from character, local voice, avatar and conversation
selection. Every request receives the same character profile, voice contract,
selected recent exchanges, enabled relevant memories and reviewed summary.
Wording can vary by model; the profile remains the source of identity. Summary
generation keeps its existing summary prompt through the chosen backend.

Codex gets a fresh ephemeral thread for each reply, replacing its coding persona
with the app-owned instructions. The input contains ordered message data. Only
final-answer text reaches chat/TTS; reasoning and commentary are excluded. Older
protocol variants without marked final deltas deliver text at message completion.

Codex owns sign-in, storage and refresh in **`data/codex-profile/`**. Never publish
that folder; Git and the publishing guard exclude it. The app does not copy your
other Codex tokens, developer config or chat history. Connection results omit
account email and identifiers. Credentials are not saved in app preferences or
copied to `.env`.

The child uses an empty temporary workspace, a private profile, read-only sandbox
settings, disabled shell/browser/plugin/agent features and no instruction files.
Its environment excludes API keys and the Hugging Face token. Unexpected tool
operations/approval requests stop the turn. This integration supports conversation.
Stop closes the owned app-server; sign-in/discovery run asynchronously and are
cancellable, including on quit.

Selected context goes to the chosen online provider; local TTS stays local.

## Verified and pending

Live checks initialized the installed app-server, loaded its catalog and created
the exact ephemeral character thread with zero instruction sources. Native UI
checks passed for discovery, selection, saved choice, unchanged character and
conversation, and immediate-close cancellation. Protocol tests cover final-only
streaming, profile/context delivery, cancellation, failures and API-fallback refusal.

**A live subscription reply and browser sign-in are not yet verified:** this
assistant's isolated profile has not been signed in. Use the sign-in button for
that account-dependent check. No model request was charged during verification.

Suggested commit: `feat: add Codex subscription model selection`
