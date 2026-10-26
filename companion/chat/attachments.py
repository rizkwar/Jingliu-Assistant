"""Images and files attached to a message: validation, local copies and model input blocks."""
import base64
import json
from pathlib import Path
import shutil
from uuid import uuid4

from ..core.config import PROJECT_ROOT


ATTACHMENT_ROOT = PROJECT_ROOT / "data" / "attachments"
IMAGE_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif", ".webp": "image/webp",
               ".bmp": "image/png"}
MAX_FILES = 6
MAX_IMAGE_EDGE = 1568        # Larger images are downscaled by the model anyway; send less.
MAX_IMAGE_BYTES = 3_500_000  # Stays under the 5 MB per-image API limit after base64.
MAX_PDF_BYTES = 20_000_000
MAX_TEXT_BYTES = 2_000_000
MAX_TEXT_CHARS = 60_000      # Per file, so one log cannot crowd out the conversation.
FILE_FILTER = ("Images and documents (*.png *.jpg *.jpeg *.gif *.webp *.bmp *.pdf *.txt *.md *.csv *.json *.py *.js *.ts "
               "*.html *.css *.xml *.yaml *.yml *.toml *.ini *.log *.c *.cpp *.h *.java *.cs *.go *.rs *.sql);;All files (*)")


class AttachmentError(ValueError):
    """A file that cannot be attached, with a reason the user can act on."""


def classify(path):
    """Return (kind, mime) for a file the companion can send, or raise AttachmentError."""
    path = Path(path)
    if not path.is_file():
        raise AttachmentError(f"{path.name} could not be found.")
    suffix = path.suffix.lower()
    size = path.stat().st_size
    if suffix in IMAGE_TYPES:
        # Qt is imported here so storage (and the startup check) never need it.
        from PySide6.QtGui import QImage
        if QImage(str(path)).isNull():
            raise AttachmentError(f"{path.name} is not a readable image.")
        return "image", IMAGE_TYPES[suffix]
    if suffix == ".pdf":
        if size > MAX_PDF_BYTES:
            raise AttachmentError(f"{path.name} is larger than 20 MB.")
        return "pdf", "application/pdf"
    if size > MAX_TEXT_BYTES:
        raise AttachmentError(f"{path.name} is too large to read as text (over 2 MB).")
    sample = path.read_bytes()
    if b"\0" in sample[:8192]:
        raise AttachmentError(f"{path.name} isn't an image, PDF or text file, so it can't be read here.")
    try:
        sample.decode("utf-8")
    except UnicodeDecodeError:
        try:
            sample.decode("cp1252")
        except UnicodeDecodeError:
            raise AttachmentError(f"{path.name} isn't readable text.") from None
    return "text", "text/plain"


def store(paths, root=ATTACHMENT_ROOT):
    """Copy attachments into the app's data folder so the chat can show them later."""
    if len(paths) > MAX_FILES:
        raise AttachmentError(f"Attach up to {MAX_FILES} files per message.")
    folder = Path(root) / uuid4().hex
    folder.mkdir(parents=True, exist_ok=True)
    stored = []
    try:
        for index, source in enumerate(map(Path, paths)):
            kind, mime = classify(source)
            target = folder / f"{index}-{source.name}"
            if kind == "image":
                target, mime = _store_image(source, target, mime)
            else:
                shutil.copyfile(source, target)
            stored.append({"name": source.name, "kind": kind, "mime": mime, "path": str(target)})
    except (OSError, AttachmentError):
        shutil.rmtree(folder, ignore_errors=True)
        raise
    return stored


def _store_image(source, target, mime):
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QImage
    image = QImage(str(source))
    small = max(image.width(), image.height()) <= MAX_IMAGE_EDGE
    if small and source.stat().st_size <= MAX_IMAGE_BYTES and source.suffix.lower() != ".bmp":
        shutil.copyfile(source, target)
        return target, mime
    if not small:
        image = image.scaled(MAX_IMAGE_EDGE, MAX_IMAGE_EDGE, Qt.AspectRatioMode.KeepAspectRatio,
                             Qt.TransformationMode.SmoothTransformation)
    alpha = image.hasAlphaChannel()
    target = target.with_suffix(".png" if alpha else ".jpg")
    if not image.save(str(target), "PNG" if alpha else "JPG", -1 if alpha else 88):
        raise AttachmentError(f"{source.name} could not be prepared.")
    return target, "image/png" if alpha else "image/jpeg"


def note(attachments):
    """Short history line: later turns know what was shared without resending it."""
    return "\n".join(f"[Attached {'image' if item['kind'] == 'image' else 'file'}: {item['name']}]" for item in attachments)


def read_text(item):
    raw = Path(item["path"]).read_bytes()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode("cp1252", errors="replace")
    if len(text) > MAX_TEXT_CHARS:
        text = text[:MAX_TEXT_CHARS] + f"\n[… truncated; the file has {len(text):,} characters]"
    return f'<attached_file name="{item["name"]}">\n{text}\n</attached_file>'


def encoded(item):
    return base64.b64encode(Path(item["path"]).read_bytes()).decode("ascii")


def content_blocks(text, attachments):
    """Anthropic-style user content: the message text, then each attachment."""
    blocks = [{"type": "text", "text": text or "(See the attached files.)"}]
    for item in attachments:
        if item["kind"] == "image":
            blocks.append({"type": "image", "source": {"type": "base64", "media_type": item["mime"], "data": encoded(item)}})
        elif item["kind"] == "pdf":
            blocks.append({"type": "document", "title": item["name"],
                           "source": {"type": "base64", "media_type": "application/pdf", "data": encoded(item)}})
        else:
            blocks.append({"type": "text", "text": read_text(item)})
    return blocks


def dumps(attachments):
    return json.dumps(list(attachments), ensure_ascii=False) if attachments else ""


def loads(value):
    try:
        items = json.loads(value) if value else []
    except ValueError:
        return []
    return [item for item in items if isinstance(item, dict) and {"name", "kind", "path"} <= item.keys()]


def remove_files(attachments, root=None):
    """Delete stored copies, never anything outside the attachment folder."""
    root = Path(root or ATTACHMENT_ROOT).resolve()
    for item in attachments:
        folder = Path(item["path"]).resolve().parent
        if folder.parent == root:
            shutil.rmtree(folder, ignore_errors=True)
