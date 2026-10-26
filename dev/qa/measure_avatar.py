"""Opt-in Windows native QA and resource measurement. Plays local test speech.

No model API requests or microphone capture. Uses a temporary empty chat store.
Results contain measurements and test outcomes, never credentials or conversations.
"""
import json
import os
from pathlib import Path
import sys
import tempfile
import time
from dataclasses import replace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.environ['HF_HUB_OFFLINE'] = '1'

import httpx
from PySide6.QtCore import QEvent
from PySide6.QtWidgets import QApplication
from PySide6.QtWidgets import QScrollArea
from companion.core.config import load_settings
from companion.core.preferences import Preferences
from companion.core.storage import Store
from companion.ui.window import CompanionWindow
from windows_process_metrics import sample_tree


def main():
    app = QApplication([])
    app.setStyle('Fusion')
    temporary = tempfile.TemporaryDirectory()
    defaults = Preferences(ROOT / 'data/preferences.json').load(load_settings())
    settings = replace(defaults, api_key='offline-check', llm_provider='openrouter',
                       tts_enabled=False, avatar_enabled=False, avatar_hd=True,
                       avatar_animated=True, avatar_width=320, avatar_height=350,
                       avatar_motion=100, avatar_lip_sensitivity=100)
    store = Store(':memory:')
    window = CompanionWindow(settings, store=store, preferences=Preferences(Path(temporary.name) / 'preferences.json'))
    errors = []
    window.speech.failed.connect(errors.append)
    window.show(); window.show_avatar.setChecked(True)
    widget = window.avatar.widget

    def wait(condition, timeout=120):
        end = time.monotonic() + timeout
        while not condition():
            app.processEvents(); time.sleep(.005)
            if time.monotonic() > end:
                raise RuntimeError('Native check timed out')

    def delay(seconds):
        end = time.monotonic() + seconds
        wait(lambda: time.monotonic() >= end, seconds + 2)

    def state():
        result = []
        widget.page.runJavaScript('JSON.stringify(avatarDiagnostics())', lambda value: result.append(json.loads(value)))
        wait(lambda: bool(result), 5)
        return result[0]

    def speak(text):
        window.speech.speak(text, window._speech_voice(), min(50, window.volume.value()), window.delivery_rate.value())

    def measure(name, seconds=8):
        before = sample_tree(); initial_frames = state()['frames']; start = time.monotonic()
        memory = []; counts = []
        while time.monotonic() - start < seconds:
            snapshot = sample_tree()
            memory.append(sum(value[1] for value in snapshot.values()) / 1024**2)
            counts.append(len(snapshot))
            delay(.2)
        after = sample_tree(); duration = time.monotonic() - start
        cpu = sum(max(0, value[0] - before.get(pid, (0, 0))[0]) for pid, value in after.items())
        result = {'phase':name, 'seconds':round(duration, 2), 'cpu_one_core_percent':round(cpu / duration * 100, 2),
                  'cpu_machine_percent':round(cpu / duration * 100 / (os.cpu_count() or 1), 2),
                  'mean_working_set_mib':round(sum(memory) / len(memory), 1), 'peak_working_set_mib':round(max(memory), 1),
                  'process_count_min':min(counts), 'process_count_max':max(counts),
                  'draws':state()['frames'] - initial_frames}
        result['draws_per_second'] = round(result['draws'] / duration, 2)
        print(json.dumps(result), flush=True)
        return result

    report = {'logical_cpus':os.cpu_count(), 'cpu':os.environ.get('PROCESSOR_IDENTIFIER', 'unknown'),
              'window_logical_pixels':[320, 350], 'hd':True,
              'offline_tts':True, 'phases':[], 'checks':{}}
    try:
        wait(lambda: getattr(widget, 'ready', False) or getattr(widget, 'failed', False), 25)
        if not getattr(widget, 'ready', False):
            raise RuntimeError('Restore the local rig and Qt WebEngine dependencies before measuring')
        print('Warming the cached local voice; no microphone or online model requests.', flush=True)
        speak('All right. You have my attention.')
        wait(lambda: not window.speech.busy)
        if errors:
            raise RuntimeError('Cached local voice unavailable; preview it normally before measuring')
        window.show_avatar.setChecked(False); delay(1)
        report['phases'].append(measure('hidden_with_voice_loaded'))
        assert report['phases'][-1]['draws'] == 0
        window.show_avatar.setChecked(True); delay(1)
        report['phases'].append(measure('idle_with_voice_loaded'))
        speak('The moon is quiet tonight. There is no need to hurry. We can take the next step together, and if something needs attention, we will deal with it one thing at a time.')
        wait(lambda: window.speech.state == 'speaking' or bool(errors))
        if errors: raise RuntimeError('Local voice failed')
        report['phases'].append(measure('speech_playback'))
        wait(lambda: not window.speech.busy); delay(.3)
        assert state()['parameters']['mouthOpen'] < .01
        # Real interrupted playback, including a future pending mouth update.
        speak('We can continue when you are ready. There is no need to rush this conversation.')
        wait(lambda: window.speech.state == 'speaking' or bool(errors))
        if errors: raise RuntimeError('Local voice failed')
        delay(.3); window._stop(); delay(.3)
        assert not window.speech.busy and state()['parameters']['mouthOpen'] < .01
        report['checks']['live_playback_and_interruption'] = True
        # Repeated conversations use mocked HTTP, with the real Qt worker and storage.
        client = httpx.AsyncClient
        def reply(request):
            return httpx.Response(200, text='data: {"choices":[{"delta":{"content":"All right. I am listening."},"finish_reason":"stop"}]}\n\ndata: [DONE]\n\n')
        with patch('companion.chat.worker.httpx.AsyncClient', side_effect=lambda **kw: client(
                transport=httpx.MockTransport(reply), trust_env=False, **kw)):
            for index in range(3):
                window.input.setPlainText(f'Offline verification turn {index + 1}')
                window._send(); wait(lambda: window._worker is None, 10)
            assert len(window._messages) == 6
        report['checks']['three_mocked_conversation_turns'] = True
        window.avatar_size.setValue(440); delay(.2)
        assert widget.width() == 440
        widget.resize(500, 520); delay(.2)
        assert window.avatar.dimensions() == (500, 520)
        window.avatar_motion.setValue(0); window.avatar_lip_sensitivity.setValue(160); delay(.4)
        assert state()['movement'] == 0 and state()['sensitivity'] == 1.6
        window._save_preferences()
        restored = window.preferences.load(settings)
        assert (restored.avatar_width, restored.avatar_height, restored.avatar_motion, restored.avatar_lip_sensitivity) == (500, 520, 0, 160)
        report['checks']['resize_controls_and_persistence'] = True
        window.open_settings(); delay(.2)
        window.settings_dialog.findChild(QScrollArea).ensureWidgetVisible(window.avatar_lip_sensitivity)
        delay(.2)
        window.settings_dialog.grab().save(str(ROOT / '.cache/stage7-controls.png'))
        window.settings_dialog.hide()
        for index in range(5):
            old = widget
            window.avatar.reload_avatar(); widget = window.avatar.widget
            wait(lambda: widget.ready or widget.failed, 25)
            assert widget.ready and old._disposed
            delay(.1)
            assert (widget.width(), widget.height()) == (500, 520)
        report['checks']['five_avatar_reloads'] = True
        window.show_avatar.setChecked(False); delay(.3)
        before = state()['frames']; delay(.5)
        assert state()['frames'] == before
        report['checks']['hidden_frames_stopped_after_reload'] = True
    finally:
        owned = set(sample_tree()) - {os.getpid()}
        window.request_quit(); window.deleteLater()
        app.sendPostedEvents(None, QEvent.Type.DeferredDelete); app.processEvents()
        store.close(); temporary.cleanup()
        report['checks']['shutdown'] = window.avatar._shutdown and window.avatar.widget is None
        # Chromium's shared GPU/utility children live until QApplication teardown.
        # Include that normal exit boundary before testing for orphaned children.
        import shiboken6
        shiboken6.delete(app)
        time.sleep(.5)
        survivors = owned & (set(sample_tree()) - {os.getpid()})
        report['checks']['owned_child_processes_reaped'] = not survivors
        # Never persist paths, prompts, tokens or chat data in the report.
        output = ROOT / '.cache/avatar-performance.json'
        output.parent.mkdir(exist_ok=True)
        output.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report['checks']), flush=True)
    if survivors:
        raise RuntimeError('A child process outlived the shutdown check')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
