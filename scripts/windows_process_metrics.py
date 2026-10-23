"""Read CPU time and working sets for this process tree; no command lines collected."""
import ctypes as c
from ctypes import wintypes as w
import os


class Entry(c.Structure):
    _fields_ = [('size', w.DWORD), ('usage', w.DWORD), ('pid', w.DWORD),
                ('heap', c.c_size_t), ('module', w.DWORD), ('threads', w.DWORD),
                ('parent', w.DWORD), ('priority', w.LONG), ('flags', w.DWORD), ('name', w.WCHAR * 260)]


class Memory(c.Structure):
    _fields_ = [('size', w.DWORD), ('faults', w.DWORD)] + [
        (name, c.c_size_t) for name in ('peak_working', 'working', 'peak_paged', 'paged',
                                      'peak_nonpaged', 'nonpaged', 'pagefile', 'peak_pagefile')]


def sample_tree():
    if os.name != 'nt':
        raise RuntimeError('This measurement helper requires Windows.')
    kernel = c.WinDLL('kernel32', use_last_error=True)
    kernel.CreateToolhelp32Snapshot.argtypes = [w.DWORD, w.DWORD]
    kernel.CreateToolhelp32Snapshot.restype = w.HANDLE
    kernel.Process32FirstW.argtypes = kernel.Process32NextW.argtypes = [w.HANDLE, c.POINTER(Entry)]
    kernel.CloseHandle.argtypes = [w.HANDLE]
    kernel.OpenProcess.argtypes = [w.DWORD, w.BOOL, w.DWORD]
    kernel.OpenProcess.restype = w.HANDLE
    kernel.GetProcessTimes.argtypes = [w.HANDLE] + [c.POINTER(w.FILETIME)] * 4
    psapi = c.WinDLL('psapi', use_last_error=True)
    psapi.GetProcessMemoryInfo.argtypes = [w.HANDLE, c.POINTER(Memory), w.DWORD]
    snapshot = kernel.CreateToolhelp32Snapshot(2, 0)
    if snapshot == c.c_void_p(-1).value:
        raise OSError('Could not enumerate process tree')
    parents = {}
    try:
        entry = Entry(); entry.size = c.sizeof(entry)
        ok = kernel.Process32FirstW(snapshot, c.byref(entry))
        while ok:
            parents[entry.pid] = entry.parent
            ok = kernel.Process32NextW(snapshot, c.byref(entry))
    finally:
        kernel.CloseHandle(snapshot)
    selected = {os.getpid()}
    while True:
        more = {pid for pid, parent in parents.items() if parent in selected}
        if more <= selected:
            break
        selected |= more
    result = {}
    for pid in selected:
        handle = kernel.OpenProcess(0x410, False, pid)
        if not handle:
            raise OSError('Could not query an assistant child process')
        try:
            created, exited, system, user = [w.FILETIME() for _ in range(4)]
            memory = Memory(); memory.size = c.sizeof(memory)
            if not (kernel.GetProcessTimes(handle, c.byref(created), c.byref(exited), c.byref(system), c.byref(user))
                    and psapi.GetProcessMemoryInfo(handle, c.byref(memory), c.sizeof(memory))):
                raise OSError('Could not read assistant process counters')
            seconds = sum((value.dwHighDateTime << 32) | value.dwLowDateTime for value in (system, user)) / 1e7
            result[pid] = (seconds, memory.working)
        finally:
            kernel.CloseHandle(handle)
    return result
