"""Gentle check-ins (off by default): a morning greeting, and a nudge to rest after a long stretch.

Activity comes from Windows' "time since the last mouse or keyboard input" only: nothing about
what the person is doing is read. She delivers each check-in herself, like a due reminder.
"""

from datetime import timedelta
import sys

MARK = "🌙 Check-in"
MORNING = range(5, 12)          # Hours that count as morning.
LONG_SESSION = 3 * 3600         # Seconds of computer use without a real break.
BREAK = 10 * 60                 # Idle this long counts as a real break.

PROMPT = """Check-ins: a user message starting with "{mark}" comes from the app, not from the user typing. It
says why you are checking in (a first greeting of the morning, or a long stretch at the computer). Speak to
them yourself, briefly and warmly, in your own voice, in one or two sentences; for a long stretch, gently
suggest a short rest rather than lecturing. Do not set reminders or tasks because of a check-in."""


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


class CheckIns:
    """Decides when to check in. `greeted` is the date of the last morning greeting (ISO), kept by
    the app between runs so she greets once a day."""

    def __init__(self, greeted=""):
        self.greeted = greeted
        self.active_since = None
        self.nudged_at = None

    def morning(self, now, idle):
        """The first time the person is at the computer this morning: greet once."""
        if now.hour not in MORNING or idle > 60 or self.greeted == now.date().isoformat():
            return False
        self.greeted = now.date().isoformat()
        return True

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


def morning_message(now):
    return (f"{MARK} ({now:%H:%M}): it is morning and the user has just come to the computer for the first time "
            "today. Greet them.")


def rest_message(now, hours):
    return (f"{MARK} ({now:%H:%M}): the user has been at the computer for about {hours} hours without a real "
            "break. Gently suggest a short rest.")
