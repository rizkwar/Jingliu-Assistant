"""Claude Code sessions that continue a conversation, so earlier messages are read from the prompt cache.

Without a session every reply sends the recent history again, and the service processes all of it again (a
cache write, which costs more than plain input). A continuing session sends only what is new; everything before
is read from the cache at about a tenth of the price. A conversation starts a fresh session when its session no
longer matches it (a message was edited or deleted, the model or notes changed), has grown large, or has been idle
long enough for the cache to expire. Claude Code keeps each session's transcript on this computer; the app deletes
it with the conversation, when the session is replaced, and after SESSION_DAYS.

Computer tasks continue the conversation's previous task session for a while, so files she read for one task are
still in front of her for the next.
"""

from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
from uuid import uuid4

from ..core.config import PROJECT_ROOT
from .continuity import split_turns


FOLDER = PROJECT_ROOT / "data" / "claude-sessions"  # Where chat sessions run: an empty folder of their own.
ROTATE_TOKENS = 40_000  # A session larger than this starts again from the recent window.
MAX_TURNS = 40
IDLE_SECONDS = 55 * 60  # The cache lasts an hour; after that, resuming a large session would process it all again.
COLD_TOKENS = 12_000  # A cold session smaller than this is still worth continuing.
TASK_ROTATE_TOKENS = 120_000
TASK_IDLE_SECONDS = 3 * 60 * 60
SESSION_DAYS = 30


def _now():
    return datetime.now(timezone.utc)


def _age(stamp, moment=None):
    try:
        return ((moment or _now()) - datetime.fromisoformat(stamp)).total_seconds()
    except (TypeError, ValueError):
        return float("inf")


def claude_home():
    return Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude")


def transcripts(session_id):
    """Where Claude Code keeps this session's transcript (under the folder it ran in)."""
    if not re.fullmatch(r"[0-9a-f-]{36}", str(session_id)):
        return []
    return list((claude_home() / "projects").glob(f"*/{session_id}.jsonl"))


def delete_transcript(session_id):
    for path in transcripts(session_id):
        try:
            path.unlink()
        except OSError:
            pass


def fingerprint(turns):
    """What a session holds, so an edited or deleted message is noticed."""
    data = [(turn["user_id"], turn["assistant_id"], turn["user"], turn["assistant"]) for turn in turns]
    return hashlib.sha256(json.dumps(data, ensure_ascii=False).encode("utf-8")).hexdigest()


def notes_hash(notes):
    return hashlib.sha256((notes or "").encode("utf-8")).hexdigest()[:16] if notes else ""


def _messages(turns):
    return [message for turn in turns for message in (
        {"role": "user", "content": turn["user"]}, {"role": "assistant", "content": turn["assistant"]})]


def window_seed(turns):
    """The first message a new session starts from: the start of the recent window."""
    _, recent = split_turns(turns, stepped=True)
    return recent[0]["user_id"] if recent else 0


def stale(row, turns, model, notes, moment=None):
    """Why this conversation's session can no longer continue it, or an empty string."""
    if row["model"] != model:
        return "model"
    if row["notes"] != notes_hash(notes):
        return "notes"
    if row["size"] > ROTATE_TOKENS or row["turns"] >= MAX_TURNS:
        return "full"
    if _age(row["updated_at"], moment) > IDLE_SECONDS and row["size"] > COLD_TOKENS:
        return "cold"
    covered = [turn for turn in turns if row["seed_from"] <= turn["user_id"] and turn["assistant_id"] <= row["through_id"]]
    if fingerprint(covered) != row["fingerprint"]:
        return "edited"
    if not transcripts(row["session_id"]):
        return "missing"
    return ""


def plan(store, conversation_id, turns, model, notes, moment=None):
    """How the next reply runs: {"id", "resume", "since", "sent"}. `since`: messages the session has not seen
    (a task's report, say), sent along with the new message; `sent`: study passages it already has."""
    row = store.chat_session(conversation_id)
    if row and not stale(row, turns, model, notes, moment):
        since = [turn for turn in turns if turn["assistant_id"] > row["through_id"]]
        try:
            sent = json.loads(row["passages"])
        except ValueError:
            sent = []
        return {"id": row["session_id"], "resume": True, "since": _messages(since), "sent": sent,
                "seed_from": row["seed_from"], "turns": row["turns"], "size": row["size"]}
    if row:
        forget_chat(store, conversation_id)
    return {"id": str(uuid4()), "resume": False, "since": [], "sent": [], "seed_from": window_seed(turns), "turns": 0,
            "size": 0}


def record(store, conversation_id, session, model, notes, through_id, size, first_user_id=0):
    """After a complete reply: the session now holds everything up to `through_id`."""
    seed = session["seed_from"] or first_user_id
    turns = store.context_turns(conversation_id)
    covered = [turn for turn in turns if seed <= turn["user_id"] and turn["assistant_id"] <= through_id]
    store.save_chat_session(conversation_id, session_id=session["id"], model=model, seed_from=seed,
                            through_id=through_id, fingerprint=fingerprint(covered), notes=notes_hash(notes),
                            passages=json.dumps(session.get("sent", [])[-200:]), size=int(size or 0),
                            turns=session.get("turns", 0) + 1)


def forget(store, conversation_id):
    """Ends a conversation's sessions: their rows and Claude Code's transcripts."""
    for get, drop in ((store.chat_session, store.drop_chat_session), (store.task_session, store.drop_task_session)):
        row = get(conversation_id)
        if row:
            drop(conversation_id)
            delete_transcript(row["session_id"])


def forget_chat(store, conversation_id):
    row = store.chat_session(conversation_id)
    if row:
        store.drop_chat_session(conversation_id)
        delete_transcript(row["session_id"])


_MATERIAL = re.compile(r'<material file="[^"]*"(?: where="[^"]*")?>\n.*?\n</material>', re.DOTALL)


def dedupe(context, sent):
    """Study passages the session already has are not sent again. Returns (context, every passage sent)."""
    if not context:
        return context, list(sent)
    known, kept = set(sent), list(sent)
    repeated = 0

    def keep(match):
        nonlocal repeated
        key = hashlib.sha256(match.group(0).encode("utf-8")).hexdigest()[:16]
        if key in known:
            repeated += 1
            return ""
        known.add(key)
        kept.append(key)
        return match.group(0)
    text = _MATERIAL.sub(keep, context)
    if repeated:
        text = re.sub(r"\n{3,}", "\n\n", text) + (f"\n({repeated} related passage{'s' if repeated != 1 else ''} "
                                                 "shown earlier in this conversation not repeated.)")
    return text, kept


def task_plan(store, conversation_id, cwd, model, moment=None):
    """The session a computer task runs in: the conversation's last task session while it is recent and was in the
    same folder, so she still has what she read; otherwise a new one."""
    row = store.task_session(conversation_id)
    if row:
        fresh = (row["cwd"] == str(cwd) and row["model"] == model and row["size"] <= TASK_ROTATE_TOKENS
                 and _age(row["updated_at"], moment) <= TASK_IDLE_SECONDS and transcripts(row["session_id"]))
        if fresh:
            return {"id": row["session_id"], "resume": True, "tasks": row["tasks"]}
        store.drop_task_session(conversation_id)
        delete_transcript(row["session_id"])
    return {"id": str(uuid4()), "resume": False, "tasks": 0}


def record_task(store, conversation_id, session, cwd, model, size):
    store.save_task_session(conversation_id, session_id=session["id"], cwd=str(cwd), model=model, size=int(size or 0),
                            tasks=session.get("tasks", 0) + 1)


def cleanup(store, moment=None):
    """Transcripts that are no longer needed: replaced chat sessions, old task sessions, and anything past
    SESSION_DAYS in the app's own session folder."""
    moment = moment or _now()
    for kind, conversation_id, session_id, updated in store.sessions():
        limit = TASK_IDLE_SECONDS if kind == "task" else SESSION_DAYS * 86400
        if _age(updated, moment) > limit:
            (store.drop_task_session if kind == "task" else store.drop_chat_session)(conversation_id)
            delete_transcript(session_id)
    kept = {session_id for _, _, session_id, _ in store.sessions()}
    folder = claude_home() / "projects" / re.sub(r"[^A-Za-z0-9]", "-", str(FOLDER.resolve()))
    if folder.is_dir():
        for path in folder.glob("*.jsonl"):
            if path.stem not in kept:
                try:
                    path.unlink()
                except OSError:
                    pass
