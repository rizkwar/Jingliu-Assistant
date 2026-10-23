"""Compare native HD renderer costs without loading voice models or contacting APIs.

Run before and after a renderer change with different --label values. Reports
contain process counters and renderer diagnostics, never settings or chat data.
"""
import argparse
import json
import os
from pathlib import Path
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QEvent
from PySide6.QtWidgets import QApplication
from companion.config import DEFAULT_MODEL, Settings
from companion.preferences import Preferences
from companion.storage import Store
from companion.ui import CompanionWindow
from windows_process_metrics import sample_tree


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--label', choices=['before', 'after'], required=True)
    args = parser.parse_args()
    app = QApplication([])
    app.setStyle('Fusion')
    folder = tempfile.TemporaryDirectory()
    store = Store(':memory:')
    settings = Settings('', DEFAULT_MODEL, 'Renderer check', 'Offline check',
                        character_path=str(ROOT / 'character.toml'), tts_enabled=False,
                        avatar_hd=True, avatar_width=320, avatar_height=350)
    window = CompanionWindow(settings, store=store,
                             preferences=Preferences(Path(folder.name) / 'preferences.json'))
    window.show()
    window.show_avatar.setChecked(True)
    widget = window.avatar.widget

    def wait(condition, timeout=25):
        end = time.monotonic() + timeout
        while not condition():
            app.processEvents()
            time.sleep(.005)
            if time.monotonic() > end:
                raise RuntimeError('Renderer check timed out')

    def delay(seconds):
        end = time.monotonic() + seconds
        wait(lambda: time.monotonic() >= end, seconds + 2)

    def state():
        result = []
        widget.page.runJavaScript('JSON.stringify(avatarDiagnostics())',
                                 lambda value: result.append(json.loads(value)))
        wait(lambda: bool(result), 5)
        return result[0]

    def measure(phase):
        before = sample_tree()
        initial = state()
        start = time.monotonic()
        memory = []
        while time.monotonic() - start < 8:
            snapshot = sample_tree()
            memory.append(sum(value[1] for value in snapshot.values()) / 1024**2)
            delay(.2)
        after = sample_tree()
        duration = time.monotonic() - start
        cpu = sum(max(0, value[0] - before.get(pid, (0, 0))[0])
                  for pid, value in after.items())
        final = state()
        result = {'phase': phase, 'seconds': round(duration, 2),
                  'cpu_machine_percent': round(cpu / duration * 100 / (os.cpu_count() or 1), 2),
                  'mean_working_set_mib': round(sum(memory) / len(memory), 1),
                  'draws_per_second': round((final['frames'] - initial['frames']) / duration, 2),
                  'canvas': final['canvas']}
        print(json.dumps(result), flush=True)
        return result

    report = {'logical_cpus': os.cpu_count(), 'hd': True, 'voice_loaded': False,
              'window_logical_pixels': [320, 350], 'phases': []}
    (ROOT / '.cache').mkdir(exist_ok=True)
    try:
        wait(lambda: getattr(widget, 'ready', False) or getattr(widget, 'failed', False))
        if not widget.ready:
            raise RuntimeError('Restore the assigned local avatar and Qt WebEngine first')
        delay(2)
        for phase, activity in [('idle_first', 'ready'), ('thinking', 'thinking'),
                                ('idle_second', 'ready')]:
            window.activity_changed.emit(activity)
            delay(2)
            report['phases'].append(measure(phase))
        widget.grab().save(str(ROOT / f'.cache/avatar-rendering-{args.label}.png'))
        window.show_avatar.setChecked(False)
        delay(.5)
        report['phases'].append(measure('hidden'))
        assert report['phases'][-1]['draws_per_second'] == 0
    finally:
        window.request_quit()
        window.deleteLater()
        app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        app.processEvents()
        store.close()
        folder.cleanup()
        import shiboken6
        shiboken6.delete(app)
    output = ROOT / f'.cache/avatar-rendering-{args.label}.json'
    output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps(report, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
