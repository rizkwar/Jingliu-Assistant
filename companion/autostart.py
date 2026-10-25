"""Start with Windows: a per-user Run entry that opens Jingliu quietly in the tray at sign-in.

Task Manager's Startup apps lists it as "Jingliu", where it can also be disabled.
"""

import sys
from pathlib import Path

from .config import PROJECT_ROOT

KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
NAME = "Jingliu"
BACKGROUND = "--background"  # Start in the tray, without opening the chat window.


def command():
    """The same windowed Python and launcher as the Start Menu shortcut, plus --background."""
    python = PROJECT_ROOT / ".venv" / "Scripts" / "pythonw.exe"
    if not python.exists():
        python = Path(sys.executable).with_name("pythonw.exe")
    return f'"{python}" "{PROJECT_ROOT / "launch_mira.pyw"}" {BACKGROUND}'


def _key(write=False):
    import winreg
    access = winreg.KEY_READ | (winreg.KEY_SET_VALUE if write else 0)
    return winreg.OpenKey(winreg.HKEY_CURRENT_USER, KEY, 0, access)


def enabled():
    if sys.platform != "win32":
        return False
    import winreg
    try:
        with _key() as key:
            value, _ = winreg.QueryValueEx(key, NAME)
    except OSError:
        return False
    return BACKGROUND in str(value) and "launch_mira.pyw" in str(value)


def set_enabled(on):
    """Add or remove the Run entry. Raises OSError if Windows refuses."""
    if sys.platform != "win32":
        raise OSError("Starting with Windows is only available on Windows.")
    import winreg
    with _key(write=True) as key:
        if on:
            winreg.SetValueEx(key, NAME, 0, winreg.REG_SZ, command())
        else:
            try:
                winreg.DeleteValue(key, NAME)
            except FileNotFoundError:
                pass
