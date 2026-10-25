"""Read command lines from the app without freezing the engine on Windows.

The voice and microphone engines read commands on a background thread. A blocking read left
pending on a Windows pipe stalls other threads that touch the same handle, and loading native
libraries (numpy, torch, ctranslate2, PortAudio) does exactly that: the engine froze while
"loading", using no CPU. Here the pipe is only peeked at, and read when data is waiting.
"""

import os
import sys
import time

POLL_SECONDS = 0.02


def lines(stream):
    """Yield text lines from `stream`, never leaving a blocking read pending on a Windows pipe."""
    try:
        fd = stream.fileno()
    except (AttributeError, OSError, ValueError):
        yield from stream  # In-memory streams (tests) cannot block.
        return
    if sys.platform != "win32":
        yield from stream
        return
    import ctypes
    import msvcrt
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.GetFileType.argtypes = (wintypes.HANDLE,)
    kernel32.PeekNamedPipe.argtypes = (wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD, ctypes.c_void_p,
                                       ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p)
    kernel32.PeekNamedPipe.restype = wintypes.BOOL
    handle = msvcrt.get_osfhandle(fd)
    if kernel32.GetFileType(handle) != 3:  # FILE_TYPE_PIPE; a file or console is read normally.
        yield from stream
        return
    buffer = b""
    available = wintypes.DWORD()
    while kernel32.PeekNamedPipe(handle, None, 0, None, ctypes.byref(available), None):
        if not available.value:
            time.sleep(POLL_SECONDS)
            continue
        buffer += os.read(fd, available.value)
        while b"\n" in buffer:
            line, buffer = buffer.split(b"\n", 1)
            yield line.decode("utf-8", "replace") + "\n"
    # The app closed the pipe (or exited): finish with whatever is left.
    if buffer:
        yield buffer.decode("utf-8", "replace")
