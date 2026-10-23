# A voice conditioned on a recording

The active character's voice conditions Pocket TTS on a local WAV,
so new dialogue uses vocal characteristics from that recording. This is a
different approach from adjusting the speed of Jane or another stock voice.
The existing streaming, interruption, and local playback system still applies.

To keep a recording with a particular character, use **Settings > Add character**
or **Edit character**, choose the WAV, preview it, and **Save and use character**.
The app keeps a local copy and restores it when you select that character again.
See the [character guide](character-guide.md) for creating and switching profiles.

This workspace now has a prepared local reference at `voices/jingliu-reference.wav`,
selected at 100% Delivery. See [its sources and preparation](jingliu-reference.md).
The recording is excluded from Git and is not bundled with source-code copies.
The full model is now cached in this workspace, and new speech has been generated
locally on CPU. An additional test with network connections blocked succeeded
without supplying a Hugging Face token. Generated voice similarity still needs
your listening comparison. New installations need the full model setup below.

## Prepare the reference

For the closest English delivery, choose an appropriate recording of the target
performance speaking conversationally, with no background music, effects, or
other speakers. A trailer or a combat shout is a poor reference for quiet chat.
Aim for roughly 8–15 seconds of clear, uninterrupted speech. The app accepts:

- A local `.wav` file, 3–30 seconds long and at most 20 MiB.
- Mono or stereo PCM audio, 16/24/32-bit, sampled at 16–48 kHz.
- Export to **16-bit PCM WAV** if an audio editor offers multiple WAV formats.

The app rejects silent, truncated, unsupported, and out-of-bounds files. These
checks cannot establish that a recording contains only one speaker or no music;
listen to the reference yourself. Quality and similarity depend on the recording
and model. An exact match to every inflection or emotion is not guaranteed.

Keep references under a local `voices` folder if convenient. That folder is
excluded from Git. The app reads the selected file in place; it does not copy,
upload, or include its audio in language-model requests. Keep it at the saved path.

## Enable the full speech model

1. Open [kyutai/pocket-tts](https://huggingface.co/kyutai/pocket-tts), review its
   model terms and access requirements, and obtain access through your own account.
2. Set a Hugging Face read token with that access in your local `.env`:

   ```dotenv
   HF_TOKEN=your_hugging_face_read_token
   ```

   This token is separate from `OPENROUTER_API_KEY`. Keep it out of the character
   profile, Git, and chat. The app passes it only to the local speech process's
   environment, excluding it from saved preferences and speech command payloads.

   Alternatively, authenticate using the installed CLI with the same cache home
   as the speech process. From PowerShell in the project folder:

   ```powershell
   $env:HF_HOME = Join-Path (Get-Location) '.cache\huggingface'
   .\.venv\Scripts\hf.exe auth login
   ```

3. Reload settings or restart the app after changing credentials/model access.
   The first successful reference preview downloads the full model into this
   project's `.cache/huggingface`. Subsequent uses reuse it locally.

The app never accepts model terms or performs account login on your behalf.
Reference mode checks that the loaded checkpoint actually supports conditioning;
if Pocket TTS falls back to its stock-only weights, the app reports the setup
problem and does **not** substitute a stock voice. Text chat remains usable.

## Select and test

1. Open **Settings > Choose reference WAV** and select the recording. This selects
   the character's recording voice and resets Delivery to **100%** to preserve its natural
   pitch and timing before you audition it.
2. Click **Preview**. It uses the profile's preview sentence, so you hear newly
   generated dialogue rather than simply playing the original recording.
3. Enable **Speak replies**, then try a short typed or spoken exchange. Streaming
   replies and **Read last reply** use the same selected reference.
4. Use **Save defaults** to retain the voice mode and local reference path across
   restarts. **Clear** removes the current recording and keeps reference mode
   unconfigured; it never substitutes a stock speaker. **Use character voice**
   restores the profile's recording. Settings shows one active voice, and the
   character editor no longer exposes the stock-speaker catalog.

The reference is encoded once per speech process and reused across phrases.
Replacing its audio causes the next request to rebuild that state. Stop can
terminate the voice process, so the next request may load and encode it again.
No voice embedding is exported or committed by this integration.

You can also configure defaults in `.env`:

```dotenv
TTS_VOICE=reference
TTS_REFERENCE=voices/jingliu-reference.wav
TTS_RATE=100
```

Relative paths resolve against the project. Saved app preferences take precedence
over `.env` audio defaults, as before; selecting the file in Settings and saving
is the most direct way to replace a previously saved stock-voice choice.

**Check Setup.cmd** checks reference-file validity when reference mode is selected,
without downloading a model or capturing audio. **Preview** is the actual test of
model access and generated sound. A successful setup test does not certify similarity.

Implementation follows the [Pocket TTS conditioning API](https://kyutai-labs.github.io/pocket-tts/API%20Reference/python-api/),
[Hugging Face authentication](https://huggingface.co/docs/huggingface_hub/en/quick-start#authentication),
and [HF_TOKEN/HF_HOME configuration](https://huggingface.co/docs/huggingface_hub/en/package_reference/environment_variables).
