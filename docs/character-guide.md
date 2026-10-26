# Editing the companion's character

The active example is [character.toml](../character.toml). It portrays Jingliu
with reserved confidence, dry humor, and a gradual, affectionate interest in you.
Her fictional background draws on Honkai: Star Rail. Her everyday preferences,
gentler private manner, and romantic interest are original adaptations for this
companion. All sample dialogue is newly written, rather than copied game lines.

## Apply and personalize

1. Launch using **Start Jinger.cmd**; the existing script name still works for any character.
2. Open **Settings > Add character**. Give them a name and describe their identity,
   personality, background, interests, speaking style, reactions, and relationship
   with you. Add example conversations and behaviors to avoid in the same text.
   The [description example](examples/character-description.toml) shows one approach.
3. Optionally choose a clean voice recording: one English speaker, no music,
   **3–30 seconds of PCM WAV** (8–15 seconds recommended). The editor validates
   the format and copies it locally; it does not change your source recording.
   Use **Preview voice** to audition and **Stop voice** to cancel.
4. Click **Save and use character**. The selection is saved automatically and
   remains active after restarting. Pick another profile from the dropdown to
   switch back. Characters have separate chat histories and conversation notes.
   Explicit **Memories** remain shared; review any records about a particular
   character before reusing them with another. Other characters' experiences
   are not evidence of this character's relationship with you.
5. **Edit character** lets you revise the active description and recording, then
   save and apply them to the same profile without losing its chats. For an older
   structured profile, the full traits, reactions, and dialogue examples appear
   in the description. Saving converts it to that editable description format;
   a `.toml.bak` file preserves the original before the first edit, and research
   references are retained. Cancel leaves the profile unchanged.

Creation and editing use your description directly, without an extra model request.
Every normal chat request includes it as character instructions. The voice recording
is used by the local speech engine, rather than sent with the description. This
adapts the generated voice to a sample; it does not guarantee an identical performance.

New profiles and their recordings are stored in `data/characters/` and excluded
from Git. Do not delete a character's folder if you intend to keep using it.
The selector remembers your last applied voice adjustments for each profile.
Saving an edit intentionally applies the voice chosen in the editor.
Selecting a profile also saves current app adjustments. Use **Save defaults**
for later changes to volume, voice, microphone, or other settings.

### Editing TOML directly

Use **Settings > Open profile file** to open the active file in your associated
editor. Save it, then choose **Reload .env + character**. Restarting also loads
it. A malformed file produces an error; a failed reload keeps the current profile
and unsent draft intact.

For the original Jingliu profile, **Use character voice** applies her local
recording at **100% delivery**. The preview sentence comes from the profile.
Settings displays one active character voice, without alternative stock speakers.
The character editor also hides the old stock-speaker selector. Existing profiles
without recordings retain their configured voice for compatibility. To replace
the character's recording, select
**Choose reference WAV** or save it through **Edit character**. The
[reference-voice guide](reference-voice.md) covers model access and setup.

Use **New** to sample a changed personality without older messages shaping the
exchange. Your selected saved memories can still accompany the new chat.

The default file is `character.toml`. To keep several profiles, copy it to another
`.toml` file and set an initial selection in `.env`, using a path relative to the project:

```dotenv
CHARACTER_PROFILE=characters/my-jingliu.toml
```

Absolute paths also work. A TOML profile's `identity.name` is authoritative,
including when an older `.env` still contains `COMPANION_NAME=Jinger`. Your existing
`.env` is not rewritten. No API key belongs in the character file.
An app-saved character selection takes precedence over `CHARACTER_PROFILE`.
The selector lists the original profile, the active profile, library profiles,
and previously selected profiles. Markdown profiles can be selected and opened
in an external editor; the in-app editor creates and edits TOML profiles.

Without an explicit selection, projects lacking `character.toml` fall back to
the older `character.md` and `COMPANION_NAME` mechanism. To select that legacy
profile here explicitly, set `CHARACTER_PROFILE=character.md`. An explicitly
selected missing or invalid profile fails visibly instead of silently switching.

## Profile fields

Use `schema_version = 1`. Strings use double quotes or triple double quotes for
multiple lines. Lists use square brackets and quoted items. Keep the file under
32 KiB; fields are limited to 6,000 characters and lists to 30 items.

| Section | Fields | Purpose |
| --- | --- | --- |
| `identity` | `name`, `identity`, `background` | Name, portrayal, and optional fictional history. |
| `personality` | `traits`, `interests`, `likes`, `dislikes`, `opinions` | Stable temperament and judgments. |
| `speech` | `style`, `vocabulary`, `humor`, `response_length`, `preview` | Spoken phrasing and a local voice audition. |
| `voice` | `builtin`, `rate`, `description`, `reference` | Local voice preset and optional recording, applied with Use character voice. |
| `relationship` | `dynamic`, `affection`, `boundaries` | How she expresses interest and responds to your comfort. |
| `reactions` | `excited`, `confused`, `frustrated`, `joking`, `disagreeing`, `vulnerable` | Situational reactions without changing her core identity. |
| `continuity` | `shared_developments` | Relevant kinds of real discussion to acknowledge. |
| `avoid` | `behaviors` | Praise, repetition, narration, and other habits to avoid. |
| `reference` | `sources`, `adaptation_note` | Editing/research metadata, omitted from the model prompt. |
| `[[examples]]` | `situation`, optional `context`, `user`, `assistant` | Up to 16 original style demonstrations. |

`identity.name`, a nonempty `personality.traits` list, and `speech.style` are
required. The other fields are optional. Unknown fields are rejected to expose
typos rather than silently ignoring your edits.

Alternatively, use a top-level `description` string with `[identity].name`,
optional `[speech].preview`, `[voice]`, and `[reference]`, as shown in the
description example. In this format the entire personality and any examples
go inside `description` (up to 24,000 characters, still within the 32 KiB file
limit). Do not combine it with structured personality/reaction/example sections:
the reader rejects competing sets of instructions. The form saves this format.

If present, `[voice]` needs a valid built-in `builtin` name. `rate` is a whole
percentage from 80 to 115, defaulting to 100. Below 100%, playback becomes slower
and lower-pitched together; above 100%, faster and higher-pitched. This changes
acoustic delivery, rather than asking the language model to narrate a voice.
An optional `voice.reference` names a local WAV relative to the profile's folder
or by absolute path. The editor uses relative paths for its managed audio copies.
**Use character voice** applies this recording if present, or the built-in preset.
The voice section is kept out of the dialogue prompt. Existing saved voices
remain in effect until you apply a preset or choose another voice yourself.

For a more romantic interpretation, edit `relationship.affection` and the flirting
examples. For a more reserved one, reduce overt affection there. Keep practical
help, sincere disagreement, and respect for your requests in either version.
Changes to quiet-evening preferences or humor are adaptations, not additions to canon.

Ordinary affectionate dialogue stays in character. Questions about caring or love
receive a personal response suited to the profile and current relationship, without
an unsolicited explanation of AI emotions. This does not require a declaration of
love: restraint, teasing, and honest disagreement still belong to her. Explicit
questions about whether she is human or an AI receive a brief, honest answer.
Older out-of-character replies and neutral summaries do not set the speaking style.
Edit `relationship.affection`, `speech`, and `examples` to tune this balance, then
use **Reload .env + character**. Existing conversations and memories stay intact.

## Personality and continuity

Every reply contains the full active profile, separate from selected memories,
reviewed conversation notes, and recent exchanges. Summarization does not replace
the profile. The summary generator remains a neutral note-taking task and is
asked to preserve explicit preferences, boundaries, and concrete developments,
while separating fictional scenes from real discussions.

- **Same chat after restarting:** saved notes and recent exchanges return with
  the current profile.
- **A new chat:** the same profile and relevant enabled memories apply; the old
  chat's notes and messages do not automatically cross over.
- **Across chats:** save an explicit preference or real development in **Memories**,
  or use `/remember`. For example, `/remember I prefer less teasing while debugging.`
- **A long chat:** use **Context > Generate draft**, inspect the notes, then save.
  You can also write or correct notes yourself.

This retains the existing explicit memory model: she does not silently save a
relationship state, extract a personal profile, or search your full archive.
If she lacks evidence of a conversation, the prompt tells her to acknowledge the
gap. A fictional scene together on the Luofu is not evidence of a real meeting.
The examples are labeled demonstrations, never previous interactions with you.
The model still generates the dialogue, so exact wording and adherence can vary.

The speech path also suppresses common marked performance cues, including
`*smiles*`, `_blushes_`, `[sighs]`, and `(chuckles softly)`, during streaming and
**Read last reply**. Ordinary dialogue, emphasis, and useful asides remain spoken;
the visible transcript is unchanged. Free-form prose narration is discouraged
by the prompt, rather than removed by guessing which sentences are dialogue.

## Research references

The fictional swordmaster background and restrained manner were informed by the
[official Swordward trailer](https://www.youtube.com/watch?v=fMiYAEj46Rc), the
[game dialogue transcription](https://honkai-star-rail.fandom.com/wiki/Jingliu/Voice-Overs),
and the [High-Cloud Quintet reference](https://honkai-star-rail.fandom.com/wiki/High-Cloud_Quintet).
The everyday companion reactions and affectionate dynamic are our interpretation.
See [character-samples.md](character-samples.md) for a repeatable manual check.
