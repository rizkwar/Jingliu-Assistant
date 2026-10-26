"""Saved paths are kept relative to the project folder, so moving or renaming the folder loses nothing."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def portable(path, root=ROOT) -> str:
    """How to save `path`: relative to the project folder when it is inside it, else as given."""
    if not Path(path).is_absolute():
        return Path(path).as_posix()
    try:
        return Path(path).resolve().relative_to(Path(root).resolve()).as_posix()
    except ValueError:
        return str(path)


def resolve(saved, root=ROOT) -> Path:
    """A saved path as a real one. A full path saved before the project folder moved no longer exists;
    it is found again by its end (...\\OldName\\voices\\her.wav -> voices/her.wav), longest end first."""
    path = Path(saved)
    if not path.is_absolute():
        return (Path(root) / path).resolve()
    if path.exists():
        return path
    parts = path.parts[1:]
    for start in range(len(parts)):
        candidate = Path(root).joinpath(*parts[start:])
        if candidate.exists():
            return candidate.resolve()
    return path
