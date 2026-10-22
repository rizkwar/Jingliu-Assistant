"""Produce a spoken version without changing the visible conversation."""

import re


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


def spoken_text(text: str) -> str:
    # Omit code blocks, including an unclosed fence in an interrupted answer.
    text = re.sub(r"(```|~~~)[\s\S]*?(?:\1|\Z)", " ", text)
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"https?://\S+", " ", text)
    # Inline code is often meaningful (e.g. a function name); keep its words.
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"(?m)^\s*(?:#{1,6}\s+|>\s*|[-*+]\s+|\d+[.)]\s+)", "", text)
    text = text.replace("**", "").replace("__", "")
    text = re.sub(r"\*([^*\n]+)\*", r"\1", text)
    text = re.sub(r"\s+", " ", text).strip()
    # Keep a long coding answer from becoming many minutes of unsolicited speech.
    if len(text) > 2400:
        cut = text.rfind(". ", 0, 2300)
        if cut < 0:
            cut = text.rfind(" ", 0, 2300)
        text = text[:cut + 1].strip() + " You can read the rest in the conversation."
    return text

