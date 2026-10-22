from dataclasses import dataclass, field
import os
from pathlib import Path

from dotenv import dotenv_values


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MODEL = "nvidia/nemotron-3-ultra-550b-a55b:free"


@dataclass(frozen=True)
class Settings:
    api_key: str = field(repr=False)
    model: str
    name: str
    system_prompt: str

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
    return Settings(
        api_key=(values.get("OPENROUTER_API_KEY") or "").strip(),
        model=(values.get("OPENROUTER_MODEL") or DEFAULT_MODEL).strip(),
        name=name,
        system_prompt=template.replace("{name}", name),
    )

