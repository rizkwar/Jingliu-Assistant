"""How hard she thinks before answering: a fixed level, or Auto, which picks one for each message.

Higher effort means more reasoning tokens and slower replies. Auto keeps small talk quick and cheap,
and gives code, maths, study and hard problems the thought they need.
"""

import re


# key: (name, what it means for you)
LEVELS = {
    "auto": ("Auto", "Picks for each message: quick for small talk, deeper for code, maths and study"),
    "low": ("Low", "Quickest and lightest on your limits"),
    "medium": ("Medium", "Thinks a little first; good for most questions"),
    "high": ("High", "Careful reasoning for hard problems; uses more tokens"),
    "xhigh": ("Extra high", "Deep reasoning; slower and uses your limits faster"),
    "max": ("Max", "Her deepest thinking; slowest, uses your limits fastest"),
}
TASK_LEVELS = ("low", "medium", "high", "xhigh", "max")

_HARD = re.compile(r"\b(think (hard|carefully|deeply|it through)|step[- ]by[- ]step|prove|proof|derive|"
                   r"time limit|memory limit|constraints?:|codeforces|leetcode|atcoder|icpc|olympiad)\b|"
                   r"\d\s*(≤|<=)\s*[a-z]", re.IGNORECASE)
_THOUGHTFUL = re.compile(r"```|\$[^$\n]+\$|\\(frac|sum|int|sigma|times|bowtie)|\b(explain|why|how (do|does|can|to)|"
                         r"debug|error|exception|traceback|fix|solve|calculate|compute|compare|analy[sz]e|summari[sz]e|"
                         r"quiz|exam|essay|review|optimi[sz]e|algorithm|query|sql|function|class|complexity|"
                         r"difference between|what if|plan)\b", re.IGNORECASE)


def choose(text, attachments=(), study=False):
    """The level Auto uses for this message."""
    text = text or ""
    if _HARD.search(text) or (len(text) > 1500 and "```" in text):
        return "high"
    if _THOUGHTFUL.search(text) or attachments or study or len(text) > 400:
        return "medium"
    return "low"


def resolve(level, text="", attachments=(), study=False):
    """A concrete level for one reply: Auto decides now; anything unknown is treated as Auto."""
    if level in LEVELS and level != "auto":
        return level
    return choose(text, attachments, study)


def claude(level):
    """Claude Code's --effort."""
    return level if level in TASK_LEVELS else "low"


def codex(level):
    """Codex's reasoning effort; its deepest is xhigh."""
    return {"low": "low", "medium": "medium", "high": "high", "xhigh": "xhigh", "max": "xhigh"}.get(level, "low")


def openrouter(level):
    """OpenRouter's reasoning setting: none at Low, as before; otherwise the nearest effort it knows."""
    if level not in TASK_LEVELS or level == "low":
        return {"enabled": False, "exclude": True}
    return {"effort": {"medium": "medium"}.get(level, "high"), "exclude": True}
