# Editing the companion's character

The active example is [character.toml](../character.toml). It portrays Jingliu
with reserved confidence, dry humor, and a gradual, affectionate interest in you.
Her fictional background draws on Honkai: Star Rail. Her everyday preferences,
gentler private manner, and romantic interest are original adaptations for this
companion. All sample dialogue is newly written, rather than copied game lines.

## Apply and personalize

1. Launch using **Start Mira.cmd**; the existing script name still works for any character.
2. Open **Settings > Edit character profile** to open the active file in your
   system's associated editor. You can also open `character.toml` directly in VS Code.
3. Edit the profile, save it, then click **Reload .env + character**. Restarting
   also loads it. A malformed file produces an error; a failed reload keeps your
   current profile and unsent draft intact.
4. Choose a built-in **Voice**, click **Preview**, and use **Save defaults** to
   keep it. The preview sentence comes from the profile. Voice selection is
   independent of personality; this uses Pocket TTS's existing voices, not the
   game's actor or a voice clone.
5. Use **New** to sample the character without old conversation messages shaping
   the exchange. Your selected saved memories can still accompany the new chat.

The default file is `character.toml`. To keep several profiles, copy it to another
`.toml` file and select it in `.env`, using a path relative to the project:

```dotenv
CHARACTER_PROFILE=characters/my-jingliu.toml
```

Absolute paths also work. A TOML profile's `identity.name` is authoritative,
including when an older `.env` still contains `COMPANION_NAME=Mira`. Your existing
`.env` is not rewritten. No API key belongs in the character file.

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
| `relationship` | `dynamic`, `affection`, `boundaries` | How she expresses interest and responds to your comfort. |
| `reactions` | `excited`, `confused`, `frustrated`, `joking`, `disagreeing`, `vulnerable` | Situational reactions without changing her core identity. |
| `continuity` | `shared_developments` | Relevant kinds of real discussion to acknowledge. |
| `avoid` | `behaviors` | Praise, repetition, narration, and other habits to avoid. |
| `reference` | `sources`, `adaptation_note` | Editing/research metadata, omitted from the model prompt. |
| `[[examples]]` | `situation`, optional `context`, `user`, `assistant` | Up to 16 original style demonstrations. |

`identity.name`, a nonempty `personality.traits` list, and `speech.style` are
required. The other fields are optional. Unknown fields are rejected to expose
typos rather than silently ignoring your edits.

For a more romantic interpretation, edit `relationship.affection` and the flirting
examples. For a more reserved one, reduce overt affection there. Keep practical
help, sincere disagreement, and respect for your requests in either version.
Changes to quiet-evening preferences or humor are adaptations, not additions to canon.

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
