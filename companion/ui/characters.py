"""Describe a character and attach a local voice sample without editing code."""

from pathlib import Path

from PySide6.QtCore import Signal, Slot
from PySide6.QtWidgets import (
    QComboBox, QDialog, QFileDialog, QFormLayout, QFrame, QHBoxLayout, QLabel, QLineEdit,
    QPlainTextEdit, QPushButton, QScrollArea, QSizePolicy, QSpinBox, QVBoxLayout, QWidget,
)

from ..character.library import ProfileDraft
from ..voice.reference import inspect_reference


class CharacterDialog(QDialog):
    preview_requested = Signal(str, str, int)
    stop_requested = Signal()

    def __init__(self, library, parent=None, *, existing=None, draft=None):
        super().__init__(parent)
        self.library = library
        self.existing = existing
        self.saved_path = None
        draft = draft or (library.draft(existing) if existing else ProfileDraft("", ""))
        self.reference = draft.reference
        self.setWindowTitle("Edit character" if existing else "Add character")
        self.resize(660, 740)
        self.setMinimumSize(500, 500)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(22, 22, 22, 22)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(0, 0, 12, 0)
        layout.setSpacing(12)
        scroll.setWidget(body)
        outer.addWidget(scroll, 1)
        hint = QLabel("Describe who they are and how they talk. Add a recording for their local speaking voice. Existing profiles keep their configured voice when no recording is attached.")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        form = QFormLayout()
        self.name = QLineEdit(draft.name)
        self.name.setMaxLength(80)
        self.name.setPlaceholderText("Character name")
        form.addRow("Name", self.name)
        layout.addLayout(form)
        layout.addWidget(QLabel("Character description"))
        self.description = QPlainTextEdit(draft.description)
        self.description.setMinimumHeight(240)
        self.description.setPlaceholderText(
            "Describe identity, background, traits, interests, humor, speaking style, and relationship with you. "
            "How do they react to excitement, frustration, teasing, and disagreement? "
            "Add example user/character exchanges and behaviors to avoid. Separate fictional history from real memories.")
        layout.addWidget(self.description)
        if existing:
            note = QLabel("Edit all personality instructions and examples above. Your first saved edit keeps a .toml.bak backup; structured profiles are converted to this description format.")
            note.setObjectName("hint")
            note.setWordWrap(True)
            layout.addWidget(note)
        self.reference_label = QLabel()
        self.reference_label.setWordWrap(True)
        self.reference_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        layout.addWidget(self.reference_label)
        audio_buttons = QHBoxLayout()
        self.choose_audio = QPushButton("Choose voice recording")
        self.choose_audio.clicked.connect(self._choose_audio)
        self.clear_audio = QPushButton("Remove recording")
        self.clear_audio.clicked.connect(self._clear_audio)
        audio_buttons.addWidget(self.choose_audio)
        audio_buttons.addWidget(self.clear_audio)
        audio_buttons.addStretch()
        layout.addLayout(audio_buttons)
        audio_hint = QLabel("Use one clear English speaker, without music: PCM WAV, 3–30 seconds (8–15 recommended), 16–48 kHz, up to 20 MiB. A copy stays with your local profiles. Voice matching varies with the sample.")
        audio_hint.setObjectName("hint")
        audio_hint.setWordWrap(True)
        layout.addWidget(audio_hint)
        voice_form = QFormLayout()
        self.builtin = QComboBox(self)
        # Retain legacy profile metadata without exposing alternative speakers.
        self.builtin.addItem(draft.builtin)
        self.builtin.hide()
        self.rate = QSpinBox()
        self.rate.setRange(80, 115)
        self.rate.setSuffix("%")
        self.rate.setValue(draft.rate)
        self.rate.setToolTip("100% preserves the generated delivery. Lower settings slow and lower the voice together.")
        voice_form.addRow("Delivery", self.rate)
        self.preview_text = QLineEdit(draft.preview)
        self.preview_text.setMaxLength(6000)
        self.preview_text.setPlaceholderText("Optional sentence to audition this character's voice")
        voice_form.addRow("Preview sentence", self.preview_text)
        layout.addLayout(voice_form)
        self.preview = QPushButton("Preview voice")
        self.preview.clicked.connect(self._preview)
        preview_buttons = QHBoxLayout()
        preview_buttons.addWidget(self.preview)
        self.stop_preview = QPushButton("Stop voice")
        self.stop_preview.clicked.connect(self.stop_requested.emit)
        preview_buttons.addWidget(self.stop_preview)
        preview_buttons.addStretch()
        layout.addLayout(preview_buttons)
        self.feedback = QLabel("Creating a profile needs no API call. Chat uses your existing model; speech stays local.")
        self.feedback.setWordWrap(True)
        outer.addWidget(self.feedback)
        buttons = QHBoxLayout()
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        buttons.addWidget(cancel)
        buttons.addStretch()
        self.save = QPushButton("Save and use character")
        self.save.setObjectName("send")
        self.save.clicked.connect(self._save)
        buttons.addWidget(self.save)
        outer.addLayout(buttons)
        self._refresh_reference()

    def _draft(self):
        return ProfileDraft(self.name.text(), self.description.toPlainText(), self.reference,
                            self.builtin.currentText(), self.rate.value(), self.preview_text.text())

    def _refresh_reference(self):
        self.reference_label.setText("Voice recording: " + Path(self.reference).name if self.reference else "Voice recording: none")
        self.reference_label.setToolTip(self.reference)
        self.clear_audio.setEnabled(bool(self.reference))

    @Slot()
    def _choose_audio(self):
        source, _ = QFileDialog.getOpenFileName(self, "Choose voice recording", "", "PCM WAV audio (*.wav)")
        if not source:
            return
        try:
            audio = inspect_reference(source)
        except ValueError as exc:
            self.feedback.setText(str(exc))
            return
        self.reference = str(audio.path)
        self.rate.setValue(100)
        self._refresh_reference()
        self.feedback.setText(f"Recording ready · {audio.seconds:.1f} seconds. Preview it or save the character.")

    @Slot()
    def _clear_audio(self):
        self.reference = ""
        self._refresh_reference()

    @Slot()
    def _preview(self):
        try:
            if self.reference:
                inspect_reference(self.reference)
        except ValueError as exc:
            self.feedback.setText(str(exc))
            return
        text = self.preview_text.text().strip() or "Hello. Take your time. What would you like to talk about?"
        self.feedback.setText("Preparing the local voice. First use may need time to load the model; Stop voice cancels playback.")
        self.preview_requested.emit(text, self.reference or self.builtin.currentText(), self.rate.value())

    @Slot()
    def _save(self):
        try:
            self.saved_path = self.library.save(self._draft(), self.existing)
        except (OSError, ValueError) as exc:
            self.feedback.setText("Could not save character: " + str(exc))
            return
        self.accept()
