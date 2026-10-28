"""Skills: packaged instructions (a folder with a SKILL.md) that she can use, the way Claude Code uses them.

Her skills are her own, apart from your Claude Code setup: they live in data/skills/plugin, a Claude Code plugin
folder passed with --plugin-dir to her replies and computer tasks, and only those load. A skill switched off moves
to data/skills/off. Skills are added from a folder, from your Claude Code skills, or installed from GitHub
(a repository, or a folder in one), by you in Settings or by her when you agree.
"""

import io
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
import zipfile

from ..core.config import PROJECT_ROOT

ROOT = PROJECT_ROOT / "data" / "skills"
PLUGIN = ROOT / "plugin"
OFF = ROOT / "off"
PLUGIN_NAME = "her-skills"
MAX_DOWNLOAD = 60 * 1024 * 1024
SKIP = {".git", "node_modules", "__pycache__", ".venv", "venv"}


class SkillError(Exception):
    """Something to tell the person: a skill could not be added."""


def _ready():
    (PLUGIN / ".claude-plugin").mkdir(parents=True, exist_ok=True)
    (PLUGIN / "skills").mkdir(exist_ok=True)
    manifest = PLUGIN / ".claude-plugin" / "plugin.json"
    if not manifest.is_file():
        manifest.write_text(json.dumps({"name": PLUGIN_NAME, "version": "1.0.0",
                                        "description": "Skills added to her in the companion app"}), encoding="utf-8")


def describe(skill_md):
    """(name, description) from a SKILL.md's front matter (the folder's name when it has none)."""
    text = Path(skill_md).read_text(encoding="utf-8", errors="replace")
    name, description = Path(skill_md).parent.name, ""
    front = re.match(r"\A---\s*\n(.*?)\n---", text, re.S)
    if front:
        for line in front.group(1).splitlines():
            key, _, value = line.partition(":")
            if key.strip() == "name" and value.strip():
                name = value.strip().strip("'\"")
            elif key.strip() == "description":
                description = value.strip().strip("'\"")
    return name, description


def _safe(name):
    name = re.sub(r"[^A-Za-z0-9._-]+", "-", name).strip("-.")[:64]
    if not name:
        raise SkillError("That skill has no usable name.")
    return name


def installed():
    """Every skill she has: [{name, description, enabled, path}], by name."""
    found = []
    for enabled, folder in ((True, PLUGIN / "skills"), (False, OFF)):
        if folder.is_dir():
            for path in folder.iterdir():
                if (path / "SKILL.md").is_file():
                    _, description = describe(path / "SKILL.md")
                    found.append({"name": path.name, "description": description, "enabled": enabled, "path": path})
    return sorted(found, key=lambda skill: skill["name"].lower())


def plugin_dir():
    """The folder to pass with --plugin-dir, or None while she has no skill switched on."""
    folder = PLUGIN / "skills"
    if folder.is_dir() and any((path / "SKILL.md").is_file() for path in folder.iterdir()):
        _ready()
        return str(PLUGIN)
    return None


def find(folder, depth=4):
    """The skill folders (holding a SKILL.md) in `folder`, at most `depth` levels down."""
    folder = Path(folder)
    if (folder / "SKILL.md").is_file():
        return [folder]
    found = []
    if depth > 0 and folder.is_dir():
        for child in sorted(folder.iterdir()):
            if child.is_dir() and child.name not in SKIP:
                found += find(child, depth - 1)
    return found


def add_folder(folder, replace=False):
    """Copies a skill folder in; returns its name."""
    folder = Path(folder)
    if not (folder / "SKILL.md").is_file():
        raise SkillError(f"{folder.name} has no SKILL.md, so it is not a skill.")
    name = _safe(describe(folder / "SKILL.md")[0])
    _ready()
    target = PLUGIN / "skills" / name
    for existing in (target, OFF / name):
        if existing.exists():
            if not replace:
                raise SkillError(f"She already has a skill called {name}.")
            shutil.rmtree(existing)
    shutil.copytree(folder, target, ignore=shutil.ignore_patterns(*SKIP))
    return name


def add(source, replace=True):
    """Adds every skill in a local folder; returns their names."""
    folders = find(source)
    if not folders:
        raise SkillError("No skill there: a skill is a folder with a SKILL.md in it.")
    return [add_folder(folder, replace) for folder in folders]


_GITHUB = re.compile(r"^(?:https?://)?(?:www\.)?github\.com/([\w.-]+)/([\w.-]+?)(?:\.git)?"
                     r"(?:/(?:tree|blob)/([^/]+)(?:/(.*?))?)?/?$")
_SHORT = re.compile(r"^([\w.-]+)/([\w.-]+)$")


def parse_github(source):
    """(owner, repository, branch or None, folder in it) from a GitHub link or owner/repo."""
    source = source.strip()
    match = _GITHUB.match(source)
    if match:
        owner, repo, branch, path = match.groups()
        path = (path or "").removesuffix("/SKILL.md").strip("/")
        return owner, repo, branch, path
    match = _SHORT.match(source)
    if match:
        return match.group(1), match.group(2), None, ""
    raise SkillError("That is not a GitHub link. Use one like https://github.com/owner/repo or owner/repo.")


def _get(url, limit=MAX_DOWNLOAD):
    import httpx
    with httpx.Client(timeout=httpx.Timeout(60.0, connect=15.0), follow_redirects=True,
                      headers={"User-Agent": "jingliu-companion"}) as client:
        response = client.get(url)
        if response.status_code == 404:
            raise SkillError("GitHub could not find that repository or branch. Is it public?")
        if response.is_error:
            raise SkillError(f"GitHub answered {response.status_code}. Try again in a moment.")
        if len(response.content) > limit:
            raise SkillError("That download is too large for a skill.")
        return response.content


def install(source, replace=True):
    """Installs the skills from a GitHub link (a repository, or a folder in one) or a local folder; returns names."""
    if Path(source).expanduser().is_dir():
        return add(Path(source).expanduser(), replace)
    owner, repo, branch, path = parse_github(source)
    if not branch:
        try:
            branch = json.loads(_get(f"https://api.github.com/repos/{owner}/{repo}", 1_000_000)).get("default_branch")
        except ValueError:
            branch = None
        branch = branch or "main"
    archive = _get(f"https://codeload.github.com/{owner}/{repo}/zip/refs/heads/{branch}")
    with tempfile.TemporaryDirectory(prefix="jingliu-skill-") as temporary:
        root = Path(temporary).resolve()
        with zipfile.ZipFile(io.BytesIO(archive)) as bundle:
            for member in bundle.infolist():
                target = (root / member.filename).resolve()
                if root not in target.parents and target != root:
                    raise SkillError("That archive tries to write outside its folder, so it was not installed.")
            bundle.extractall(root)
        top = next((child for child in root.iterdir() if child.is_dir()), root)
        base = top / path if path else top
        if not base.exists():
            raise SkillError(f"There is no folder {path} in {owner}/{repo}.")
        return add(base, replace)


def set_enabled(name, on):
    _ready()
    OFF.mkdir(parents=True, exist_ok=True)
    source, target = (OFF / name, PLUGIN / "skills" / name) if on else (PLUGIN / "skills" / name, OFF / name)
    if source.is_dir() and not target.exists():
        shutil.move(str(source), str(target))


def remove(name):
    for folder in (PLUGIN / "skills" / name, OFF / name):
        if folder.is_dir():
            shutil.rmtree(folder)


def claude_code_skills():
    """Your own Claude Code skills (~/.claude/skills) that she does not have yet: [(name, description, path)]."""
    home = Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude") / "skills"
    have = {skill["name"] for skill in installed()}
    found = []
    for folder in find(home, depth=2) if home.is_dir() else []:
        name, description = describe(folder / "SKILL.md")
        if _safe(name) not in have:
            found.append((name, description, folder))
    return found
