"""Silent avatar cues such as [[blush]] in model replies: removed from text, forwarded to the avatar."""

import re

# Must match CUES in companion/avatar/web/avatar-life.js.
CUES = ("smile", "happy", "blush", "shy", "laugh", "wink", "surprised", "sad", "pout", "annoyed",
        "worried", "think", "nod", "shake", "tilt", "sigh", "yawn", "stretch", "moon", "calm", "neutral")
EXPRESSION_MENU = (("Smile", "smile"), ("Blush", "blush"), ("Shy", "shy"), ("Laugh", "laugh"),
                   ("Wink", "wink"), ("Surprised", "surprised"), ("Sad", "sad"), ("Pout", "pout"),
                   ("Worried", "worried"), ("Nod", "nod"), ("Shake head", "shake"), ("Tilt head", "tilt"),
                   ("Sigh", "sigh"), ("Yawn", "yawn"), ("Stretch", "stretch"), ("Gaze at the moon", "moon"),
                   ("Neutral", "neutral"))
# The animation tester: every cue, plus life moments that are otherwise rare or slow to reach.
TEST_GROUPS = (
    ("Expressions (moods)", (("Neutral", "neutral"), ("Smile", "smile"), ("Blush", "blush"), ("Shy", "shy"),
                             ("Sad", "sad"), ("Pout", "pout"), ("Worried", "worried"))),
    ("Gestures", (("Happy", "happy"), ("Laugh", "laugh"), ("Wink", "wink"), ("Surprised", "surprised"),
                  ("Nod", "nod"), ("Shake head", "shake"), ("Tilt head", "tilt"), ("Think", "think"),
                  ("Sigh", "sigh"), ("Yawn", "yawn"), ("Stretch", "stretch"), ("Moon gaze", "moon"))),
    ("Reactions", (("Greeting", "test:greet"), ("Poke", "test:poke"), ("Flustered", "test:fluster"),
                   ("Being petted", "test:pet"))),
    ("Working on a task", (("Start", "test:work:start"), ("Reading", "test:work:read"),
                           ("Writing", "test:work:type"), ("Running a command", "test:work:command"),
                           ("Using the screen", "test:work:look"), ("Waiting for approval", "test:work:wait"),
                           ("Task done", "test:work:done"), ("Task failed", "test:work:failed"))),
    ("Sleep cycle", (("Get drowsy", "test:drowsy"), ("Nod off", "test:nodOff"), ("Fall asleep", "test:sleep"),
                     ("Dream", "test:dream"), ("Wake gently", "test:wake"), ("Wake startled", "test:wakeStartled"))),
)
TESTS = {name for _, items in TEST_GROUPS for _, name in items if name.startswith("test:")}
PROMPT = (
    "Avatar cues: your desktop avatar can show expressions. You may place a silent cue in double square "
    "brackets where your feeling changes, usually at the start of a sentence, for example "
    "\"[[blush]] You noticed that?\". Available cues: " + ", ".join(CUES) + ". "
    "[[neutral]] returns to your usual composed face. "
    "Cues are removed before your words are shown or spoken, so they are not stage directions and do not "
    "replace dialogue; never describe them, explain them, or mention brackets. Use them sparingly and in "
    "character: often none, usually at most two per reply, only where a reaction is genuinely felt."
)
# Cues for the app itself rather than the avatar, with a description of the work:
# [[offer: …]] proposes a computer task for the person to confirm; [[task: …]] starts one.
ACTIONS = ("task", "offer", "remember", "forget", "remind", "unremind", "undotask", "look", "card", "score", "focus",
           "installskill")
_CUE = re.compile(r"\[\[\s*([A-Za-z]{2,12})\s*(?::\s*([^\[\]]{0,1500}?))?\s*\]\]")
_ACTION_START = re.compile(r"\[\[\s*(?:task|offer|remember|forget|remind|unremind|card|score|focus|installskill)\s*:",
                           re.IGNORECASE)
_LONGEST = 20  # "[[" + name + spaces + "]]"; longer bracket text is ordinary text.
_ACTION_LONGEST = 1520  # An action cue may carry a description of up to 1,500 characters.


class CueFilter:
    """Strip known cues from streamed text. Text that only looks like a cue passes through.

    feed() returns (clean_text, [(offset, cue)]), where offset is the cue's position in the
    clean reply so far. A partial "[[..." at a chunk boundary is held until it can be decided.
    """

    def __init__(self):
        self.pending = ""
        self.length = 0
        self.last = "\n"
        self.skip_space = False

    def feed(self, text):
        self.pending += text
        if self.skip_space and self.pending:
            # The space after a cue arrived in this chunk.
            if self.pending[0] in " \t":
                self.pending = self.pending[1:]
            self.skip_space = not self.pending
        out, cues = [], []
        while self.pending:
            start = self.pending.find("[[")
            if start < 0:
                keep = 1 if self.pending.endswith("[") else 0
                out.append(self.pending[:len(self.pending) - keep])
                self.pending = self.pending[len(self.pending) - keep:]
                break
            out.append(self.pending[:start])
            rest = self.pending[start:]
            match = _CUE.match(rest)
            if match and (match.group(1).lower() in CUES or match.group(1).lower() in ACTIONS):
                emitted = "".join(out)
                name, detail = match.group(1).lower(), " ".join((match.group(2) or "").split())
                # Action cues keep their description as "task:…"; avatar cues ignore any.
                cues.append((self.length + len(emitted), f"{name}:{detail}" if name in ACTIONS and detail else name))
                rest = rest[match.end():]
                before = emitted[-1:] or self.last
                # "Hello [[smile]] there" and "[[smile]] Hello" leave no doubled or leading space.
                if before.isspace() and rest[:1] in {" ", "\t"}:
                    rest = rest[1:]
                elif before.isspace() and not rest:
                    self.skip_space = True
                self.pending = rest
                continue
            limit = _ACTION_LONGEST if _ACTION_START.match(rest) else _LONGEST
            if match or "]]" in rest[:limit] or len(rest) >= limit:
                out.append("[[")
                self.pending = rest[2:]
                continue
            self.pending = rest
            break
        clean = "".join(out)
        self.length += len(clean)
        if clean:
            self.last = clean[-1]
        return clean, cues

    def finish(self):
        text, self.pending = self.pending, ""
        self.length += len(text)
        return text


def strip_cues(text):
    """Remove cues from a complete text, such as a stored reply."""
    cues = CueFilter()
    clean, _ = cues.feed(text)
    return clean + cues.finish()
