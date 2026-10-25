"""Back up, restore and export what the companion keeps about you.

A backup is one zip: the database (conversations, memories, reminders, notes), shared images and
files, settings, characters and avatar choices, and the character profile. The Live2D model files
themselves are not included (large, and re-importable). Restoring first saves what is there now.
"""

from datetime import datetime
import json
import os
from pathlib import Path
import shutil
import sqlite3
import tempfile
import time
import zipfile

from .config import PROJECT_ROOT

DATA = PROJECT_ROOT / "data"
DATABASE = "companion.sqlite3"
FILES = ("preferences.json", "avatars.json", "avatar_models.json")
FOLDERS = ("attachments", "characters")
PROFILE = "character.toml"
MANIFEST = "jingliu-backup.json"
README = """This is a backup of Jingliu, your desktop companion.

Restore it from Settings -> App -> Restore from a backup. Or by hand: quit Jingliu, then copy
everything in data/ into the project's data folder, and project/character.toml into the project folder.
"""


def backup(store, target, data=DATA, project=PROJECT_ROOT):
    """Write a backup zip to `target`. The database is copied consistently while the app runs."""
    target = Path(target)
    with tempfile.TemporaryDirectory(prefix="jingliu-backup-") as folder:
        copy = Path(folder) / DATABASE
        destination = sqlite3.connect(str(copy))
        try:
            store.connection.backup(destination)
        finally:
            destination.close()
        partial = target.with_name(target.name + ".partial")
        with zipfile.ZipFile(partial, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(MANIFEST, json.dumps({"app": "Jingliu", "created": datetime.now().astimezone().isoformat(),
                                                   "schema": store.connection.execute("PRAGMA user_version").fetchone()[0]}))
            archive.writestr("README.txt", README)
            archive.write(copy, f"data/{DATABASE}")
            for name in FILES:
                if (Path(data) / name).is_file():
                    archive.write(Path(data) / name, f"data/{name}")
            for name in FOLDERS:
                root = Path(data) / name
                for path in sorted(root.rglob("*")) if root.is_dir() else ():
                    if path.is_file():
                        archive.write(path, f"data/{name}/{path.relative_to(root).as_posix()}")
            if (Path(project) / PROFILE).is_file():
                archive.write(Path(project) / PROFILE, f"project/{PROFILE}")
        os.replace(partial, target)
    return target


def check(source):
    """The backup's description, or ValueError if this is not a Jingliu backup."""
    try:
        with zipfile.ZipFile(source) as archive:
            names = set(archive.namelist())
            if MANIFEST not in names or f"data/{DATABASE}" not in names:
                raise ValueError("This file is not a Jingliu backup.")
            for name in names:  # Nothing may land outside the data and project folders.
                parts = Path(name).parts
                if Path(name).is_absolute() or ".." in parts or (parts and parts[0] not in {"data", "project", MANIFEST, "README.txt"}):
                    raise ValueError("This backup contains unexpected paths and was not used.")
            return json.loads(archive.read(MANIFEST))
    except zipfile.BadZipFile as exc:
        raise ValueError("This file is not a readable backup.") from exc


def restore(source, safety_folder, data=DATA, project=PROJECT_ROOT, store=None):
    """Replace the current data with a backup's. What is there now is saved to `safety_folder`
    first (a zip, returned). The app must be closed and reopened afterwards."""
    check(source)
    safety_folder = Path(safety_folder)
    safety_folder.mkdir(parents=True, exist_ok=True)
    safety = safety_folder / f"before-restore-{time.strftime('%Y%m%d-%H%M%S')}.zip"
    if store is not None:
        backup(store, safety, data, project)
        store.close()
    with zipfile.ZipFile(source) as archive:
        for name in FOLDERS:
            shutil.rmtree(Path(data) / name, ignore_errors=True)  # Replaced as a whole, not merged.
        for sidecar in ("-wal", "-shm"):
            (Path(data) / (DATABASE + sidecar)).unlink(missing_ok=True)
        for item in archive.infolist():
            if item.is_dir() or item.filename in {MANIFEST, "README.txt"}:
                continue
            top, _, rest = item.filename.partition("/")
            target = (Path(data) if top == "data" else Path(project)) / rest
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(item) as source_file, open(target, "wb") as output:
                shutil.copyfileobj(source_file, output)
    return safety


def export_text(store, target, name="Jingliu"):
    """Every conversation, memory and reminder as one readable Markdown file."""
    from . import attachments
    from .reminders import describe
    lines = [f"# Conversations with {name}", "", f"Exported {datetime.now():%d %B %Y, %H:%M}.", ""]
    memories = store.memories()
    lines += ["## Memories", ""]
    lines += [f"- {memory['content']}" + (" (pinned)" if memory["pinned"] else "") for memory in memories] or ["(none)"]
    upcoming = store.reminders()
    lines += ["", "## Reminders", ""]
    lines += [f"- {item['text']} — {describe(item)}" for item in upcoming] or ["(none)"]
    for conversation in store.conversations():
        messages = [m for m in store.messages(conversation["id"]) if m.get("display")]
        if not messages:
            continue
        lines += ["", f"## {conversation['title']}", "", f"_{_when(conversation['created_at'])}_", ""]
        for message in messages:
            speaker = "You" if message["role"] == "user" else name
            files = attachments.loads(message.get("attachments") or "")
            attached = "".join(f"\n\n*[Attached: {item.get('name', 'file')}]*" for item in files)
            lines += [f"**{speaker}:** {message['display'].strip()}{attached}", ""]
    Path(target).write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return Path(target)


def _when(timestamp):
    try:
        return f"{datetime.fromisoformat(timestamp).astimezone():%d %B %Y, %H:%M}"
    except (TypeError, ValueError):
        return ""
