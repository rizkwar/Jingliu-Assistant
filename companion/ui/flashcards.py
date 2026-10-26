"""Reviewing a subject's flashcards: question, answer, and how well you knew it (spaced repetition)."""
import sqlite3

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from ..chat import study
from .theme import ICONS

GRADE_LABELS = {"again": "Again", "hard": "Hard", "good": "Good", "easy": "Easy"}


class FlashcardReview(QDialog):
    def __init__(self, store, project_id, parent=None):
        super().__init__(parent)
        self.store, self.project_id = store, project_id
        subject = store.project(project_id)
        self.setWindowTitle(f"Flashcards · {subject['name']}" if subject else "Flashcards")
        self.cards, self.index, self.reviewed, self.revealed = [], 0, 0, False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(14)
        layout.addStretch(1)  # Counter, card and buttons sit together in the middle of the page.
        self.counter = QLabel()
        self.counter.setObjectName("rowHint")
        layout.addWidget(self.counter, 0, Qt.AlignmentFlag.AlignHCenter)

        self.card = QFrame()
        self.card.setObjectName("flashcard")
        card = QVBoxLayout(self.card)
        card.setContentsMargins(36, 26, 36, 30)
        card.setSpacing(14)
        card.addStretch(1)  # The card's words sit together in its middle.
        moon = QLabel(ICONS["moon"])
        moon.setObjectName("flashcardMoon")
        card.addWidget(moon, 0, Qt.AlignmentFlag.AlignHCenter)
        self.front = QLabel()
        self.front.setObjectName("flashcardFront")
        self.front.setWordWrap(True)
        self.front.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.front.setTextFormat(Qt.TextFormat.PlainText)
        card.addWidget(self.front)
        self.rule = QFrame()
        self.rule.setObjectName("flashcardRule")
        self.rule.setFixedHeight(1)
        card.addWidget(self.rule)
        self.back = QLabel()
        self.back.setObjectName("flashcardBack")
        self.back.setWordWrap(True)
        self.back.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.back.setTextFormat(Qt.TextFormat.PlainText)
        self.back.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        card.addWidget(self.back)
        card.addStretch(1)
        self.card.setMaximumHeight(420)
        layout.addWidget(self.card)

        self.show_answer = QPushButton("Show answer  ·  Space")
        self.show_answer.setObjectName("primary")
        self.show_answer.setCursor(Qt.CursorShape.PointingHandCursor)
        self.show_answer.clicked.connect(self._reveal)
        layout.addWidget(self.show_answer, 0, Qt.AlignmentFlag.AlignHCenter)
        grades = QHBoxLayout()
        grades.setSpacing(10)
        grades.addStretch()
        self.grade_buttons = {}
        for number, grade in enumerate(study.GRADES, 1):
            button = QPushButton()
            button.setObjectName("grade")
            button.setProperty("grade", grade)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(lambda _=False, grade=grade: self._grade(grade))
            self.grade_buttons[grade] = button
            grades.addWidget(button)
        grades.addStretch()
        layout.addLayout(grades)
        footer = QHBoxLayout()
        self.delete = QPushButton("Delete this card")
        self.delete.setObjectName("sideLink")
        self.delete.setCursor(Qt.CursorShape.PointingHandCursor)
        self.delete.clicked.connect(self._delete)
        footer.addWidget(self.delete)
        footer.addStretch()
        self.practise = QPushButton()
        self.practise.setObjectName("chip")
        self.practise.setCursor(Qt.CursorShape.PointingHandCursor)
        self.practise.clicked.connect(lambda: self._start(due_only=False))
        footer.addWidget(self.practise)
        layout.addLayout(footer)
        layout.addStretch(1)
        self._start(due_only=True)

    def _start(self, due_only):
        try:
            self.cards = self.store.flashcards(self.project_id, study.today().isoformat() if due_only else None)
        except sqlite3.Error:
            self.cards = []
        self.index = 0
        self._show()

    def _show(self):
        total = len(self.store.flashcards(self.project_id))
        if self.index >= len(self.cards):
            # The end of the queue, or nothing due today.
            self.counter.setText("")
            self.front.setText("Done for now." if self.reviewed else "Nothing is due today.")
            upcoming = self.store.flashcards(self.project_id)
            later = min((card["due_at"] for card in upcoming), default="")
            self.back.setText(f"You reviewed {self.reviewed} card{'s' if self.reviewed != 1 else ''}. "
                              + (f"The next one returns on {later}." if later else "") if self.reviewed else
                              ("Every card is scheduled for later. You can still practise them all." if total else
                               "Ask her for flashcards in a study session; they collect here."))
            self.rule.hide()
            self.back.show()
            self.show_answer.hide()
            for button in self.grade_buttons.values():
                button.hide()
            self.delete.hide()
            self.practise.setText(f"Practise all {total}")
            self.practise.setVisible(bool(total))
            return
        card = self.cards[self.index]
        self.counter.setText(f"Card {self.index + 1} of {len(self.cards)}"
                             + (" · new" if not card["reviews"] else f" · seen {card['reviews']}×"))
        self.front.setText(card["front"])
        self.back.setText(card["back"])
        self.back.hide()
        self.revealed = False
        self.rule.hide()
        self.show_answer.show()
        self.show_answer.setFocus()
        for grade, button in self.grade_buttons.items():
            button.setText(f"{GRADE_LABELS[grade]}\n{study.next_label(card, grade)}")
            button.hide()
        self.delete.show()
        self.practise.hide()

    def _reveal(self):
        if self.index >= len(self.cards):
            return
        self.back.show()
        self.revealed = True
        self.rule.show()
        self.show_answer.hide()
        for button in self.grade_buttons.values():
            button.show()

    def _grade(self, grade):
        if self.index >= len(self.cards) or not self.revealed:
            return
        card = self.cards[self.index]
        due, interval, ease, lapsed = study.schedule(card, grade)
        try:
            self.store.schedule_flashcard(card["id"], due, interval, ease, lapsed)
        except sqlite3.Error:
            return
        self.reviewed += 1
        if grade == "again":
            self.cards.append({**card, "interval": interval, "ease": ease, "reviews": card["reviews"] + 1})
        self.index += 1
        self._show()

    def _delete(self):
        if self.index < len(self.cards):
            card = self.cards.pop(self.index)
            self.cards = [other for other in self.cards if other["id"] != card["id"]]
            try:
                self.store.delete_flashcards([card["id"]])
            except sqlite3.Error:
                pass
            self._show()

    def keyPressEvent(self, event):
        key = event.key()
        if key in (Qt.Key.Key_Space, Qt.Key.Key_Return, Qt.Key.Key_Enter) and not self.revealed and self.index < len(self.cards):
            self._reveal()
            return
        grades = {Qt.Key.Key_1: "again", Qt.Key.Key_2: "hard", Qt.Key.Key_3: "good", Qt.Key.Key_4: "easy"}
        if key in grades and self.revealed and self.index < len(self.cards):
            self._grade(grades[key])
            return
        super().keyPressEvent(event)
