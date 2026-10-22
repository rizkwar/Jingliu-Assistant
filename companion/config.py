from dataclasses import dataclass, field
import os
from pathlib import Path

from dotenv import dotenv_values


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MODEL = "nvidia/nemotron-3-ultra-550b-a55b:free"
VOICES = ("alba", "anna", "azelma", "cosette", "eponine", "fantine", "jane", "vera")


@dataclass(frozen=True)
class Settings:
    api_key: str = field(repr=False)
    model: str
    name: str
    system_prompt: str
    tts_voice: str = "alba"
    tts_enabled: bool = True
    tts_volume: int = 70
    stt_model: str = "base.en"
    stt_auto_send: bool = True
    stt_microphone: str = ""

    def validate_connection(self) -> None:
        if not self.api_key or self.api_key == "your_key_here":
            raise ValueError(
                "Add your OpenRouter key to OPENROUTER_API_KEY in .env, "
                "then click Reload settings."
            )
        if not self.model or "#" in self.model or "/" not in self.model:
            raise ValueError(
                "OPENROUTER_MODEL must be a model ID such as "
                f"{DEFAULT_MODEL}, without #providers or a webpage URL."
            )
        if "://" in self.model:
            raise ValueError("Use the model ID in OPENROUTER_MODEL, not its webpage URL.")


def load_settings(root: Path = PROJECT_ROOT) -> Settings:
    # Read afresh so Reload settings works; do not overwrite process environment.
    values = {**dotenv_values(root / ".env", encoding="utf-8"), **os.environ}
    name = (values.get("COMPANION_NAME") or "Mira").strip() or "Mira"
    template = (root / "character.md").read_text(encoding="utf-8")
    voice = (values.get("TTS_VOICE") or "alba").strip().lower()
    if voice not in VOICES:
        raise ValueError("TTS_VOICE must be one of: " + ", ".join(VOICES))
    enabled = (values.get("TTS_ENABLED") or "true").strip().lower()
    if enabled not in {"true", "false", "1", "0", "yes", "no"}:
        raise ValueError("TTS_ENABLED must be true or false.")
    try:
        volume = int(values.get("TTS_VOLUME") or "70")
    except ValueError as exc:
        raise ValueError("TTS_VOLUME must be a whole number from 0 to 100.") from exc
    if not 0 <= volume <= 100:
        raise ValueError("TTS_VOLUME must be a whole number from 0 to 100.")
    stt_model = (values.get("STT_MODEL") or "base.en").strip()
    if stt_model not in {"tiny.en", "base.en", "small.en"}:
        raise ValueError("STT_MODEL must be tiny.en, base.en, or small.en.")
    stt_auto_send = (values.get("STT_AUTO_SEND") or "true").strip().lower()
    if stt_auto_send not in {"true", "false", "1", "0", "yes", "no"}:
        raise ValueError("STT_AUTO_SEND must be true or false.")
    return Settings(
        api_key=(values.get("OPENROUTER_API_KEY") or "").strip(),
        model=(values.get("OPENROUTER_MODEL") or DEFAULT_MODEL).strip(),
        name=name,
        system_prompt=template.replace("{name}", name),
        tts_voice=voice,
        tts_enabled=enabled in {"true", "1", "yes"},
        tts_volume=volume,
        stt_model=stt_model,
        stt_auto_send=stt_auto_send in {"true", "1", "yes"},
        stt_microphone=(values.get("STT_MICROPHONE") or "").strip(),
    )

