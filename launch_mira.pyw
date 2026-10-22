"""Double-click/shortcut target; diagnostic failures do not require Qt to show a message."""

if __name__ == "__main__":
    try:
        from companion.launcher import launch
    except Exception:
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, "Project files are missing or unreadable. Restore the project folder and run Setup Mira.cmd.",
                                       "Desktop Companion", 0x10)
        raise SystemExit(1)
    raise SystemExit(launch())
