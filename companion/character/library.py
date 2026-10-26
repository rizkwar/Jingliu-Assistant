"""Local character library: editable descriptions and managed reference recordings."""

from dataclasses import dataclass
import json
import os
from pathlib import Path
import tempfile
from uuid import uuid4

from .profile import MAX_PROFILE_BYTES, character_key, profile_document, read_profile
from ..voice.reference import inspect_reference
from ..voice.settings import validate_rate, VOICES


@dataclass(frozen=True)
class ProfileDraft:
    name: str
    description: str
    reference: str = ""
    builtin: str = "alba"
    rate: int = 100
    preview: str = ""


def _atomic_write(path, content):
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix="character-", suffix=".tmp", delete=False) as output:
            temporary = Path(output.name)
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


class CharacterLibrary:
    def __init__(self, root: Path):
        self.root = Path(root).resolve()
        self.directory = self.root / "data" / "characters"

    def profiles(self, current="", known=()):
        """Include configured/existing profiles even if they live outside the library."""
        paths = [self.root / "character.toml", *sorted(self.directory.glob("*/profile.toml")),
                 *(Path(path) for path in known)]
        if current:
            paths.insert(0, Path(current))
        entries, seen = [], set()
        for path in paths:
            key = character_key(str(path))
            if key in seen or not path.is_file() or path.suffix.lower() not in {".toml", ".md"}:
                continue
            seen.add(key)
            if path.suffix.lower() == ".md":
                entries.append((str(path.resolve()), "Legacy character (Markdown)", ""))
                continue
            try:
                entries.append((str(path.resolve()), read_profile(path).name, ""))
            except (OSError, ValueError) as exc:
                entries.append((str(path.resolve()), path.stem + " (needs repair)", str(exc)))
        return entries

    def draft(self, path) -> ProfileDraft:
        character = read_profile(Path(path))
        return ProfileDraft(character.name, character.description, character.reference,
                            character.voice or "alba", character.rate, character.preview)

    def save(self, draft: ProfileDraft, existing=None) -> Path:
        """Validate before changing a profile; copy audio without changing the source file."""
        name, description = draft.name.strip(), draft.description.strip()
        if not name or len(name) > 80 or any(char in name for char in "\r\n"):
            raise ValueError("Give the character a single-line name of 1 to 80 characters.")
        if not description or len(description) > 24000:
            raise ValueError("Describe the character in 1 to 24,000 characters.")
        if draft.builtin not in VOICES:
            raise ValueError("Choose an available built-in voice.")
        validate_rate(draft.rate)
        reference = inspect_reference(draft.reference) if draft.reference else None
        document = {"schema_version": 1, "description": description, "identity": {"name": name},
                    "voice": {"builtin": draft.builtin, "rate": draft.rate}}
        if draft.preview.strip():
            document["speech"] = {"preview": draft.preview.strip()}
        path = Path(existing).resolve() if existing else self.directory / uuid4().hex / "profile.toml"
        # Preserve research provenance when converting a structured profile to a description.
        original = path.read_bytes() if existing else None
        if existing:
            old = profile_document(path)
            if "reference" in old:
                document["reference"] = old["reference"]
        voice_path = None
        if reference:
            audio_dir = path.parent if path.parent.is_relative_to(self.directory.resolve()) else self.directory / "_audio"
            voice_path = audio_dir / ("voice-" + reference.fingerprint + ".wav")
            document["voice"]["reference"] = Path(os.path.relpath(voice_path, path.parent)).as_posix()
        lines = ["# Edit this description directly, or use Settings > Edit character.",
                 "schema_version = 1", "description = " + json.dumps(description, ensure_ascii=False)]
        for section in ("identity", "speech", "voice", "reference"):
            if section in document:
                lines.append("\n[" + section + "]")
                lines.extend(key + " = " + json.dumps(value, ensure_ascii=False)
                             for key, value in document[section].items())
        content = ("\n".join(lines) + "\n").encode("utf-8")
        if len(content) > MAX_PROFILE_BYTES:
            raise ValueError("The saved profile would exceed 32 KiB. Shorten the description or preview.")
        created_audio = False
        created_directory = not path.parent.exists()
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary_profile = None
        try:
            # Validate the complete file using the same reader as startup, before replacing anything.
            with tempfile.NamedTemporaryFile(dir=path.parent, suffix=".toml", delete=False) as output:
                temporary_profile = Path(output.name)
                output.write(content)
            read_profile(temporary_profile)
            if reference and not voice_path.exists():
                voice_path.parent.mkdir(parents=True, exist_ok=True)
                _atomic_write(voice_path, reference.path.read_bytes())
                created_audio = True
            if reference:
                if inspect_reference(voice_path).fingerprint != reference.fingerprint:
                    raise ValueError("The managed voice recording changed. Choose the source recording again.")
            # Keep a first-edit backup of existing hand-authored profiles.
            backup = path.with_suffix(path.suffix + ".bak")
            if original is not None and not backup.exists():
                with backup.open("xb") as output:
                    output.write(original)
            _atomic_write(path, content)
        except Exception:
            if created_audio:
                voice_path.unlink(missing_ok=True)
            raise
        finally:
            if temporary_profile is not None:
                temporary_profile.unlink(missing_ok=True)
            if created_directory and not any(path.parent.iterdir()):
                path.parent.rmdir()
        return path.resolve()
