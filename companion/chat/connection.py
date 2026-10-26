"""Account/model discovery runs outside the UI thread; no credentials leave the CLIs."""
import asyncio
import threading
from PySide6.QtCore import QThread, Signal
from . import claude as claude_backend
from .codex import connect
from .llm import ChatError


async def connect_claude(login=False):
    result = await claude_backend.account()
    if login and not result['signed_in']:
        claude_backend.open_login()
        # Sign-in finishes in Claude Code's own window; wait for it to report success.
        while not result['signed_in']:
            await asyncio.sleep(2)
            result = await claude_backend.account()
    return result


class ConnectionWorker(QThread):
    ready = Signal(object)
    failed = Signal(str)
    browser_requested = Signal(str)

    def __init__(self, login=False, parent=None, provider='codex'):
        super().__init__(parent)
        self.login = login
        self.provider = provider
        self.name = 'Claude Code' if provider == 'claude' else 'Codex'
        self.loop = self.task = None
        self.cancelled = threading.Event()

    def run(self):
        try: asyncio.run(self._run())
        except asyncio.CancelledError: self.failed.emit(f'{self.name} connection cancelled.')
        except ChatError as exc: self.failed.emit(str(exc))
        except TimeoutError: self.failed.emit(f'{self.name} connection timed out. Try again from Settings.')
        except Exception: self.failed.emit(f'Could not connect to {self.name}. Check the installation and try again.')
        finally: self.loop = self.task = None

    async def _run(self):
        self.loop = asyncio.get_running_loop(); self.task = asyncio.current_task()
        if self.cancelled.is_set(): return
        async with asyncio.timeout(300 if self.login else 30):
            if self.provider == 'claude':
                self.ready.emit(await connect_claude(self.login))
            else:
                self.ready.emit(await connect(self.login, self.browser_requested.emit))

    def stop(self):
        self.cancelled.set()
        if self.loop and self.task:
            try: self.loop.call_soon_threadsafe(self.task.cancel)
            except RuntimeError: pass
