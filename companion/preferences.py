"""Nonsecret UI preferences. Connection credentials always stay in .env."""

from dataclasses import replace
import json
import os
from pathlib import Path
import tempfile

from .config import Settings, VOICES, PROJECT_ROOT, with_character
from .character import character_key, load_character
from .voice_settings import validate_rate


FIELDS = {
    "tts_voice": str, "tts_enabled": bool, "tts_volume": int,
    "tts_rate": int,
    "tts_reference": str,
    "character_path": str,
    "stt_model": str, "stt_auto_send": bool, "stt_microphone": str,
    "memory_enabled": bool, "close_to_tray": bool,
    "stt_pause_ms": int,
    "avatar_enabled": bool, "avatar_animated": bool,
    "avatar_x": (int, type(None)), "avatar_y": (int, type(None)),
}


def validate(values):
    if not isinstance(values, dict):
        raise ValueError("Saved preferences must be an object.")
    clean = {key: value for key, value in values.items() if key in FIELDS}
    if any(type(value) not in (FIELDS[key] if isinstance(FIELDS[key], tuple) else (FIELDS[key],))
           for key, value in clean.items()):
        raise ValueError("Saved preferences contain an invalid value type.")
    if "tts_voice" in clean and clean["tts_voice"] not in (*VOICES, "reference"):
        raise ValueError("Saved voice is not available.")
    if "tts_volume" in clean and not 0 <= clean["tts_volume"] <= 100:
        raise ValueError("Saved volume must be from 0 to 100.")
    if "tts_rate" in clean:
        validate_rate(clean["tts_rate"])
    if len(clean.get("tts_reference", "")) > 4096:
        raise ValueError("Saved reference audio path is too long.")
    if len(clean.get("character_path", "")) > 4096:
        raise ValueError("Saved character profile path is too long.")
    if "stt_model" in clean and clean["stt_model"] not in {"tiny.en", "base.en", "small.en"}:
        raise ValueError("Saved transcription model is not available.")
    if "stt_pause_ms" in clean and not 600 <= clean["stt_pause_ms"] <= 2500:
        raise ValueError("Speech pause must be from 600 to 2,500 milliseconds.")
    x, y = clean.get("avatar_x"), clean.get("avatar_y")
    if (x is None) != (y is None) or any(value is not None and abs(value) > 1000000 for value in (x, y)):
        raise ValueError("Saved avatar position is invalid.")
    return clean


class Preferences:
    def __init__(self, path: Path | None = None):
        self.path = path
        self._values = {}
        self._voices = {}

    def character_paths(self):
        return tuple(self._voices)

    def load(self, defaults: Settings) -> Settings:
        if self.path is not None and self.path.exists():
            try:
                document = json.loads(self.path.read_text(encoding="utf-8"))
            except (UnicodeError, json.JSONDecodeError) as exc:
                raise ValueError("Saved preferences could not be read. Use Save defaults to replace them.") from exc
            if not isinstance(document, dict) or document.get("version") != 1:
                raise ValueError("Saved preferences have an unsupported format.")
            values = validate(document.get("settings"))
            voices = document.get("character_voices", {})
            if not isinstance(voices, dict) or any(not isinstance(key, str) or len(key) > 4096 for key in voices):
                raise ValueError("Saved character voices have an invalid format.")
            self._voices = {key: {field: value for field, value in validate(audio).items()
                                 if field in {"tts_voice", "tts_reference", "tts_rate"}} for key, audio in voices.items()}
        else:
            values = self._values
        settings = replace(defaults, **values)
        if settings.character_path:
            settings = with_character(settings, load_character(PROJECT_ROOT, settings.character_path, defaults.name))
        return settings

    def select(self, current: Settings, character, *, use_profile_voice=False) -> Settings:
        """Persist the selection and each character's voice without storing prompts or credentials."""
        settings = with_character(current, character, use_voice=True)
        audio = self._voices.get(character_key(settings.character_path))
        if audio and not use_profile_voice:
            settings = replace(settings, **audio)
        self.save(settings, previous=current)
        return settings

    def save(self, settings: Settings, *, previous=None) -> None:
        values = validate({key: getattr(settings, key) for key in FIELDS})
        voices = dict(self._voices)
        for item in (previous, settings):
            if item is not None and item.character_path:
                voices[character_key(item.character_path)] = {
                    key: getattr(item, key) for key in ("tts_voice", "tts_reference", "tts_rate")}
        if self.path is not None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = None
            try:
                with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=self.path.parent,
                                                 prefix="preferences-", suffix=".tmp", delete=False) as output:
                    temporary = Path(output.name)
                    json.dump({"version": 1, "settings": values, "character_voices": voices}, output, indent=2)
                    output.write("\n")
                    output.flush()
                    os.fsync(output.fileno())
                os.replace(temporary, self.path)
            finally:
                if temporary is not None:
                    temporary.unlink(missing_ok=True)
        self._values = values
        self._voices = voices
