"""Produce a spoken version without changing the visible conversation."""

import re


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

