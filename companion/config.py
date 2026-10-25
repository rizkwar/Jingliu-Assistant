from dataclasses import dataclass, field, replace
import os
from pathlib import Path

from dotenv import dotenv_values

from .character import load_character
from .voice_settings import VOICES, validate_rate


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MODEL = "nvidia/nemotron-3-ultra-550b-a55b:free"


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
    memory_enabled: bool = True
    close_to_tray: bool = True
    stt_pause_ms: int = 1200
    avatar_enabled: bool = False
    avatar_animated: bool = True
    avatar_x: int | None = None
    avatar_y: int | None = None
    avatar_width: int = 320
    avatar_height: int = 350
    avatar_motion: int = 100
    avatar_lip_sensitivity: int = 100
    avatar_hd: bool = True
    avatar_cursor_attention: bool = True
    avatar_gaze: int = 100
    avatar_hair: int = 45
    avatar_sleep_minutes: int = 5
    character_path: str = ""
    voice_preview: str = ""
    tts_rate: int = 100
    tts_engine: str = 'pocket'
    computer_tasks: bool = True
    confirm_tasks: bool = True
    approve_steps: bool = True
    auto_memory: bool = True
    character_voice: str = ""
    character_voice_rate: int = 100
    character_voice_description: str = ""
    character_reference: str = ""
    tts_reference: str = ""
    hf_token: str = field(default="", repr=False)
    llm_provider: str = 'openrouter'
    openrouter_model: str = ''
    codex_model: str = ''
    claude_model: str = ''

    def missing_key(self) -> bool:
        """Only OpenRouter needs a key in .env; subscriptions sign in through their CLI."""
        return self.llm_provider == 'openrouter' and not self.api_key

    def validate_connection(self) -> None:
        import re
        if self.llm_provider in {'codex', 'claude'}:
            model = self.codex_model if self.llm_provider == 'codex' else self.claude_model
            if model and not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,119}', model):
                raise ValueError('Choose a valid model from Settings.')
            return
        if self.llm_provider != 'openrouter':
            raise ValueError('Choose OpenRouter, Claude subscription, or ChatGPT subscription via Codex in Settings.')
        if not self.api_key or self.api_key == "your_key_here":
            raise ValueError(
                "Add your OpenRouter key to OPENROUTER_API_KEY in .env, "
                "then open Settings and click Reload .env + character."
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
    character = load_character(root, (values.get("CHARACTER_PROFILE") or "").strip(), name)
    voice = (values.get("TTS_VOICE") or "alba").strip().lower()
    if voice not in (*VOICES, "reference"):
        raise ValueError("TTS_VOICE must be one of: " + ", ".join((*VOICES, "reference")))
    reference = (values.get("TTS_REFERENCE") or "").strip()
    enabled = (values.get("TTS_ENABLED") or "true").strip().lower()
    if enabled not in {"true", "false", "1", "0", "yes", "no"}:
        raise ValueError("TTS_ENABLED must be true or false.")
    try:
        volume = int(values.get("TTS_VOLUME") or "70")
    except ValueError as exc:
        raise ValueError("TTS_VOLUME must be a whole number from 0 to 100.") from exc
    if not 0 <= volume <= 100:
        raise ValueError("TTS_VOLUME must be a whole number from 0 to 100.")
    try:
        rate = validate_rate(int(values.get("TTS_RATE") or "100"))
    except ValueError as exc:
        raise ValueError("TTS_RATE must be a whole percentage from 80 to 115.") from exc
    stt_model = (values.get("STT_MODEL") or "base.en").strip()
    if stt_model not in {"tiny.en", "base.en", "small.en"}:
        raise ValueError("STT_MODEL must be tiny.en, base.en, or small.en.")
    stt_auto_send = (values.get("STT_AUTO_SEND") or "true").strip().lower()
    if stt_auto_send not in {"true", "false", "1", "0", "yes", "no"}:
        raise ValueError("STT_AUTO_SEND must be true or false.")
    return Settings(
        api_key=(values.get("OPENROUTER_API_KEY") or "").strip(),
        model=(values.get("OPENROUTER_MODEL") or DEFAULT_MODEL).strip(),
        name=character.name,
        system_prompt=character.prompt,
        tts_voice=voice,
        tts_enabled=enabled in {"true", "1", "yes"},
        tts_volume=volume,
        stt_model=stt_model,
        stt_auto_send=stt_auto_send in {"true", "1", "yes"},
        stt_microphone=(values.get("STT_MICROPHONE") or "").strip(),
        character_path=str(character.path),
        voice_preview=character.preview,
        tts_rate=rate,
        character_voice=character.voice,
        character_voice_rate=character.rate,
        character_voice_description=character.voice_description,
        character_reference=character.reference,
        tts_reference=str((root / reference).resolve()) if reference else "",
        hf_token=(values.get("HF_TOKEN") or "").strip(),
        # Saved preferences override this default once another provider is chosen.
        llm_provider='claude',
        claude_model='claude-sonnet-5-5',
    )


def with_character(settings: Settings, character, *, use_voice=False) -> Settings:
    values = dict(name=character.name, system_prompt=character.prompt, character_path=str(character.path),
                  voice_preview=character.preview, character_voice=character.voice,
                  character_voice_rate=character.rate, character_voice_description=character.voice_description,
                  character_reference=character.reference)
    if use_voice:
        values.update(tts_voice="reference" if character.reference else character.voice or "alba",
                      tts_reference=character.reference, tts_rate=character.rate)
    return replace(settings, **values)


def active_character_voice(settings: Settings) -> Settings:
    """Use the selected recording, then the profile's recording, without a stock menu.

    Old stock preferences remain readable. A configured recording takes
    priority over that old selection; a missing recording is reported by TTS,
    never silently replaced with a different speaker.
    """
    if settings.tts_reference:
        return replace(settings, tts_voice='reference',
                       tts_rate=settings.tts_rate if settings.tts_voice == 'reference' else 100)
    if settings.character_reference:
        return replace(settings, tts_voice='reference', tts_reference=settings.character_reference,
                       tts_rate=settings.character_voice_rate)
    return settings

