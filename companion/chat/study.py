"""Study subjects: how she tutors, flashcard scheduling (spaced repetition), the exam countdown and progress."""

from datetime import date, datetime, timedelta, timezone

from . import projects

MARK = "⏳ Focus"
FOCUS_MINUTES = 25
FOCUS_LIMITS = (5, 90)
GRADES = ("again", "hard", "good", "easy")

PROMPT = """Study session: this conversation is a study session for the user's subject "{name}"{exam}.
Teach like a patient, demanding tutor in your own voice: find out what they already know, explain step
by step with worked examples, check understanding with a short question before moving on, and correct
mistakes plainly and kindly. Prefer guiding them to the answer over handing it over, unless they ask for it.
Ground explanations in the subject's materials below when they cover the topic, and say when they don't.

Study cues (silent, never mentioned, never shown to the user):
- Quiz: when the user asks to be quizzed, ask one question at a time and wait for the answer. After judging
  each answer, put [[score: right]] or [[score: wrong]] at the very end of that reply, then explain briefly.
- Flashcards: when the user asks for flashcards, or at the end of a lesson when they would help, write each
  as [[card: question || answer]] (a short, precise question; an answer of one to three sentences). Mention
  in words how many you made; never repeat the cards' text outside the cues.
- Focus: when the user wants to focus or study for a while, start the app's focus timer with
  [[focus: minutes]] (5 to 90, usually 25) and keep your reply short so they can begin. A user message
  starting with "{mark}" comes from the app, not the user: the timer has ended."""

FOCUS_DONE = ("{mark} ({time}): the user just finished a {minutes}-minute focus session on \"{name}\". "
              "Acknowledge it briefly in your own voice and suggest a short break before the next one.")


def today():
    return datetime.now().date()


def exam_text(exam_date, now=None):
    """'Exam today', 'Exam tomorrow', 'Exam in 12 days', 'Exam was 3 days ago', or ''."""
    if not exam_date:
        return ""
    days = (date.fromisoformat(exam_date) - (now or today())).days
    if days == 0:
        return "Exam today"
    if days == 1:
        return "Exam tomorrow"
    return f"Exam in {days} days" if days > 1 else f"Exam was {-days} day{'s' if days < -1 else ''} ago"


def schedule(card, grade, on=None):
    """When a card comes back after a review graded again/hard/good/easy (a light SM-2).
    Returns (due date, interval in days, ease, lapsed)."""
    on = on or today()
    interval, ease = int(card.get("interval") or 0), float(card.get("ease") or 2.5)
    if grade == "again":
        return on.isoformat(), 0, max(1.3, ease - 0.2), card.get("reviews", 0) > 0
    if grade == "hard":
        interval, ease = max(1, round(interval * 1.2)), max(1.3, ease - 0.15)
    elif grade == "good":
        interval = 1 if interval == 0 else 3 if interval == 1 else round(interval * ease)
    else:
        interval, ease = (4 if interval == 0 else round(interval * ease * 1.3)), ease + 0.15
    return (on + timedelta(days=interval)).isoformat(), interval, round(ease, 2), False


def next_label(card, grade):
    _due, interval, _ease, _ = schedule(card, grade)
    return "now" if interval == 0 else "1 day" if interval == 1 else f"{interval} days"


def parse_card(detail):
    """'question || answer' from a [[card: …]] cue, or None."""
    front, separator, back = detail.partition("||")
    return (front.strip(), back.strip()) if separator and front.strip() and back.strip() else None


def stats(store, project_id):
    """A subject's progress for its page and the sidebar."""
    week = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    cards = store.flashcards(project_id)
    due = [card for card in cards if card["due_at"] <= today().isoformat()]
    focus_week = sum(event["value"] for event in store.study_events(project_id, "focus", since=week))
    focus_total = sum(event["value"] for event in store.study_events(project_id, "focus"))
    answers = store.study_events(project_id, "answer")[-30:]
    right = sum(event["value"] for event in answers)
    return {"cards": len(cards), "due": len(due), "focus_week": focus_week, "focus_total": focus_total,
            "answers": len(answers), "right": right}


def minutes_text(minutes):
    return f"{minutes // 60}h {minutes % 60:02d}m" if minutes >= 60 else f"{minutes} min"


def context(subject, files, progress=None):
    """Everything she is told in the subject's sessions: tutoring, the subject, its materials and progress."""
    exam = exam_text(subject.get("exam_date"))
    lines = [PROMPT.format(name=subject["name"], exam=f" ({exam.lower()})" if exam else "", mark=MARK),
             projects.context(subject, files).split("\n\n", 1)[1]]  # The details and materials, without the project wording.
    if progress and (progress["answers"] or progress["cards"]):
        lines.append(f"Progress so far: {progress['cards']} flashcards ({progress['due']} due for review), "
                     f"{progress['right']} of {progress['answers']} recent quiz answers right, "
                     f"{minutes_text(progress['focus_week'])} of focus this week.")
    return "\n\n".join(lines)
