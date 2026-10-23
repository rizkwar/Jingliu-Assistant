"""Account/model discovery runs outside the UI thread; no credentials leave Codex."""
import asyncio
import threading
from PySide6.QtCore import QThread, Signal
from .codex_backend import connect
from .llm import ChatError


class ConnectionWorker(QThread):
    ready = Signal(object)
    failed = Signal(str)
    browser_requested = Signal(str)

    def __init__(self, login=False, parent=None):
        super().__init__(parent)
        self.login = login
        self.loop = self.task = None
        self.cancelled = threading.Event()

    def run(self):
        try: asyncio.run(self._run())
        except asyncio.CancelledError: self.failed.emit('Codex connection cancelled.')
        except ChatError as exc: self.failed.emit(str(exc))
        except TimeoutError: self.failed.emit('Codex connection timed out. Try again from Settings.')
        except Exception: self.failed.emit('Could not connect to Codex. Check the installation and try again.')
        finally: self.loop = self.task = None

    async def _run(self):
        self.loop = asyncio.get_running_loop(); self.task = asyncio.current_task()
        if self.cancelled.is_set(): return
        async with asyncio.timeout(300 if self.login else 30):
            self.ready.emit(await connect(self.login, self.browser_requested.emit))

    def stop(self):
        self.cancelled.set()
        if self.loop and self.task:
            try: self.loop.call_soon_threadsafe(self.task.cancel)
            except RuntimeError: pass
