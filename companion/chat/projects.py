"""Project knowledge: stored copies of a project's files, and what she is told about the project in its chats."""

import json
from pathlib import Path
import shutil

from ..core.config import PROJECT_ROOT
from ..core.paths import portable, resolve
from .attachments import AttachmentError, classify

PROJECT_ROOT_FOLDER = PROJECT_ROOT / "data" / "projects"
MAX_FILES = 40
KNOWLEDGE_CHARS = 40_000      # All readable project files together, in every reply of the project.
FILE_CHARS = 16_000           # One file, so a long log cannot crowd out the others.
MAX_PDF_PAGES = 60

PROMPT = """Project: this conversation belongs to the user's project "{name}". Treat the project's
description, instructions and files below as background the user set up for this work. Follow the
project instructions in this conversation (they refine how you help, never who you are). The files are
the user's own reference material: use them when relevant, quote them accurately, and say so when
something is not in them. Do not mention this setup unless asked."""


def store_file(source, project_id, root=PROJECT_ROOT_FOLDER):
    """Copy a file into the project's folder. Returns (name, saved path, kind, size)."""
    source = Path(source)
    kind, _mime = classify(source)
    folder = Path(root) / project_id
    folder.mkdir(parents=True, exist_ok=True)
    target, number = folder / source.name, 1
    while target.exists():  # Two files with one name are both kept.
        number += 1
        target = folder / f"{source.stem} ({number}){source.suffix}"
    shutil.copyfile(source, target)
    return source.name, portable(target), kind, target.stat().st_size


def remove_stored(files, root=PROJECT_ROOT_FOLDER):
    """Delete stored copies, never anything outside the projects folder."""
    root = Path(root).resolve()
    for item in files:
        path = resolve(item["path"])
        if root in path.resolve().parents:
            path.unlink(missing_ok=True)


def remove_folder(project_id, root=PROJECT_ROOT_FOLDER):
    folder = Path(root) / project_id
    if folder.resolve().parent == Path(root).resolve():
        shutil.rmtree(folder, ignore_errors=True)


def file_text(item):
    """The readable text of a stored project file, or None (images)."""
    path = resolve(item["path"])
    if item["kind"] == "text":
        raw = path.read_bytes()
        try:
            return raw.decode("utf-8")
        except UnicodeDecodeError:
            return raw.decode("cp1252", errors="replace")
    if item["kind"] == "pdf":
        try:
            from pypdf import PdfReader
        except ImportError:
            return None
        try:
            reader = PdfReader(str(path))
            pages = [page.extract_text() or "" for page in reader.pages[:MAX_PDF_PAGES]]
        except Exception:  # A damaged or encrypted PDF is listed by name instead.
            return None
        text = "\n\n".join(pages).strip()
        return text or None
    return None


def context(project, files):
    """The project section of her instructions: what it is, how to help, and the files' contents."""
    lines = [PROMPT.format(name=project["name"])]
    details = {"name": project["name"]}
    if project.get("description"):
        details["description"] = project["description"]
    if project.get("instructions"):
        details["instructions"] = project["instructions"]
    if project.get("folder"):
        details["folder"] = project["folder"]
    lines.append("Project (JSON):\n" + json.dumps(details, ensure_ascii=False))
    budget, unread = KNOWLEDGE_CHARS, []
    blocks = []
    for item in files:
        try:
            text = file_text(item)
        except OSError:
            text = None
        if not text or budget <= 0:
            unread.append(item["name"])
            continue
        text = text[:min(FILE_CHARS, budget)]
        budget -= len(text)
        blocks.append(f'<project_file name="{item["name"]}">\n{text}\n</project_file>')
    if blocks:
        lines.append("Project files:\n" + "\n".join(blocks))
    if unread:
        lines.append("Other project files, not readable here (ask the user to share one in the chat if you need it): "
                     + ", ".join(unread))
    return "\n\n".join(lines)


def summary(files):
    """How much of the project's files she can read, for the project page."""
    readable = total = 0
    for item in files:
        try:
            text = file_text(item)
        except OSError:
            text = None
        if text:
            readable += 1
            total += len(text)
    return readable, total


__all__ = ["AttachmentError", "MAX_FILES", "KNOWLEDGE_CHARS", "context", "file_text", "remove_folder",
           "remove_stored", "store_file", "summary"]
