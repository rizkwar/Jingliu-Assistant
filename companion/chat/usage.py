"""How much of her service is left: plan limits as each service reports them, and the tokens each reply used.

Limits come with replies (Claude Code and Codex report them as they answer) or are read on request (Codex,
and OpenRouter's credit balance). Only percentages, reset times and token counts are kept, on this computer.
"""

from datetime import datetime, timedelta
import json
import os
from pathlib import Path

from ..core.config import PROJECT_ROOT


LIMITS_FILE = PROJECT_ROOT / "data" / "usage-limits.json"
LOW = 20  # Percent left below which the sidebar and moons turn amber.
PROVIDERS = {"claude": "Claude subscription", "codex": "ChatGPT via Codex", "openrouter": "OpenRouter"}
CLAUDE_WINDOWS = {"five_hour": "Session · 5 hours", "seven_day": "This week", "seven_day_opus": "Opus this week",
                  "seven_day_sonnet": "Sonnet this week"}


def _number(value):
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _left(used_fraction):
    try:
        return max(0.0, min(100.0, 100.0 * (1 - float(used_fraction))))
    except (TypeError, ValueError):
        return None


def claude_windows(info):
    """Windows from a Claude Code `rate_limit_info`: each with the percent left and when it resets."""
    windows = []
    for key, window in ((info or {}).get("unifiedWindows") or {}).items():
        if isinstance(window, dict) and window.get("utilization") is not None:
            windows.append({"key": key, "label": CLAUDE_WINDOWS.get(key, key.replace("_", " ").capitalize()),
                            "left": _left(window["utilization"]), "resets_at": window.get("resetsAt"),
                            "blocked": window.get("status") == "rejected"})
    if not windows and (info or {}).get("status") == "rejected":
        key = info.get("rateLimitType") or "five_hour"
        windows.append({"key": key, "label": CLAUDE_WINDOWS.get(key, "Plan limit"), "left": 0.0,
                        "resets_at": info.get("resetsAt"), "blocked": True})
    order = list(CLAUDE_WINDOWS)
    return sorted(windows, key=lambda w: order.index(w["key"]) if w["key"] in order else len(order))


def _span(minutes):
    if minutes == 300:
        return "Session · 5 hours"
    if minutes == 10080:
        return "This week"
    if minutes and minutes % 1440 == 0:
        return f"{minutes // 1440} days"
    if minutes and minutes % 60 == 0:
        return f"{minutes // 60} hours"
    return "Limit"


def codex_windows(snapshot):
    """Windows from a Codex `RateLimitSnapshot` (primary is usually 5 hours, secondary a week)."""
    windows = []
    for key in ("primary", "secondary"):
        window = (snapshot or {}).get(key)
        if isinstance(window, dict) and window.get("usedPercent") is not None:
            windows.append({"key": key, "label": _span(window.get("windowDurationMins")),
                            "left": _left(_number(window["usedPercent"]) / 100), "resets_at": window.get("resetsAt"),
                            "blocked": _number(window["usedPercent"]) >= 100})
    return windows


def openrouter_windows(key=None, credits=None):
    """OpenRouter's balance: the key's own limit when it has one, else the account's credits."""
    key, credits = key or {}, credits or {}
    if key.get("limit"):
        limit, remaining = float(key["limit"]), float(key.get("limit_remaining") or 0)
    elif credits.get("total_credits") is not None:
        limit = float(credits["total_credits"] or 0)
        remaining = limit - float(credits.get("total_usage") or 0)
    else:
        return []
    left = 100.0 * remaining / limit if limit > 0 else 0.0
    return [{"key": "credits", "label": "Credits", "left": max(0.0, min(100.0, left)), "resets_at": None,
             "detail": f"${max(0.0, remaining):,.2f} left of ${limit:,.2f}", "blocked": remaining <= 0}]


def current(windows, moment=None):
    """Windows as they stand now: one whose reset time has passed is full again."""
    stamp = (moment or datetime.now()).timestamp()
    return [dict(window, left=100.0, blocked=False, resets_at=None)
            if window.get("resets_at") and window["resets_at"] <= stamp else window for window in windows]


def load_limits(path=None):
    try:
        data = json.loads(Path(path or LIMITS_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def save_limits(provider, windows, path=None, moment=None):
    """Keeps the latest windows a service reported, with when; a report without windows changes nothing."""
    if not windows or provider not in PROVIDERS:
        return
    data = load_limits(path)
    data[provider] = {"windows": windows, "at": (moment or datetime.now()).timestamp()}
    path = Path(path or LIMITS_FILE)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(data, indent=1), encoding="utf-8")
        os.replace(temporary, path)
    except OSError:
        pass  # Limits are a convenience; a reply never fails over them.


def least_left(windows):
    """The window closest to running out, which the sidebar shows."""
    known = [window for window in windows if window.get("left") is not None]
    return min(known, key=lambda window: window["left"]) if known else None


def short(count):
    """48210 -> '48.2k', the way the page and sidebar show tokens."""
    count = int(count)
    if count >= 1_000_000:
        return f"{count / 1_000_000:.1f}M".replace(".0M", "M")
    if count >= 1000:
        return f"{count / 1000:.1f}k".replace(".0k", "k")
    return str(count)


def _clock(moment):
    return moment.strftime("%H:%M")


def until(resets_at, moment=None):
    """'resets 15:40 (in 2 h 14 min)' today, or 'resets Monday 08:00' further away."""
    if not resets_at:
        return ""
    moment = moment or datetime.now()
    when = datetime.fromtimestamp(resets_at)
    seconds = (when - moment).total_seconds()
    if seconds <= 0:
        return "reset now"
    if seconds < 86400:
        hours, minutes = int(seconds // 3600), int(seconds % 3600 // 60)
        wait = f"{hours} h {minutes} min" if hours else f"{max(1, minutes)} min"
        return f"resets {_clock(when)} (in {wait})"
    day = "tomorrow" if when.date() == (moment + timedelta(days=1)).date() else when.strftime("%A")
    return f"resets {day} {_clock(when)}"


def ago(stamp, moment=None):
    if not stamp:
        return ""
    seconds = ((moment or datetime.now()) - datetime.fromtimestamp(stamp)).total_seconds()
    if seconds < 60:
        return "just now"
    if seconds < 3600:
        minutes = int(seconds // 60)
        return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
    if seconds < 86400:
        hours = int(seconds // 3600)
        return f"{hours} hour{'s' if hours != 1 else ''} ago"
    return datetime.fromtimestamp(stamp).strftime("%d %b, %H:%M")


def model_name(model):
    """A short model name for the table: 'claude-sonnet-5-5' -> 'Sonnet', 'openai/gpt-5' -> 'gpt-5'."""
    model = str(model or "")
    if model.startswith("claude-"):
        return model.split("-")[1].capitalize()
    return model.rsplit("/", 1)[-1] or "—"


def _local(stamp):
    return datetime.fromisoformat(stamp).astimezone().replace(tzinfo=None)


def daily(rows, days=14, moment=None):
    """[(date, {input, output, cached})] for the last `days` days, oldest first, today last; quiet days are 0."""
    today = (moment or datetime.now()).date()
    totals = {today - timedelta(days=offset): {"input": 0, "output": 0, "cached": 0} for offset in range(days)}
    for row in rows:
        day = _local(row["at"]).date()
        if day in totals:
            for name in ("input", "output", "cached"):
                totals[day][name] += row[name]
    return sorted(totals.items())


def today(rows, moment=None):
    """Tokens and replies today, with the input, output and cached split."""
    day = (moment or datetime.now()).date()
    mine = [row for row in rows if _local(row["at"]).date() == day]
    parts = {name: sum(row[name] for row in mine) for name in ("input", "output", "cached")}
    return dict(parts, total=sum(parts.values()), replies=len(mine))


def by_conversation(rows, limit=6):
    """The chats that used the most: [{id, title, model, tokens}], most first. The model is the one used most."""
    chats = {}
    for row in rows:
        chat = chats.setdefault(row["conversation_id"], {"id": row["conversation_id"], "tokens": 0, "models": {},
                                                         "title": row["title"] or "A deleted chat"})
        tokens = row["input"] + row["output"] + row["cached"]
        chat["tokens"] += tokens
        chat["models"][row["model"]] = chat["models"].get(row["model"], 0) + tokens
    ranked = sorted(chats.values(), key=lambda chat: -chat["tokens"])[:limit]
    for chat in ranked:
        chat["model"] = model_name(max(chat.pop("models").items(), key=lambda item: item[1])[0])
    return ranked


async def fetch_limits(settings):
    """Limits read now, for services that can be asked between replies; None for Claude (it reports with replies)."""
    if settings.llm_provider == "codex":
        from .codex import read_limits
        return codex_windows(await read_limits())
    if settings.llm_provider == "openrouter" and settings.api_key:
        import httpx
        headers = {"Authorization": f"Bearer {settings.api_key}"}
        async with httpx.AsyncClient(timeout=httpx.Timeout(15.0)) as client:
            key = credits = None
            response = await client.get("https://openrouter.ai/api/v1/key", headers=headers)
            if response.is_success:
                key = response.json().get("data")
            if not (key or {}).get("limit"):
                response = await client.get("https://openrouter.ai/api/v1/credits", headers=headers)
                if response.is_success:
                    credits = response.json().get("data")
        return openrouter_windows(key, credits)
    return None
