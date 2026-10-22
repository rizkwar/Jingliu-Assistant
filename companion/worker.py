import asyncio
import threading
from uuid import uuid4

import httpx
from PySide6.QtCore import QThread, Signal

from .config import Settings
from .llm import ChatError, stream_reply


class ReplyWorker(QThread):
    chunk = Signal(str, str)

    def __init__(self, settings: Settings, messages: list[dict[str, str]], parent=None):
        super().__init__(parent)
        self.turn_id = uuid4().hex
        self.settings = settings
        self.messages = messages
        self.error = ""
        self.stop_requested = threading.Event()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._task: asyncio.Task | None = None

    def stop(self) -> None:
        self.stop_requested.set()
        loop, task = self._loop, self._task
        if loop is not None and task is not None:
            try:
                loop.call_soon_threadsafe(task.cancel)
            except RuntimeError:
                pass  # The loop already finished.

    def run(self) -> None:
        try:
            asyncio.run(self._generate())
        except asyncio.CancelledError:
            pass
        except (ChatError, ValueError) as exc:
            self.error = str(exc).replace(self.settings.api_key, "[redacted]")
        except Exception:
            # Never dump credentials, transcripts, or provider internals into logs.
            self.error = "An unexpected error occurred while generating the reply. Try again."
        finally:
            self._loop = None
            self._task = None

    async def _generate(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._task = asyncio.current_task()
        if self.stop_requested.is_set():
            return
        timeout = httpx.Timeout(90.0, connect=15.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            # A total deadline also bounds a provider that only sends keep-alives.
            try:
                async with asyncio.timeout(180):
                    async for text in stream_reply(client, self.settings, self.messages):
                        if self.stop_requested.is_set():
                            return
                        self.chunk.emit(self.turn_id, text)
            except TimeoutError as exc:
                raise ChatError("The reply took too long. Please try again.") from exc

