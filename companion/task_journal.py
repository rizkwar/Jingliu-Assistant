"""Undo for computer tasks: a record of every file change a task makes, and its reversal.

Each task gets a folder under data/task_undo holding journal.jsonl (one change per line, in
order) and copies of what it replaced or deleted. Both the companion app (for Claude Code's
Write and Edit, recorded just before they are allowed) and the task tool server (for moving,
copying, deleting and making folders) append to it. Undo walks it backwards.
Commands and screen actions cannot be reversed; they are listed so the person knows.
"""

import json
import os
from pathlib import Path
import shutil
import time

KEEP_DAYS = 7
UNDOABLE = {"create", "create_dir", "replace", "move", "delete"}


def _normal(path):
    return os.path.normcase(os.path.abspath(str(path)))


class Journal:
    def __init__(self, folder):
        self.folder = Path(folder)
        self.files = self.folder / "files"
        self.path = self.folder / "journal.jsonl"
        self.files.mkdir(parents=True, exist_ok=True)

    # Recording ------------------------------------------------------------------

    def entries(self):
        if not self.path.exists():
            return []
        items = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            try:
                items.append(json.loads(line))
            except ValueError:
                continue
        return items

    def record(self, entry):
        with open(self.path, "a", encoding="utf-8") as output:
            output.write(json.dumps({**entry, "at": time.time()}, ensure_ascii=False) + "\n")

    def _keep(self, path, label):
        """Move (or copy) something into the journal's own storage; returns its stored name."""
        name = f"{len(list(self.files.iterdir())):04d}-{label}-{Path(path).name}"[:180]
        return name

    def _journaled(self, path):
        wanted = _normal(path)
        return any(_normal(item.get("path", "")) == wanted for item in self.entries()
                   if item.get("op") in {"create", "replace"})

    def before_write(self, path):
        """Called just before a file is written or edited: keep the original once per task."""
        path = Path(path)
        if not str(path) or self._journaled(path):
            return
        if path.is_file():
            name = self._keep(path, "original")
            shutil.copy2(path, self.files / name)
            self.record({"op": "replace", "path": str(path), "stored": name})
        elif not path.exists():
            self.record({"op": "create", "path": str(path)})

    def move(self, source, destination):
        source, destination = Path(source), Path(destination)
        if not source.exists():
            raise FileNotFoundError(f"{source} does not exist.")
        if destination.is_dir():
            destination = destination / source.name
        if destination.exists():
            raise FileExistsError(f"{destination} already exists; choose another name.")
        made = self._parents(destination)
        shutil.move(str(source), str(destination))
        for folder in made:
            self.record({"op": "create_dir", "path": str(folder)})
        self.record({"op": "move", "source": str(source), "destination": str(destination)})
        return destination

    def copy(self, source, destination):
        source, destination = Path(source), Path(destination)
        if not source.exists():
            raise FileNotFoundError(f"{source} does not exist.")
        if destination.is_dir():
            destination = destination / source.name
        if destination.exists():
            raise FileExistsError(f"{destination} already exists; choose another name.")
        made = self._parents(destination)
        if source.is_dir():
            shutil.copytree(source, destination)
        else:
            shutil.copy2(source, destination)
        for folder in made:
            self.record({"op": "create_dir", "path": str(folder)})
        self.record({"op": "create", "path": str(destination)})
        return destination

    def delete(self, path):
        """Deleting keeps the item in the journal, so undo can put it back."""
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"{path} does not exist.")
        name = self._keep(path, "deleted")
        shutil.move(str(path), str(self.files / name))
        self.record({"op": "delete", "path": str(path), "stored": name})

    def make_folder(self, path):
        path = Path(path)
        if path.is_dir():
            return path
        for folder in self._parents(path / "x"):
            self.record({"op": "create_dir", "path": str(folder)})
        return path

    def _parents(self, path):
        """Create missing parent folders; returns the ones made, outermost first."""
        missing, folder = [], Path(path).parent
        while not folder.exists():
            missing.append(folder)
            folder = folder.parent
        for folder in reversed(missing):
            folder.mkdir()
        return list(reversed(missing))

    def note(self, kind, text):
        self.record({"op": "note", "kind": kind, "text": str(text)[:300]})

    # Undoing --------------------------------------------------------------------

    def undoable(self):
        return [item for item in self.entries() if item.get("op") in UNDOABLE]

    def plan(self):
        """What undo would do, in plain words, for the confirmation."""
        counts = {}
        for item in self.undoable():
            counts[item["op"]] = counts.get(item["op"], 0) + 1
        words = {"replace": ("restore {} edited file", "restore {} edited files"),
                 "create": ("remove {} new file or folder", "remove {} new files or folders"),
                 "move": ("move {} item back", "move {} items back"),
                 "delete": ("bring back {} deleted item", "bring back {} deleted items"),
                 "create_dir": ("remove {} new folder (if empty)", "remove {} new folders (if empty)")}
        lines = [words[op][count != 1].format(count) for op, count in counts.items() if op in words]
        notes = self.notes()
        return lines, notes

    def notes(self):
        """Steps undo cannot reverse: commands she ran, and screen actions."""
        commands = [item["text"] for item in self.entries() if item.get("op") == "note" and item.get("kind") == "command"]
        screen = any(item.get("op") == "note" and item.get("kind") == "screen" for item in self.entries())
        notes = []
        if commands:
            notes.append(f"{len(commands)} command{'s' if len(commands) != 1 else ''} she ran "
                         f"(for example: {commands[0][:80]})")
        if screen:
            notes.append("clicks and typing in other apps")
        return notes

    def undo(self):
        """Reverse every recorded change, newest first. Returns (done, problems) as plain sentences."""
        done, problems = [], []
        removed = self.files / "removed-by-undo"
        removed.mkdir(exist_ok=True)
        for item in reversed(self.undoable()):
            op = item["op"]
            try:
                if op == "create":
                    path = Path(item["path"])
                    if path.exists():
                        # Not destroyed: set aside with the journal until it is cleaned up.
                        shutil.move(str(path), str(removed / f"{len(list(removed.iterdir())):04d}-{path.name}"))
                    done.append(f"Removed {path}")
                elif op == "create_dir":
                    path = Path(item["path"])
                    if path.is_dir():
                        if any(path.iterdir()):
                            problems.append(f"Left the folder {path}, because it now holds other things")
                            continue
                        path.rmdir()
                    done.append(f"Removed the folder {path}")
                elif op == "replace":
                    path = Path(item["path"])
                    if path.exists():
                        shutil.move(str(path), str(removed / f"{len(list(removed.iterdir())):04d}-{path.name}"))
                    path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(self.files / item["stored"], path)
                    done.append(f"Restored {path}")
                elif op == "move":
                    source, destination = Path(item["source"]), Path(item["destination"])
                    if not destination.exists():
                        problems.append(f"Could not find {destination} to move it back")
                    elif source.exists():
                        problems.append(f"Did not move {destination} back, because {source} exists again")
                    else:
                        source.parent.mkdir(parents=True, exist_ok=True)
                        shutil.move(str(destination), str(source))
                        done.append(f"Moved {destination.name} back to {source.parent}")
                elif op == "delete":
                    path = Path(item["path"])
                    if path.exists():
                        problems.append(f"Did not bring back {path}, because something else is there now")
                    else:
                        path.parent.mkdir(parents=True, exist_ok=True)
                        shutil.move(str(self.files / item["stored"]), str(path))
                        done.append(f"Brought back {path}")
            except OSError as exc:
                problems.append(f"Could not undo a change to {item.get('path') or item.get('destination')}: {exc.strerror or exc}")
        self.record({"op": "undone"})
        return done, problems

    @property
    def undone(self):
        return any(item.get("op") == "undone" for item in self.entries())


def cleanup(root, days=KEEP_DAYS):
    """Forget journals older than a week (their stored copies go with them)."""
    root = Path(root)
    if not root.is_dir():
        return
    limit = time.time() - days * 86400
    for folder in root.iterdir():
        try:
            if folder.is_dir() and folder.stat().st_mtime < limit:
                shutil.rmtree(folder, ignore_errors=True)
        except OSError:
            continue
