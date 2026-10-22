# Prepared Jingliu English reference

The local reference is **`voices/jingliu-reference.wav`**. It has been selected in
saved preferences as **Reference recording**, with Delivery at **100%**. Other
preferences and `.env` were preserved. This file is an original spoken recording,
not a generated sample of new dialogue. Reference-conditioned synthesis has now
been verified locally, including a fresh process with network connections blocked.

## Sources and selection

The opening 20 seconds of [THUNDER's English voice-line compilation](https://www.youtube.com/watch?v=9pMbfvqJ84Q)
were retrieved without browser cookies or account credentials. Local transcription
located the complete introductory line before the next voice line began. The
13.35-second opening excerpt was saved for comparison at
`voices/jingliu-youtube-excerpt.wav`.

The [isolated archive recording of the same introductory line](https://honkai-star-rail.fandom.com/wiki/File:VO_Archive_Jingliu_1.ogg)
was then retrieved as a cleaner reference candidate. The quietest measured
250 ms interval had an RMS amplitude around **0.000011**, compared with
**0.003472** in the decoded video excerpt. This supports choosing the isolated
recording for its quieter non-speech sections; it is not a model-similarity score.
Local transcription also confirmed the complete 22-word line.

The isolated source was decoded to mono PCM WAV at 24 kHz. No pitch adjustment,
playback-speed change, voice conversion, or generated speech was applied.
The character and source game performance come from Honkai: Star Rail; the
linked video and archive retain their respective source attribution.

| Property | Prepared reference |
| --- | --- |
| Duration | 11.87375 seconds |
| Sample rate | 24,000 Hz |
| Channels | Mono |
| Encoding | Signed 16-bit PCM WAV |
| SHA-256 | `bf015a9b649ae25560103770929e9138b8d4d61b8ad8247b5dc1f1a55053ed7f` |

Audio and local source metadata are under the Git-ignored `voices` folder.
Temporary downloads, transcription timings, and download tools are also excluded
from Git. No new application dependency was added for retrieving this clip.

## Local synthesis verification

The full [Pocket TTS model](https://huggingface.co/kyutai/pocket-tts) was downloaded
using the configured local Hugging Face token. The engine confirmed that the
loaded checkpoint supports reference conditioning and runs on **CPU**.

- `artifacts/jingliu-local-preview.wav`: 4.32 seconds of newly generated dialogue
  at 24 kHz. In this one check, generation took 1.33 seconds after loading and
  reference encoding; timing is machine- and request-dependent.
- `artifacts/jingliu-offline-preview.wav`: 3.04 seconds of new speech generated in
  a fresh process with `HF_HUB_OFFLINE=1`, no Hugging Face token supplied, and
  socket connections blocked. **Zero network attempts** occurred.

Neither verification opened an audio playback device or called OpenRouter.
These are synthesis checks, not a subjective certification of the voice match.
Listen to the generated previews and the original reference to judge similarity.

Restart the app, or reload settings, then click **Preview** to use the cached full
model through the normal voice controls. See [reference-voice.md](reference-voice.md)
for setup when copying the project to another machine.

The previous voice settings were backed up locally at
`data/preferences.before-reference-voice.json` before this selection was saved.
