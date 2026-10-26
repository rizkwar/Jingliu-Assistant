"""Give memory back to Windows while the companion sits unused in the background.

Trimming a working set moves idle pages out of RAM; Windows brings back what is needed the
moment the window is used again. Nothing is lost, and Task Manager shows the true idle size.
"""

import gc
import sys


def trim(pids=()):
    """Trim this process (after a garbage collection) and any of the given processes."""
    if sys.platform != "win32":
        return
    import ctypes
    from ctypes import wintypes
    gc.collect()
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
    psapi.EmptyWorkingSet.argtypes = (wintypes.HANDLE,)
    psapi.EmptyWorkingSet(kernel32.GetCurrentProcess())
    for pid in pids:
        if not pid:
            continue
        # PROCESS_SET_QUOTA | PROCESS_QUERY_LIMITED_INFORMATION: enough to trim, nothing more.
        handle = kernel32.OpenProcess(0x0100 | 0x1000, False, int(pid))
        if handle:
            psapi.EmptyWorkingSet(handle)
            kernel32.CloseHandle(handle)
