"""Local conversation archive and user-managed memory. No model calls."""

from datetime import datetime, timezone
import hashlib
from pathlib import Path
import re
import sqlite3
from uuid import uuid4

from . import attachments
from .config import PROJECT_ROOT
from .continuity import MAX_SUMMARY_CHARS


DEFAULT_DATABASE = PROJECT_ROOT / "data" / "companion.sqlite3"
SCHEMA_VERSION = 5
STOP_WORDS = set("a an and are as at be been but by can do for from have how i in is it me my of on or that the this to was we what with you your".split())


def now():
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def terms(text):
    words = set(re.findall(r"[a-z0-9]+", text.casefold())) - STOP_WORDS
    return {word[:-1] if len(word) > 4 and word.endswith("s") else word for word in words}


def fingerprint(content):
    return hashlib.sha256(" ".join(content.casefold().split()).encode("utf-8")).hexdigest()


class Store:
    def __init__(self, path=DEFAULT_DATABASE):
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(str(path), timeout=0.5)
        self.connection.row_factory = sqlite3.Row
        if self.connection.execute("PRAGMA user_version").fetchone()[0] > SCHEMA_VERSION:
            self.close()
            raise sqlite3.DatabaseError("This database was created by a newer version of the companion.")
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.connection.execute("PRAGMA journal_mode = WAL")
        self.connection.execute("PRAGMA secure_delete = ON")
        self.connection.executescript("""
            CREATE TABLE IF NOT EXISTS conversations (
                id TEXT PRIMARY KEY, title TEXT NOT NULL,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
                role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
                display TEXT NOT NULL, context TEXT,
                status TEXT NOT NULL, notice TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS messages_by_conversation ON messages(conversation_id, id);
            CREATE TABLE IF NOT EXISTS memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT, content TEXT NOT NULL,
                fingerprint TEXT NOT NULL UNIQUE, pinned INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS reminders (
                id INTEGER PRIMARY KEY AUTOINCREMENT, text TEXT NOT NULL,
                due_at TEXT NOT NULL, repeat TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL, delivered_at TEXT
            );
            CREATE INDEX IF NOT EXISTS reminders_by_due ON reminders(delivered_at, due_at);
            CREATE TABLE IF NOT EXISTS conversation_summaries (
                conversation_id TEXT PRIMARY KEY REFERENCES conversations(id) ON DELETE CASCADE,
                content TEXT NOT NULL CHECK (length(content) BETWEEN 1 AND 6000),
                through_id INTEGER NOT NULL DEFAULT 0, updated_at TEXT NOT NULL
            );
        """)
        with self.connection:
            columns = {row["name"] for row in self.connection.execute("PRAGMA table_info(conversations)")}
            if "character_key" not in columns:
                self.connection.execute("ALTER TABLE conversations ADD COLUMN character_key TEXT NOT NULL DEFAULT ''")
            columns = {row["name"] for row in self.connection.execute("PRAGMA table_info(messages)")}
            if "attachments" not in columns:
                # JSON list of locally stored copies; the files live under data/attachments.
                self.connection.execute("ALTER TABLE messages ADD COLUMN attachments TEXT NOT NULL DEFAULT ''")
            self.connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")

    def close(self):
        if self.connection is not None:
            self.connection.close()
            self.connection = None

    def conversations(self, character=None):
        return [dict(row) for row in self.connection.execute(
            "SELECT c.*, COUNT(m.id) AS message_count FROM conversations c "
            "LEFT JOIN messages m ON m.conversation_id=c.id "
            + ("WHERE c.character_key=? " if character is not None else "")
            + "GROUP BY c.id ORDER BY c.updated_at DESC, c.rowid DESC",
            (character,) if character is not None else (),
        )]

    def last_message(self, conversation_id):
        row = self.connection.execute(
            "SELECT role, display FROM messages WHERE conversation_id=? AND display!='' ORDER BY id DESC LIMIT 1",
            (conversation_id,)).fetchone()
        return dict(row) if row else None

    def conversation(self, conversation_id):
        row = self.connection.execute("SELECT * FROM conversations WHERE id=?", (conversation_id,)).fetchone()
        return dict(row) if row else None

    def claim_legacy_conversations(self, character):
        """Attach unassigned chats once, preserving the previous single-character archive."""
        if character:
            with self.connection:
                self.connection.execute("UPDATE conversations SET character_key=? WHERE character_key=''", (character,))

    def create_conversation(self, character=""):
        conversation_id, timestamp = uuid4().hex, now()
        with self.connection:
            self.connection.execute("INSERT INTO conversations(id,title,created_at,updated_at,character_key) VALUES (?, ?, ?, ?, ?)",
                                    (conversation_id, "New conversation", timestamp, timestamp, character))
        return conversation_id

    def delete_conversation(self, conversation_id):
        stored = [item for row in self.connection.execute(
            "SELECT attachments FROM messages WHERE conversation_id=? AND attachments!=''", (conversation_id,))
            for item in attachments.loads(row["attachments"])]
        with self.connection:
            self.connection.execute("DELETE FROM conversations WHERE id=?", (conversation_id,))
        attachments.remove_files(stored)

    def rename_conversation(self, conversation_id, title):
        """A name chosen by the person. It is kept: automatic titles only replace "New conversation"."""
        title = " ".join(str(title).split())
        if not title or len(title) > 120:
            raise ValueError("A conversation name must contain 1 to 120 characters.")
        with self.connection:
            self.connection.execute("UPDATE conversations SET title=? WHERE id=?", (title, conversation_id))
        return title

    def touch_conversation(self, conversation_id):
        with self.connection:
            self.connection.execute("UPDATE conversations SET updated_at=? WHERE id=?", (now(), conversation_id))

    def messages(self, conversation_id):
        return [dict(row) for row in self.connection.execute(
            "SELECT * FROM messages WHERE conversation_id=? ORDER BY id", (conversation_id,)
        )]

    def context(self, conversation_id):
        return [message for turn in self.context_turns(conversation_id)[-12:] for message in (
            {"role": "user", "content": turn["user"]},
            {"role": "assistant", "content": turn["assistant"]},
        )]

    def context_turns(self, conversation_id):
        # Include only exchanges with a visible answer. Failed unanswered turns remain in the archive.
        rows = self.connection.execute(
            "SELECT id,role,context,status,display FROM messages WHERE conversation_id=? ORDER BY id",
            (conversation_id,),
        )
        result, user = [], None
        for row in rows:
            if row["role"] == "user":
                user = (row["id"], row["context"]) if row["context"] else None
            elif user and row["status"] != "local":
                text = row["context"]
                if row["status"] == "pending" and row["display"]:
                    text = (text or row["display"]) + "\n[The app closed during this reply; only this text was shown.]"
                if text:
                    result.append({"user_id": user[0], "assistant_id": row["id"], "user": user[1], "assistant": text})
                user = None
        return result

    def summary(self, conversation_id):
        row = self.connection.execute("SELECT * FROM conversation_summaries WHERE conversation_id=?", (conversation_id,)).fetchone()
        return dict(row) if row else None

    def save_summary(self, conversation_id, content, through_id=0):
        content = content.strip()
        if not content or len(content) > MAX_SUMMARY_CHARS:
            raise ValueError("A summary must contain 1 to 6,000 characters.")
        if type(through_id) is not int or through_id < 0:
            raise ValueError("Invalid summary coverage.")
        if through_id:
            row = self.connection.execute(
                "SELECT role,context,status FROM messages WHERE id=? AND conversation_id=?",
                (through_id, conversation_id),
            ).fetchone()
            if not row or row["role"] != "assistant" or not row["context"] or row["status"] == "local":
                raise ValueError("Summary coverage does not belong to an answered turn in this conversation.")
        with self.connection:
            self.connection.execute(
                "INSERT INTO conversation_summaries VALUES (?,?,?,?) ON CONFLICT(conversation_id) "
                "DO UPDATE SET content=excluded.content,through_id=excluded.through_id,updated_at=excluded.updated_at",
                (conversation_id, content, through_id, now()),
            )

    def clear_summary(self, conversation_id):
        with self.connection:
            self.connection.execute("DELETE FROM conversation_summaries WHERE conversation_id=?", (conversation_id,))

    def start_turn(self, conversation_id, text, files=()):
        timestamp = now()
        # Later turns see a short note about attachments instead of their contents.
        context = "\n".join(part for part in (text, attachments.note(files)) if part)
        with self.connection:
            user = self.connection.execute(
                "INSERT INTO messages(conversation_id,role,display,context,status,created_at,attachments) "
                "VALUES (?,'user',?,?,'complete',?,?)",
                (conversation_id, text, context, timestamp, attachments.dumps(files)),
            ).lastrowid
            assistant = self.connection.execute(
                "INSERT INTO messages(conversation_id,role,display,status,created_at) VALUES (?,'assistant','','pending',?)",
                (conversation_id, timestamp),
            ).lastrowid
            title = " ".join((text or ", ".join(item["name"] for item in files)).split())[:64]
            self.connection.execute(
                "UPDATE conversations SET title=CASE WHEN title='New conversation' THEN ? ELSE title END, updated_at=? WHERE id=?",
                (title, timestamp, conversation_id),
            )
        return user, assistant

    def save_turn(self, turn, display, context, status, notice=""):
        user_id, assistant_id = turn
        with self.connection:
            self.connection.execute("UPDATE messages SET display=?,context=?,status=?,notice=? WHERE id=?",
                                    (display, context, status, notice, assistant_id))
            if status != "pending" and not display:
                self.connection.execute("UPDATE messages SET context=NULL,status='error' WHERE id=?", (user_id,))
            self.connection.execute(
                "UPDATE conversations SET updated_at=? WHERE id=(SELECT conversation_id FROM messages WHERE id=?)",
                (now(), assistant_id),
            )

    def update_context(self, message_id, context):
        with self.connection:
            self.connection.execute("UPDATE messages SET context=? WHERE id=?", (context, message_id))

    def local_exchange(self, conversation_id, command, response):
        timestamp = now()
        with self.connection:
            for role, display in (("user", command), ("assistant", response)):
                self.connection.execute(
                    "INSERT INTO messages(conversation_id,role,display,status,created_at) VALUES (?,?,?,'local',?)",
                    (conversation_id, role, display, timestamp),
                )
            self.connection.execute("UPDATE conversations SET updated_at=? WHERE id=?", (timestamp, conversation_id))

    def memories(self):
        return [dict(row) for row in self.connection.execute("SELECT * FROM memories ORDER BY pinned DESC, updated_at DESC, id DESC")]

    # Reminders: due times are UTC ISO strings, so they sort and compare as text.

    def add_reminder(self, text, due_utc, repeat=""):
        with self.connection:
            return self.connection.execute(
                "INSERT INTO reminders(text,due_at,repeat,created_at) VALUES (?,?,?,?)",
                (text, due_utc.isoformat(timespec="seconds"), repeat, now())).lastrowid

    def reminders(self):
        """Upcoming reminders, soonest first."""
        return [dict(row) for row in self.connection.execute(
            "SELECT * FROM reminders WHERE delivered_at IS NULL ORDER BY due_at, id")]

    def due_reminders(self, moment_utc):
        return [dict(row) for row in self.connection.execute(
            "SELECT * FROM reminders WHERE delivered_at IS NULL AND due_at<=? ORDER BY due_at, id",
            (moment_utc.isoformat(timespec="seconds"),))]

    def finish_reminder(self, reminder_id, next_due_utc=None):
        """Delivered: a repeating reminder moves to its next time, any other is marked done."""
        with self.connection:
            if next_due_utc is not None:
                self.connection.execute("UPDATE reminders SET due_at=? WHERE id=?",
                                        (next_due_utc.isoformat(timespec="seconds"), reminder_id))
            else:
                self.connection.execute("UPDATE reminders SET delivered_at=? WHERE id=?", (now(), reminder_id))

    def delete_reminder(self, reminder_id):
        with self.connection:
            self.connection.execute("DELETE FROM reminders WHERE id=?", (reminder_id,))

    def save_memory(self, content, pinned=True, memory_id=None):
        content = content.strip()
        if not content or len(content) > 1000:
            raise ValueError("A memory must contain 1 to 1,000 characters.")
        key = fingerprint(content)
        existing = self.connection.execute("SELECT id FROM memories WHERE fingerprint=?", (key,)).fetchone()
        if existing and memory_id is not None and existing["id"] != memory_id:
            raise ValueError("That memory already exists.")
        timestamp = now()
        with self.connection:
            if memory_id is None and existing:
                self.connection.execute("UPDATE memories SET pinned=?,updated_at=? WHERE id=?", (int(pinned), timestamp, existing["id"]))
                return existing["id"]
            if memory_id is None:
                return self.connection.execute(
                    "INSERT INTO memories(content,fingerprint,pinned,created_at,updated_at) VALUES (?,?,?,?,?)",
                    (content, key, int(pinned), timestamp, timestamp),
                ).lastrowid
            result = self.connection.execute(
                "UPDATE memories SET content=?,fingerprint=?,pinned=?,updated_at=? WHERE id=?",
                (content, key, int(pinned), timestamp, memory_id),
            )
            if not result.rowcount:
                raise ValueError("This memory no longer exists. Refresh the list.")
        return memory_id

    def delete_memory(self, memory_id):
        with self.connection:
            result = self.connection.execute("DELETE FROM memories WHERE id=?", (memory_id,))
        return bool(result.rowcount)

    def relevant_memories(self, query, limit=6, max_chars=3000):
        query_terms = terms(query)
        ranked = []
        for memory in self.memories():
            overlap = len(query_terms & terms(memory["content"]))
            if memory["pinned"] or overlap:
                ranked.append((bool(memory["pinned"]), overlap, memory["updated_at"], memory))
        ranked.sort(key=lambda item: item[:3], reverse=True)
        selected, size = [], 0
        for _, _, _, memory in ranked:
            if len(selected) >= limit:
                break
            if size + len(memory["content"]) <= max_chars:
                selected.append({"id": memory["id"], "content": memory["content"]})
                size += len(memory["content"])
        return selected
