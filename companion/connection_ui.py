"""Model choice is independent of character, voice and local conversation."""
from PySide6.QtCore import QSignalBlocker, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget
from .claude_backend import CLAUDE_MODELS, DEFAULT_CLAUDE_MODEL, LEGACY_ALIASES
from .connection_worker import ConnectionWorker


class ConnectionPanel(QWidget):
    changed = Signal()

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.worker = None
        self.models = []
        layout = QVBoxLayout(self); layout.setContentsMargins(0, 0, 0, 0); layout.setSpacing(0)
        self.provider = QComboBox()
        self.provider.addItem('OpenRouter (API key)', 'openrouter')
        self.provider.addItem('Claude subscription via Claude Code', 'claude')
        self.provider.addItem('ChatGPT subscription via Codex', 'codex')
        self.model = QComboBox()
        for title, combo in (("Service", self.provider), ("Model", self.model)):
            line = QWidget(); line.setObjectName("settingRow")
            row = QHBoxLayout(line); row.setContentsMargins(0, 7, 0, 7); row.setSpacing(16)
            name = QLabel(title); name.setObjectName("rowTitle"); row.addWidget(name, 1)
            combo.setMinimumWidth(230); combo.setMaximumWidth(300); row.addWidget(combo)
            layout.addWidget(line)
        actions = QHBoxLayout(); actions.setContentsMargins(0, 6, 0, 0); actions.addStretch()
        self.sign_in = QPushButton()
        self.refresh = QPushButton()
        actions.addWidget(self.sign_in); actions.addWidget(self.refresh)
        layout.addLayout(actions)
        self.note = QLabel(); self.note.setWordWrap(True); self.note.setObjectName("rowHint"); layout.addWidget(self.note)
        self.apply(settings)
        self.provider.currentIndexChanged.connect(self._switch)
        self.model.currentIndexChanged.connect(self._change)
        self.model.editTextChanged.connect(self._change)
        self.sign_in.clicked.connect(lambda: self._connect(True))
        self.refresh.clicked.connect(lambda: self._connect(False))

    def apply(self, settings):
        self.openrouter = settings.openrouter_model or settings.model
        self.codex = settings.codex_model
        self.claude = LEGACY_ALIASES.get(settings.claude_model, settings.claude_model) or DEFAULT_CLAUDE_MODEL
        with QSignalBlocker(self.provider):
            self.provider.setCurrentIndex(self.provider.findData(settings.llm_provider))
        self._populate()

    def _labels(self):
        claude = self.provider.currentData() == 'claude'
        self.sign_in.setText('Sign in to Claude' if claude else 'Sign in to ChatGPT')
        self.refresh.setText('Check Claude sign-in' if claude else 'Check connection / models')

    def _populate(self):
        codex = self.provider.currentData() == 'codex'
        claude = self.provider.currentData() == 'claude'
        with QSignalBlocker(self.model):
            self.model.clear(); self.model.setEditable(not codex and not claude)
            if claude:
                for name, model in CLAUDE_MODELS: self.model.addItem(name, model)
                index = self.model.findData(self.claude)
                if index < 0:
                    self.model.addItem(self.claude, self.claude); index = self.model.count() - 1
                self.model.setCurrentIndex(index)
            elif codex:
                self.model.addItem('Codex default model', '')
                for model in self.models: self.model.addItem(model['name'], model['id'])
                index = self.model.findData(self.codex)
                if index < 0:
                    self.model.addItem(self.codex, self.codex); index = self.model.count() - 1
                self.model.setCurrentIndex(index)
            else: self.model.addItem(self.openrouter)
        self._labels()
        self.sign_in.setVisible(codex or claude); self.refresh.setVisible(codex or claude)
        self.note.setText('Uses your ChatGPT/Codex plan limits. Sign in once for this assistant, then check models. Character and memory stay the same.' if codex else
                          'Uses your Claude Pro/Max plan through the Claude Code CLI on this computer. No API key is needed or used. Character and memory stay the same.' if claude else
                          'Enter an OpenRouter model ID. The API key stays in .env. Changing models keeps your character and conversation.')

    def _switch(self):
        self._populate(); self.changed.emit()

    def _change(self):
        if self.provider.currentData() == 'codex': self.codex = self.model.currentData() or ''
        elif self.provider.currentData() == 'claude': self.claude = self.model.currentData() or DEFAULT_CLAUDE_MODEL
        else: self.openrouter = self.model.currentText().strip()
        self.changed.emit()

    def values(self):
        return dict(llm_provider=self.provider.currentData(), openrouter_model=self.openrouter,
                    model=self.openrouter, codex_model=self.codex, claude_model=self.claude)

    def _connect(self, login):
        if self.worker is not None:
            self.worker.stop(); self.note.setText('Cancelling sign-in…'); return
        provider = self.provider.currentData()
        worker = ConnectionWorker(login, self, provider)
        self.worker = worker
        self.provider.setEnabled(False); self.model.setEnabled(False)
        self.sign_in.setText('Cancel sign-in' if login else 'Cancel check')
        self.refresh.setEnabled(False)
        if provider == 'claude':
            self.note.setText('Checking Claude sign-in. If needed, finish sign-in in the Claude Code window and browser…' if login else
                              'Checking Claude Code sign-in…')
        else:
            self.note.setText('Opening ChatGPT sign-in…' if login else 'Checking Codex and its model catalog…')
        worker.browser_requested.connect(self._open_login)
        worker.ready.connect(self._connected)
        worker.failed.connect(self.note.setText)
        worker.finished.connect(self._finished)
        worker.start()

    def _open_login(self, url):
        self.note.setText('Finish sign-in in your browser. Credentials stay with the local Codex profile.')
        if not QDesktopServices.openUrl(QUrl(url)):
            self.note.setText('Could not open the sign-in browser. Check your default browser and try again.')
            self.worker.stop()

    def _connected(self, result):
        if 'plan' in result:
            plan = f' ({result["plan"]} plan)' if result['plan'] else ''
            self.note.setText(f'Signed in to Claude{plan}. Replies use your plan limits; no API key or other provider is used.' if result['signed_in'] else
                              'Claude Code is installed but not signed in. Click Sign in to Claude.')
            return
        self.models = result['models']; self._populate()
        self.note.setText('Signed in with ChatGPT. Access depends on your plan; unavailable models show an error and never trigger a paid fallback.' if result['signed_in'] else
                          'Codex is available. Sign in to ChatGPT to use your subscription. The catalog alone does not confirm model access.')

    def _finished(self):
        worker, self.worker = self.worker, None
        self._labels(); self.refresh.setEnabled(True)
        self.provider.setEnabled(True); self.model.setEnabled(True)
        if worker is not None: worker.deleteLater()

    def shutdown(self):
        if self.worker is not None:
            self.worker.stop(); self.worker.wait(6000)
