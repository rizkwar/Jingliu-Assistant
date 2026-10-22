"""Validate bounded local reference audio before passing it to the speech model."""

from dataclasses import dataclass
import hashlib
from pathlib import Path
import wave


class VoiceSetupError(ValueError):
    """A fixed, actionable voice setup error safe to show through the JSON protocol."""


@dataclass(frozen=True)
class ReferenceAudio:
    path: Path
    seconds: float
    channels: int
    sample_rate: int
    fingerprint: str


def inspect_reference(source):
    if not isinstance(source, (str, Path)) or not str(source).strip():
        raise VoiceSetupError("Choose a reference WAV in Settings before using a reference voice.")
    path = Path(source).expanduser()
    if path.suffix.lower() != ".wav":
        raise VoiceSetupError("Choose a local PCM WAV file, not a URL, embedding, or compressed audio file.")
    try:
        if path.stat().st_size > 20 * 1024 * 1024:
            raise VoiceSetupError("Reference WAV must be at most 20 MiB and 3 to 30 seconds long.")
        with path.open("rb") as stream:
            with wave.open(stream, "rb") as recording:
                channels, width, rate = recording.getnchannels(), recording.getsampwidth(), recording.getframerate()
                frames = recording.getnframes()
                if channels not in (1, 2) or width not in (2, 3, 4) or not 16000 <= rate <= 48000:
                    raise VoiceSetupError("Use mono or stereo PCM WAV, 16/24/32-bit, at 16 to 48 kHz.")
                seconds = frames / rate
                if not 3 <= seconds <= 30:
                    raise VoiceSetupError("Use a 3 to 30 second reference of one speaker, without music or other voices.")
                pcm = recording.readframes(frames)
                if len(pcm) != frames * channels * width:
                    raise VoiceSetupError("Reference WAV is incomplete. Export a new complete PCM WAV file.")
                if not any(pcm):
                    raise VoiceSetupError("Reference WAV is silent. Choose a recording with clear speech.")
    except VoiceSetupError:
        raise
    except (OSError, EOFError, wave.Error, ValueError):
        raise VoiceSetupError("Reference WAV is missing, unreadable, or unsupported. Choose it again or export 16-bit PCM WAV.") from None
    signature = hashlib.sha256(f"{channels}/{width}/{rate}/".encode() + pcm).hexdigest()
    return ReferenceAudio(path.resolve(), seconds, channels, rate, signature)
