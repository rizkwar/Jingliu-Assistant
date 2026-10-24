"""Offline publishing checks. Findings contain locations/rules, never matched values.

Complements Gitleaks and GitHub push protection; no pattern scanner proves that
arbitrary prose contains no private information. Review your staged changes too.
"""
from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import PurePosixPath

SECRET_RULES = {
    "OpenRouter credential": rb"\bsk-or-v1-[A-Za-z0-9_-]{20,}",
    "API credential": rb"\bsk-(?:proj-)?[A-Za-z0-9_-]{30,}",
    "Hugging Face credential": rb"\bhf_[A-Za-z0-9]{20,}",
    "GitHub credential": rb"\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})",
    "AWS credential": rb"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b",
    "Private key": rb"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----",
}
SECRET_RULES = {name: re.compile(pattern) for name, pattern in SECRET_RULES.items()}
EMAIL = re.compile(rb"(?i)[A-Z0-9][A-Z0-9._%+\-]*@[A-Z0-9.\-]+\.[A-Z]{2,}")
USER_PATH = re.compile(rb"(?i)(?:[A-Z]:[/\\]+Users[/\\]+[^\s/\\\"']+|/(?:Users|home)/[^\s/\"']+)")
NO_REPLY = b"@users.noreply.github.com"
SYSTEM_EMAILS = {b"noreply@github.com"}
EXAMPLE_DOMAINS = {b"example.com", b"example.net", b"example.org"}
PRIVATE_DIRS = {".venv", ".cache", "artifacts", "data", "voices", "ext_sources", "recordings",
                "attachments", "backups", "logs", ".aws", ".ssh", ".codex"}
PRIVATE_SUFFIXES = {".wav", ".mp3", ".m4a", ".flac", ".ogg", ".opus", ".aac", ".aiff",
                    ".sqlite", ".sqlite3", ".db", ".log", ".bak", ".backup", ".bundle",
                    ".pem", ".key", ".p12", ".pfx"}


def git(*arguments: str, data: bytes | None = None) -> bytes:
    return subprocess.run(["git", *arguments], input=data, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, check=True).stdout


def private_path(path: str) -> bool:
    path = path.replace("\\", "/")
    parts = PurePosixPath(path.lower()).parts
    name = parts[-1] if parts else ""
    if any(part in PRIVATE_DIRS for part in parts):
        return True
    if name == ".env.example":
        return False
    return (name == ".env" or name.startswith(".env.")
            or PurePosixPath(name).suffix in PRIVATE_SUFFIXES
            or bool(re.search(r"\.(?:sqlite3?|db)-", name)))


def content_rules(data: bytes, local_values: tuple[bytes, ...] = ()) -> set[str]:
    findings = {name for name, pattern in SECRET_RULES.items() if pattern.search(data)}
    for email in EMAIL.findall(data):
        email = email.lower()
        if (not email.endswith(NO_REPLY) and email not in SYSTEM_EMAILS
                and email.rsplit(b"@", 1)[-1] not in EXAMPLE_DOMAINS):
            findings.add("Personal/contact email")
    if USER_PATH.search(data):
        findings.add("Absolute user-home path")
    if any(value in data for value in local_values):
        findings.add("Configured local credential")
    return findings


def objects(oids: list[bytes]):
    if not oids:
        return
    output = git("cat-file", "--batch", data=b"\n".join(oids) + b"\n")
    offset = 0
    while offset < len(output):
        end = output.index(b"\n", offset)
        oid, kind, size = output[offset:end].split()
        start = end + 1
        offset = start + int(size) + 1
        yield oid, kind, output[start:offset - 1]


def audit(history: bool = False, local_values: tuple[bytes, ...] = ()):
    issues: set[tuple[str, str]] = set()
    paths: set[str] = set()
    blobs: dict[bytes, str] = {}
    for item in git("ls-files", "--stage", "-z").split(b"\0"):
        if not item:
            continue
        metadata, path = item.split(b"\t", 1)
        path = path.decode("utf-8", "replace")
        paths.add(path)
        blobs[metadata.split()[1]] = path
    if history:
        for item in git("-c", "core.quotepath=false", "rev-list", "--objects", "--all").splitlines():
            oid, separator, path = item.partition(b" ")
            if separator:
                blobs.setdefault(oid, path.decode("utf-8", "replace"))
        paths.update(path.strip(b"\n").decode("utf-8", "replace") for path in
                     git("log", "--all", "--format=", "--name-only", "-z").split(b"\0") if path.strip(b"\n"))
        for oid, kind, data in objects(git("rev-list", "--all").splitlines()):
            location = f"commit {oid.decode()[:12]}"
            for rule in content_rules(data, local_values):
                issues.add((location, rule))
            for name, email in re.findall(rb"(?m)^(?:author|committer) (.*?) <([^<>]*)> [^\n]*$", data):
                public_email = email.lower().endswith(NO_REPLY) or email.lower() in SYSTEM_EMAILS
                public_name = not re.search(rb"\s", name) or name == b"GitHub Actions"
                if not public_email or not public_name:
                    issues.add((location, "Commit identity must use a handle and GitHub no-reply email"))
    for path in paths:
        if private_path(path):
            issues.add((path, "Private local file"))
    checked = 0
    for oid, kind, data in objects(list(blobs)):
        if kind != b"blob":
            continue
        checked += 1
        for rule in content_rules(data, local_values):
            issues.add((blobs[oid], rule))
    return checked, sorted(issues)


def safe_location(value: str, local_values: tuple[bytes, ...]) -> str:
    data = value.encode("utf-8", "replace")
    for pattern in (*SECRET_RULES.values(), EMAIL, USER_PATH):
        data = pattern.sub(b"[redacted]", data)
    for secret in local_values:
        data = data.replace(secret, b"[redacted]")
    return data.decode("utf-8", "replace")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--history", action="store_true", help="Include every reachable commit, its metadata and historical filenames")
    parser.add_argument("--compare-local-env", action="store_true", help="Also compare configured credentials in .env without printing them")
    args = parser.parse_args()
    local_values: tuple[bytes, ...] = ()
    try:
        if args.compare_local_env:
            from dotenv import dotenv_values
            values = dotenv_values(".env")
            names = ("OPENROUTER_API_KEY", "ANTHROPIC_API_KEY", "HF_TOKEN", "OPENAI_API_KEY", "GITHUB_TOKEN")
            local_values = tuple(values[name].encode() for name in names if len(values.get(name) or "") >= 8)
        checked, issues = audit(args.history, local_values)
    except (subprocess.CalledProcessError, ValueError, ImportError, OSError):
        print("Safety check could not complete. Check Git access and the required local Python dependencies.")
        return 2
    if issues:
        for location, rule in issues:
            print(f"BLOCKED: {safe_location(location, local_values)} [{rule}]")
        print(f"Publishing blocked: {len(issues)} findings. Matched values are not printed.")
        return 1
    print(f"Publish safety passed: {checked} indexed/historical blobs; no matching publication findings.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
