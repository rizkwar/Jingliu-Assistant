"""A study subject's materials folder: read in place, never copied, and given to her a little at a time.

Every reply she sees the folder's index (what is in it), and only the passages most related to the
message, instead of every file in full. Text taken out of a file is cached by its path, size and time,
so a PDF is read once, not on every message."""
from __future__ import annotations

import hashlib
import json
import math
import re
import threading
import time
import zipfile
from pathlib import Path

from ..core.config import PROJECT_ROOT
from ..core.storage import terms

CACHE = PROJECT_ROOT / "data/cache/materials"
TEXT = {".txt", ".md", ".markdown", ".csv", ".tsv", ".json", ".sql", ".py", ".java", ".c", ".cpp", ".h", ".js",
        ".ts", ".html", ".css", ".xml", ".yaml", ".yml", ".tex", ".r", ".m", ".ipynb", ".rst", ".log"}
DOCUMENTS = {".pdf", ".docx", ".pptx"}
MAX_FILES = 400            # Listed in the index; a folder of a whole course is still well under this.
MAX_FILE_BYTES = 64 * 1024 * 1024
INDEX_CHARS = 4_000        # The folder's index, every reply.
EXCERPT_CHARS = 12_000     # The passages related to the message, every reply.
CHUNK = 1_400              # One passage.
READ_BUDGET = 1.5          # Seconds spent reading new files while you wait for a reply; the rest is read later.

_lock = threading.Lock()


def files(folder):
    """The readable-looking files in a folder and its subfolders, as (relative path, Path), sorted."""
    root = Path(folder)
    if not root.is_dir():
        return []
    found = []
    for path in sorted(root.rglob("*")):
        if len(found) >= MAX_FILES:
            break
        if path.is_file() and not any(part.startswith(".") or part.startswith("~$") for part in path.relative_to(root).parts):
            found.append((path.relative_to(root).as_posix(), path))
    return found


def _cache_path(path, stat):
    key = f"{path.resolve()}|{stat.st_size}|{stat.st_mtime_ns}".encode("utf-8")
    return CACHE / (hashlib.sha256(key).hexdigest()[:32] + ".json")


def _xml_text(archive, names, tag):
    parts = []
    for name in names:
        raw = archive.read(name).decode("utf-8", errors="replace")
        parts.append(" ".join(re.findall(rf"<{tag}[^>]*>([^<]*)</{tag}>", raw)))
    return parts


def _extract(path):
    """[(where, text)] for a file: PDF pages, slides, or the whole text. Empty when unreadable."""
    suffix = path.suffix.lower()
    if suffix in TEXT:
        raw = path.read_bytes()[:4 * 1024 * 1024]
        try:
            return [("", raw.decode("utf-8"))]
        except UnicodeDecodeError:
            return [("", raw.decode("cp1252", errors="replace"))]
    if suffix == ".pdf":
        from pypdf import PdfReader
        reader = PdfReader(str(path))
        return [(f"page {number}", page.extract_text() or "") for number, page in enumerate(reader.pages[:400], 1)]
    if suffix == ".pptx":
        with zipfile.ZipFile(path) as archive:
            slides = sorted((n for n in archive.namelist() if re.fullmatch(r"ppt/slides/slide\d+\.xml", n)),
                            key=lambda n: int(re.search(r"\d+", n.rsplit("/", 1)[1]).group()))
            return [(f"slide {number}", text) for number, text in enumerate(_xml_text(archive, slides, "a:t"), 1)]
    if suffix == ".docx":
        with zipfile.ZipFile(path) as archive:
            return [("", "\n".join(_xml_text(archive, ["word/document.xml"], "w:t")))]
    return []


def text(path, cache=None):
    """A file's text as [(where, text)], from the cache when the file has not changed. None if unreadable."""
    cache = Path(cache or CACHE)
    try:
        stat = path.stat()
        if stat.st_size > MAX_FILE_BYTES or path.suffix.lower() not in TEXT | DOCUMENTS:
            return None
        cached = cache / _cache_path(path, stat).name
        if cached.is_file():
            return [tuple(part) for part in json.loads(cached.read_text(encoding="utf-8"))] or None
        parts = [(where, " ".join(body.split())) for where, body in _extract(path)]
        parts = [(where, body) for where, body in parts if body]
        with _lock:
            cached.parent.mkdir(parents=True, exist_ok=True)
            cached.write_text(json.dumps(parts, ensure_ascii=False), encoding="utf-8")
        return parts or None
    except Exception:  # A damaged, locked or encrypted file is listed by name instead.
        return None


def is_cached(path, cache=None):
    cache = Path(cache or CACHE)
    try:
        return (cache / _cache_path(path, path.stat()).name).is_file()
    except OSError:
        return False


_warming = set()


def warm(folder, cache=None):
    """Reads the folder's files into the cache in the background, so her first reply is not kept waiting."""
    cache = Path(cache or CACHE)
    key = str(Path(folder).resolve())
    with _lock:
        if key in _warming:
            return
        _warming.add(key)

    def read():
        try:
            for _, path in files(folder):
                text(path, cache)
        finally:
            with _lock:
                _warming.discard(key)
    threading.Thread(target=read, name="materials", daemon=True).start()


def _passages(name, parts):
    for where, body in parts:
        for start in range(0, len(body), CHUNK):
            yield name, where, body[start:start + CHUNK + 200]  # A little overlap keeps sentences whole.


def context(folder, query, cache=None, budget=READ_BUDGET):
    """Her materials section: the index of the folder, then the passages most related to `query`."""
    cache = Path(cache or CACHE)
    listed = files(folder)
    if not listed:
        return (f"Materials folder: {folder} (it is empty or could not be opened; ask the user to check it in the "
                "subject's page).")
    deadline, readable, waiting, unreadable = time.monotonic() + budget, {}, [], []
    for name, path in listed:
        if is_cached(path, cache) or time.monotonic() < deadline:
            parts = text(path, cache)
            (readable.__setitem__(name, parts) if parts else unreadable.append(name))
        else:
            waiting.append(name)
    if waiting:
        warm(folder, cache)
    index, used = [], 0
    for name, _ in listed:
        parts = readable.get(name)
        line = f"- {name}" + (f" ({len(parts)} {'pages' if parts[0][0].startswith('page') else 'slides' if parts[0][0].startswith('slide') else 'parts'})"
                               if parts and parts[0][0] else "")
        if used + len(line) > INDEX_CHARS:
            index.append(f"- … and {len(listed) - len(index)} more files")
            break
        index.append(line)
        used += len(line)
    lines = [f"Materials folder: {folder}\nWhat is in it:\n" + "\n".join(index)]
    # The passages that share the most (rarer counting more) words with the message.
    wanted = terms(query or "")
    passages = [(name, where, body) for name, parts in readable.items() for name, where, body in _passages(name, parts)]
    if wanted and passages:
        seen = [terms(body) for _, _, body in passages]
        rarity = {word: math.log(1 + len(passages) / (1 + sum(word in found for found in seen))) for word in wanted}
        scored = sorted(((sum(rarity[word] for word in wanted & found), k) for k, found in enumerate(seen)), reverse=True)
        chosen, room = [], EXCERPT_CHARS
        for score, k in scored:
            if score <= 0 or room <= 0:
                break
            name, where, body = passages[k]
            place = f' where="{where}"' if where else ""
            chosen.append(f'<material file="{name}"{place}>\n{body[:room]}\n</material>')
            room -= len(body)
        if chosen:
            lines.append("Passages from these materials related to the message (the rest is not shown; if you need "
                         "a part that is not here, say which file and the user can ask about it):\n" + "\n".join(chosen))
    if waiting:
        lines.append("Still being read, not searched yet: " + ", ".join(waiting[:20]))
    if unreadable:
        lines.append("Not readable as text here (listed only): " + ", ".join(unreadable[:20]))
    return "\n\n".join(lines)


def summary(folder, cache=None):
    """(files, read so far, characters) for the subject's page."""
    cache = Path(cache or CACHE)
    listed = files(folder)
    read = total = 0
    for _, path in listed:
        if is_cached(path, cache):
            parts = text(path, cache)
            if parts:
                read += 1
                total += sum(len(body) for _, body in parts)
    return len(listed), read, total
