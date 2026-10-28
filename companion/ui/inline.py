"""Editing and asking in place, instead of popup windows: rename a name where it is shown, and confirm or
report something in a bar inside the window.

edit_in_place(view, rect, text, commit): a line editor over `rect` of an item view (or any widget). Enter or
clicking away saves (commit(text) returns an error message to show, or None); Esc cancels.
ask(widget, text, action, on_yes): a question in the window's bar, with Cancel and `action`.
tell(widget, text, tone): a short notice in the window's bar, which leaves by itself."""
from PySide6.QtCore import QEvent, QObject, QPropertyAnimation, QRect, QTimer, Qt, Signal, QEasingCurve
from PySide6.QtWidgets import (QAbstractItemView, QFrame, QGraphicsOpacityEffect, QHBoxLayout, QLabel, QLineEdit,
                               QMessageBox, QPushButton, QWidget)


class InlineEditor(QLineEdit):
    finished = Signal()

    def __init__(self, parent, text, commit):
        super().__init__(text, parent)
        self.setObjectName('inlineEdit')
        self.original, self.commit, self.done = text, commit, False
        self.selectAll()
        self.returnPressed.connect(self.save)
        self.textEdited.connect(lambda: self._error(''))

    def _error(self, message):
        self.setProperty('invalid', bool(message))
        self.setToolTip(message)
        self.style().unpolish(self)
        self.style().polish(self)

    def save(self):
        if self.done:
            return
        text = ' '.join(self.text().split())
        if not text or text == self.original:
            self.close_editor()
            return
        error = self.commit(text)
        if error:
            self._error(error)  # Stays open, red, with the reason, until fixed or cancelled.
            self.setFocus()
            return
        self.close_editor()

    def close_editor(self):
        if not self.done:
            self.done = True
            self.finished.emit()
            self.deleteLater()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.close_editor()
            return
        super().keyPressEvent(event)

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        if not self.done and not self.property('invalid'):
            QTimer.singleShot(0, self, self.save)  # Clicking away keeps the new name, like ChatGPT.


def edit_in_place(view, rect, text, commit):
    """Opens an InlineEditor over `rect` (in `view`'s viewport for item views)."""
    host = view.viewport() if isinstance(view, QAbstractItemView) else view
    editor = InlineEditor(host, text, commit)
    editor.setGeometry(QRect(rect.x() + 2, rect.y() + 2, max(80, rect.width() - 4), rect.height() - 4))
    editor.show()
    editor.setFocus(Qt.FocusReason.OtherFocusReason)
    return editor


class InlineBar(QFrame):
    """A bar inside the window, above the message box: a question with its answers, or a short notice."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('inlineBar')
        row = QHBoxLayout(self)
        row.setContentsMargins(14, 8, 8, 8)
        row.setSpacing(8)
        self.text = QLabel()
        self.text.setObjectName('inlineBarText')
        self.text.setWordWrap(True)
        row.addWidget(self.text, 1)
        self.buttons = QHBoxLayout()
        self.buttons.setSpacing(6)
        row.addLayout(self.buttons)
        self.fade = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.fade)
        self.animation = QPropertyAnimation(self.fade, b'opacity', self)
        self.animation.setDuration(160)
        self.animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.dismiss)
        self.hide()

    def _clear(self):
        while self.buttons.count():
            widget = self.buttons.takeAt(0).widget()
            if widget:
                widget.deleteLater()

    def _button(self, text, slot, name='chip'):
        button = QPushButton(text)
        button.setObjectName(name)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.clicked.connect(slot)
        self.buttons.addWidget(button)
        return button

    def _show(self, tone):
        self.setProperty('tone', tone)
        self.style().unpolish(self)
        self.style().polish(self)
        self.show()
        self.raise_()
        self.animation.stop()
        self.animation.setStartValue(0.0)
        self.animation.setEndValue(1.0)
        self.animation.start()

    def ask(self, text, action, on_yes, danger=True, on_no=None):
        self.timer.stop()
        self._clear()
        self.text.setText(text)

        def answer(yes):
            self.dismiss()
            (on_yes if yes else on_no or (lambda: None))()
        self._button('Cancel', lambda: answer(False))
        self._button(action, lambda: answer(True), 'danger' if danger else 'primary').setFocus()
        self._show('ask')

    def tell(self, text, tone='info', seconds=6, action=None, on_action=None):
        self._clear()
        self.text.setText(text)
        if action and on_action:
            self._button(action, lambda: (self.dismiss(), on_action()))
        self._button('✕', self.dismiss, 'barClose').setToolTip('Dismiss')
        self._show(tone)
        self.timer.start(int(seconds * 1000))

    def dismiss(self):
        self.timer.stop()
        self.hide()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.dismiss()
            return
        super().keyPressEvent(event)


def _bar(widget):
    window = widget.window() if widget is not None else None
    return getattr(window, 'inline_bar', None)


def ask(widget, title, text, action, on_yes, danger=True, on_no=None):
    """Asks in the window's bar; a window without one (a separate dialog) still asks in a popup."""
    bar = _bar(widget)
    if bar is not None:
        bar.ask(text, action, on_yes, danger, on_no)
        return
    if QMessageBox.question(widget, title, text) == QMessageBox.StandardButton.Yes:
        on_yes()
    elif on_no:
        on_no()


def tell(widget, title, text, tone='info', **options):
    """Reports in the window's bar ('info', 'error' or 'done'); a popup only where there is no bar."""
    bar = _bar(widget)
    if bar is not None:
        bar.tell(text, tone, **options)
        return
    (QMessageBox.warning if tone == 'error' else QMessageBox.information)(widget, title, text)
