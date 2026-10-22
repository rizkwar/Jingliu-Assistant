"""Nonsecret UI preferences. Connection credentials always stay in .env."""

from dataclasses import replace
import json
import os
from pathlib import Path
import tempfile

from .config import Settings, VOICES


FIELDS = {
    "tts_voice": str, "tts_enabled": bool, "tts_volume": int,
    "stt_model": str, "stt_auto_send": bool, "stt_microphone": str,
    "memory_enabled": bool, "close_to_tray": bool,
}


def validate(values):
    if not isinstance(values, dict):
        raise ValueError("Saved preferences must be an object.")
    clean = {key: value for key, value in values.items() if key in FIELDS}
    if any(type(value) is not FIELDS[key] for key, value in clean.items()):
        raise ValueError("Saved preferences contain an invalid value type.")
    if "tts_voice" in clean and clean["tts_voice"] not in VOICES:
        raise ValueError("Saved voice is not available.")
    if "tts_volume" in clean and not 0 <= clean["tts_volume"] <= 100:
        raise ValueError("Saved volume must be from 0 to 100.")
    if "stt_model" in clean and clean["stt_model"] not in {"tiny.en", "base.en", "small.en"}:
        raise ValueError("Saved transcription model is not available.")
    return clean


class Preferences:
    def __init__(self, path: Path | None = None):
        self.path = path
        self._values = {}

    def load(self, defaults: Settings) -> Settings:
        if self.path is not None and self.path.exists():
            try:
                document = json.loads(self.path.read_text(encoding="utf-8"))
            except (UnicodeError, json.JSONDecodeError) as exc:
                raise ValueError("Saved preferences could not be read. Use Save defaults to replace them.") from exc
            if not isinstance(document, dict) or document.get("version") != 1:
                raise ValueError("Saved preferences have an unsupported format.")
            values = validate(document.get("settings"))
        else:
            values = self._values
        return replace(defaults, **values)

    def save(self, settings: Settings) -> None:
        values = validate({key: getattr(settings, key) for key in FIELDS})
        if self.path is not None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = None
            try:
                with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=self.path.parent,
                                                 prefix="preferences-", suffix=".tmp", delete=False) as output:
                    temporary = Path(output.name)
                    json.dump({"version": 1, "settings": values}, output, indent=2)
                    output.write("\n")
                    output.flush()
                    os.fsync(output.fileno())
                os.replace(temporary, self.path)
            finally:
                if temporary is not None:
                    temporary.unlink(missing_ok=True)
        self._values = values
