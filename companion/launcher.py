"""GUI launch boundary. Fatal logs deliberately exclude exception messages and tracebacks."""

from datetime import datetime, timezone
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parent.parent


def notify(message):
    if sys.platform == "win32":
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, message, "Desktop Companion", 0x10)
    elif sys.stderr is not None:
        print(message, file=sys.stderr)


def record_failure(stage, exception=None, root=ROOT):
    try:
        folder = root / "data"
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / "startup-error.log"
        if path.exists() and path.stat().st_size > 65536:
            path.replace(folder / "startup-error.previous.log")
        kind = type(exception).__name__ if exception is not None else "CheckFailed"
        with path.open("a", encoding="utf-8") as output:
            output.write(f"{datetime.now(timezone.utc).isoformat()} {stage}: {kind}\n")
    except OSError:
        pass  # The message box still works if the project is read-only.


def launch():
    try:
        from .doctor import run_checks
        errors = [check for check in run_checks() if check.status == "error"]
        if errors:
            record_failure("preflight")
            notify("The companion could not start:\n\n" + "\n".join(f"- {check.name}: {check.detail}" for check in errors)
                   + "\n\nRun Setup Mira.cmd, then Check Setup.cmd for details.")
            return 1
        from .__main__ import main
        return main()
    except Exception as exc:
        record_failure("startup", exc)
        notify("The companion could not start. Run Check Setup.cmd or Setup Mira.cmd.\n\n"
               "A minimal error record is in data/startup-error.log. It contains no exception messages, API keys, or conversations.")
        return 1
