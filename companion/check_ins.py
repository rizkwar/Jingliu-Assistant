"""Gentle check-ins (off by default): a greeting that fits the time of day, and a nudge to rest
after a long stretch.

Activity comes from Windows' "time since the last mouse or keyboard input" only: nothing about
what the person is doing is read. She delivers each check-in herself, like a due reminder.
"""

from datetime import timedelta
import sys

MARK = "🌙 Check-in"
DAY_STARTS = 5                  # A new day begins at 5 am (working past midnight is the same day).
AWAY = 2 * 3600                 # Back after this long away: greet again.
LONG_SESSION = 3 * 3600         # Seconds of computer use without a real break.
BREAK = 10 * 60                 # Idle this long counts as a real break.

PROMPT = """Check-ins: a user message starting with "{mark}" comes from the app, not from the user typing. It
says why you are checking in (a greeting when they arrive, or a long stretch at the computer) and the time
of day. Speak to them yourself, briefly and warmly, in your own voice, in one or two sentences, fitting the
hour (a late-night greeting is not a cheerful good morning); for a long stretch, gently suggest a short
rest rather than lecturing. Do not set reminders or tasks because of a check-in."""


def idle_seconds():
    """Seconds since the last mouse or keyboard input anywhere on this computer (Windows)."""
    if sys.platform != "win32":
        return 0.
    import ctypes
    from ctypes import wintypes

    class LASTINPUTINFO(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]

    info = LASTINPUTINFO(ctypes.sizeof(LASTINPUTINFO), 0)
    if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info)):
        return 0.
    ticks = ctypes.windll.kernel32.GetTickCount() & 0xFFFFFFFF
    return ((ticks - info.dwTime) & 0xFFFFFFFF) / 1000


def part_of_day(now):
    hour = now.hour
    if hour < 5 or hour >= 22:
        return "late night"
    return "morning" if hour < 12 else "afternoon" if hour < 17 else "evening"


def day_of(now):
    """The day a moment belongs to, starting at 5 am."""
    return (now - timedelta(hours=DAY_STARTS)).date().isoformat()


class CheckIns:
    """Decides when to check in. `greeted` is the day of the last greeting (ISO), kept by the app
    between runs so she greets once a day, plus again when the person comes back after a while."""

    def __init__(self, greeted=""):
        self.greeted = greeted
        self.away = False
        self.active_since = None
        self.nudged_at = None

    def greeting(self, now, idle):
        """'first' the first time today, 'back' after a long time away, else None."""
        if idle >= AWAY:
            self.away = True
        if idle > 60:
            return None  # Greet when they are actually here.
        reason = "first" if self.greeted != day_of(now) else "back" if self.away else None
        if reason:
            self.greeted, self.away = day_of(now), False
        return reason

    def long_session(self, moment, idle):
        """`moment` is a monotonic time in seconds. True once after LONG_SESSION of use without a break."""
        if idle >= BREAK:
            self.active_since = None
            return False
        if self.active_since is None:
            self.active_since = moment - idle
        if moment - self.active_since < LONG_SESSION:
            return False
        if self.nudged_at is not None and moment - self.nudged_at < LONG_SESSION:
            return False
        self.nudged_at = moment
        return True

    def hours(self, moment):
        return max(1, round((moment - (self.active_since or moment)) / 3600))


def greeting_message(now, reason):
    arrival = ("has just come to the computer for the first time today" if reason == "first"
               else "is back at the computer after being away for a while")
    return f"{MARK} ({now:%H:%M}, {part_of_day(now)}): the user {arrival}. Greet them in a way that fits the hour."


def greeting_label(now, reason):
    part = part_of_day(now)
    hello = "late at night" if part == "late night" else f"good {part}"
    return f"Check-in · {'welcome back, ' if reason == 'back' else ''}{hello}"


def rest_message(now, hours):
    return (f"{MARK} ({now:%H:%M}): the user has been at the computer for about {hours} hours without a real "
            "break. Gently suggest a short rest.")
