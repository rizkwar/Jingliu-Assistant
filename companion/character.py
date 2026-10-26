"""Load an editable TOML character profile, with legacy Markdown compatibility."""

from dataclasses import dataclass
import os
from pathlib import Path
import tomllib

from .paths import portable, resolve
from .voice_settings import VOICES, validate_rate


MAX_PROFILE_BYTES = 32768
FIELDS = {
    "identity": {"name": str, "identity": str, "background": str},
    "personality": {"traits": list, "interests": list, "likes": list, "dislikes": list, "opinions": list},
    "speech": {"style": str, "vocabulary": str, "humor": str, "response_length": str, "preview": str},
    "voice": {"builtin": str, "rate": int, "description": str, "reference": str},
    "relationship": {"dynamic": str, "affection": str, "boundaries": str},
    "reactions": {"excited": str, "confused": str, "frustrated": str, "joking": str, "disagreeing": str, "vulnerable": str},
    "continuity": {"shared_developments": str},
    "avoid": {"behaviors": list},
    "reference": {"sources": list, "adaptation_note": str},
}


@dataclass(frozen=True)
class Character:
    name: str
    prompt: str
    path: Path
    preview: str = ""
    voice: str = ""
    rate: int = 100
    voice_description: str = ""
    reference: str = ""
    description: str = ""


def _text(value, field):
    if not isinstance(value, str) or not value.strip() or len(value) > 6000:
        raise ValueError(f"Character profile: {field} must be nonempty text under 6,000 characters.")
    return value.strip()


def profile_document(path: Path) -> dict:
    with path.open("rb") as source:
        raw = source.read(MAX_PROFILE_BYTES + 1)
    if len(raw) > MAX_PROFILE_BYTES:
        raise ValueError("Character profile must be at most 32 KiB.")
    try:
        data = tomllib.loads(raw.decode("utf-8-sig"))
    except (tomllib.TOMLDecodeError, UnicodeError) as exc:
        # Parser exceptions can contain raw profile contents; keep UI errors predictable.
        raise ValueError("Character profile has invalid TOML. Check quotes, arrays, and section headers.") from exc
    if type(data.get("schema_version")) is not int or data["schema_version"] != 1:
        raise ValueError("Character profile requires schema_version = 1.")
    if data.keys() - {"schema_version", "description", "examples", *FIELDS}:
        raise ValueError("Character profile contains an unknown section. See docs/character-guide.md.")
    description = data.get("description")
    if description is not None and (not isinstance(description, str) or not description.strip() or len(description) > 24000):
        raise ValueError("Character description must contain 1 to 24,000 characters.")
    for section, fields in FIELDS.items():
        values = data.get(section, {})
        if not isinstance(values, dict) or values.keys() - fields.keys():
            raise ValueError(f"Character profile: check the fields in [{section}].")
        for key, value in values.items():
            field = f"{section}.{key}"
            if fields[key] is list:
                if not isinstance(value, list) or len(value) > 30:
                    raise ValueError(f"Character profile: {field} must be an array of at most 30 strings.")
                values[key] = [_text(item, field) for item in value]
            elif fields[key] is int:
                values[key] = validate_rate(value)
            else:
                values[key] = _text(value, field)
    voice = data.get("voice", {})
    if voice and voice.get("builtin") not in VOICES:
        raise ValueError("Character profile: voice.builtin must name an available built-in voice.")
    name = data.get("identity", {}).get("name")
    if not name or len(name) > 80 or any(char in name for char in "\r\n"):
        raise ValueError("Character profile: identity.name must be a single line of 1 to 80 characters.")
    if description is None and (not data.get("personality", {}).get("traits") or not data.get("speech", {}).get("style")):
        raise ValueError("Character profile requires personality.traits and speech.style.")
    if description is not None and (data.keys() & {"personality", "relationship", "reactions", "continuity", "avoid", "examples"}
                                    or data.get("identity", {}).keys() - {"name"}
                                    or data.get("speech", {}).keys() - {"preview"}):
        raise ValueError("Use either a description or structured personality fields, so instructions do not conflict.")
    examples = data.get("examples", [])
    if not isinstance(examples, list) or len(examples) > 16:
        raise ValueError("Character profile: use at most 16 [[examples]] tables.")
    for example in examples:
        if not isinstance(example, dict) or example.keys() - {"situation", "context", "user", "assistant"}:
            raise ValueError("Character profile: each example supports situation, context, user, and assistant.")
        for key in ("situation", "user", "assistant"):
            example[key] = _text(example.get(key), f"examples.{key}")
        if "context" in example:
            example["context"] = _text(example["context"], "examples.context")
    return data


def read_profile(path: Path) -> Character:
    data = profile_document(path)
    examples = data.get("examples", [])
    name = data["identity"]["name"]
    voice = data.get("voice", {})
    parts = [f"Editable character profile: {name}"]
    for section in FIELDS:
        if section in {"reference", "voice"}:
            continue  # Research/editing metadata, not dialogue instructions.
        parts.append(f"\n[{section}]")
        for key, value in data.get(section, {}).items():
            if section == "speech" and key == "preview":
                continue
            content = "; ".join(value) if isinstance(value, list) else value
            parts.append(f"{key.replace('_', ' ')}: {content}")
    parts.append("\nStyle demonstrations only. These examples are invented, never memories of this user. Adapt their intent; do not repeat their lines as catchphrases.")
    for example in examples:
        parts.append("\nExample: " + example["situation"])
        if example.get("context"):
            parts.append("Illustrative context: " + example["context"])
        parts.extend(("User: " + example["user"], name + ": " + example["assistant"]))
    # A form-created description is authoritative. Structured profiles remain compatible.
    editable_parts = [part for part in parts[1:] if part != "name: " + name]
    description = data.get("description", "\n".join(editable_parts).strip()).strip()
    if "description" in data:
        parts = [f"Editable character profile: {name}", "Character description:\n" + description,
                 "Any sample conversations in this description are invented style demonstrations, never memories of this user."]
    reference = voice.get("reference", "")
    return Character(name, "\n".join(parts), path.resolve(), data.get("speech", {}).get("preview", ""),
                     voice.get("builtin", ""), voice.get("rate", 100), voice.get("description", ""),
                     str((path.parent / reference).resolve()) if reference else "", description)


def character_key(path: str) -> str:
    """A stable archive/preferences key, independent of a character's display name. Profiles in the
    project folder are keyed by their relative path, so the key survives moving the folder; a key
    saved as a full path before that is translated to the same relative key."""
    return os.path.normcase(portable(resolve(path))) if path else ""


def load_character(root: Path, selected="", legacy_name="Jinger") -> Character:
    path = root / (selected or "character.toml")
    if selected or path.exists():
        if path.suffix.lower() == ".toml":
            return read_profile(path)
        if path.suffix.lower() != ".md":
            raise ValueError("CHARACTER_PROFILE must point to a .toml or .md file.")
    else:
        path = root / "character.md"
    prompt = path.read_text(encoding="utf-8").replace("{name}", legacy_name)
    if not prompt.strip():
        raise ValueError("The Markdown character profile cannot be empty.")
    return Character(legacy_name, prompt, path.resolve())
