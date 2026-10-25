from dataclasses import replace
from datetime import datetime, timezone
import sqlite3
from pathlib import Path
import tempfile
import time

from PySide6.QtCore import QEvent, QSignalBlocker, Qt, QTimer, QUrl, Signal, Slot
from PySide6.QtGui import QCloseEvent, QDesktopServices, QImage, QKeyEvent
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QFileDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QMainWindow, QMenu,
    QMessageBox,
    QListWidget, QListWidgetItem, QPlainTextEdit, QProgressBar, QPushButton, QScrollArea, QSizePolicy, QSlider,
    QStackedWidget, QTabWidget, QVBoxLayout, QWidget,
)
from PySide6.QtCore import QEventLoop

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
from .avatar_cues import TEST_GROUPS, CueFilter
from .reference_voice import inspect_reference, VoiceSetupError
from . import attachments
from . import reminders
from .chat_view import AttachmentCard, ChatView
from .theme import ACTIVITY_COLORS, ICONS, STYLE, NightSky, WindowChrome, glyph_icon, icon_button, moon_icon, repolish


# Calm, everyday states that should not displace the default footer hint.
IDLE_NOTES = {"", "Microphone off", "Voice loads on first use", "Voice ready", "Voice stopped", "Hands-free off"}
SEALS = {"jingliu": "镜流"}


_YES = {"yes", "yeah", "yep", "yup", "sure", "ok", "okay", "alright", "go", "do", "sounds"}
_NO = {"no", "nope", "nah", "not", "cancel", "dont", "never", "stop"}
_FILLER = {"please", "ahead", "it", "for", "good", "great", "perfect", "thanks", "thank", "you", "that",
           "then", "now", "mind", "jingliu", "go", "do", "sure", "of", "course"}


def offer_answer(text):
    """"yes" or "no" for a short, plain answer to her proposal ("yeah go ahead", "not now, thanks");
    None for anything else, such as "yes, but skip the PDFs", which she should read herself."""
    words = "".join(c if c.isalnum() or c.isspace() else " " for c in text.lower().replace("'", "")).split()
    if not words or len(words) > 6:
        return None
    if words[0] in _NO and all(word in _NO | _FILLER for word in words):
        return "no"
    if (words[0] in _YES or words[0] == "please") and all(word in _YES | _FILLER for word in words):
        return "yes"
    return None


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


ENGINE_IDLE_SECONDS = 600   # Voice and microphone engines close after 10 idle minutes.
TRIM_EVERY_SECONDS = 600    # While hidden, memory is handed back at most every 10 minutes.


class SideTabs(QWidget):
    """Settings sections as a quiet list on the left and the chosen section beside it
    (the subset of QTabWidget's interface the window uses)."""
    currentChanged = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(18)
        self.nav = QListWidget()
        self.nav.setObjectName("nav")
        self.nav.setFixedWidth(150)
        self.nav.setFrameShape(QFrame.Shape.NoFrame)
        self.nav.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.nav.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.nav.setCursor(Qt.CursorShape.PointingHandCursor)
        layout.addWidget(self.nav)
        self.stack = QStackedWidget()
        layout.addWidget(self.stack, 1)
        self.nav.currentRowChanged.connect(self._select)

    def _select(self, index):
        if index >= 0:
            self.stack.setCurrentIndex(index)
            self.currentChanged.emit(index)

    def addTab(self, widget, title):
        item = QListWidgetItem(title)
        self.nav.addItem(item)
        self.stack.addWidget(widget)
        if self.nav.count() == 1:
            self.nav.setCurrentRow(0)
        return self.nav.count() - 1

    def setCurrentIndex(self, index):
        self.nav.setCurrentRow(index)

    def currentIndex(self):
        return self.nav.currentRow()

    def currentWidget(self):
        return self.stack.currentWidget()

    def widget(self, index):
        return self.stack.widget(index)

    def count(self):
        return self.stack.count()


class PanelPage(QWidget):
    """A page inside the main window (Settings, History, Memories…) with a way back to the chat."""

    def __init__(self, title, parent=None):
        super().__init__(parent)
        self.setObjectName("panel")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 18, 22, 14)
        layout.setSpacing(6)
        header = QHBoxLayout()
        header.setSpacing(10)
        self.back = icon_button("back", "Back to the conversation (Esc)")
        header.addWidget(self.back, 0, Qt.AlignmentFlag.AlignVCenter)
        self.title = QLabel(title)
        self.title.setObjectName("title")
        header.addWidget(self.title, 1)
        layout.addLayout(header)
        self.body = QWidget()
        self.body.setObjectName("panelBody")
        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.body, 1)


class CompanionWindow(QMainWindow):
    closed = Signal()
    suspended_changed = Signal(bool)
    activity_changed = Signal(str)
    notify = Signal(str, str)  # title, message: a desktop notification (the tray shows it).

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
        self._cues, self._pending_cues, self._spoken_chars = CueFilter(), [], 0
        self._task, self._task_request, self._task_offer, self._offer_card = None, None, None, None
        self._memory_actions = []
        self._last_undo = None  # (task card, journal) of the latest task with undoable changes.
        self._voice_note = ""
        self._voice_message = None
        # The entry point injects a disk store. Isolated previews/tests use RAM.
        self.store = store if store is not None else Store(":memory:")
        self._owns_store = store is None
        # Reminders are checked every few seconds and soon after start, for ones due while closed.
        self._reminder_timer = QTimer(self)
        self._reminder_timer.setInterval(10000)
        self._reminder_timer.timeout.connect(self._check_reminders)
        self._reminder_timer.start()
        QTimer.singleShot(4000, self, self._check_reminders)
        # In the background, give memory back: close idle voice/microphone engines, trim RAM.
        self._hidden_at = time.monotonic()
        self._trimmed_at = float("-inf")  # Never: monotonic time starts at boot, so 0 can be recent.
        self._idle_timer = QTimer(self)
        self._idle_timer.setInterval(30_000)
        self._idle_timer.timeout.connect(self._save_memory_when_idle)
        self._idle_timer.start()
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
        self._chrome = WindowChrome(self)
        self._chrome.watch(self)
        self.resize(780, 860)
        self.setMinimumSize(460, 560)
        self.setStyleSheet(STYLE)

        root = NightSky()
        self.setCentralWidget(root)
        centring = QHBoxLayout(root)
        centring.setContentsMargins(0, 0, 0, 0)
        # One window: the conversation, and pages such as Settings or History in its place.
        self.pages = QStackedWidget()
        self.pages.setObjectName("pages")
        self.pages.setMaximumWidth(900)  # Keep lines readable on a maximized window.
        column = QWidget()
        column.setObjectName("column")
        self.chat_page = column
        self.pages.addWidget(column)
        centring.addStretch(1)
        centring.addWidget(self.pages, 100)
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
        self.reminders_button = menu.addAction(glyph_icon("clock"), "Reminders")
        self.tasks_button = menu.addAction(glyph_icon("history"), "Recent tasks")
        self.tasks_button.setToolTip("Tasks from the last week, with Undo for the files they changed")
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
        self.reminders_button.triggered.connect(self._open_reminders)
        self.tasks_button.triggered.connect(self._open_recent_tasks)
        self.suspend_button.triggered.connect(self.toggle_suspended)
        self.new_chat.clicked.connect(self._new_conversation)
        self.reload.clicked.connect(self._reload_settings)

        self.settings_dialog = PanelPage("Settings")
        self.settings_dialog.back.clicked.connect(self._close_panel)
        self.pages.addWidget(self.settings_dialog)
        settings_outer = self.settings_dialog.body_layout
        settings_outer.setContentsMargins(0, 4, 0, 0)
        settings_outer.setSpacing(12)
        self.settings_tabs = SideTabs()
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
            label = QLabel(text)
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
        engine_row = QHBoxLayout()
        engine_label = QLabel("Voice engine")
        self.voice_engine = QComboBox()
        self.voice_engine.setAccessibleName("Voice engine")
        engine_label.setBuddy(self.voice_engine)
        self.voice_engine.addItem("Pocket TTS · fast and light (CPU)", "pocket")
        self.voice_engine.addItem("Chatterbox · more natural (needs the GPU)", "chatterbox")
        self.voice_engine.setCurrentIndex(max(0, self.voice_engine.findData(settings.tts_engine)))
        engine_row.addWidget(engine_label)
        engine_row.addWidget(self.voice_engine, 1)
        settings_layout.addLayout(engine_row)
        self.voice_engine_hint = QLabel()
        self.voice_engine_hint.setObjectName("hint")
        self.voice_engine_hint.setWordWrap(True)
        settings_layout.addWidget(self.voice_engine_hint)
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
        self.voice_engine.currentIndexChanged.connect(self._voice_engine_changed)
        self._apply_voice_engine(settings.tts_engine)
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
        self.auto_memory = QCheckBox("Let her remember important things on her own")
        self.auto_memory.setChecked(settings.auto_memory)
        self.auto_memory.setToolTip("On: like other assistants, she saves lasting preferences and facts you mention. "
                                    "Off: she saves only when you ask (\"remember that…\"). Either way you see each "
                                    "change in the chat, can undo it, and can edit everything in Memories.")
        settings_layout.addWidget(self.auto_memory)
        self.auto_memory.toggled.connect(self._auto_memory_toggled)
        memory_hint = QLabel("Ask her to remember or forget something in your own words. Turning off relevant "
                             "memories affects future requests; existing conversation context still applies.")
        memory_hint.setObjectName("hint")
        memory_hint.setWordWrap(True)
        settings_layout.addWidget(memory_hint)
        section(settings_layout, "Computer tasks")
        self.computer_tasks = QCheckBox("Let her do tasks on this computer when I ask")
        self.computer_tasks.setChecked(settings.computer_tasks)
        settings_layout.addWidget(self.computer_tasks)
        self.confirm_tasks = QCheckBox("Confirm with me before she starts a task")
        self.confirm_tasks.setChecked(settings.confirm_tasks)
        self.confirm_tasks.setToolTip("On: she describes what she would do and waits for your yes. "
                                      "Off: she starts clear, specific requests right away and only asks when unsure.")
        settings_layout.addWidget(self.confirm_tasks)
        self.confirm_tasks.toggled.connect(self._confirm_tasks_toggled)
        self.approve_steps = QCheckBox("Ask before she runs commands or uses the mouse and keyboard")
        self.approve_steps.setChecked(settings.approve_steps)
        self.approve_steps.setToolTip("On: commands, file changes, clicks and typing wait for your Allow. "
                                      "Off: she does them immediately; each step still appears in the chat "
                                      "and Stop cancels the task.")
        settings_layout.addWidget(self.approve_steps)
        self.approve_steps.toggled.connect(self._approve_steps_toggled)
        self.tasks_hint = tasks_hint = QLabel()
        tasks_hint.setObjectName("hint")
        tasks_hint.setWordWrap(True)
        settings_layout.addWidget(tasks_hint)
        self.computer_tasks.toggled.connect(self._computer_tasks_toggled)
        self._describe_tasks()
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
        sleep_row = QHBoxLayout()
        sleep_label = QLabel('Doze off when left alone')
        self.avatar_sleep = QComboBox()
        self.avatar_sleep.setAccessibleName('Doze off when left alone')
        sleep_label.setBuddy(self.avatar_sleep)
        for label, minutes in (('Never', 0), ('After 2 minutes', 2), ('After 5 minutes', 5),
                               ('After 10 minutes', 10), ('After 20 minutes', 20)):
            self.avatar_sleep.addItem(label, minutes)
        self._set_sleep_option(settings.avatar_sleep_minutes)
        self.avatar_sleep.setToolTip(
            'Live2D only. With no conversation, clicks or hovering, she grows drowsy and falls asleep '
            '(a little sooner late at night). Talking to her, clicking her or resting the pointer on her wakes her. '
            'Save defaults to keep this setting.')
        sleep_row.addWidget(sleep_label)
        sleep_row.addWidget(self.avatar_sleep, 1)
        settings_layout.addLayout(sleep_row)
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
        section(settings_layout, "Animation tester")
        self.animation_tester = QWidget()
        tester = QVBoxLayout(self.animation_tester)
        tester.setContentsMargins(0, 0, 0, 0)
        tester.setSpacing(6)
        tester_hint = QLabel("Play any expression, gesture or sleep stage on the Live2D avatar right away. "
                             "These are the same expressions she chooses herself while replying.")
        tester_hint.setObjectName("hint")
        tester_hint.setWordWrap(True)
        tester.addWidget(tester_hint)
        self.animation_buttons = {}
        for title, items in TEST_GROUPS:
            group = QLabel(title)
            group.setObjectName("subtitle")
            tester.addWidget(group)
            grid = QGridLayout()
            grid.setSpacing(6)
            for column in range(4):
                grid.setColumnStretch(column, 1)  # Same button width in every group.
            for index, (label, name) in enumerate(items):
                button = QPushButton(label)
                button.setObjectName("chip")
                button.setCursor(Qt.CursorShape.PointingHandCursor)
                button.clicked.connect(lambda _=False, name=name, label=label: self._test_animation(name, label))
                grid.addWidget(button, index // 4, index % 4)
                self.animation_buttons[name] = button
            tester.addLayout(grid)
        self.animation_status = QLabel("Show the Live2D avatar, then pick an animation.")
        self.animation_status.setObjectName("hint")
        self.animation_status.setWordWrap(True)
        tester.addWidget(self.animation_status)
        settings_layout.addWidget(self.animation_tester)
        settings_layout.addStretch()
        self.preference_status = QLabel("Changes apply now. Your model, character and avatar settings are remembered "
                                        "automatically; Save defaults keeps voice, microphone and app settings.")
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
        done.clicked.connect(self._close_panel)
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
        # Avatar choices are remembered as you make them; no Save defaults needed.
        self._avatar_save = QTimer(self)
        self._avatar_save.setSingleShot(True)
        self._avatar_save.setInterval(600)
        self._avatar_save.timeout.connect(self._remember_avatar)
        for control in (self.show_avatar, self.animate_avatar, self.avatar_hd, self.avatar_cursor_attention):
            control.toggled.connect(self._avatar_save.start)
        for slider in (self.avatar_size, self.avatar_motion, self.avatar_lip_sensitivity, self.avatar_gaze, self.avatar_hair):
            slider.valueChanged.connect(self._avatar_save.start)
        self.avatar_sleep.currentIndexChanged.connect(self._avatar_save.start)
        self.avatar.placed.connect(self._avatar_save.start)
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
        if self._offer_card is not None and self._offer_card.open and not self._closing:
            # A plain yes (typed or spoken) starts the offered plan at once; anything more goes to her.
            answer = offer_answer(text) if not files else None
            if answer == "yes":
                self.input.clear()
                self._accept_offer(self._offer_card, self._offer_card.description, text)
                return
            self._offer_card.close_offer("Not now." if answer == "no" else "You answered in the chat.",
                                         "failed" if answer == "no" else "done")
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
        self._begin_reply(text, files)

    def _begin_reply(self, text, files=(), reminder=False) -> bool:
        """Save the turn and start her reply. A reminder's line comes from the app, not the input box."""
        self._activity_error = False
        self._interrupt_speech()
        if self._active_turn and not self._save_active_turn():
            return False
        try:
            stored = attachments.store(files) if files else []
        except (OSError, attachments.AttachmentError) as exc:
            self._flash(f"Could not attach: {exc}" if isinstance(exc, attachments.AttachmentError)
                        else "An attachment could not be copied. Check the file and try again.")
            return False
        try:
            turns = self.store.context_turns(self._conversation_id)
            summary = self.store.summary(self._conversation_id)
            recent_topics = "\n".join(message["content"] for message in self._messages[-4:] if message["role"] == "user")
            memories = self.store.relevant_memories(recent_topics[-4000:] + "\n" + text) if self.use_memories.isChecked() else []
            turn = self.store.start_turn(self._conversation_id, text, stored)
        except sqlite3.Error:
            attachments.remove_files(stored)
            self.privacy.setText("Could not save this message. No request was sent. Please try again.")
            return False
        if not reminder:
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
        self._reply = ""
        if reminder:
            # The clock icon already says it; her message keeps the mark that tells her what this is.
            self.transcript.add_memory_note(text.replace(reminders.MARK, "Reminder"), can_undo=False, icon="clock")
        else:
            self.input.clear()
            self.transcript.add_message("user", "You", text, attachments=stored)
        self.transcript.begin_reply(self.settings.name)
        prompt = reply_prompt(self.settings.system_prompt, memories, summary["content"] if summary else None,
                              avatar_cues=self.show_avatar.isChecked(),
                              computer_tasks=self.computer_tasks.isChecked(),
                              confirm_tasks=self.confirm_tasks.isChecked(),
                              memory_cues=True, auto_memory=self.auto_memory.isChecked(),
                              reminders=self._reminder_prompt())
        self._task_request = self._task_offer = None
        self._memory_actions = []
        self._cues, self._pending_cues, self._spoken_chars = CueFilter(), [], 0
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
        return True

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
                                    or self.hands_free.isChecked() or preview_active
                                    or getattr(self, "_task", None) is not None)
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
        # Expression cues leave the text here, before display, speech or saving.
        text, cues = self._cues.feed(text)
        self._queue_cues(cues)
        if not text:
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
        tail = self._cues.finish()
        if tail and not interrupted:
            self._reply += tail
            self.transcript.append_reply(tail)
            if self._streaming_voice:
                self.speech.feed_reply(tail)
        if not self._streaming_voice or interrupted:
            self._flush_cues(all_cues=not interrupted)
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
        task_turn = self._active_turn
        self._save_active_turn()
        self.transcript.end_reply(notice="Reply stopped" if interrupted and not worker.error else "",
                                  error=worker.error)
        if not worker.error:
            self._apply_memory_actions()
        self._memory_actions = []
        if not interrupted and self.computer_tasks.isChecked():
            if self._task_request is not None:
                # Her own description of the agreed job; the person's words are the fallback.
                request = self._task_request or next(
                    (m["content"] for m in reversed(self._messages) if m["role"] == "user"), "")
                acknowledgement = self._reply
                QTimer.singleShot(0, lambda: self._start_task(request, task_turn, acknowledgement))
            elif self._task_offer:
                self._show_offer(self._task_offer)
        self._task_request = self._task_offer = None
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
        if self._task is not None:
            self._task.stop()
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
        self._set_sleep_option(settings.avatar_sleep_minutes)
        with QSignalBlocker(self.voice_engine):
            self.voice_engine.setCurrentIndex(max(0, self.voice_engine.findData(settings.tts_engine)))
        self._apply_voice_engine(settings.tts_engine)
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
            self._chrome.watch(dialog)
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "Could not edit character", str(exc))
            return
        dialog.preview_requested.connect(self._preview_character_voice)
        dialog.stop_requested.connect(self._interrupt_speech)
        self.speech.changed.connect(dialog.feedback.setText)
        self.speech.failed.connect(dialog.feedback.setText)
        try:
            accepted = self._present(dialog) == QDialog.DialogCode.Accepted
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
        self._chrome.guard(self.settings_dialog)
        self.pages.setCurrentWidget(self.settings_dialog)

    @Slot()
    def _close_panel(self):
        """Back to the conversation from Settings (dialog pages close themselves)."""
        if self.pages.currentWidget() is self.settings_dialog:
            self.pages.setCurrentWidget(self.chat_page)
            self.input.setFocus()

    def _present(self, dialog):
        """Show a dialog as a page in this window and wait for it, like exec(); returns its result."""
        if not self.isVisible() or self.isMinimized():
            self.show_companion()  # Pages live in this window, so it has to be on screen.
        page = PanelPage(dialog.windowTitle())
        dialog.setParent(page.body)
        dialog.setWindowFlags(Qt.WindowType.Widget)
        dialog.setProperty("embedded", True)
        page.body_layout.addWidget(dialog)
        page.back.clicked.connect(dialog.reject)
        previous = self.pages.currentWidget()
        self.pages.addWidget(page)
        self.pages.setCurrentWidget(page)
        self._chrome.guard(dialog)
        loop = QEventLoop()
        dialog.finished.connect(loop.quit)
        dialog.show()
        if not self._closing:
            loop.exec()
        result = dialog.result()
        back = previous if self.pages.indexOf(previous) >= 0 else self.chat_page
        self.pages.setCurrentWidget(back)
        self.pages.removeWidget(page)
        dialog.hide()
        dialog.setParent(self)  # The caller still owns and deletes it.
        page.deleteLater()
        if back is self.chat_page:
            self.input.setFocus()
        return result

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
            avatar_sleep_minutes=self.avatar_sleep.currentData(),
            tts_engine=self.voice_engine.currentData(),
        )

    AVATAR_FIELDS = ("avatar_enabled", "avatar_animated", "avatar_x", "avatar_y", "avatar_width", "avatar_height",
                     "avatar_motion", "avatar_lip_sensitivity", "avatar_hd", "avatar_cursor_attention",
                     "avatar_gaze", "avatar_hair", "avatar_sleep_minutes")

    @Slot()
    def _remember_avatar(self):
        if self._closing:
            return
        current = self._current_preferences()
        self.settings = replace(self.settings, **{key: getattr(current, key) for key in self.AVATAR_FIELDS})
        try:
            self.preferences.remember(current, self.AVATAR_FIELDS)
        except (OSError, ValueError):
            pass  # The choice still applies now; Save defaults reports problems explicitly.

    # Computer tasks ---------------------------------------------------------------

    @Slot(bool)
    def _computer_tasks_toggled(self, enabled):
        self.settings = replace(self.settings, computer_tasks=enabled)
        try:
            self.preferences.remember(self.settings, ("computer_tasks",))
        except (OSError, ValueError):
            pass

    @Slot(bool)
    def _approve_steps_toggled(self, enabled):
        self.settings = replace(self.settings, approve_steps=enabled)
        self._describe_tasks()
        try:
            self.preferences.remember(self.settings, ("approve_steps",))
        except (OSError, ValueError):
            pass

    def _describe_tasks(self):
        steps = ("she asks you before running commands, changing files, or using the mouse and keyboard."
                 if self.approve_steps.isChecked() else
                 "she runs commands, changes files and uses the mouse and keyboard without asking, "
                 "showing each step in the chat.")
        self.tasks_hint.setText("Uses Claude Code with your Claude plan. She can read files, search and look at the "
                                f"screen; {steps} Ask in chat, or type /do followed by the task. Stop cancels a task.")

    # Memory ----------------------------------------------------------------------

    @Slot(bool)
    def _auto_memory_toggled(self, enabled):
        self.settings = replace(self.settings, auto_memory=enabled)
        try:
            self.preferences.remember(self.settings, ("auto_memory",))
        except (OSError, ValueError):
            pass

    def _apply_memory_actions(self):
        actions, self._memory_actions = self._memory_actions, []
        handlers = {"remember": self._remember, "forget": self._forget,
                    "remind": self._set_reminder, "unremind": self._cancel_reminder,
                    # After her reply is shown, so the confirmation comes after her words.
                    "undotask": lambda _: QTimer.singleShot(0, self, self._undo_latest)}
        for action, detail in actions:
            handlers[action](detail)

    def _remember(self, fact):
        fact = " ".join(fact.split())[:1000]
        try:
            known = {memory["id"] for memory in self.store.memories()}
            memory_id = self.store.save_memory(fact)
        except (ValueError, sqlite3.Error):
            self.transcript.add_note("She tried to remember something, but it could not be saved.", "warning")
            return
        if memory_id in known:
            self.transcript.add_memory_note(f"Already remembered: “{fact}”", can_undo=False)
            return
        note = self.transcript.add_memory_note(f"Memory saved: “{fact}”")

        def undo(note=note, memory_id=memory_id, fact=fact):
            try:
                self.store.delete_memory(memory_id)
            except sqlite3.Error:
                return
            note.settle(f"Not remembered: “{fact}”")
        note.undo.connect(undo)

    def _forget(self, description):
        from .storage import terms
        wanted = terms(description)
        try:
            memories = self.store.memories()
        except sqlite3.Error:
            return
        # The memory sharing the most words with her description; it must clearly match.
        scored = sorted(((len(wanted & terms(m["content"])) / max(1, len(wanted)), m) for m in memories),
                        key=lambda item: item[0], reverse=True)
        if not scored or scored[0][0] < .5:
            self.transcript.add_memory_note(f"No saved memory matched “{description}”. Open Memories to remove it.",
                                            can_undo=False)
            return
        memory = scored[0][1]
        try:
            self.store.delete_memory(memory["id"])
        except sqlite3.Error:
            return
        note = self.transcript.add_memory_note(f"Forgot: “{memory['content']}”")

        def undo(note=note, memory=memory):
            try:
                self.store.save_memory(memory["content"], pinned=bool(memory["pinned"]))
            except (ValueError, sqlite3.Error):
                return
            note.settle(f"Kept: “{memory['content']}”")
        note.undo.connect(undo)

    @Slot(bool)
    def _confirm_tasks_toggled(self, enabled):
        self.settings = replace(self.settings, confirm_tasks=enabled)
        try:
            self.preferences.remember(self.settings, ("confirm_tasks",))
        except (OSError, ValueError):
            pass

    def _show_offer(self, description):
        if self._offer_card is not None and self._offer_card.open:
            self._offer_card.close_offer("Replaced by her newer suggestion.")
        card = self.transcript.add_offer(description)
        self._offer_card = card
        card.accepted.connect(lambda text, card=card: self._accept_offer(card, text))
        card.declined.connect(lambda card=card: self._decline_offer(card))

    def _accept_offer(self, card, description, words="Yes, do it."):
        if self._worker or self.suspended or self._task is not None:
            self.transcript.add_note("Wait until she has finished what she is doing, then confirm again.", "warning")
            return
        card.close_offer("Confirmed. She is starting.")
        self.transcript.add_message("user", "You", words)
        try:
            turn = self.store.start_turn(self._conversation_id, words)
        except sqlite3.Error:
            turn = None
        self._messages.append({"role": "user", "content": words})
        self._start_task(description, turn, "")

    def _decline_offer(self, card):
        if self._worker or self.microphone.busy or self.suspended:
            return
        card.close_offer("Not now.", "failed")
        # Said in the chat, so she can answer it naturally and remember the decision.
        self.input.setPlainText("Not now, thank you.")
        self._send()

    def _do_command(self, request):
        self.input.clear()
        if not request:
            self.transcript.add_note("Type /do followed by what you want done, for example: /do tidy my Downloads folder.",
                                     "warning")
            return
        if not self.computer_tasks.isChecked():
            self.transcript.add_note("Computer tasks are turned off. Turn them on in Settings → App.", "warning")
            return
        self.transcript.add_message("user", "You", "/do " + request)
        try:
            turn = self.store.start_turn(self._conversation_id, "/do " + request)
        except sqlite3.Error:
            turn = None
        self._messages.append({"role": "user", "content": "/do " + request})
        self._start_task(request, turn, "")

    def _start_task(self, request, turn, acknowledgement):
        from .computer_tasks import ComputerTask
        if self._task is not None:
            self.transcript.add_note("She is still working on the previous task. Stop it first to start another.", "warning")
            return
        if not request.strip() or self._closing:
            return
        context = [m for m in self._messages[:-1] if m.get("role") in {"user", "assistant"}]
        task = ComputerTask(request, context, self.settings, self)
        card = self.transcript.add_task_card(self.settings.name, request)
        self._task, self._task_card, self._task_turn, self._task_ack = task, card, turn, acknowledgement
        task.step.connect(card.add_step)
        task.step.connect(self._task_step)
        task.approval.connect(self._ask_approval)
        task.finished.connect(self._task_finished)
        self.avatar.work("start", request)
        self.status.setText("Working on a task…")
        task.start()
        self._refresh_stop_button()

    def _task_step(self, summary):
        from .computer_tasks import step_kind
        self.avatar.work(step_kind(summary), summary)

    def _ask_approval(self, request):
        from .approval_ui import ApprovalDialog
        card = self._task_card
        card.set_status("Waiting for your approval…", "approval")
        self.avatar.work("wait", request.summary)
        self.show_companion()
        dialog = ApprovalDialog(self.settings.name, request, self)
        self._chrome.watch(dialog)

        def decided(choice, dialog=dialog):
            if choice == "deny":
                request.answer(False, "The person did not allow this step. Do not try it another way.")
                card.add_step("Not allowed: " + request.summary)
            else:
                if choice == "task" and self._task is not None:
                    self._task.remember_approval(request)
                request.answer(True)
                card.add_step(request.summary)
            if self._task is not None:
                card.set_status("Working…", "working")
                if choice == "deny":
                    self.avatar.work("think", "Finding another way to finish what I can…")
                else:
                    self._task_step(request.summary)
            dialog.deleteLater()
        dialog.decided.connect(decided)
        dialog.open()

    def _task_finished(self, report, succeeded):
        task, self._task = self._task, None
        card = self._task_card
        card.set_status("Done" if succeeded else "Stopped" if "stopped" in report.lower() else "Not finished",
                        "done" if succeeded else "failed")
        for dialog in self.findChildren(QDialog):
            if dialog.windowTitle() == "Allow this step?" and dialog.isVisible():
                dialog.reject()
        self.transcript.add_message("assistant", self.settings.name, report)
        self._messages.append({"role": "assistant", "content": "[Task report] " + report})
        if self._task_turn is not None:
            # The report joins the reply that accepted the task, so later replies know the outcome.
            shown = (self._task_ack + "\n\n" if self._task_ack else "") + report
            try:
                self.store.save_turn(self._task_turn, shown, shown, "complete")
            except sqlite3.Error:
                pass
        self.avatar.work("done" if succeeded else "failed", report)
        journal = getattr(task, "journal", None)
        if journal is not None and journal.undoable():
            card.offer_undo()
            card.undo_requested.connect(lambda card=card, journal=journal: self._undo_task(card, journal))
            self._last_undo = (card, journal)
        if self.auto_speak.isChecked() and self.volume.value() > 0 and not self._closing:
            self.speech.speak(report, self._speech_voice(), self.volume.value(), self.delivery_rate.value())
        self.status.setText("Ready")
        self._refresh_stop_button()
        if task is not None:
            task.deleteLater()

    # Reminders --------------------------------------------------------------------

    def _reminder_prompt(self):
        try:
            return reminders.prompt(self.store.reminders())
        except sqlite3.Error:
            return reminders.prompt([])

    def _set_reminder(self, payload):
        try:
            due, text, repeat = reminders.parse(payload)
            reminder_id = self.store.add_reminder(text, due, repeat)
        except ValueError as exc:
            self.transcript.add_note(f"The reminder could not be set: {exc}", "warning")
            return
        except sqlite3.Error:
            self.transcript.add_note("The reminder could not be saved.", "warning")
            return
        when = reminders.describe({"due_at": due.isoformat(), "repeat": repeat})
        note = self.transcript.add_memory_note(f"Reminder set: “{text}” · {when}", button="Cancel", icon="clock")

        def cancel(note=note, reminder_id=reminder_id, text=text):
            try:
                self.store.delete_reminder(reminder_id)
            except sqlite3.Error:
                return
            note.settle(f"Reminder cancelled: “{text}”")
        note.undo.connect(cancel)

    def _cancel_reminder(self, description):
        try:
            upcoming = self.store.reminders()
        except sqlite3.Error:
            return
        scored = sorted(((reminders.match(description, r["text"]), r) for r in upcoming),
                        key=lambda item: item[0], reverse=True)
        if not scored or scored[0][0] < .5:
            self.transcript.add_memory_note(f"No reminder matched “{description}”. Open Reminders to remove it.",
                                            can_undo=False, icon="clock")
            return
        reminder = scored[0][1]
        try:
            self.store.delete_reminder(reminder["id"])
        except sqlite3.Error:
            return
        note = self.transcript.add_memory_note(f"Reminder cancelled: “{reminder['text']}”", icon="clock")

        def restore(note=note, reminder=reminder):
            try:
                self.store.add_reminder(reminder["text"], datetime.fromisoformat(reminder["due_at"]), reminder["repeat"])
            except (ValueError, sqlite3.Error):
                return
            note.settle(f"Reminder kept: “{reminder['text']}”")
        note.undo.connect(restore)

    def _finish_reminder(self, reminder):
        repeat = reminder.get("repeat") or ""
        following = reminders.following(datetime.fromisoformat(reminder["due_at"]), repeat) if repeat else None
        self.store.finish_reminder(reminder["id"], following)

    @Slot()
    def _check_reminders(self):
        """Every few seconds: deliver a due reminder once she is free; list long-missed ones."""
        if self._closing:
            return
        try:
            due = self.store.due_reminders(datetime.now(timezone.utc))
            now = reminders.now_local()
            fresh = []
            for reminder in due:
                if now - datetime.fromisoformat(reminder["due_at"]) > reminders.LATE_LIMIT:
                    self._finish_reminder(reminder)
                    self.transcript.add_memory_note(f"Missed while the app was closed: “{reminder['text']}” "
                                                    f"({reminders.describe(reminder)})", can_undo=False, icon="clock")
                else:
                    fresh.append(reminder)
            busy = (self._worker or self._task is not None or self.microphone.busy or self.suspended
                    or self.speech.busy)
            if not fresh or busy:
                return
            reminder = fresh[0]
            self._finish_reminder(reminder)
        except sqlite3.Error:
            return
        self._deliver_reminder(reminder)

    def _deliver_reminder(self, reminder):
        line = reminders.message(reminder)
        if not self.isVisible() or self.isMinimized():
            self.notify.emit(f"{self.settings.name} · Reminder", reminder["text"])
        try:
            self.settings.validate_connection()
            started = self._begin_reply(line, reminder=True)
        except ValueError:
            started = False
        if not started:
            # Without a model she cannot speak it herself; the reminder still appears.
            self.transcript.add_memory_note(f"Reminder: {reminder['text']}", can_undo=False, icon="clock")

    @Slot()
    def _open_reminders(self) -> None:
        from .library_ui import ReminderDialog
        try:
            dialog = ReminderDialog(self.store, self)
        except sqlite3.Error:
            QMessageBox.warning(self, "Could not open reminders", "Reminders could not be read. Please try again.")
            return
        self._chrome.watch(dialog)
        self._present(dialog)
        dialog.deleteLater()

    def _latest_undo(self):
        """The newest task whose changes can still be undone: this session's, else one saved earlier."""
        if self._last_undo is not None:
            return self._last_undo
        from .computer_tasks import UNDO_ROOT
        from .task_journal import recent
        journal = next((item for item in recent(UNDO_ROOT) if not item.undone), None)
        return (None, journal) if journal is not None else None

    @Slot()
    def _undo_latest(self):
        latest = self._latest_undo()
        if latest is None:
            self.transcript.add_note("There is no recent task with changes to undo.")
        else:
            self._undo_task(*latest)

    @Slot()
    def _open_recent_tasks(self) -> None:
        from .computer_tasks import UNDO_ROOT
        from .library_ui import TasksDialog
        dialog = TasksDialog(UNDO_ROOT, self)
        dialog.undo_requested.connect(lambda journal: self._undo_task(None, journal) or dialog.refresh())
        self._chrome.watch(dialog)
        self._present(dialog)
        dialog.deleteLater()

    def _undo_task(self, card, journal):
        """Reverse a finished task's file changes, after showing what will happen."""
        if journal.undone or self._task is not None:
            if self._task is not None:
                self.transcript.add_note("Stop the current task before undoing an earlier one.", "warning")
            return
        lines, notes = journal.plan()
        text = "This will " + "; ".join(lines) + "." if lines else "There is nothing left to undo."
        if notes:
            text += "\n\nIt cannot reverse " + " or ".join(notes) + "."
        request = journal.details.get("request")
        if card is None and request:
            text = f"Task: {request[:200]}\n\n" + text
        if QMessageBox.question(self, "Undo this task?", text) != QMessageBox.StandardButton.Yes:
            return
        done, problems = journal.undo()
        if card is not None:
            card.offer_undo(False)
            card.set_status("Undone" if not problems else "Partly undone", "undone")
        if self._last_undo and self._last_undo[1] is journal:
            self._last_undo = None
        summary = f"Undid the task: {len(done)} change{'s' if len(done) != 1 else ''} reversed."
        if problems:
            summary += " Not reversed: " + "; ".join(problems[:4]) + ("…" if len(problems) > 4 else ".")
        if notes:
            summary += " Commands and screen actions were left as they are."
        self.transcript.add_note(summary, "warning" if problems else "")
        # She should know her work was taken back, so later replies do not assume it is still there.
        self._messages.append({"role": "assistant", "content": "[Task undone by the person] " + summary})

    @Slot()
    def _voice_engine_changed(self):
        engine = self.voice_engine.currentData()
        self._interrupt_speech()
        self._apply_voice_engine(engine)
        self.settings = replace(self.settings, tts_engine=engine)
        try:
            # Like the response model, the engine choice is remembered at once.
            self.preferences.remember(self.settings, ("tts_engine",))
        except (OSError, ValueError):
            pass

    def _apply_voice_engine(self, engine):
        if hasattr(self.speech, "set_engine"):
            self.speech.set_engine(engine)
        installed = getattr(self.speech, "chatterbox_installed", lambda: True)()
        if installed or engine != "chatterbox":
            QTimer.singleShot(2500, self, self._warm_voice)
        self.voice_engine_hint.setText(
            "Kyutai Pocket TTS: starts speaking quickly and runs comfortably on the CPU." if engine != "chatterbox" else
            "Resemble AI Chatterbox in her calm, composed style: more human-sounding, but slower. It loads in the "
            "background when the app opens, and prepares her next sentences while she is still speaking, so on this "
            "laptop's RTX 4060 the pauses between sentences are short (on the CPU, much longer). The first use "
            "downloads about 3 GB."
            + ("" if installed else " Not installed yet: run Setup Chatterbox.cmd in the project folder."))

    @Slot()
    def _warm_voice(self):
        """Loading a voice takes a while (Pocket ~20 s): start it early when her replies will be spoken."""
        from .voice_settings import VOICES
        voice = self._speech_voice()
        chatterbox = self.settings.tts_engine == "chatterbox"
        if (hasattr(self.speech, "warm") and not self._closing and self.auto_speak.isChecked()
                and self.volume.value() > 0 and not (chatterbox and voice in VOICES)):
            self.speech.warm(voice)

    def _test_animation(self, name, label):
        widget = self.avatar.widget
        if widget is None or not self.show_avatar.isChecked():
            self.animation_status.setText("Turn on Show desktop avatar first.")
        elif getattr(widget, "kind", "") != "live2d":
            self.animation_status.setText("The animation tester needs the Live2D visual model.")
        elif not self.animate_avatar.isChecked():
            self.animation_status.setText("Turn on Animate avatar to play animations.")
        elif self.avatar.cue(name):
            self.animation_status.setText(f"Playing: {label}.")
        else:
            self.animation_status.setText("The avatar is still loading. Try again in a moment.")

    def open_animation_tester(self) -> None:
        self.open_settings()
        self.settings_tabs.setCurrentIndex(2)
        scroll = self.settings_tabs.currentWidget()
        QTimer.singleShot(0, lambda: scroll.ensureWidgetVisible(self.animation_tester, 0, 0))

    def _set_sleep_option(self, minutes):
        if self.avatar_sleep.findData(minutes) < 0:
            self.avatar_sleep.addItem(f"After {minutes} minutes", minutes)
        self.avatar_sleep.setCurrentIndex(self.avatar_sleep.findData(minutes))

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
        QTimer.singleShot(500, self, self._warm_voice)  # Reloads the voice if it was closed while away.

    @Slot()
    def _save_memory_when_idle(self):
        """Every 30 s while the window is hidden or minimized: close voice and microphone engines
        unused for 10 minutes, and hand the app's idle memory back to Windows (at most every 10
        minutes). While the window is open, nothing is unloaded: she is ready to answer."""
        now = time.monotonic()
        if self.isVisible() and not self.isMinimized():
            self._hidden_at = now
            return
        if self._worker or self._task is not None:
            return
        for engine in (self.speech, self.microphone):
            if hasattr(engine, "release"):
                engine.release(ENGINE_IDLE_SECONDS)
        if now - self._hidden_at >= 30 and now - self._trimmed_at >= TRIM_EVERY_SECONDS:
            from .memory_saver import trim
            trim()  # This process only: the engines are either in use or closed.
            self._trimmed_at = now

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
        self._close_panel()
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
        if self._task is not None:
            self._task.stop("The app was closed, so I stopped the task where it was.")
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
        if getattr(self.speech, "state", "") == "speaking":
            self._flush_cues()  # Cues at the very start show as the voice begins.
        elif not self.speech.busy:
            self._pending_cues = []  # Playback ended or stopped; late cues would be out of place.
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
        self._spoken_chars += len(text) + 1
        self._flush_cues()

    def _queue_cues(self, cues):
        # Action cues are for the app, not the avatar: tasks, offers and memory changes.
        for _, cue in cues:
            name, _, detail = cue.partition(":")
            if name == "task":
                self._task_request = detail
            elif name == "offer" and detail:
                self._task_offer = detail
            elif name in {"remember", "forget", "remind", "unremind"} and detail:
                self._memory_actions.append((name, detail))
            elif name == "undotask":
                self._memory_actions.append((name, ""))
        cues = [(offset, cue) for offset, cue in cues if cue.partition(":")[0] not in
                {"task", "offer", "remember", "forget", "remind", "unremind", "undotask"}]
        # Spoken replies show each expression as the voice reaches it; silent ones show it at once.
        self._pending_cues.extend(cues)
        if not self._streaming_voice:
            self._flush_cues(all_cues=True)
        elif getattr(self.speech, "state", "") == "speaking":
            self._flush_cues()

    def _flush_cues(self, all_cues=False):
        due = [cue for offset, cue in self._pending_cues if all_cues or offset <= self._spoken_chars]
        self._pending_cues = [(offset, cue) for offset, cue in self._pending_cues
                              if not all_cues and offset > self._spoken_chars]
        for cue in due[-3:]:  # A burst of cues collapses to its latest few.
            self.avatar.cue(cue)

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
            self._chrome.watch(dialog)
            self._summary_dialog = dialog
            dialog.generate_requested.connect(self._generate_summary)
            dialog.cancel_requested.connect(self._stop)
            dialog.saved.connect(self._refresh_continuity)
            self._present(dialog)
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
            self._chrome.watch(dialog)
            accepted = self._present(dialog)
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
            self._chrome.watch(dialog)
            self._present(dialog)
            dialog.deleteLater()
        except sqlite3.Error:
            QMessageBox.warning(self, "Could not open memories", "Saved memories could not be read. Please try again.")

    def _local_command(self, text) -> bool:
        parts = text.split(maxsplit=1)
        command, argument = parts[0], parts[1] if len(parts) > 1 else ""
        if command.lower() == "/do":
            self._do_command(argument.strip())
            return True
        if command.lower() == "/undo":
            self.input.clear()
            self._undo_latest()
            return True
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

