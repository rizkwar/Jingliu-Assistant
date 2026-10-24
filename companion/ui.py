from dataclasses import replace
import sqlite3
from pathlib import Path
import tempfile
import time

from PySide6.QtCore import QEvent, QSignalBlocker, Qt, QTimer, QUrl, Signal, Slot
from PySide6.QtGui import QCloseEvent, QDesktopServices, QImage, QKeyEvent
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QFileDialog, QFrame, QHBoxLayout, QLabel, QMainWindow, QMenu, QMessageBox,
    QPlainTextEdit, QProgressBar, QPushButton, QScrollArea, QSizePolicy, QSlider, QTabWidget, QVBoxLayout, QWidget,
)

from .config import PROJECT_ROOT, Settings, VOICES, active_character_voice, load_settings
from .character import character_key, load_character, read_profile
from .characters import CharacterLibrary
from .character_ui import CharacterDialog
from .speech import SpeechController
from .microphone import MicrophoneController
from .worker import ReplyWorker
from .storage import Store
from .library_ui import HistoryDialog, MemoryDialog
from .preferences import Preferences
from .continuity import MAX_SUMMARY_CHARS, SUMMARY_PROMPT, recent_messages, split_turns
from .summary_ui import SummaryDialog
from .avatar import AvatarController, activity_state
from .avatar_presets import AVATAR_MOTION_PRESETS, motion_preset_name
from .avatar_models import AvatarModels
from .connection_ui import ConnectionPanel
from .prompts import reply_prompt
from .reference_voice import inspect_reference, VoiceSetupError
from . import attachments
from .chat_view import AttachmentCard, ChatView
from .theme import ACTIVITY_COLORS, ICONS, STYLE, NightSky, glyph_icon, icon_button, moon_icon, repolish


# Calm, everyday states that should not displace the default footer hint.
IDLE_NOTES = {"", "Microphone off", "Voice loads on first use", "Voice ready", "Voice stopped", "Hands-free off"}
SEALS = {"jingliu": "镜流"}


class Note(QLabel):
    """A status message shown in the shared footer line instead of a row of its own."""
    updated = Signal(str)

    def setText(self, text):
        super().setText(text)
        self.updated.emit(text)


class MessageInput(QPlainTextEdit):
    submitted = Signal()
    files_added = Signal(list)

    def canInsertFromMimeData(self, source):
        return source.hasImage() or any(url.isLocalFile() for url in source.urls()) or super().canInsertFromMimeData(source)

    def insertFromMimeData(self, source):
        # Pasted or dropped files and screenshots become attachments, not file paths in the text.
        files = [url.toLocalFile() for url in source.urls() if url.isLocalFile()]
        if files:
            self.files_added.emit(files)
        elif source.hasImage():
            image = QImage(source.imageData())
            folder = Path(tempfile.mkdtemp(prefix="companion-paste-"))
            path = folder / f"pasted-{time.strftime('%Y%m%d-%H%M%S')}.png"
            if not image.isNull() and image.save(str(path), "PNG"):
                self.files_added.emit([str(path)])
        else:
            super().insertFromMimeData(source)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.document().contentsChanged.connect(self._fit)
        self._fit()

    def _fit(self):
        # Grow with the draft from one line up to six, then scroll inside the box.
        lines = max(1, int(self.document().size().height()))
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded if lines > 6
                                        else Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        line = self.fontMetrics().lineSpacing()
        self.setFixedHeight(min(6, lines) * line + 2 * int(self.document().documentMargin()) + 10)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._fit()  # Wrapping changes with width.

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and not (
            event.modifiers() & Qt.KeyboardModifier.ShiftModifier
        ):
            self.submitted.emit()
            event.accept()
        else:
            super().keyPressEvent(event)


class CompanionWindow(QMainWindow):
    closed = Signal()
    suspended_changed = Signal(bool)
    activity_changed = Signal(str)

    def __init__(self, settings: Settings, speech=None, microphone=None, store=None, preferences=None, characters=None, models=None):
        super().__init__()
        settings = active_character_voice(settings)
        self.settings = settings
        self.activity = "ready"
        self._activity_error = False
        self._worker: ReplyWorker | None = None
        self._worker_kind = "reply"
        self._summary_dialog = None
        self._summary_text = ""
        self._summary_error = ""
        self._summary_through = 0
        self._messages: list[dict[str, str]] = []
        self._reply = ""
        self._closing = False
        self._quitting = False
        self.tray_enabled = False
        self.suspended = False
        self.preferences = preferences if preferences is not None else Preferences()
        self.characters = characters if characters is not None else CharacterLibrary(PROJECT_ROOT)
        self.avatar_models = models if models is not None else AvatarModels(PROJECT_ROOT)
        self._last_reply = ""
        self.speech = speech if speech is not None else SpeechController(self)
        if hasattr(self.speech, "set_hf_token"):
            self.speech.set_hf_token(settings.hf_token)
        self._reference_path = settings.tts_reference
        self.microphone = microphone if microphone is not None else MicrophoneController(self)
        self._mic_draft = ""
        self._handsfree_capture = False
        self._handsfree_timer = QTimer(self)
        self._handsfree_timer.setSingleShot(True)
        self._handsfree_timer.timeout.connect(self._arm_handsfree)
        self._pending_transcription = ""
        self._streaming_voice = False
        self._voice_for_reply = False
        self._spoken_phrases = []
        self._voice_note = ""
        self._voice_message = None
        # The entry point injects a disk store. Isolated previews/tests use RAM.
        self.store = store if store is not None else Store(":memory:")
        self._owns_store = store is None
        key = character_key(settings.character_path)
        self.store.claim_legacy_conversations(key)
        conversations = self.store.conversations(key)
        self._conversation_id = conversations[0]["id"] if conversations else self.store.create_conversation(key)
        self._active_turn = None
        self._reply_status = "pending"
        self._reply_notice = ""
        self._last_reply_id = None
        self._voice_message_id = None
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(500)
        self._save_timer.timeout.connect(self._save_active_turn)
        self._scroll_timer = QTimer(self)
        self._scroll_timer.setSingleShot(True)
        self._scroll_timer.timeout.connect(self._scroll_to_latest)
        self.setWindowTitle(f"{settings.name} · Desktop Companion")
        self.setWindowIcon(moon_icon())
        self.resize(780, 860)
        self.setMinimumSize(460, 560)
        self.setStyleSheet(STYLE)

        root = NightSky()
        self.setCentralWidget(root)
        centring = QHBoxLayout(root)
        centring.setContentsMargins(0, 0, 0, 0)
        column = QWidget()
        column.setObjectName("column")
        column.setMaximumWidth(900)  # Keep lines readable on a maximized window.
        centring.addStretch(1)
        centring.addWidget(column, 100)
        centring.addStretch(1)
        layout = QVBoxLayout(column)
        layout.setContentsMargins(22, 18, 22, 12)
        layout.setSpacing(12)

        heading = QHBoxLayout()
        heading.setSpacing(12)
        emblem = QLabel(ICONS["moon"])
        emblem.setObjectName("emblem")
        emblem.setFixedSize(44, 44)
        emblem.setAlignment(Qt.AlignmentFlag.AlignCenter)
        heading.addWidget(emblem)
        names = QVBoxLayout()
        names.setSpacing(0)
        title_row = QHBoxLayout()
        title_row.setSpacing(10)
        self.title = QLabel(settings.name)
        self.title.setObjectName("title")
        title_row.addWidget(self.title)
        self.seal = QLabel(SEALS.get(settings.name.lower(), ""))
        self.seal.setObjectName("seal")
        title_row.addWidget(self.seal)
        title_row.addStretch()
        names.addLayout(title_row)
        self.conversation_title = QLabel("New conversation")
        self.conversation_title.setObjectName("subtitle")
        self.conversation_title.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        names.addWidget(self.conversation_title)
        heading.addLayout(names, 1)
        pill = QFrame()
        pill.setObjectName("pill")
        self.status_pill = pill
        pill_row = QHBoxLayout(pill)
        pill_row.setContentsMargins(10, 4, 12, 4)
        pill_row.setSpacing(7)
        self.status_dot = QLabel("●")
        pill_row.addWidget(self.status_dot)
        self.status = QLabel("Ready")
        self.status.setObjectName("status")
        pill_row.addWidget(self.status)
        heading.addWidget(pill, 0, Qt.AlignmentFlag.AlignVCenter)
        self.speak_toggle = icon_button("speaker", "Speak replies aloud", checkable=True)
        self.new_chat = icon_button("new", "New conversation · the current one stays in History")
        self.more_button = icon_button("more", "History, memories and settings")
        for button in (self.speak_toggle, self.new_chat, self.more_button):
            heading.addWidget(button, 0, Qt.AlignmentFlag.AlignVCenter)
        layout.addLayout(heading)
        self.context_hint = Note(self)
        self.context_hint.hide()  # Its summary state is shown on the Context menu item.

        menu = QMenu(self)
        self.history_button = menu.addAction(glyph_icon("history"), "History")
        self.memory_button = menu.addAction(glyph_icon("memories"), "Memories")
        self.context_button = menu.addAction(glyph_icon("context"), "Context and summary")
        self.context_button.setToolTip("Inspect or summarize older exchanges in this conversation")
        menu.addSeparator()
        self.settings_button = menu.addAction(glyph_icon("settings"), "Settings")
        self.suspend_button = menu.addAction(glyph_icon("pause"), "Suspend")
        menu.addSeparator()
        menu.addAction("Quit", self.request_quit)
        menu.setToolTipsVisible(True)
        self.more_button.setMenu(menu)
        self.reload = QPushButton("Reload .env + character")
        self.reload.setToolTip("Reload connection and character; keep saved app preferences")
        self.settings_button.triggered.connect(self.open_settings)
        self.context_button.triggered.connect(self._open_summary)
        self.history_button.triggered.connect(self._open_history)
        self.memory_button.triggered.connect(self._open_memories)
        self.suspend_button.triggered.connect(self.toggle_suspended)
        self.new_chat.clicked.connect(self._new_conversation)
        self.reload.clicked.connect(self._reload_settings)

        self.settings_dialog = QDialog(self)
        self.settings_dialog.setWindowTitle("Settings")
        self.settings_dialog.setWindowIcon(moon_icon())
        self.settings_dialog.setMinimumWidth(520)
        self.settings_dialog.resize(600, 720)
        settings_outer = QVBoxLayout(self.settings_dialog)
        settings_outer.setContentsMargins(20, 16, 20, 18)
        settings_outer.setSpacing(12)
        self.settings_tabs = QTabWidget()
        self.settings_tabs.setDocumentMode(True)
        settings_outer.addWidget(self.settings_tabs, 1)

        def page(title):
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QFrame.Shape.NoFrame)
            body = QWidget()
            body_layout = QVBoxLayout(body)
            body_layout.setContentsMargins(4, 14, 12, 8)
            body_layout.setSpacing(12)
            scroll.setWidget(body)
            self.settings_tabs.addTab(scroll, title)
            return body_layout

        def section(target, text):
            label = QLabel(text.upper())
            label.setObjectName("section")
            target.addWidget(label)

        companion_page, voice_page, avatar_page, app_page = (page(title) for title in ("Companion", "Voice", "Avatar", "App"))
        settings_layout = companion_page
        section(settings_layout, "Response model")
        self.connection = ConnectionPanel(settings)
        settings_layout.addWidget(self.connection)
        self.connection.changed.connect(self._connection_changed)
        section(settings_layout, "Character")
        character_row = QHBoxLayout()
        self.character_label = QLabel()
        self.character_label.setWordWrap(True)
        self.character_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        character_row.addWidget(self.character_label, 1)
        settings_layout.addLayout(character_row)
        self.character_select = QComboBox()
        self.character_select.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.character_select.setMinimumContentsLength(12)
        self.character_select.activated.connect(self._select_character)
        settings_layout.addWidget(self.character_select)
        character_buttons = QHBoxLayout()
        self.add_character = QPushButton("Add character")
        self.add_character.clicked.connect(self._add_character)
        self.edit_character = QPushButton("Edit character")
        self.edit_character.clicked.connect(self._edit_character)
        self.open_character_file = QPushButton("Open profile file")
        self.open_character_file.clicked.connect(self._open_character_file)
        character_buttons.addWidget(self.add_character)
        character_buttons.addWidget(self.edit_character)
        character_buttons.addWidget(self.open_character_file)
        settings_layout.addLayout(character_buttons)
        self._refresh_character_label()
        self._refresh_characters()
        settings_layout.addStretch()
        settings_layout = voice_page
        section(settings_layout, "Voice")
        voice_row = QHBoxLayout()
        self.auto_speak = QCheckBox("Speak replies")
        self.auto_speak.setChecked(settings.tts_enabled)
        voice_row.addWidget(self.auto_speak)
        voice_row.addStretch()
        voice_row.addWidget(QLabel("Voice"))
        self.voice = QComboBox()
        self._set_voice_option(settings.tts_voice)
        self.voice.setEnabled(False)  # One active character voice, no stock catalog.
        voice_row.addWidget(self.voice)
        self.preview = QPushButton("Preview")
        self.preview.clicked.connect(self._preview_voice)
        voice_row.addWidget(self.preview)
        settings_layout.addLayout(voice_row)
        reference_row = QHBoxLayout()
        self.reference_label = QLabel()
        self.reference_label.setObjectName("hint")
        self.reference_label.setWordWrap(True)
        self.reference_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        reference_row.addWidget(self.reference_label, 1)
        self.choose_reference = QPushButton("Choose reference WAV")
        self.choose_reference.clicked.connect(self._choose_reference)
        reference_row.addWidget(self.choose_reference)
        self.clear_reference = QPushButton("Clear")
        self.clear_reference.clicked.connect(self._clear_reference)
        reference_row.addWidget(self.clear_reference)
        settings_layout.addLayout(reference_row)
        self._refresh_reference_label()
        delivery_row = QHBoxLayout()
        delivery_row.addWidget(QLabel("Delivery"))
        self.delivery_rate = QSlider(Qt.Orientation.Horizontal)
        self.delivery_rate.setRange(80, 115)
        self.delivery_rate.setValue(settings.tts_rate)
        self.delivery_rate.setMaximumWidth(130)
        self.delivery_rate.setToolTip("Below 100% is slower and lower-pitched; above 100% is faster and higher-pitched.")
        delivery_row.addWidget(self.delivery_rate)
        self.delivery_label = QLabel(f"{settings.tts_rate}%")
        self.delivery_label.setMinimumWidth(36)
        delivery_row.addWidget(self.delivery_label)
        delivery_row.addStretch()
        self.character_voice_button = QPushButton("Use character voice")
        self.character_voice_button.setEnabled(bool(settings.character_voice))
        self.character_voice_button.setToolTip(settings.character_voice_description)
        self.character_voice_button.clicked.connect(self._apply_character_voice)
        delivery_row.addWidget(self.character_voice_button)
        settings_layout.addLayout(delivery_row)
        audio_row = QHBoxLayout()
        audio_row.addWidget(QLabel("Volume"))
        self.volume = QSlider(Qt.Orientation.Horizontal)
        self.volume.setRange(0, 100)
        self.volume.setValue(settings.tts_volume)
        self.volume.setMaximumWidth(130)
        audio_row.addWidget(self.volume)
        self.volume_label = QLabel(f"{settings.tts_volume}%")
        self.volume_label.setMinimumWidth(36)
        audio_row.addWidget(self.volume_label)
        audio_row.addStretch()
        self.replay = QPushButton("Read last reply")
        self.replay.setEnabled(False)
        self.replay.clicked.connect(self._read_last_reply)
        audio_row.addWidget(self.replay)
        settings_layout.addLayout(audio_row)
        self.voice_status = Note(self)
        self.voice_status.hide()
        self.voice_status.setText("Voice loads on first use")
        self.speech.changed.connect(self._voice_changed)
        self.speech.failed.connect(self._voice_failed)
        self.speech.spoken.connect(self._phrase_spoken)
        self.auto_speak.toggled.connect(self._speech_toggled)
        self.voice.currentTextChanged.connect(self._voice_selected)
        self.volume.valueChanged.connect(self._volume_changed)
        self.delivery_rate.valueChanged.connect(self._delivery_changed)

        section(settings_layout, "Microphone")
        mic_row = QHBoxLayout()
        self.mic_device = QComboBox()
        self.mic_device.setMinimumWidth(100)
        self.mic_device.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.mic_device.addItem("Windows default microphone", None)
        if settings.stt_microphone:
            self.mic_device.addItem(settings.stt_microphone, settings.stt_microphone)
            self.mic_device.setCurrentIndex(1)
        mic_row.addWidget(self.mic_device, 1)
        self.refresh_mics = QPushButton("Refresh")
        self.refresh_mics.setToolTip("Find available microphones")
        self.refresh_mics.clicked.connect(self.microphone.refresh_devices)
        mic_row.addWidget(self.refresh_mics)
        settings_layout.addLayout(mic_row)
        self.stt_model = QComboBox()
        self.stt_model.addItems(("tiny.en", "base.en", "small.en"))
        self.stt_model.setCurrentText(settings.stt_model)
        model_row = QHBoxLayout()
        model_row.addWidget(QLabel("English transcription model"))
        model_row.addStretch()
        model_row.addWidget(self.stt_model)
        settings_layout.addLayout(model_row)
        self.auto_send = QCheckBox("Send transcription automatically")
        self.auto_send.setChecked(settings.stt_auto_send)
        settings_layout.addWidget(self.auto_send)
        pause_row = QHBoxLayout()
        pause_row.addWidget(QLabel("Hands-free: finish after a pause"))
        pause_row.addStretch()
        self.speech_pause = QComboBox()
        for label, milliseconds in (("0.8 seconds", 800), ("1.2 seconds", 1200), ("1.8 seconds", 1800)):
            self.speech_pause.addItem(label, milliseconds)
        if self.speech_pause.findData(settings.stt_pause_ms) < 0:
            self.speech_pause.addItem(f"{settings.stt_pause_ms / 1000:g} seconds", settings.stt_pause_ms)
        self.speech_pause.setCurrentIndex(self.speech_pause.findData(settings.stt_pause_ms))
        pause_row.addWidget(self.speech_pause)
        settings_layout.addLayout(pause_row)
        settings_layout.addStretch()
        settings_layout = app_page
        section(settings_layout, "Memory")
        self.use_memories = QCheckBox("Include relevant saved memories in online replies")
        self.use_memories.setChecked(settings.memory_enabled)
        self.use_memories.toggled.connect(self._memory_toggled)
        settings_layout.addWidget(self.use_memories)
        memory_hint = QLabel("Turning this off affects future requests. Existing conversation context still applies.")
        memory_hint.setObjectName("hint")
        memory_hint.setWordWrap(True)
        settings_layout.addWidget(memory_hint)
        section(settings_layout, "Window")
        self.close_to_tray = QCheckBox("Keep running in the system tray when I close the window")
        self.close_to_tray.setChecked(settings.close_to_tray)
        settings_layout.addWidget(self.close_to_tray)
        section(settings_layout, "Configuration")
        reload_row = QHBoxLayout()
        reload_hint = QLabel("Re-read .env and the character profile after editing them by hand.")
        reload_hint.setObjectName("hint")
        reload_hint.setWordWrap(True)
        reload_row.addWidget(reload_hint, 1)
        reload_row.addWidget(self.reload)
        settings_layout.addLayout(reload_row)
        settings_layout.addStretch()
        settings_layout = avatar_page
        section(settings_layout, "Desktop avatar")
        avatar_row = QHBoxLayout()
        self.show_avatar = QCheckBox("Show desktop avatar")
        self.show_avatar.setChecked(settings.avatar_enabled)
        avatar_row.addWidget(self.show_avatar)
        avatar_row.addStretch()
        self.reset_avatar = QPushButton("Reset position")
        avatar_row.addWidget(self.reset_avatar)
        settings_layout.addLayout(avatar_row)
        model_row = QHBoxLayout()
        self.avatar_model_label = QLabel('Visual model')
        self.avatar_model = QComboBox()
        self.avatar_model.setAccessibleName('Character visual model')
        self.avatar_model_label.setBuddy(self.avatar_model)
        model_row.addWidget(self.avatar_model_label)
        model_row.addWidget(self.avatar_model, 1)
        self.add_avatar_model = QPushButton('Add Live2D model')
        self.add_avatar_model.setToolTip('Import a local model ZIP or .model3.json for this character.')
        model_row.addWidget(self.add_avatar_model)
        settings_layout.addLayout(model_row)
        self.avatar_model_status = QLabel()
        self.avatar_model_status.setTextFormat(Qt.TextFormat.PlainText)
        self.avatar_model_status.setObjectName('hint')
        self.avatar_model_status.setWordWrap(True)
        settings_layout.addWidget(self.avatar_model_status)
        framing_row = QHBoxLayout()
        framing_row.addWidget(QLabel('Model framing'))
        self.avatar_framing = QComboBox()
        self.avatar_framing.addItem('Portrait', 'portrait')
        self.avatar_framing.addItem('Full model', 'full')
        framing_row.addWidget(self.avatar_framing, 1)
        self.avatar_blindfold = QCheckBox('Blindfold')
        framing_row.addWidget(self.avatar_blindfold)
        settings_layout.addLayout(framing_row)
        self._refresh_avatar_models()
        self.avatar_model.currentIndexChanged.connect(self._select_avatar_model)
        self.avatar_framing.currentIndexChanged.connect(self._set_avatar_framing)
        self.avatar_blindfold.toggled.connect(self._set_avatar_blindfold)
        self.add_avatar_model.clicked.connect(self._import_avatar_model)
        self.animate_avatar = QCheckBox("Animate avatar")
        self.animate_avatar.setChecked(settings.avatar_animated)
        settings_layout.addWidget(self.animate_avatar)
        self.avatar_hd = QCheckBox('HD rendering')
        self.avatar_hd.setChecked(settings.avatar_hd)
        self.avatar_hd.setToolTip('Sharper portrait rendering. Turn off to reduce graphics load.')
        settings_layout.addWidget(self.avatar_hd)
        self.avatar_cursor_attention = QCheckBox('Occasionally look toward my cursor')
        self.avatar_cursor_attention.setChecked(settings.avatar_cursor_attention)
        self.avatar_cursor_attention.setToolTip(
            'Brief desktop cursor glances with pauses between them. Cursor positions stay on this computer. '
            'Save defaults to keep this setting.')
        settings_layout.addWidget(self.avatar_cursor_attention)
        preset_row = QHBoxLayout()
        preset_label = QLabel('Motion preset')
        self.avatar_preset = QComboBox()
        self.avatar_preset.setAccessibleName('Motion preset')
        preset_label.setBuddy(self.avatar_preset)
        self.avatar_preset.addItems([*AVATAR_MOTION_PRESETS, 'Custom'])
        self.avatar_preset.setToolTip(
            'Calm reduces movement and gaze. Natural uses the original movement settings. '
            'Lively adds hair follow-through within the same head-turn limits. '
            'Adjust the sliders for Custom; Save defaults keeps the values.')
        preset_row.addWidget(preset_label)
        preset_row.addWidget(self.avatar_preset, 1)
        settings_layout.addLayout(preset_row)
        for field, label, lower, upper, value, unit in (
            ('avatar_size', 'Avatar size', 220, 640, settings.avatar_width, 'px'),
            ('avatar_motion', 'Movement intensity', 0, 100, settings.avatar_motion, '%'),
            ('avatar_lip_sensitivity', 'Lip-sync sensitivity', 25, 200, settings.avatar_lip_sensitivity, '%'),
            ('avatar_gaze', 'Gaze intensity', 0, 100, settings.avatar_gaze, '%'),
            ('avatar_hair', 'Hair response', 20, 80, settings.avatar_hair, '%'),
        ):
            row = QHBoxLayout()
            name = QLabel(label)
            name.setMinimumWidth(160)
            row.addWidget(name)
            slider = QSlider(Qt.Orientation.Horizontal)
            slider.setRange(lower, upper)
            slider.setValue(value)
            slider.setAccessibleName(label)
            slider.setToolTip('Controls the mesh portrait. Save defaults to keep this setting.')
            if field == 'avatar_gaze':
                slider.setToolTip('Eye movement strength during idle and cursor glances. '
                                  '0% keeps the gaze centered. Save defaults to keep this setting.')
            elif field == 'avatar_hair':
                slider.setToolTip('Lower values keep hair firmer; higher values allow more follow-through. '
                                  'Save defaults to keep this setting.')
            amount = QLabel(f'{value}{unit}')
            amount.setMinimumWidth(55)
            slider.valueChanged.connect(lambda value, amount=amount, unit=unit: amount.setText(f'{value}{unit}'))
            row.addWidget(slider, 1)
            row.addWidget(amount)
            setattr(self, field, slider)
            setattr(self, field + '_label', amount)
            settings_layout.addLayout(row)
        # Set the initial label before connecting the combo: loading saved or
        # custom slider values must never apply a named preset over them.
        self._sync_avatar_preset()
        self.avatar_preset.currentTextChanged.connect(self._apply_avatar_preset)
        for slider in (self.avatar_motion, self.avatar_gaze, self.avatar_hair):
            slider.valueChanged.connect(self._sync_avatar_preset)
        self.preview_avatar_motion = QPushButton('Preview movement')
        self.preview_avatar_motion.setEnabled(False)
        self.preview_avatar_motion.setToolTip(
            'A short silent movement preview. It does not record audio or start a conversation.')
        settings_layout.addWidget(self.preview_avatar_motion)
        self.avatar_preview_status = QLabel('Show and animate a mesh avatar to preview its movement.')
        self.avatar_preview_status.setObjectName('hint')
        self.avatar_preview_status.setWordWrap(True)
        settings_layout.addWidget(self.avatar_preview_status)
        settings_layout.addStretch()
        self.preference_status = QLabel("Changes apply now. Your model and character are remembered automatically; "
                                        "Save defaults keeps everything else after restarting.")
        self.preference_status.setObjectName("hint")
        self.preference_status.setWordWrap(True)
        settings_outer.addWidget(self.preference_status)
        settings_actions = QHBoxLayout()
        settings_actions.addStretch()
        self.save_defaults = QPushButton("Save defaults")
        self.save_defaults.clicked.connect(self._save_preferences)
        settings_actions.addWidget(self.save_defaults)
        done = QPushButton("Done")
        done.setObjectName("primary")
        done.clicked.connect(self.settings_dialog.hide)
        settings_actions.addWidget(done)
        settings_outer.addLayout(settings_actions)

        self.transcript = ChatView()
        self.transcript.suggestion.connect(self._use_suggestion)
        layout.addWidget(self.transcript, 1)

        self.composer = QFrame()
        self.composer.setObjectName("composer")
        composer_layout = QVBoxLayout(self.composer)
        composer_layout.setContentsMargins(16, 12, 10, 10)
        composer_layout.setSpacing(6)
        self._pending_files: list[str] = []
        self.attachment_tray = QWidget()
        self.attachment_row = QHBoxLayout(self.attachment_tray)
        self.attachment_row.setContentsMargins(0, 0, 0, 4)
        self.attachment_row.setSpacing(8)
        self.attachment_row.addStretch()
        self.attachment_tray.hide()
        composer_layout.addWidget(self.attachment_tray)
        self.input = MessageInput()
        self.input.setObjectName("input")
        self.input.setPlaceholderText(f"Message {settings.name}…")
        self.input.submitted.connect(self._send)
        self.input.files_added.connect(self._add_attachments)
        self.input.installEventFilter(self)
        composer_layout.addWidget(self.input)
        tools = QHBoxLayout()
        tools.setSpacing(4)
        self.attach_button = icon_button("attach", "Attach images or files · you can also paste or drag them in")
        self.attach_button.clicked.connect(self._choose_attachments)
        tools.addWidget(self.attach_button)
        self.record_button = icon_button("mic", "Hold to talk · or press Ctrl+Alt+Space · up to 60 seconds")
        self.record_button.pressed.connect(self._begin_recording)
        self.record_button.released.connect(self._finish_recording)
        tools.addWidget(self.record_button)
        self.hands_free = icon_button(
            "handsfree", "Hands-free: listen for a turn, pause during replies, then listen again", checkable=True)
        self.hands_free.toggled.connect(self._handsfree_toggled)
        tools.addWidget(self.hands_free)
        self.mic_level = QProgressBar()
        self.mic_level.setRange(0, 100)
        self.mic_level.setValue(0)
        self.mic_level.setTextVisible(False)
        self.mic_level.setFixedWidth(90)
        self.mic_level.hide()
        tools.addSpacing(6)
        tools.addWidget(self.mic_level, 0, Qt.AlignmentFlag.AlignVCenter)
        tools.addStretch()
        self.stop_button = icon_button("stop", "Stop the reply, voice or recording")
        repolish(self.stop_button, danger=True)
        self.stop_button.setEnabled(False)
        self.stop_button.hide()
        self.stop_button.clicked.connect(self._stop)
        tools.addWidget(self.stop_button)
        self.send_button = icon_button("send", "Send · Enter (Shift+Enter for a new line)", name="send")
        self.send_button.clicked.connect(self._send)
        tools.addWidget(self.send_button)
        composer_layout.addLayout(tools)
        layout.addWidget(self.composer)
        self.setAcceptDrops(True)
        self.drop_hint = QWidget(self.centralWidget())
        self.drop_hint.setObjectName("dropHint")
        self.drop_hint.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        self.drop_hint.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        drop_layout = QVBoxLayout(self.drop_hint)
        drop_text = QLabel(f"Drop images or files to share with {settings.name}")
        drop_text.setObjectName("dropText")
        drop_layout.addWidget(drop_text, 0, Qt.AlignmentFlag.AlignCenter)
        self.drop_hint.hide()

        self.footer = QLabel()
        self.footer.setObjectName("footer")
        self.footer.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        layout.addWidget(self.footer)
        self._fresh_note, self._fresh_until = "", 0.0
        self._footer_timer = QTimer(self)
        self._footer_timer.setSingleShot(True)
        self._footer_timer.timeout.connect(self._refresh_footer)
        self.mic_hint = Note(self)
        self.mic_hint.hide()
        self.mic_status = Note(self)
        self.mic_status.hide()
        self.privacy = Note(self)
        self.privacy.hide()
        for note in (self.mic_hint, self.mic_status, self.privacy, self.voice_status):
            note.updated.connect(self._note_updated)
        self.mic_hint.setText("Enter to send · Hold the mic or press Ctrl+Alt+Space to talk")
        self._manual_mic_hint = self.mic_hint.text()
        self.mic_status.setText("Microphone off")
        self.privacy.setText(self._privacy_text())
        self.microphone.changed.connect(self._mic_changed)
        self.microphone.transcribed.connect(self._on_transcribed)
        self.microphone.failed.connect(self._mic_failed)
        self.microphone.devices.connect(self._mic_devices)
        self.microphone.level.connect(self.mic_level.setValue)

        self.speak_toggle.setChecked(settings.tts_enabled)
        self._speak_glyph(settings.tts_enabled)
        self.speak_toggle.toggled.connect(self.auto_speak.setChecked)
        self.auto_speak.toggled.connect(self.speak_toggle.setChecked)
        self.auto_speak.toggled.connect(self._speak_glyph)
        self._restore_conversation(self._conversation_id)
        self.avatar = AvatarController(self)
        self.input.setFocus()

    def eventFilter(self, watched, event):
        if watched is self.input and event.type() in (QEvent.Type.FocusIn, QEvent.Type.FocusOut):
            repolish(self.composer, focused=event.type() == QEvent.Type.FocusIn)
        return super().eventFilter(watched, event)

    def _speak_glyph(self, enabled):
        self.speak_toggle.setText(ICONS["speaker" if enabled else "muted"])
        self.speak_toggle.setToolTip("Speaking replies aloud · click to mute" if enabled else "Replies are muted · click to speak them")

    @Slot(str)
    def _use_suggestion(self, text):
        if self._worker or self.microphone.busy or self.suspended:
            return
        self.input.setPlainText(text)
        self._send()

    @Slot()
    def _choose_attachments(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "Share images or files", str(Path.home()), attachments.FILE_FILTER)
        self._add_attachments(paths)

    @Slot(list)
    def _add_attachments(self, paths):
        problems = []
        for path in paths:
            path = str(Path(path))
            if path in self._pending_files:
                continue
            if len(self._pending_files) >= attachments.MAX_FILES:
                problems.append(f"Attach up to {attachments.MAX_FILES} files per message.")
                break
            try:
                attachments.classify(path)
            except (OSError, attachments.AttachmentError) as exc:
                problems.append(str(exc))
                continue
            self._pending_files.append(path)
        self._render_attachments()
        if problems:
            self._flash(" ".join(problems))
        self.input.setFocus()

    @Slot(str)
    def _remove_attachment(self, path):
        if path in self._pending_files:
            self._pending_files.remove(path)
        self._render_attachments()

    def _render_attachments(self):
        while self.attachment_row.count() > 1:
            widget = self.attachment_row.takeAt(0).widget()
            if widget is not None:
                widget.hide()
                widget.deleteLater()
        for path in self._pending_files:
            kind = "file"
            try:
                kind, _ = attachments.classify(path)
            except (OSError, attachments.AttachmentError):
                pass
            card = AttachmentCard({"name": Path(path).name, "kind": kind, "path": path}, thumbnail=40, removable=True)
            card.removed.connect(self._remove_attachment)
            self.attachment_row.insertWidget(self.attachment_row.count() - 1, card)
        self.attachment_tray.setVisible(bool(self._pending_files))

    def _flash(self, text):
        self._fresh_note, self._fresh_until = text, time.monotonic() + 8
        self._footer_timer.start(8000)
        self._refresh_footer()

    def _dropped_files(self, event):
        return [url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()]

    def dragEnterEvent(self, event):
        if self._dropped_files(event) and not self.suspended:
            event.acceptProposedAction()
            self.drop_hint.setGeometry(self.centralWidget().rect().adjusted(14, 14, -14, -14))
            self.drop_hint.raise_()
            self.drop_hint.show()

    def dragLeaveEvent(self, event):
        self.drop_hint.hide()

    def dropEvent(self, event):
        self.drop_hint.hide()
        files = self._dropped_files(event)
        if files:
            event.acceptProposedAction()
            self._add_attachments(files)

    @Slot(str)
    def _note_updated(self, text):
        if text not in IDLE_NOTES and text != self._privacy_text() and self.sender() is not self.mic_hint:
            self._fresh_note, self._fresh_until = text, time.monotonic() + 8
            self._footer_timer.start(8000)
        self._refresh_footer()

    def _refresh_footer(self):
        if not hasattr(self, "footer"):
            return
        if self.microphone.busy or self.hands_free.isChecked():
            text = self.mic_status.text()
        elif self._fresh_note and time.monotonic() < self._fresh_until:
            text = self._fresh_note
        elif self.speech.busy and self.voice_status.text() not in IDLE_NOTES:
            text = self.voice_status.text()
        else:
            text = self.mic_hint.text()
        self.footer.setText(text)
        self.footer.setToolTip(self.privacy.text())

    def _welcome(self) -> None:
        self.transcript.show_welcome(self.settings.name)
        if self.settings.missing_key():
            self.status.setText("Add API key")
            self.transcript.add_note("Setup: add your OpenRouter key to .env, then open Settings and reload .env.", "warning")
        else:
            self.status.setText("Ready")

    def _connection_changed(self):
        if self._closing: return
        self._end_handsfree()
        self._interrupt_speech()
        self.settings = replace(self.settings, **self.connection.values())
        self.status.setText('Add API key' if self.settings.missing_key() else 'Ready')
        try:
            # The response model is remembered immediately; other settings still wait for Save defaults.
            self.preferences.remember(self.settings, ('llm_provider', 'openrouter_model', 'codex_model', 'claude_model'))
        except (OSError, ValueError):
            pass  # E.g. a half-typed OpenRouter ID; the choice still applies to this session.

    @Slot()
    def _send(self) -> None:
        text = self.input.toPlainText().strip()
        files = list(self._pending_files)
        if self._closing or self.suspended or self._worker or self.microphone.busy or not (text or files):
            return
        if not files and self._local_command(text):
            return
        try:
            self.settings.validate_connection()
        except ValueError as exc:
            self._activity_error = True
            self._refresh_activity()
            QMessageBox.information(self, "Connection settings", str(exc))
            return
        if len(text) > 16000:
            QMessageBox.information(self, "Message too long", "Please keep a message under 16,000 characters.")
            return
        self._activity_error = False
        self._interrupt_speech()
        if self._active_turn and not self._save_active_turn():
            return
        try:
            stored = attachments.store(files) if files else []
        except (OSError, attachments.AttachmentError) as exc:
            self._flash(f"Could not attach: {exc}" if isinstance(exc, attachments.AttachmentError)
                        else "An attachment could not be copied. Check the file and try again.")
            return
        try:
            turns = self.store.context_turns(self._conversation_id)
            summary = self.store.summary(self._conversation_id)
            recent_topics = "\n".join(message["content"] for message in self._messages[-4:] if message["role"] == "user")
            memories = self.store.relevant_memories(recent_topics[-4000:] + "\n" + text) if self.use_memories.isChecked() else []
            turn = self.store.start_turn(self._conversation_id, text, stored)
        except sqlite3.Error:
            attachments.remove_files(stored)
            self.privacy.setText("Could not save this message. No request was sent. Please try again.")
            return
        self._pending_files.clear()
        self._render_attachments()
        self._active_turn = turn
        self._reply_status, self._reply_notice = "pending", ""
        self._spoken_phrases = []
        self._voice_note = ""
        self._voice_message = None
        self._voice_message_id = None
        self._pending_transcription = ""
        self._messages.append({"role": "user", "content": "\n".join(part for part in (text, attachments.note(stored)) if part)})
        # Only this turn carries the files themselves; history keeps a short note about them.
        context = [*recent_messages(turns), {"role": "user", "content": text, "attachments": stored}]
        self.input.clear()
        self._reply = ""
        self.transcript.add_message("user", "You", text, attachments=stored)
        self.transcript.begin_reply(self.settings.name)
        prompt = reply_prompt(self.settings.system_prompt, memories, summary["content"] if summary else None)
        self._worker_kind = "reply"
        worker = ReplyWorker(replace(self.settings, system_prompt=prompt), context, self)
        self._worker = worker
        worker.chunk.connect(self._on_chunk)
        worker.finished.connect(self._on_finished)
        self._set_busy(True)
        self._streaming_voice = self.auto_speak.isChecked() and self.volume.value() > 0
        self._voice_for_reply = self._streaming_voice
        if self._streaming_voice:
            self.speech.begin_reply(self._speech_voice(), self.volume.value(), self.delivery_rate.value())
        self._update_conversation_title()
        worker.start()

    def _set_busy(self, busy: bool) -> None:
        self._refresh_controls()
        self.status.setText("Thinking…" if busy else "Ready")
        if self.microphone.busy:
            self.status.setText("Listening…" if self.microphone.state in {"opening", "listening", "recording"} else "Transcribing…")
        if self.suspended:
            self.status.setText("Suspended")

    def _refresh_controls(self) -> None:
        busy = self._worker is not None or self.microphone.busy or self.suspended
        self.send_button.setEnabled(not busy)
        self.input.setEnabled(not self.microphone.busy)
        self.attach_button.setEnabled(not self.suspended and not self.microphone.busy)
        self._refresh_stop_button()
        self.new_chat.setEnabled(not busy)
        self.reload.setEnabled(not busy)
        self.history_button.setEnabled(not busy)
        self.memory_button.setEnabled(not busy)
        self.context_button.setEnabled(not busy)
        self.preview.setEnabled(not busy and not self.speech.busy)
        self.character_voice_button.setEnabled(bool(self.settings.character_voice) and not busy)
        self.character_select.setEnabled(not busy)
        self.connection.setEnabled(not busy)
        self.add_character.setEnabled(not busy)
        self.edit_character.setEnabled(not busy and Path(self.settings.character_path).suffix.lower() == ".toml")
        self.choose_reference.setEnabled(not busy)
        self.clear_reference.setEnabled(bool(self._reference_path) and not busy)
        self.replay.setEnabled(not busy and bool(self._last_reply) and not self.speech.busy)
        self.mic_device.setEnabled(not busy)
        self.refresh_mics.setEnabled(not busy)
        self.stt_model.setEnabled(not busy)
        self.speech_pause.setEnabled(not busy)
        self.hands_free.setEnabled(not self._closing and not self.suspended and (self.hands_free.isChecked() or not self.microphone.busy))
        self.record_button.setEnabled(not self.suspended and self.microphone.state not in {"loading", "transcribing"})
        self._refresh_activity()

    def _refresh_stop_button(self) -> None:
        preview_active = bool(getattr(getattr(getattr(self, 'avatar', None), 'widget', None),
                                      '_preview_active', False))
        self.stop_button.setEnabled(self._worker is not None or self.microphone.busy or self.speech.busy
                                    or self.hands_free.isChecked() or preview_active)
        self.stop_button.setVisible(self.stop_button.isEnabled())

    def _refresh_activity(self) -> None:
        state = activity_state(
            closing=self._closing, suspended=self.suspended, microphone=self.microphone.state,
            speech=getattr(self.speech, "state", "idle"), speech_busy=self.speech.busy,
            working=self._worker is not None, summary=self._worker_kind == "summary",
            has_reply=bool(self._reply), error=self._activity_error,
        )
        if state != self.activity:
            self.activity = state
            self.activity_changed.emit(state)
        self.status_dot.setStyleSheet(f"color: {ACTIVITY_COLORS.get(state, ACTIVITY_COLORS['ready'])}; font-size: 9px;")
        self.status_pill.setToolTip(self._model_label())
        self._refresh_footer()

    def _model_label(self) -> str:
        provider = self.settings.llm_provider
        if provider == "claude":
            from .claude_backend import CLAUDE_MODELS, DEFAULT_CLAUDE_MODEL
            model = self.settings.claude_model or DEFAULT_CLAUDE_MODEL
            return "Replying with " + dict((key, name) for name, key in CLAUDE_MODELS).get(model, model)
        if provider == "codex":
            return "Replying with ChatGPT via Codex" + (f" · {self.settings.codex_model}" if self.settings.codex_model else "")
        return "Replying with OpenRouter · " + self.settings.model

    @Slot(str, str)
    def _on_chunk(self, turn_id: str, text: str) -> None:
        worker = self._worker
        if not worker or worker.turn_id != turn_id or worker.stop_requested.is_set():
            return
        if self._worker_kind == "summary":
            if len(self._summary_text) + len(text) > MAX_SUMMARY_CHARS:
                self._summary_error = "The draft exceeded 6,000 characters. Your notes were kept; try again."
                worker.stop()
            else:
                self._summary_text += text
            return
        self.status.setText("Replying…")
        self._reply += text
        self._refresh_activity()
        self.transcript.append_reply(text)
        if not self._save_timer.isActive():
            self._save_timer.start()
        if self._streaming_voice:
            self.speech.feed_reply(text)

    @Slot()
    def _on_finished(self) -> None:
        worker = self._worker
        if worker is None:
            return
        if self._worker_kind == "summary":
            self._finish_summary(worker)
            return
        interrupted = worker.stop_requested.is_set() or bool(worker.error)
        if interrupted:
            self._interrupt_speech()
        elif self._streaming_voice:
            self.speech.finish_reply()
        self._streaming_voice = False
        self._reply_status = "error" if worker.error else "interrupted" if interrupted else "complete"
        self._reply_notice = worker.error or ("Reply stopped" if interrupted else "")
        if self._reply:
            self._last_reply_id = self._active_turn[1] if self._active_turn else None
            self._last_reply = self._reply
            content = self._reply
            if interrupted:
                content += "\n[This reply was interrupted; only the text above was shown.]"
            if self._voice_note:
                content += "\n" + self._voice_note
            message = {"role": "assistant", "content": content}
            self._voice_message = message
            self._voice_message_id = self._last_reply_id
            self._messages.append(message)
            self._messages = self._messages[-24:]
        else:
            self._messages.pop()  # Do not carry an unanswered failed turn into the next request.
        self._save_timer.stop()
        self._save_active_turn()
        self.transcript.end_reply(notice="Reply stopped" if interrupted and not worker.error else "",
                                  error=worker.error)
        self._worker = None
        worker.deleteLater()
        if worker.error:
            self._activity_error = True
            self._end_handsfree()
        self._set_busy(False)
        self._refresh_continuity()
        if self._closing:
            QTimer.singleShot(0, self.close)
        else:
            if self._pending_transcription:
                QTimer.singleShot(0, self._send_pending_transcription)
            self.input.setFocus()
            self._schedule_handsfree()

    @Slot()
    def _stop(self) -> None:
        self._activity_error = False
        self._end_handsfree()
        self._pending_transcription = ""
        if self.microphone.busy:
            self.microphone.cancel()
            self.mic_status.setText("Recording or transcription cancelled")
        self._interrupt_speech()
        if self._worker:
            self._worker.stop()
            self.stop_button.setEnabled(False)
            self.status.setText("Stopping…")
        self._refresh_activity()

    @Slot()
    def _new_conversation(self) -> None:
        self._end_handsfree()
        if self._worker or self.microphone.busy:
            return
        self._interrupt_speech()
        if self._active_turn and not self._save_active_turn():
            return
        try:
            conversation_id = self.store.create_conversation(character_key(self.settings.character_path))
        except sqlite3.Error:
            self.privacy.setText("Could not create a conversation. Please try again.")
            return
        self._restore_conversation(conversation_id)

    def _reset_conversation_view(self) -> None:
        self._activity_error = False
        self.speech.stop()
        self._streaming_voice = False
        self._voice_for_reply = False
        self._voice_message = None
        self._voice_message_id = None
        self._spoken_phrases = []
        self._voice_note = ""
        self._last_reply = ""
        self._last_reply_id = None
        self._pending_transcription = ""
        self.replay.setEnabled(False)
        self._messages.clear()
        self.transcript.clear()
        self._welcome()
        self.input.setFocus()

    @Slot()
    def _reload_settings(self) -> None:
        self._end_handsfree()
        if self._worker or self.microphone.busy:
            return
        try:
            settings = self.preferences.load(load_settings())
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "Could not reload settings", str(exc))
            return
        conversation = self._conversation_id
        if character_key(settings.character_path) != character_key(self.settings.character_path):
            try:
                key = character_key(settings.character_path)
                if not self.settings.character_path:
                    self.store.claim_legacy_conversations(key)
                conversations = self.store.conversations(key)
                conversation = conversations[0]["id"] if conversations else self.store.create_conversation(key)
            except sqlite3.Error:
                self.preference_status.setText("Could not load this character's conversations. Please try again.")
                return
        self._apply_settings(settings, retry_voice=True)
        if conversation != self._conversation_id:
            self._restore_conversation(conversation)
        self.transcript.add_note("Settings reloaded.")
        self.preference_status.setText("Reloaded .env and the character profile, with saved app preferences.")

    def _apply_settings(self, settings, *, retry_voice=False):
        settings = active_character_voice(settings)
        self.settings = settings
        self.connection.apply(settings)
        self._refresh_character_label()
        self._refresh_characters()
        self._refresh_avatar_models()
        self._interrupt_speech()
        if hasattr(self.speech, "set_hf_token"):
            self.speech.set_hf_token(settings.hf_token)
        if retry_voice and settings.tts_voice == "reference":
            self.speech.shutdown()  # Retry gated weights after CLI login/access changes.
        self._reference_path = settings.tts_reference
        self.auto_speak.setChecked(settings.tts_enabled)
        self._set_voice_option(settings.tts_voice)
        self._refresh_reference_label()
        self.delivery_rate.setValue(settings.tts_rate)
        self.character_voice_button.setToolTip(settings.character_voice_description)
        self.volume.setValue(settings.tts_volume)
        self.auto_send.setChecked(settings.stt_auto_send)
        self.stt_model.setCurrentText(settings.stt_model)
        if self.speech_pause.findData(settings.stt_pause_ms) < 0:
            self.speech_pause.addItem(f"{settings.stt_pause_ms / 1000:g} seconds", settings.stt_pause_ms)
        self.speech_pause.setCurrentIndex(self.speech_pause.findData(settings.stt_pause_ms))
        self.use_memories.setChecked(settings.memory_enabled)
        self.close_to_tray.setChecked(settings.close_to_tray)
        self.show_avatar.setChecked(settings.avatar_enabled)
        self.animate_avatar.setChecked(settings.avatar_animated)
        self.avatar_hd.setChecked(settings.avatar_hd)
        self.avatar_size.setValue(settings.avatar_width)
        self.avatar_motion.setValue(settings.avatar_motion)
        self.avatar_lip_sensitivity.setValue(settings.avatar_lip_sensitivity)
        self.avatar_cursor_attention.setChecked(settings.avatar_cursor_attention)
        self.avatar_gaze.setValue(settings.avatar_gaze)
        self.avatar_hair.setValue(settings.avatar_hair)
        self.mic_device.clear()
        self.mic_device.addItem("Windows default microphone", None)
        if settings.stt_microphone:
            self.mic_device.addItem(settings.stt_microphone, settings.stt_microphone)
            self.mic_device.setCurrentIndex(1)
        self.title.setText(settings.name)
        self.seal.setText(SEALS.get(settings.name.lower(), ""))
        self.input.setPlaceholderText(f"Message {settings.name}…")
        self.setWindowTitle(f"{settings.name} · Desktop Companion")
        self.status.setText("Add API key" if settings.missing_key() else "Ready")
        self._activity_error = False
        self._refresh_controls()
        self._refresh_activity()
        self.avatar.refresh()

    def _refresh_character_label(self) -> None:
        path = self.settings.character_path
        self.character_label.setText("Character: " + self.settings.name + (" · " + Path(path).name if path else ""))
        self.character_label.setToolTip(path)
        self.edit_character.setEnabled(Path(path).suffix.lower() == ".toml")
        self.open_character_file.setEnabled(bool(path))

    def _refresh_avatar_models(self):
        with QSignalBlocker(self.avatar_model), QSignalBlocker(self.avatar_framing), QSignalBlocker(self.avatar_blindfold):
            self.avatar_model.clear()
            try:
                profile = self.settings.character_path
                selected = self.avatar_models.selected(profile)
                for model in self.avatar_models.models(profile):
                    self.avatar_model.addItem(model['name'], model['id'])
                self.avatar_model.setCurrentIndex(self.avatar_model.findData(selected['id']))
                self.avatar_framing.setCurrentIndex(self.avatar_framing.findData(selected.get('framing', 'portrait')))
                live2d = selected['kind'] == 'live2d'
                self.avatar_framing.setEnabled(live2d)
                self.avatar_blindfold.setVisible(bool(selected.get('blindfold_parameter')))
                self.avatar_blindfold.setChecked(bool(selected.get('blindfold', False)))
                self.avatar_model_status.setText(
                    ('Experimental Live2D rig. ' + selected.get('credit', '') if live2d else
                     selected.get('credit', 'Current AI portrait. Choose another visual model to experiment.'))
                    + ' Model selection is saved for this character; voice and conversations stay the same.')
            except (OSError, ValueError) as exc:
                self.avatar_model.addItem('Current avatar', 'current')
                self.avatar_framing.setEnabled(False)
                self.avatar_blindfold.hide()
                self.avatar_model_status.setText(str(exc))
        self.avatar_model_label.setText(self.settings.name + ' visual model')
        self.add_avatar_model.setEnabled(bool(self.settings.character_path))

    @Slot()
    def _select_avatar_model(self):
        model_id = self.avatar_model.currentData()
        if not model_id:
            return
        try:
            self.avatar_models.select(self.settings.character_path, model_id)
            self.avatar.reload_avatar()
            self._refresh_avatar_models()
        except (OSError, ValueError) as exc:
            self._refresh_avatar_models()
            self.avatar_model_status.setText(str(exc))

    @Slot()
    def _set_avatar_framing(self):
        if not self.avatar_framing.isEnabled():
            return
        try:
            self.avatar_models.set_framing(self.settings.character_path, self.avatar_model.currentData(),
                                           self.avatar_framing.currentData())
            if self.avatar.widget is not None and hasattr(self.avatar.widget, 'set_framing'):
                self.avatar.widget.set_framing(self.avatar_framing.currentData())
        except (OSError, ValueError) as exc:
            self.avatar_model_status.setText(str(exc))

    @Slot(bool)
    def _set_avatar_blindfold(self, enabled):
        try:
            model = self.avatar_models.set_blindfold(self.settings.character_path, self.avatar_model.currentData(), enabled)
            if self.avatar.widget is not None and hasattr(self.avatar.widget, 'set_appearance'):
                self.avatar.widget.set_appearance(model.get('appearance', {}))
        except (OSError, ValueError) as exc:
            self.avatar_model_status.setText(str(exc))

    @Slot()
    def _import_avatar_model(self):
        source, _ = QFileDialog.getOpenFileName(self, 'Add a Live2D model for ' + self.settings.name,
            str(PROJECT_ROOT / 'ext_sources') if (PROJECT_ROOT / 'ext_sources').is_dir() else '',
            'Live2D models (*.zip *.model3.json)')
        if not source:
            return
        try:
            model = self.avatar_models.import_live2d(self.settings.character_path, source,
                                                    'Live2D - ' + Path(source).stem[:100])
            self.avatar_models.select(self.settings.character_path, model['id'])
            self.avatar.reload_avatar()
            self._refresh_avatar_models()
        except (OSError, ValueError) as exc:
            self.avatar_model_status.setText(str(exc))

    def _refresh_characters(self):
        self.character_select.clear()
        for path, name, error in self.characters.profiles(self.settings.character_path, self.preferences.character_paths()):
            label = name
            if self.character_select.findText(label) >= 0:
                label += " · " + Path(path).parent.name[:12]
            self.character_select.addItem(label, path)
            self.character_select.setItemData(self.character_select.count() - 1, error or path, Qt.ItemDataRole.ToolTipRole)
        current = str(Path(self.settings.character_path).resolve()) if self.settings.character_path else ""
        index = self.character_select.findData(current)
        if index < 0:
            self.character_select.addItem(self.settings.name, current)
            index = self.character_select.count() - 1
        self.character_select.setCurrentIndex(index)

    @Slot(int)
    def _select_character(self, index):
        path = self.character_select.itemData(index)
        if path and character_key(path) != character_key(self.settings.character_path):
            self._activate_character(path)

    def _activate_character(self, path, *, use_profile_voice=False):
        self._end_handsfree()
        if self._closing or self._worker or self.microphone.busy or self.suspended:
            self._refresh_characters()
            return False
        if self._active_turn and not self._save_active_turn():
            return False
        try:
            character = (load_character(PROJECT_ROOT, str(path), load_settings().name)
                         if Path(path).suffix.lower() == ".md" else read_profile(Path(path)))
            key = character_key(str(character.path))
            conversations = self.store.conversations(key)
            conversation = conversations[0]["id"] if conversations else self.store.create_conversation(key)
            settings = self.preferences.select(self._current_preferences(), character,
                                               use_profile_voice=use_profile_voice)
        except (OSError, ValueError, sqlite3.Error) as exc:
            QMessageBox.warning(self, "Could not use character", str(exc))
            self._refresh_characters()
            return False
        self._apply_settings(settings)
        self._restore_conversation(conversation)
        self.preference_status.setText("Character saved and selected. Each character keeps its own chats and voice; explicit Memories are shared.")
        return True

    @Slot()
    def _add_character(self):
        self._character_editor()

    @Slot()
    def _edit_character(self) -> None:
        self._character_editor(self.settings.character_path)

    def _character_editor(self, existing=None):
        self._end_handsfree()
        if self._worker or self.microphone.busy or self.suspended:
            return
        self._interrupt_speech()
        try:
            draft = self.characters.draft(existing) if existing else None
            if draft:
                draft = replace(draft, reference=self._reference_path if self.voice.currentData() == "reference" else "",
                                builtin=self.voice.currentData() if self.voice.currentData() in VOICES else draft.builtin,
                                rate=self.delivery_rate.value())
            dialog = CharacterDialog(self.characters, self, existing=existing, draft=draft)
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "Could not edit character", str(exc))
            return
        dialog.preview_requested.connect(self._preview_character_voice)
        dialog.stop_requested.connect(self._interrupt_speech)
        self.speech.changed.connect(dialog.feedback.setText)
        self.speech.failed.connect(dialog.feedback.setText)
        try:
            accepted = dialog.exec() == QDialog.DialogCode.Accepted
            self._interrupt_speech()
            if accepted and not self._closing:
                self._activate_character(dialog.saved_path, use_profile_voice=True)
        finally:
            dialog.deleteLater()

    @Slot(str, str, int)
    def _preview_character_voice(self, text, voice, rate):
        if self._worker or self.microphone.busy or self.suspended:
            return
        self._interrupt_speech()
        self.speech.speak(text, voice, self.volume.value(), rate)

    @Slot()
    def _open_character_file(self) -> None:
        if self.settings.character_path and not QDesktopServices.openUrl(QUrl.fromLocalFile(self.settings.character_path)):
            self.preference_status.setText("Open this file in your editor: " + self.settings.character_path)

    @Slot()
    def open_settings(self) -> None:
        self._end_handsfree()
        if self._closing:
            return
        self.show_companion()
        self.settings_dialog.show()
        self.settings_dialog.raise_()
        self.settings_dialog.activateWindow()

    def _current_preferences(self):
        return replace(
            self.settings, tts_enabled=self.auto_speak.isChecked(), tts_voice=self.voice.currentData(),
            **self.connection.values(),
            tts_reference=self._reference_path,
            tts_volume=self.volume.value(), tts_rate=self.delivery_rate.value(), stt_auto_send=self.auto_send.isChecked(),
            stt_model=self.stt_model.currentText(),
            stt_pause_ms=self.speech_pause.currentData(),
            stt_microphone="" if self.mic_device.currentData() is None else str(self.mic_device.currentData()),
            memory_enabled=self.use_memories.isChecked(), close_to_tray=self.close_to_tray.isChecked(),
            avatar_enabled=self.show_avatar.isChecked(), avatar_animated=self.animate_avatar.isChecked(),
            avatar_x=self.avatar.position()[0], avatar_y=self.avatar.position()[1],
            avatar_width=self.avatar.dimensions()[0], avatar_height=self.avatar.dimensions()[1],
            avatar_motion=self.avatar_motion.value(), avatar_lip_sensitivity=self.avatar_lip_sensitivity.value(),
            avatar_hd=self.avatar_hd.isChecked(),
            avatar_cursor_attention=self.avatar_cursor_attention.isChecked(),
            avatar_gaze=self.avatar_gaze.value(), avatar_hair=self.avatar_hair.value(),
        )

    @Slot()
    def _sync_avatar_preset(self) -> None:
        name = motion_preset_name(self.avatar_motion.value(), self.avatar_gaze.value(),
                                  self.avatar_hair.value())
        with QSignalBlocker(self.avatar_preset):
            self.avatar_preset.setCurrentText(name)

    @Slot(str)
    def _apply_avatar_preset(self, name: str) -> None:
        preset = AVATAR_MOTION_PRESETS.get(name)
        if preset is None:
            self._sync_avatar_preset()
            return
        for slider, value in zip((self.avatar_motion, self.avatar_gaze, self.avatar_hair), preset):
            slider.setValue(value)
        self._sync_avatar_preset()

    @Slot()
    def _save_preferences(self) -> None:
        settings = self._current_preferences()
        try:
            self.preferences.save(settings)
        except (OSError, ValueError) as exc:
            self.preference_status.setText(f"Could not save defaults: {exc}")
            return
        self.settings = settings
        self.preference_status.setText("Defaults saved. These preferences override the audio defaults in .env.")

    def _privacy_text(self) -> str:
        return "Saved locally · " + (
            "Relevant memories accompany online replies" if self.use_memories.isChecked()
            else "Saved memory retrieval is off"
        )

    @Slot(bool)
    def _memory_toggled(self, enabled: bool) -> None:
        self.privacy.setText(self._privacy_text())

    @Slot()
    def show_companion(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    @Slot()
    def hide_to_tray(self) -> None:
        if not self.tray_enabled or self._closing:
            return
        self._end_handsfree()
        # Never leave an invisible recording or pending automatic send behind.
        self._pending_transcription = ""
        if self.microphone.busy:
            self.microphone.cancel()
            self.mic_status.setText("Recording or transcription cancelled when the window was hidden")
        self._dismiss_dialogs()
        self.hide()

    def _dismiss_dialogs(self) -> None:
        self.settings_dialog.hide()
        for dialog in self.findChildren(QDialog):
            if dialog is not self.settings_dialog and dialog.isVisible():
                dialog.reject()

    @Slot()
    def toggle_suspended(self) -> None:
        if self._closing:
            return
        self.suspended = not self.suspended
        if self.suspended:
            self._stop()
            self.microphone.shutdown()
            self.speech.shutdown()
        self.suspend_button.setText("Resume" if self.suspended else "Suspend")
        self.suspend_button.setIcon(glyph_icon("play" if self.suspended else "pause"))
        self._set_busy(self._worker is not None)
        self.suspended_changed.emit(self.suspended)

    @Slot()
    def request_quit(self) -> None:
        self._quitting = True
        self.close()

    def closeEvent(self, event: QCloseEvent) -> None:
        if self.tray_enabled and self.close_to_tray.isChecked() and not self._quitting:
            self.hide_to_tray()
            event.ignore()
            return
        self._end_handsfree()
        if self._worker is None and self._active_turn and not self._save_active_turn():
            if QMessageBox.question(self, "Reply not saved", "The latest reply could not be saved. Close anyway? The last successful checkpoint will remain in History.") != QMessageBox.StandardButton.Yes:
                self._closing = False
                self._quitting = False
                self.centralWidget().setEnabled(True)
                self._refresh_controls()
                self.show_companion()
                event.ignore()
                return
        self._closing = True
        self.connection.shutdown()
        self._refresh_activity()
        self._dismiss_dialogs()
        self._pending_transcription = ""
        self.microphone.shutdown()
        self._interrupt_speech()
        self.speech.shutdown()
        if self._worker:
            self._closing = True
            self._stop()
            self.status.setText("Closing…")
            self.centralWidget().setEnabled(False)
            event.ignore()
        else:
            self._save_timer.stop()
            self._scroll_timer.stop()
            if self._owns_store:
                self.store.close()
            event.accept()
            self.closed.emit()

    @Slot()
    def _preview_voice(self) -> None:
        if self.suspended or self._closing:
            return
        self._activity_error = False
        self._end_handsfree()
        self._interrupt_speech()
        self.speech.speak(
            self.settings.voice_preview or f"Hi, I'm {self.settings.name}. Let's think it through, one step at a time.",
            self._speech_voice(), self.volume.value(), self.delivery_rate.value(),
        )

    @Slot()
    def _read_last_reply(self) -> None:
        if self._last_reply and not self.suspended and not self._closing:
            self._activity_error = False
            self._end_handsfree()
            self._interrupt_speech()
            if self._voice_message is not None and self._voice_note:
                self._voice_message["content"] = self._voice_message["content"].removesuffix("\n" + self._voice_note)
                self._save_voice_context()
            self._spoken_phrases = []
            self._voice_note = ""
            self._voice_for_reply = True
            self._voice_message = self._messages[-1] if self._messages and self._messages[-1]["role"] == "assistant" else None
            self._voice_message_id = self._last_reply_id
            self.speech.speak(self._last_reply, self._speech_voice(), self.volume.value(), self.delivery_rate.value())

    @Slot(str)
    def _voice_changed(self, state: str) -> None:
        self.voice_status.setText(state)
        self._refresh_controls()
        if not self.speech.busy:
            self._schedule_handsfree()

    @Slot(str)
    def _voice_failed(self, message: str) -> None:
        self._activity_error = True
        self._end_handsfree()
        if self._voice_for_reply:
            self._record_voice_interruption()
        self._streaming_voice = False
        self._voice_for_reply = False
        self.voice_status.setText(message)
        self._refresh_activity()

    @Slot(bool)
    def _speech_toggled(self, enabled: bool) -> None:
        if not enabled:
            self._interrupt_speech()

    @Slot(int)
    def _volume_changed(self, volume: int) -> None:
        self.volume_label.setText(f"{volume}%")
        # The current process has a fixed gain; stop so mute takes effect immediately.
        self._interrupt_speech()

    @Slot(str)
    def _voice_selected(self, voice: str) -> None:
        self._interrupt_speech()
        self._refresh_reference_label()

    def _speech_voice(self) -> str:
        if self.voice.currentData() == "reference":
            return self._reference_path or "reference"
        return self.voice.currentData()

    def _set_voice_option(self, mode):
        with QSignalBlocker(self.voice):
            self.voice.clear()
            label = f"{self.settings.name}'s voice" if mode == 'reference' else mode
            self.voice.addItem(label, mode)
        self.voice.setToolTip('The active character voice. Use a reference recording to change its sound.')

    def _refresh_reference_label(self) -> None:
        if not self._reference_path:
            self.reference_label.setText("No reference selected · Use a clean 3–30 second WAV of one speaker.")
        else:
            active = self.voice.currentData() == "reference"
            self.reference_label.setText(("Reference: " if active else "Saved reference (inactive): ") + Path(self._reference_path).name)
        self.reference_label.setToolTip(self._reference_path)
        self.clear_reference.setEnabled(bool(self._reference_path))

    @Slot()
    def _choose_reference(self) -> None:
        self._end_handsfree()
        path, _ = QFileDialog.getOpenFileName(self.settings_dialog, "Choose a reference voice", self._reference_path, "PCM WAV audio (*.wav)")
        if not path:
            return
        try:
            reference = inspect_reference(path)
        except VoiceSetupError as exc:
            QMessageBox.warning(self, "Reference voice", str(exc))
            return
        self._interrupt_speech()
        self._reference_path = str(reference.path)
        self._set_voice_option('reference')
        self.delivery_rate.setValue(100)
        self._refresh_reference_label()
        self.preference_status.setText(f"Reference selected: {reference.seconds:.1f}s. Preview to test model access and the voice; Save defaults to keep it.")

    @Slot()
    def _clear_reference(self) -> None:
        self._interrupt_speech()
        self._reference_path = ""
        self._set_voice_option('reference')
        self.delivery_rate.setValue(100)
        self._refresh_reference_label()

    @Slot(int)
    def _delivery_changed(self, rate: int) -> None:
        self.delivery_label.setText(f"{rate}%")
        self._interrupt_speech()

    @Slot()
    def _apply_character_voice(self) -> None:
        if self._worker or self.microphone.busy or self.suspended or not self.settings.character_voice:
            return
        self._end_handsfree()
        self._interrupt_speech()
        self._reference_path = self.settings.character_reference
        self._set_voice_option('reference' if self._reference_path else self.settings.character_voice)
        self._refresh_reference_label()
        self.delivery_rate.setValue(self.settings.character_voice_rate)
        self.preference_status.setText("Character voice applied. Preview to listen; Save defaults to keep it.")

    @Slot(str)
    def _phrase_spoken(self, text: str) -> None:
        if self._voice_for_reply:
            self._spoken_phrases.append(text)

    def _record_voice_interruption(self) -> None:
        completed = " ".join(self._spoken_phrases) or "none confirmed"
        note = (
            "[Voice playback was interrupted. Completed spoken phrases: " + completed
            + ". Part of the current phrase may also have played; the reply text is visible on screen.]"
        )
        if self._voice_message is not None:
            content = self._voice_message["content"]
            if self._voice_note:
                content = content.removesuffix("\n" + self._voice_note)
            self._voice_message["content"] = content + "\n" + note
            self._save_voice_context()
        self._voice_note = note

    def _interrupt_speech(self) -> None:
        if self._voice_for_reply and self.speech.busy:
            self._record_voice_interruption()
        self._voice_for_reply = False
        self._streaming_voice = False
        self.speech.stop()

    @Slot(bool)
    def _handsfree_toggled(self, enabled: bool) -> None:
        self._handsfree_timer.stop()
        self.hands_free.setText("End hands-free" if enabled else "Hands-free")
        if not enabled:
            self.mic_hint.setText(self._manual_mic_hint)
            was_capturing = self._handsfree_capture
            self._handsfree_capture = False
            if was_capturing:
                self._pending_transcription = ""
                self.microphone.cancel()
            self.mic_status.setText("Hands-free off")
            self._refresh_controls()
            return
        self._manual_mic_hint = self.mic_hint.text()
        self.mic_hint.setText("Hands-free · Pause to finish a turn · 30-second turn limit")
        if self._closing or self.suspended or self.microphone.busy:
            self._end_handsfree()
            return
        if self.input.toPlainText().strip():
            self._end_handsfree()
            self.mic_status.setText("Send or clear your draft before starting hands-free mode.")
            return
        if self.auto_send.isChecked():
            try:
                self.settings.validate_connection()
            except ValueError:
                self._end_handsfree()
                self.mic_status.setText("Set up your API connection, or uncheck automatic sending in Settings to review transcripts offline.")
                return
        self.mic_status.setText(f"Hands-free waiting for {self.settings.name} to finish… Microphone off.")
        self._schedule_handsfree(0)
        self._refresh_controls()

    def _end_handsfree(self) -> None:
        self._handsfree_timer.stop()
        if self.hands_free.isChecked():
            self.hands_free.setChecked(False)

    def _schedule_handsfree(self, delay=800) -> None:
        if self.hands_free.isChecked() and not self._closing and not self.suspended:
            if not self._worker and not self.speech.busy and not self.microphone.busy:
                self.mic_status.setText("Hands-free: microphone off. Listening resumes shortly…")
                self._handsfree_timer.start(delay)

    @Slot()
    def _arm_handsfree(self) -> None:
        if not self.hands_free.isChecked() or self._closing or self.suspended:
            return
        if not self.isVisible() or self.isMinimized() or QApplication.activeModalWidget() is not None:
            self._end_handsfree()
            return
        if self._worker or self.speech.busy or self.microphone.busy:
            return
        if self.input.toPlainText().strip():
            self._end_handsfree()
            self.mic_status.setText("Hands-free paused for your draft. Send or clear it before restarting.")
            return
        self._mic_draft = ""
        self._pending_transcription = ""
        self._handsfree_capture = True
        self._activity_error = False
        self.microphone.start(self.mic_device.currentData(), self.stt_model.currentText(),
                              hands_free=True, pause_ms=self.speech_pause.currentData())

    def changeEvent(self, event) -> None:
        if event.type() == QEvent.Type.WindowStateChange and self.isMinimized() and hasattr(self, "hands_free"):
            self._end_handsfree()
        super().changeEvent(event)

    @Slot()
    def _begin_recording(self) -> None:
        self._end_handsfree()
        if self.microphone.busy or self._closing or self.suspended:
            return
        self._activity_error = False
        if self._summary_dialog is not None:
            self._summary_dialog.reject()
        self._mic_draft = self.input.toPlainText()
        self._pending_transcription = ""
        self._interrupt_speech()
        if self._worker:
            self._worker.stop()
        device = self.mic_device.currentData()
        if isinstance(device, str) and device.isdecimal():
            device = int(device)
        self.microphone.start(device, self.stt_model.currentText())

    @Slot()
    def _finish_recording(self) -> None:
        self.microphone.finish()

    @Slot()
    def _toggle_recording(self) -> None:
        if self._closing or self.suspended or QApplication.activeModalWidget() is not None:
            return
        self._end_handsfree()
        if self.microphone.state in {"opening", "recording"}:
            self._finish_recording()
        elif not self.microphone.busy:
            self.showNormal()
            self.raise_()
            self.activateWindow()
            self._begin_recording()

    @Slot(str)
    def _mic_changed(self, state: str) -> None:
        labels = {
            "idle": "Microphone off", "opening": "Opening microphone… Wait for Listening before speaking.",
            "recording": "Listening… Release the button or press Ctrl+Alt+Space to finish.",
            "listening": "Hands-free listening… Speak normally. No speech for 30 seconds turns this mode off.",
            "loading": "Loading transcription model… First use downloads the model.",
            "transcribing": "Transcribing locally…",
        }
        self.mic_status.setText(labels.get(state, "Microphone off"))
        if self._handsfree_capture and state == "recording":
            self.mic_status.setText(f"Speech detected… A {self.speech_pause.currentData() / 1000:g}-second pause finishes this turn.")
        manual = not self._handsfree_capture and state in {"opening", "recording"}
        self.record_button.setToolTip("Release to finish · or press Ctrl+Alt+Space" if manual
                                      else "Hold to talk · or press Ctrl+Alt+Space · up to 60 seconds")
        self.record_button.setText(ICONS["mic_live" if state in {"opening", "recording", "listening"} else "mic"])
        repolish(self.record_button, live=state in {"opening", "recording", "listening"})
        self.mic_level.setVisible(state in {"opening", "recording", "listening"})
        self._refresh_controls()
        if state != "idle":
            self.status.setText("Listening…" if state in {"opening", "listening", "recording"} else "Transcribing…")
        elif not self._worker:
            self.status.setText("Ready")
        if self.suspended:
            self.status.setText("Suspended")

    @Slot(str)
    def _on_transcribed(self, text: str) -> None:
        was_handsfree = self._handsfree_capture
        self._handsfree_capture = False
        if self._closing or self.suspended:
            return
        text = text.strip()
        if not text:
            if was_handsfree:
                self._end_handsfree()
            self.mic_status.setText("No clear speech detected. Try again a little closer to the microphone.")
            self.input.setFocus()
            return
        draft = self._mic_draft.strip()
        self.input.setPlainText(draft + "\n" + text if draft else text)
        self.input.setFocus()
        if self.auto_send.isChecked() and not draft:
            if self._worker:
                # The interrupted API task may still be cleaning up; send only after it exits.
                self.mic_status.setText("Transcript ready. Waiting for the interrupted reply to stop…")
                self._pending_transcription = text
            else:
                self._send()
                self.mic_status.setText(
                    f"Hands-free: microphone off while {self.settings.name} replies." if was_handsfree and self._worker
                    else "Transcript sent" if self._worker else "Transcript ready. Press Send."
                )
                if was_handsfree and not self._worker:
                    self._end_handsfree()
        else:
            if was_handsfree:
                self._end_handsfree()
            self.mic_status.setText("Transcript ready. Edit it if needed, then press Send.")

    def _send_pending_transcription(self) -> None:
        text, self._pending_transcription = self._pending_transcription, ""
        if (
            text and not self._closing and not self.microphone.busy and not self._worker
            and self.auto_send.isChecked() and self.input.toPlainText().strip() == text
        ):
            self._send()

    @Slot(str)
    def _mic_failed(self, message: str) -> None:
        self._activity_error = True
        self._end_handsfree()
        self.mic_status.setText(message)
        self._refresh_controls()

    @Slot(list)
    def _mic_devices(self, devices: list) -> None:
        selected = self.mic_device.currentData()
        self.mic_device.clear()
        self.mic_device.addItem("Windows default microphone", None)
        for device in devices:
            self.mic_device.addItem(device["name"], device["id"])
        index = self.mic_device.findData(selected)
        if index < 0:
            index = next((i for i in range(self.mic_device.count())
                          if str(self.mic_device.itemData(i)) == str(selected)), -1)
        if index < 0 and selected is not None:
            self.mic_device.addItem(str(selected) + " (saved device)", selected)
            index = self.mic_device.count() - 1
        self.mic_device.setCurrentIndex(max(0, index))
        self.mic_status.setText(f"Found {len(devices)} microphone inputs" if devices else "No microphone inputs found")

    def _update_conversation_title(self) -> None:
        conversation = self.store.conversation(self._conversation_id)
        if conversation:
            self.conversation_title.setText(conversation["title"])
            self.conversation_title.setToolTip(conversation["title"])

    def _restore_conversation(self, conversation_id) -> None:
        rows = self.store.messages(conversation_id)
        context = self.store.context(conversation_id)
        self.store.touch_conversation(conversation_id)
        self._reset_conversation_view()
        self._conversation_id = conversation_id
        self._active_turn = None
        self._messages = context
        for row in rows:
            name = "You" if row["role"] == "user" else self.settings.name
            notice = row["notice"]
            if row["status"] == "pending":
                notice = "Interrupted during a previous session"
            self.transcript.add_message(row["role"], name, row["display"], notice or "",
                                        attachments=attachments.loads(row.get("attachments", "")))
            if row["role"] == "assistant" and row["display"] and row["status"] != "local":
                self._last_reply = row["display"]
                self._last_reply_id = row["id"]
        self.replay.setEnabled(bool(self._last_reply))
        self._update_conversation_title()
        self._refresh_continuity()
        self.privacy.setText(self._privacy_text())
        self._refresh_activity()
        self._scroll_timer.start(0)

    @Slot()
    def _scroll_to_latest(self) -> None:
        if not self._closing:
            scrollbar = self.transcript.verticalScrollBar()
            scrollbar.setValue(scrollbar.maximum())

    @Slot()
    def _refresh_continuity(self) -> None:
        if self._closing:
            return
        try:
            summary = self.store.summary(self._conversation_id)
            older, _ = split_turns(self.store.context_turns(self._conversation_id))
            through_id = summary["through_id"] if summary else 0
            pending = sum(turn["assistant_id"] > through_id for turn in older)
        except sqlite3.Error:
            self.context_hint.setText("Conversation context could not be read.")
            return
        state = "Saved summary + recent exchanges" if summary else "Recent exchanges · No summary saved"
        if pending:
            state += f" · {pending} older {'exchange' if pending == 1 else 'exchanges'} to summarize in Context"
        self.context_hint.setText(state)
        self.context_button.setText(f"Context · {pending} older to summarize" if pending else "Context and summary")
        self.context_button.setToolTip(state)

    @Slot()
    def _open_summary(self) -> None:
        self._end_handsfree()
        if self._closing or self._worker or self.microphone.busy or self.suspended:
            return
        self._interrupt_speech()
        if self._active_turn and not self._save_active_turn():
            return
        try:
            dialog = SummaryDialog(self.store, self._conversation_id, self)
            self._summary_dialog = dialog
            dialog.generate_requested.connect(self._generate_summary)
            dialog.cancel_requested.connect(self._stop)
            dialog.saved.connect(self._refresh_continuity)
            dialog.exec()
            self._summary_dialog = None
            dialog.deleteLater()
            self._refresh_continuity()
        except sqlite3.Error:
            QMessageBox.warning(self, "Could not open context", "Conversation context could not be read. Please try again.")

    @Slot()
    def _generate_summary(self) -> None:
        dialog = self._summary_dialog
        if dialog is None or self._worker or self._closing or self.microphone.busy:
            return
        if self.suspended:
            dialog.status.setText("Resume the companion before generating a summary.")
            return
        try:
            self.settings.validate_connection()
            batch = dialog.batch()
        except (ValueError, sqlite3.Error) as exc:
            dialog.status.setText(str(exc) if isinstance(exc, ValueError) else "Could not read older exchanges.")
            return
        if not batch.count:
            dialog.status.setText("No additional older exchanges to summarize. You can still write and save notes yourself.")
            return
        self._interrupt_speech()
        self._summary_text, self._summary_error = "", ""
        self._activity_error = False
        self._summary_through = batch.through_id
        self._worker_kind = "summary"
        worker = ReplyWorker(replace(self.settings, system_prompt=SUMMARY_PROMPT),
                             [{"role": "user", "content": batch.source}], self)
        self._worker = worker
        worker.chunk.connect(self._on_chunk)
        worker.finished.connect(self._on_finished)
        dialog.set_busy(True)
        self._refresh_controls()
        self.status.setText("Summarizing…")
        worker.start()

    def _finish_summary(self, worker) -> None:
        dialog = self._summary_dialog
        error = self._summary_error or worker.error
        if error:
            self._activity_error = True
        stopped = worker.stop_requested.is_set()
        text = self._summary_text.strip()
        self._worker = None
        self._worker_kind = "reply"
        worker.deleteLater()
        if dialog is not None:
            dialog.set_busy(False)
            if error:
                dialog.status.setText(error)
            elif stopped:
                dialog.status.setText("Summary generation cancelled. Your saved summary and draft were kept.")
            elif not text:
                dialog.status.setText("The model returned an empty summary. Your notes were kept.")
            else:
                dialog.draft_ready(text, self._summary_through)
        self._summary_text = ""
        self._set_busy(False)
        if self._closing:
            QTimer.singleShot(0, self.close)
        elif self._pending_transcription:
            QTimer.singleShot(0, self._send_pending_transcription)

    @Slot()
    def _save_active_turn(self) -> bool:
        if self._active_turn is None:
            return True
        context = self._reply
        if self._reply_status in {"error", "interrupted"} and context:
            context += "\n[This reply was interrupted; only the text above was shown.]"
        if self._voice_note:
            context += "\n" + self._voice_note
        try:
            self.store.save_turn(self._active_turn, self._reply, context or None, self._reply_status, self._reply_notice)
        except sqlite3.Error:
            self.privacy.setText("Reply not fully saved yet. Keep this window open and try again.")
            return False
        if self._reply_status != "pending":
            self._active_turn = None
        self.privacy.setText(self._privacy_text())
        return True

    def _save_voice_context(self) -> None:
        if self._voice_message_id is not None and self._voice_message is not None:
            try:
                self.store.update_context(self._voice_message_id, self._voice_message["content"])
            except sqlite3.Error:
                self.privacy.setText("The latest voice interruption note could not be saved.")

    @Slot()
    def _open_history(self) -> None:
        self._end_handsfree()
        if self._worker or self.microphone.busy:
            return
        self._interrupt_speech()
        if self._active_turn and not self._save_active_turn():
            return
        try:
            dialog = HistoryDialog(self.store, self)
            accepted = dialog.exec()
            if self._closing:
                dialog.deleteLater()
                return
            selected = dialog.selected_id if accepted else self._conversation_id
            if not self.store.conversation(selected):
                key = character_key(self.settings.character_path)
                conversations = self.store.conversations(key)
                selected = conversations[0]["id"] if conversations else self.store.create_conversation(key)
            self._restore_conversation(selected)
            dialog.deleteLater()
        except sqlite3.Error:
            QMessageBox.warning(self, "Could not open history", "Saved conversations could not be read. Please try again.")

    @Slot()
    def _open_memories(self) -> None:
        self._end_handsfree()
        if self._worker or self.microphone.busy:
            return
        try:
            dialog = MemoryDialog(self.store, self)
            dialog.exec()
            dialog.deleteLater()
        except sqlite3.Error:
            QMessageBox.warning(self, "Could not open memories", "Saved memories could not be read. Please try again.")

    def _local_command(self, text) -> bool:
        parts = text.split(maxsplit=1)
        command, argument = parts[0], parts[1] if len(parts) > 1 else ""
        if command.lower() not in {"/remember", "/forget", "/memories"}:
            return False
        self._interrupt_speech()
        if command.lower() == "/memories":
            self.input.clear()
            self._open_memories()
            return True
        try:
            if command.lower() == "/remember":
                memory_id = self.store.save_memory(argument)
                response = f"Saved memory #{memory_id}. You can edit or delete it in Memories."
            else:
                if not argument.strip().isdecimal():
                    raise ValueError("Use /forget followed by a memory number, for example /forget 3.")
                deleted = self.store.delete_memory(int(argument))
                response = "Deleted that saved memory. Conversation messages are kept separately." if deleted else "No saved memory has that number."
        except ValueError as exc:
            self.transcript.add_note(str(exc), "warning")
            return True
        except sqlite3.Error:
            self.privacy.setText("The memory command could not be saved. Please try again.")
            return True
        try:
            self.store.local_exchange(self._conversation_id, text, response)
        except sqlite3.Error:
            self.privacy.setText("Memory changed, but its confirmation could not be saved to History.")
        self.input.clear()
        self.transcript.add_message("user", "You", text)
        self.transcript.add_message("assistant", self.settings.name, response)
        return True

