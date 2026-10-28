"""Reminders she sets when asked, and delivers in character when they are due.

She writes [[remind: 2026-10-25 19:00 | Study for the calculus exam | daily]] (local time; the
repeat part is optional) and [[unremind: a few words]] to cancel one. Times are kept in UTC.
"""

from datetime import datetime, timedelta, timezone
import re

REPEATS = ("", "daily", "weekdays", "weekly")
MAX_AHEAD = timedelta(days=366)
LATE_LIMIT = timedelta(hours=12)  # Older missed reminders are listed, not delivered.
MARK = "⏰ Reminder"

PROMPT = """Reminders: you can set reminders for the user through this app. The current local date and time is
{now}. When the user asks to be reminded of something ("remind me at 7 to…", "in 20 minutes tell me…",
"every weekday at 8…"), set it with the silent cue [[remind: YYYY-MM-DD HH:MM | what to remind them | repeat]]
using a 24-hour local time you work out from the current time; the repeat part is optional and is one of daily,
weekdays or weekly. Confirm naturally and in character, saying when. If the time is unclear, ask once.
To cancel one, use [[unremind: a few words naming it]]. The app confirms each change to the user, so never
claim a reminder was set or cancelled unless you used the cue. Upcoming reminders (JSON): {upcoming}
A user message starting with "{mark}" comes from the app, not from the user typing: it means that reminder is
due now. Deliver it to them yourself, warmly and briefly in your own voice, one to three sentences, as if
you had been keeping an eye on the time for them. Do not set a new reminder for it."""


FILLER = {"the", "one", "a", "an", "my", "me", "about", "reminder", "reminders", "remind", "to", "that", "this", "for"}


def match(description, text):
    """How well her few words name a reminder, 0..1: word forms count (stretch ~ stretching)."""
    words = lambda value: {w for w in re.findall(r"[\w']+", value.casefold()) if w not in FILLER}
    wanted, have = words(description), words(text)
    if not wanted:
        return 0.0
    close = lambda a, b: a == b or (min(len(a), len(b)) >= 4 and (a.startswith(b) or b.startswith(a)))
    return sum(any(close(w, h) for h in have) for w in wanted) / len(wanted)


def now_local():
    return datetime.now().astimezone()


def parse(payload, now=None):
    """'2026-10-25 19:00 | Study | daily' → (due UTC datetime, text, repeat). Raises ValueError."""
    now = now or now_local()
    parts = [part.strip() for part in str(payload).split("|")]
    if len(parts) < 2 or not parts[1]:
        raise ValueError("A reminder needs a time and what to remind.")
    match = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})[ T](\d{1,2}):(\d{2})", parts[0])
    if not match:
        raise ValueError(f"Could not read the time “{parts[0]}”.")
    year, month, day, hour, minute = map(int, match.groups())
    local = datetime(year, month, day, hour, minute).astimezone()  # The computer's own time zone.
    repeat = parts[2].lower() if len(parts) > 2 else ""
    if repeat not in REPEATS:
        repeat = ""
    if local < now - timedelta(minutes=2):
        if not repeat:
            raise ValueError("That time has already passed.")
        while local < now:
            local = advance(local, repeat)
    if local - now > MAX_AHEAD:
        raise ValueError("Reminders can be up to a year ahead.")
    return local.astimezone(timezone.utc), " ".join(parts[1].split())[:300], repeat


def advance(moment, repeat):
    """The next time a repeating reminder is due, after `moment`."""
    if repeat == "daily":
        return moment + timedelta(days=1)
    if repeat == "weekly":
        return moment + timedelta(days=7)
    if repeat == "weekdays":
        moment += timedelta(days=1)
        while moment.weekday() >= 5:
            moment += timedelta(days=1)
        return moment
    raise ValueError("Not a repeating reminder.")


def following(due_utc, repeat, now=None):
    """The next due time of a repeating reminder that has just been delivered (local wall-clock based)."""
    now = now or now_local()
    local = due_utc.astimezone()
    local = advance(local, repeat)
    while local <= now:
        local = advance(local, repeat)
    return local.astimezone(timezone.utc)


def when(due_utc, now=None):
    """'Today, 19:00', 'Tomorrow, 08:00', 'Monday, 08:00' or '3 Nov, 19:00' in local time."""
    now = now or now_local()
    local = due_utc.astimezone(now.tzinfo)
    days = (local.date() - now.date()).days
    clock = f"{local:%H:%M}"
    if days == 0:
        return f"Today, {clock}"
    if days == 1:
        return f"Tomorrow, {clock}"
    if 1 < days < 7:
        return f"{local:%A}, {clock}"
    return f"{local.day} {local:%b}" + (f" {local.year}" if local.year != now.year else "") + f", {clock}"


REPEAT_WORDS = {"daily": "every day", "weekdays": "every weekday", "weekly": "every week"}


def describe(reminder, now=None):
    due = datetime.fromisoformat(reminder["due_at"])
    repeat = REPEAT_WORDS.get(reminder.get("repeat") or "", "")
    return f"{when(due, now)}" + (f" · {repeat}" if repeat else "")


def prompt(upcoming, now=None, split=False):
    """Her instructions, with the current time and what is already scheduled. `split`: (instructions that stay
    the same, the time and upcoming reminders as they are now), so the instructions can be cached."""
    import json
    now = now or now_local()
    items = [{"what": item["text"], "when": describe(item, now)} for item in upcoming[:12]]
    stamp, listed = f"{now:%A %d %B %Y, %H:%M} (UTC{now:%z})", json.dumps(items, ensure_ascii=False)
    if split:
        return (PROMPT.format(now="given in the app context of each message", upcoming="listed in the app context",
                              mark=MARK),
                f"Current local date and time: {stamp}\nUpcoming reminders (JSON): {listed}")
    return PROMPT.format(now=stamp, upcoming=listed, mark=MARK)


def message(reminder, now=None):
    """The app's line that asks her to deliver a due reminder."""
    now = now or now_local()
    due = datetime.fromisoformat(reminder["due_at"]).astimezone(now.tzinfo)
    late = now - due
    lateness = "" if late < timedelta(minutes=3) else f" (it was due at {due:%H:%M}; the app was closed or busy)"
    return f"{MARK} ({now:%H:%M}): {reminder['text']}{lateness}"
