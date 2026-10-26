"""The person's say over risky task steps: allow once, allow similar steps for this task, or deny."""
import json

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout

from ..tasks.runner import approval_group


def details(request):
    """Everything the step would do, so nothing is hidden behind a short summary."""
    values = request.values or {}
    if request.tool in {"Bash", "PowerShell"}:
        return str(values.get("command", ""))
    if request.tool == "Write":
        content = str(values.get("content", ""))
        return f"{values.get('file_path', '')}\n\n{content[:1500]}{'…' if len(content) > 1500 else ''}"
    if request.tool == "Edit":
        return (f"{values.get('file_path', '')}\n\nReplace:\n{str(values.get('old_string', ''))[:600]}\n\n"
                f"With:\n{str(values.get('new_string', ''))[:600]}")
    return json.dumps(values, ensure_ascii=False, indent=2)[:1500]


class ApprovalDialog(QDialog):
    decided = Signal(str)  # "once", "task" or "deny"

    def __init__(self, name, request, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Allow this step?")
        self.setMinimumWidth(520)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(10)
        action_name = request.summary.split(":", 1)[0] if request.tool in {"Bash", "PowerShell"} else request.summary
        heading = QLabel(f"{name} wants to {action_name[:1].lower() + action_name[1:]}:")
        heading.setWordWrap(True)
        heading.setTextFormat(Qt.TextFormat.PlainText)
        heading.setObjectName("welcomeTitle")
        heading.setStyleSheet("font-size: 16px;")
        layout.addWidget(heading)
        action = QLabel(details(request))
        action.setObjectName("approvalAction")
        action.setWordWrap(True)
        action.setTextFormat(Qt.TextFormat.PlainText)
        action.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setWidget(action)
        scroll.setMaximumHeight(260)
        layout.addWidget(scroll)
        hint = QLabel("She waits for your answer. Denying stops only this step; she will finish what she can.")
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        buttons = QHBoxLayout()
        deny = QPushButton("Deny")
        always = QPushButton(f"Allow all {approval_group(request.tool)} for this task")
        once = QPushButton("Allow once")
        once.setObjectName("primary")
        once.setDefault(True)
        buttons.addWidget(deny)
        buttons.addStretch()
        buttons.addWidget(always)
        buttons.addWidget(once)
        layout.addLayout(buttons)
        self._choice = "deny"
        for button, choice in ((once, "once"), (always, "task"), (deny, "deny")):
            button.clicked.connect(lambda _=False, choice=choice: self._choose(choice))

    def _choose(self, choice):
        self._choice = choice
        self.accept()

    def done(self, result):
        # Closing the window without choosing denies the step.
        super().done(result)
        self.decided.emit(self._choice)
