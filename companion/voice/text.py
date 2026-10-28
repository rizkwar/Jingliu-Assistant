"""Produce a spoken version without changing the visible conversation."""

import re


_ACTION = re.compile(
    r"^(?:(?:she|he|i|jingliu)\s+)?(?:"
    r"smil(?:e[sd]?|ing)|blush(?:es|ing)?|sigh(?:s|ing)?|laugh(?:s|ing)?|"
    r"chuckl(?:e[sd]?|ing)|giggl(?:e[sd]?|ing)|nod(?:s|ding)?|"
    r"wink(?:s|ing)?|shrug(?:s|ging)?|frown(?:s|ing)?|"
    r"tilt(?:s|ing)?|lean(?:s|ing)?|glanc(?:e[sd]?|ing)|"
    r"gaze[sd]?|look(?:s|ing)?|rais(?:e[sd]?|ing)|"
    r"whisper(?:s|ing)?|paus(?:e[sd]?|ing)|"
    r"softly|quietly|playfully|a\s+(?:faint|small|slight)\s+smile|"
    r"clears?\s+(?:(?:her|his|my)\s+)?throat|"
    r"(?:stage\s+direction|action)\s*:)(?:\b|\s|$)", re.IGNORECASE,
)


def _is_action(text):
    return bool(_ACTION.match(text.strip()))


def _without_actions(text):
    # Preserve ordinary emphasis, math, and asides. Only marked performance cues
    # are suppressed; normal dialogue about smiling remains dialogue.
    for pattern in (r"(?<!\*)\*(?!\*)([^*]+)\*(?!\*)", r"(?<![\w_])_([^_]+)_(?![\w_])",
                    r"\[([^\]\n]+)\](?!\()", r"\(([^()\n]+)\)"):
        text = re.sub(pattern, lambda match: " " if _is_action(match[1]) else match[0], text)
    # An interrupted stream must not read a dangling *smiles ... or [sighs ... .
    text = re.sub(r"(?<![\w*_])([*_\[(])([^*_\]\)]+)\Z",
                  lambda match: " " if _is_action(match[2]) else match[0], text)
    return text


class SpeechSegmenter:
    """Wait for stable phrase boundaries while markdown arrives in arbitrary chunks."""

    ABBREVIATIONS = {"mr.", "mrs.", "ms.", "dr.", "prof.", "st.", "jr.", "sr.", "vs.", "etc.", "e.g.", "i.e.", "a.m.", "p.m.", "u.s."}

    def __init__(self):
        self.buffer = ""
        self.remaining = 2300
        self.capped = False

    def feed(self, text: str) -> list[str]:
        if self.capped:
            return []
        self.buffer += text
        phrases = []
        while (boundary := self._boundary()) is not None:
            raw, self.buffer = self.buffer[:boundary], self.buffer[boundary:]
            phrases.extend(self._accept(spoken_text(raw)))
            if self.capped:
                self.buffer = ""
                break
        if len(self.buffer) > 65536:
            self.buffer = ""
            self.capped = True
            phrases.append("You can read the rest in the conversation.")
        return phrases

    def finish(self) -> list[str]:
        if self.capped:
            return []
        raw, self.buffer = self.buffer, ""
        return self._accept(spoken_text(raw))

    def _accept(self, text: str) -> list[str]:
        if not text:
            return []
        if len(text) <= self.remaining:
            self.remaining -= len(text) + 1
            return [text]
        prefix = text[:max(0, self.remaining)].rsplit(" ", 1)[0].strip()
        self.capped = True
        return ([prefix] if prefix else []) + ["You can read the rest in the conversation."]

    def _boundary(self) -> int | None:
        text = self.buffer
        i = 0
        while i < len(text):
            fence = text[i:i + 3]
            if fence in {"```", "~~~"}:
                end = text.find(fence, i + 3)
                if end < 0:
                    return None
                i = end + 3
                continue
            if text[i] == "`":
                end = text.find("`", i + 1)
                if end < 0:
                    return None
                i = end + 1
                continue
            if text[i:i + 2] in {"**", "__"}:
                i += 2
                continue
            if (text[i] in "*_" and (i == 0 or not text[i - 1].isalnum())
                    and i + 1 < len(text) and text[i + 1].isalpha()):
                end = text.find(text[i], i + 1)
                if end < 0:
                    return None
                i = end + 1
                continue
            if text[i] == "(" and _is_action(text[i + 1:]):
                end = text.find(")", i + 1)
                if end < 0:
                    return None
                i = end + 1
                continue
            if text[i] == "[":
                end = text.find("]", i + 1)
                if end < 0 or end + 1 == len(text):
                    return None
                i = end + 1
                if text[i] == "(":
                    depth = 1
                    i += 1
                    while i < len(text) and depth:
                        depth += (text[i] == "(") - (text[i] == ")")
                        i += 1
                    if depth:
                        return None
                continue
            if text.startswith(("https://", "http://"), i):
                end = re.search(r"\s", text[i:])
                if end is None:
                    return None
                i += end.start()
                continue
            char = text[i]
            if char in ".!?":
                end = i + 1
                while end < len(text) and text[end] in '\"\'”’)]':
                    end += 1
                if end < len(text) and text[end].isspace():
                    word = re.search(r"[\w.]+$", text[:i + 1])
                    token = word.group().lower() if word else ""
                    abbreviation = char == "." and (
                        token in self.ABBREVIATIONS or token[:-1].isdecimal()
                        or (len(token) == 2 and token[0].isalpha())
                    )
                    if not abbreviation:
                        return end + 1
            if char == "\n" and len(spoken_text(text[:i])) >= 40:
                return i + 1
            if char.isspace() and i >= 280:
                return i + 1
            if char in ",;:" and i >= 100 and i + 1 < len(text) and text[i + 1].isspace():
                return i + 2
            i += 1
        return None


_ONES = ("zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen "
         "seventeen eighteen nineteen").split()
_TENS = {2: "twenty", 3: "thirty", 4: "forty", 5: "fifty"}
# A clock time: 08:00, 7:05 pm, 19.30 (the dot only where it is clearly a time: a leading zero, a.m./p.m., or
# after "at", "pukul" or "jam"), and a range such as 08:00–10:00.
_CLOCK = r"(?:[01]?\d|2[0-3])[:.][0-5]\d(?![:.]?\d)"
_SUFFIX = r"(?:\s*(?P<{0}>[ap]\.?\s?m\.?)(?![a-z]))?"
_TIME = re.compile(r"(?<![\w:.])(?P<lead>(?:at|pukul|jam)\s+)?(?P<a>" + _CLOCK + ")" + _SUFFIX.format("sa")
                   + r"(?:\s*(?:–|—|-|to|until|sampai)\s*(?P<b>" + _CLOCK + ")" + _SUFFIX.format("sb") + ")?",
                   re.IGNORECASE)


def _number(value):
    return _ONES[value] if value < 20 else _TENS[value // 10] + ("" if value % 10 == 0 else "-" + _ONES[value % 10])


def _clock(hour, minute, suffix, certain):
    """How a person says a time, and its part of the day when that is known: ("eight o'clock", "in the
    morning"), ("seven thirty", "in the evening"), ("noon", "")."""
    if suffix:
        hour = hour % 12 + (12 if suffix.lower().startswith("p") else 0)
        certain = True
    if minute == 0 and hour == 12 and certain:
        return "noon", ""
    if minute == 0 and hour == 0:
        return "midnight", ""
    twelve = hour % 12 or 12
    words = _number(twelve) + (" o'clock" if minute == 0 else (" oh " if minute < 10 else " ") + _number(minute))
    if not certain:
        return words, ""
    return words, ("at night" if hour < 5 or hour >= 21 else "in the morning" if hour < 12
                   else "in the afternoon" if hour < 17 else "in the evening")


def _times(text):
    def say(match):
        written = [(match["a"], match["sa"])] + ([(match["b"], match["sb"])] if match["b"] else [])
        # A dot is a time only when it plainly is one; "3.50" is a price or a number.
        if (any("." in value for value, _ in written) and not match["lead"]
                and not any(suffix for _, suffix in written) and not any(v.startswith("0") for v, _ in written)):
            return match[0]
        # The part of the day is known from a.m./p.m., a 24-hour hour (13+) or a leading zero (08:00); in a
        # range of 24-hour times, one such end is enough for both.
        clock = [(int(h), int(m), suffix, int(h) >= 13 or h.startswith("0"))
                 for (value, suffix) in written for h, m in [re.split(r"[:.]", value)]]
        if len(clock) == 2 and not any(item[2] for item in clock) and any(item[3] for item in clock):
            clock = [(hour, minute, suffix, True) for hour, minute, suffix, _ in clock]
        said = [_clock(*item) for item in clock]
        after = text[match.end():]
        if _DAYPART.match(after):  # "19:30 tonight": the sentence already says when.
            said = [(words, "") for words, _ in said]
        if len(said) == 2 and said[0][1] and said[0][1] == said[1][1]:
            words = f"{said[0][0]} to {said[1][0]} {said[1][1]}"  # A range: the part of the day once.
        else:
            words = " to ".join(" ".join(part for part in item if part) for item in said)
        # "7 p.m." at the end of a sentence: its full stop is the sentence's too.
        last = match["sb"] or (match["sa"] if not match["b"] else None)
        if last and last.endswith(".") and (not after.strip() or re.match(r"\s+[A-Z]", after)):
            words += "."
        return (match["lead"] or "") + words
    text = _TIME.sub(say, text)

    def hour_only(match):  # "7 p.m." → "seven in the evening"
        hour = int(match["h"]) % 12 + (12 if match["s"].lower().startswith("p") else 0)
        words, part = _clock(hour, 0, None, True)
        words = words.replace(" o'clock", "")
        if _DAYPART.match(text[match.end():]):
            part = ""
        end = "." if match["s"].endswith(".") and (not text[match.end():].strip() or re.match(r"\s+[A-Z]", text[match.end():])) else ""
        return " ".join(item for item in (words, part) if item) + end
    return re.sub(r"(?<![\w:.])(?P<h>1[0-2]|0?[1-9])\s?(?P<s>[ap]\.?\s?m\.?)(?![a-z])", hour_only, text,
                  flags=re.IGNORECASE)


_DAYPART = re.compile(r"\s*(?:tonight|today|tomorrow (?:morning|evening|night)|this (?:morning|afternoon|evening)|"
                      r"in the (?:morning|afternoon|evening)|at night|pagi|siang|sore|malam)\b", re.IGNORECASE)


def spoken_text(text: str) -> str:
    # Omit code blocks, including an unclosed fence in an interrupted answer.
    text = re.sub(r"(```|~~~)[\s\S]*?(?:\1|\Z)", " ", text)
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"https?://\S+", " ", text)
    # Inline code is often meaningful (e.g. a function name); keep its words.
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = _without_actions(text)
    text = re.sub(r"(?m)^\s*(?:#{1,6}\s+|>\s*|[-*+]\s+|\d+[.)]\s+)", "", text)
    text = text.replace("**", "").replace("__", "")
    text = re.sub(r"\*([^*\n]+)\*", r"\1", text)
    text = _times(text)  # "08:00" is said "eight o'clock in the morning", not "zero eight zero zero".
    text = re.sub(r"\s+", " ", text).strip()
    # Keep a long coding answer from becoming many minutes of unsolicited speech.
    if len(text) > 2400:
        cut = text.rfind(". ", 0, 2300)
        if cut < 0:
            cut = text.rfind(" ", 0, 2300)
        text = text[:cut + 1].strip() + " You can read the rest in the conversation."
    return text

