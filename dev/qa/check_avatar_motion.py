"""Opt-in native motion/lifecycle check. Offline; temporary conversation store.

Use --audio to play a short cached local voice sample and check real interruption.
No microphone, external model requests or settings/credential reads. Reports and
avatar-only screenshots stay ignored under .cache/head-motion-checkpoint5.
"""
import argparse
import base64
import json
import math
import os
from pathlib import Path
import sys
import tempfile
import time
from unittest.mock import patch
import httpx
from shiboken6 import isValid

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.environ['HF_HUB_OFFLINE'] = '1'
from PySide6.QtCore import QEvent, QPoint
from PySide6.QtWidgets import QApplication
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineScript
from companion.core.config import DEFAULT_MODEL, Settings
from companion.core.preferences import Preferences
from companion.core.storage import Store
from companion.ui.window import CompanionWindow
from windows_process_metrics import sample_tree


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--audio', action='store_true')
    args = parser.parse_args()
    app = QApplication([])
    app.setStyle('Fusion')
    folder = tempfile.TemporaryDirectory()
    store = Store(':memory:')
    settings = Settings('offline-check', DEFAULT_MODEL, 'Motion check', 'Offline check',
                        character_path=str(ROOT / 'character.toml'), tts_enabled=False)
    class CheckPage(QWebEnginePage):
        def __init__(self,*args):
            super().__init__(*args)
            script=QWebEngineScript()
            script.setName('Isolated motion check randomness')
            script.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentCreation)
            script.setWorldId(QWebEngineScript.ScriptWorldId.MainWorld)
            script.setSourceCode('Math.random=()=>0.1;')
            self.scripts().insert(script)

    # Install before any controller captures Math.random. This isolated test
    # cannot depend on an 80% notice chance; real sessions keep normal randomness.
    page_patch=patch('companion.avatar.mesh.QWebEnginePage',CheckPage)
    page_patch.start()
    window = CompanionWindow(settings, store=store,
                             preferences=Preferences(Path(folder.name) / 'preferences.json'))
    window.show()
    window.show_avatar.setChecked(True)
    widget = window.avatar.widget
    out = ROOT / '.cache/head-motion-checkpoint5'
    out.mkdir(parents=True, exist_ok=True)
    report = {'checks': {}, 'phases': [], 'logical_cpus': os.cpu_count(), 'audio': args.audio,
              'display_scale_ratios': [screen.devicePixelRatio() for screen in app.screens()]}
    errors = []
    window.speech.failed.connect(errors.append)

    def wait(condition, timeout=25):
        end = time.monotonic() + timeout
        while not condition():
            app.processEvents()
            # This check pumps Qt manually rather than app.exec(); emulate its
            # deferred deletion boundary so old renderer pages are released.
            app.sendPostedEvents(None,QEvent.Type.DeferredDelete)
            time.sleep(.005)
            if time.monotonic() > end:
                raise RuntimeError('Native motion check timed out')

    def delay(seconds):
        end = time.monotonic() + seconds
        wait(lambda: time.monotonic() >= end, seconds + 2)

    def js(code):
        values = []
        widget.page.runJavaScript(code, lambda value: values.append(value))
        wait(lambda: bool(values), 5)
        return values[0]

    def state():
        value = json.loads(js('JSON.stringify(avatarDiagnostics())'))
        assert all(math.isfinite(v) for v in value['parameters'].values())
        assert 0 <= value['parameters']['breath'] <= 1.15
        return value

    def save_frame(name):
        # Only this renderer's canvas, never the user's desktop.
        value = js("document.querySelector('canvas').toDataURL('image/png').split(',')[1]")
        (out / (name + '.png')).write_bytes(base64.b64decode(value))

    def activity(name):
        window.activity_changed.emit(name)
        delay(.7)

    def measure(name, seconds=6):
        before = sample_tree()
        initial = state()['frames']
        start = time.monotonic()
        memory = []
        while time.monotonic() - start < seconds:
            memory.append(sum(v[1] for v in sample_tree().values()) / 1024**2)
            delay(.2)
        after = sample_tree()
        elapsed = time.monotonic() - start
        cpu = sum(max(0, v[0] - before.get(pid, (0, 0))[0]) for pid, v in after.items())
        result = {'phase': name, 'seconds': round(elapsed, 2),
                  'cpu_machine_percent': round(cpu / elapsed * 100 / (os.cpu_count() or 1), 2),
                  'mean_working_set_mib': round(sum(memory)/len(memory), 1),
                  'draws_per_second': round((state()['frames']-initial)/elapsed, 2),
                  'activity':state()['activity'],'target_fps':state()['targetFps']}
        report['phases'].append(result)
        print(json.dumps(result), flush=True)

    try:
        wait(lambda: getattr(widget, 'ready', False) or getattr(widget, 'failed', False))
        assert widget.ready, 'Restore local avatar and Qt WebEngine dependencies'
        delay(1)
        js("window.motionCheckErrors=[];window.addEventListener('error',()=>motionCheckErrors.push('script error'));window.addEventListener('unhandledrejection',()=>motionCheckErrors.push('unhandled rejection'));true;")
        cursor = widget.view.mapToGlobal(QPoint(widget.view.width()+100, widget.view.height()//4))
        events = []
        widget.bridge.cursorChanged.connect(lambda x,y,valid,seq: events.append((x,y,valid,seq)))
        with patch('companion.avatar.mesh.QCursor.pos', return_value=cursor):
            # Geometry changes force a fresh local sample without moving OS input.
            widget._cursor_sample = None
            widget._sample_cursor()
            wait(lambda: state()['motion']['attention']['notices'] > 0, 12)
            assert state()['motion']['attention']['kind'] == 'cursor'
            delay(1.7)
            save_frame('cursor-glance')
            assert any(e[2] and e[0] > 1 for e in events)
        window.avatar_cursor_attention.setChecked(False)
        delay(.3)
        assert not widget.cursor_timer.isActive()
        notices = state()['motion']['attention']['notices']
        delay(2)
        assert state()['motion']['attention']['notices'] == notices
        report['checks']['global_cursor_mapping_and_off_switch'] = True
        for name, mode, expression in [('listening','listening','neutral'),
                                       ('thinking','thinking','halfLidded'),
                                       ('speaking','speaking','neutral')]:
            activity(name)
            assert state()['visualMode'] == mode
            assert state()['expression'] == expression
            assert not widget.cursor_timer.isActive()
            save_frame(name)
        assert state()['parameters']['mouthOpen'] < .01, 'State alone must not talk'
        activity('ready')
        measure('idle_before_voice_load')
        window.avatar_motion.setValue(0)
        window.avatar_gaze.setValue(0)
        window.avatar_hair.setValue(70)
        delay(2.6)
        current = state()
        for key in ['angleX','angleY','angleZ','bodyAngleX','bodyAngleZ','gazeX','gazeY']:
            assert current['parameters'][key] == 0, (key, current['parameters'][key])
        window._save_preferences()
        loaded = window.preferences.load(settings)
        assert (loaded.avatar_motion,loaded.avatar_gaze,loaded.avatar_hair,loaded.avatar_cursor_attention) == (0,0,70,False)
        window.avatar_motion.setValue(100)
        window.avatar_gaze.setValue(100)
        window.avatar_hair.setValue(45)
        widget.resize(440,470)
        delay(.3)
        widget.resize(320,350)
        window.animate_avatar.setChecked(False)
        delay(.2)
        before = state()['frames']
        delay(.5)
        assert state()['frames'] == before and not widget.cursor_timer.isActive()
        window.animate_avatar.setChecked(True)
        delay(.2)
        assert state()['frames'] > before
        activity('suspended')
        before = state()['frames']
        delay(.3)
        assert state()['frames'] == before and not widget.cursor_timer.isActive()
        activity('ready')
        report['checks']['states_controls_persistence_resize_pause'] = True
        if args.audio:
            print('Checking cached local speech and real playback interruption.', flush=True)
            levels = []
            window.speech.playback_level.connect(lambda v: levels.append(v))
            window.speech.speak('The moon is quiet tonight. There is no need to hurry. We can take the next step together.', 'alba', 35, 100)
            wait(lambda: window.speech.state == 'speaking' or bool(errors), 120)
            assert not errors, 'Cached voice unavailable'
            # Playback bridge carries actual output envelopes; sample mouth and nod.
            samples = []
            speech_saved=False
            cpu_before=sample_tree()
            first_frame=state()['frames']
            memory=[]
            began=time.monotonic()
            end = time.monotonic()+6
            while time.monotonic()<end and window.speech.busy:
                samples.append(state())
                memory.append(sum(v[1] for v in sample_tree().values())/1024**2)
                if not speech_saved and samples[-1]['parameters']['mouthOpen']>.15:
                    save_frame('actual-speech')
                    speech_saved=True
                delay(.08)
            cpu_after=sample_tree()
            duration=time.monotonic()-began
            cpu=sum(max(0,v[0]-cpu_before.get(pid,(0,0))[0]) for pid,v in cpu_after.items())
            result={'phase':'speech_playback','seconds':round(duration,2),
                    'cpu_machine_percent':round(cpu/duration*100/(os.cpu_count() or 1),2),
                    'mean_working_set_mib':round(sum(memory)/len(memory),1),
                    'draws_per_second':round((state()['frames']-first_frame)/duration,2)}
            report['phases'].append(result)
            print(json.dumps(result),flush=True)
            assert max(levels,default=0)>.05 and max(v['parameters']['mouthOpen'] for v in samples)>.1
            assert max(v['motion']['nod'] for v in samples)>.01
            wait(lambda: not window.speech.busy or bool(errors), 120)
            assert not errors
            delay(.3)
            assert state()['parameters']['mouthOpen'] < .01
            window.speech.speak('We can continue when you are ready. There is no need to rush this conversation.', 'alba', 35, 100)
            wait(lambda: window.speech.state == 'speaking' or bool(errors), 60)
            delay(.4)
            window._stop()
            delay(.35)
            assert not window.speech.busy
            assert state()['parameters']['mouthOpen'] < .01 and state()['motion']['nod'] == 0
            report['checks']['real_speech_output_and_interruption'] = True
        client=httpx.AsyncClient
        def reply(request):
            return httpx.Response(200,text='data: {"choices":[{"delta":{"content":"All right. I am listening."},"finish_reason":"stop"}]}\n\ndata: [DONE]\n\n')
        with patch('companion.chat.worker.httpx.AsyncClient',side_effect=lambda **kw:client(
                transport=httpx.MockTransport(reply),trust_env=False,**kw)):
            for index in range(3):
                window.input.setPlainText(f'Offline verification turn {index+1}')
                window._send()
                wait(lambda:window._worker is None,10)
            assert len(window._messages)==6
        report['checks']['three_mocked_conversations']=True
        assert js('JSON.stringify(motionCheckErrors)')=='[]'
        report['checks']['no_renderer_errors']=True
        for index in range(3):
            old = widget
            window.avatar.reload_avatar()
            widget = window.avatar.widget
            wait(lambda: widget.ready or widget.failed)
            assert widget.ready and old._disposed
            assert not isValid(old.cursor_timer) or not old.cursor_timer.isActive()
            delay(.2)
        report['checks']['three_reloads'] = True
        window.show_avatar.setChecked(False)
        delay(.3)
        assert not widget.cursor_timer.isActive()
        measure('hidden')
        assert state()['paused'] and not state()['visible']
        before=state()['frames']
        delay(.3)
        assert state()['frames']==before
        window.show_avatar.setChecked(True)
        delay(.2)
        assert state()['frames']>before
        report['checks']['hidden_stops_rendering_and_polling'] = True
        report['checks']['finite_stable_parameters'] = True
    finally:
        window.request_quit()
        window.deleteLater()
        app.sendPostedEvents(None,QEvent.Type.DeferredDelete)
        app.processEvents()
        store.close()
        folder.cleanup()
        report['checks']['shutdown'] = window.avatar._shutdown and window.avatar.widget is None
        (out/'verification.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        import shiboken6
        shiboken6.delete(app)
        page_patch.stop()
    print(json.dumps(report['checks']), flush=True)


if __name__ == '__main__':
    main()
