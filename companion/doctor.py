"""Secret-free, offline setup diagnostics. No microphone, model loading, or migrations."""

import argparse
from dataclasses import asdict, dataclass
from importlib import metadata
import json
from pathlib import Path
import sqlite3
import struct
import subprocess
import sys
import tempfile
import os


ROOT = Path(__file__).resolve().parent.parent
CORE = {"pyside6-essentials", "httpx", "python-dotenv"}


@dataclass(frozen=True)
class Check:
    status: str
    name: str
    detail: str


def engine_check(name, module, required=False):
    env = dict(os.environ)
    env.pop("OPENROUTER_API_KEY", None)
    env["HF_HUB_OFFLINE"] = "1"
    env["HF_HUB_DISABLE_TELEMETRY"] = "1"
    env["TRANSFORMERS_OFFLINE"] = "1"
    try:
        result = subprocess.run(
            [sys.executable, "-c", f"import {module}"], env=env,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        if result.returncode == 0:
            return Check("ok", name, "Native imports work; no models or audio devices were opened.")
    except (OSError, subprocess.TimeoutExpired):
        pass
    return Check("error" if required else "warning", name,
                 "Could not load this engine. Run Setup Mira.cmd to repair dependencies.")


def run_checks(root=ROOT, engines=False):
    root = Path(root)
    checks = []
    supported = (3, 11) <= sys.version_info[:2] <= (3, 12) and struct.calcsize("P") == 8
    checks.append(Check("ok" if supported else "error", "Python",
                        f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}, "
                        f"{struct.calcsize('P') * 8}-bit. Supported: Python 3.11 or 3.12, 64-bit."))
    if not supported:
        return checks
    try:
        requirements = (root / "requirements.txt").read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError):
        requirements = []
        checks.append(Check("error", "Project files", "requirements.txt is missing or unreadable."))
    missing_core = False
    for line in requirements:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        package, separator, expected = line.partition("==")
        if not separator:
            checks.append(Check("warning", "Requirements", "An unpinned dependency was not checked."))
            continue
        required = package.lower().replace("_", "-") in CORE
        try:
            installed = metadata.version(package)
        except metadata.PackageNotFoundError:
            missing_core |= required
            checks.append(Check("error" if required else "warning", package,
                                "Not installed. Run Setup Mira.cmd."))
            continue
        checks.append(Check("ok" if installed == expected else "warning", package,
                            f"Installed {installed}; project pins {expected}."))
    try:
        from .config import load_settings
        settings = load_settings(root)
        checks.append(Check("ok", "Configuration", ".env defaults and the selected character profile are valid."))
        try:
            settings.validate_connection()
            checks.append(Check("ok", "API configuration", "Key and model ID configured. No online request was made."))
        except ValueError:
            checks.append(Check("warning", "API configuration",
                                "Key or model ID needs attention in .env. Offline features remain available."))
        try:
            from .preferences import Preferences
            settings = Preferences(root / "data" / "preferences.json").load(settings)
            checks.append(Check("ok", "Saved preferences", "Readable, or defaults will be used."))
        except (OSError, ValueError):
            checks.append(Check("warning", "Saved preferences",
                                "Invalid or unreadable. The app can use defaults; Settings > Save defaults repairs the file."))
        if settings.tts_voice == "reference":
            from .reference_voice import inspect_reference, VoiceSetupError
            try:
                inspect_reference(settings.tts_reference)
                checks.append(Check("ok", "Reference audio", "Local WAV is valid. Preview checks full model access; similarity has not been evaluated."))
            except VoiceSetupError:
                checks.append(Check("warning", "Reference audio", "Choose a valid reference WAV in Settings. See docs/reference-voice.md."))
    except ImportError:
        checks.append(Check("error", "Configuration", "Configuration dependencies are missing. Run Setup Mira.cmd."))
    except (OSError, ValueError, UnicodeError):
        checks.append(Check("error", "Configuration", "Check .env values and the selected character profile. See README.md and docs/character-guide.md."))
    try:
        data = root / "data"
        data.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryFile(dir=data):
            pass
        checks.append(Check("ok", "Local storage", "The data folder is writable."))
    except OSError:
        checks.append(Check("error", "Local storage", "The data folder is not writable. Move the project to a writable folder."))
    database = root / "data" / "companion.sqlite3"
    if database.exists():
        try:
            connection = sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True, timeout=0.5)
            try:
                schema = connection.execute("PRAGMA user_version").fetchone()[0]
            finally:
                connection.close()
            checks.append(Check("error" if schema > 3 else "ok", "Conversation database",
                                "Requires a newer app version." if schema > 3 else "Schema is compatible. No messages were read or changed."))
        except sqlite3.Error:
            checks.append(Check("warning", "Conversation database", "Could not read the schema. Quit the companion and check again."))
    if engines and not missing_core:
        for name, module, required in (("Qt desktop engine", "PySide6.QtWidgets", True),
                                       ("Speech engine", "torch, pocket_tts, sounddevice", False),
                                       ("Recognition engine", "faster_whisper, onnxruntime, scipy", False)):
            checks.append(engine_check(name, module, required))
    return checks


def main(argv=None):
    parser = argparse.ArgumentParser(description="Offline setup checks; no API key values, microphone capture, or model downloads.")
    parser.add_argument("--engines", action="store_true", help="Also test native imports in isolated processes (up to 30 seconds each).")
    parser.add_argument("--json", action="store_true", help="Print a structured report without credentials or message contents.")
    args = parser.parse_args(argv)
    checks = run_checks(engines=args.engines)
    if args.json:
        print(json.dumps([asdict(check) for check in checks], indent=2))
    else:
        print("Desktop Companion setup check (offline)\n")
        for check in checks:
            print(f"[{check.status.upper()}] {check.name}: {check.detail}")
        print("\nWarnings do not prevent offline use. Errors need fixing before launch.")
    return int(any(check.status == "error" for check in checks))


if __name__ == "__main__":
    raise SystemExit(main())
