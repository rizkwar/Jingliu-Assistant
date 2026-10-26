"""Opt-in native rig check with temporary chats/preferences/model assignments.

Only the avatar canvas and this app's settings are captured. No desktop capture,
microphone, speech generation, or response-provider requests are made.
"""

import argparse
import base64
import json
import math
from pathlib import Path
import sys
import tempfile
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from PySide6.QtCore import QEvent, QObject, Qt, Signal
from PySide6.QtWidgets import QApplication
from PySide6.QtWebEngineCore import QWebEnginePage
from companion.avatar_models import AvatarModels
from companion.config import DEFAULT_MODEL, Settings
from companion.preferences import Preferences
from companion.storage import Store
from companion.ui import CompanionWindow


class Speech(QObject):
    changed = Signal(str)
    failed = Signal(str)
    spoken = Signal(str)
    playback_level = Signal(float)
    playback_reset = Signal()
    busy = False
    state = 'idle'

    def stop(self):
        self.busy = False
        self.state = 'idle'
        self.playback_reset.emit()
        self.changed.emit('Ready')

    shutdown = stop


class Microphone(QObject):
    changed = Signal(str)
    transcribed = Signal(str)
    failed = Signal(str)
    devices = Signal(list)
    level = Signal(int)
    busy = False
    state = 'idle'

    def refresh_devices(self):
        self.devices.emit([])

    def cancel(self):
        self.changed.emit('idle')

    shutdown = cancel


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--physics', action='store_true', help='Also reproduce and check ribbon timing with the real solver.')
    args = parser.parse_args()
    installed = AvatarModels()
    profile = str(ROOT / 'character.toml')
    rigs = [m for m in installed.models(profile) if m['kind'] == 'live2d']
    if not rigs:
        raise RuntimeError('Import a local Live2D model for character.toml first.')
    original = rigs[-1]
    output = ROOT / '.cache/live2d-qa'
    output.mkdir(parents=True, exist_ok=True)
    errors = []
    class LogPage(QWebEnginePage):
        def javaScriptConsoleMessage(self, level, message, line, source):
            if level == QWebEnginePage.JavaScriptConsoleMessageLevel.ErrorMessageLevel:
                errors.append(message[:300])
    app = QApplication([])
    app.setStyle('Fusion')
    temporary = tempfile.TemporaryDirectory()
    models = AvatarModels(Path(temporary.name))
    model = models.import_live2d(profile, installed.model_path(original), original['name'],
                                blindfold_parameter=original.get('blindfold_parameter', ''))
    models.select(profile, model['id'])
    settings = Settings('', DEFAULT_MODEL, 'Jingliu', 'Offline visual check',
                        character_path=profile, tts_enabled=False)
    speech = Speech()
    store = Store(':memory:')
    window = CompanionWindow(settings, speech=speech, microphone=Microphone(), store=store,
        preferences=Preferences(Path(temporary.name) / 'preferences.json'), models=models)
    window.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
    window.setWindowFlag(Qt.WindowType.WindowDoesNotAcceptFocus)
    window.settings_dialog.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
    window.settings_dialog.setWindowFlag(Qt.WindowType.WindowDoesNotAcceptFocus)
    checks = {}

    def pump(seconds=.01):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            app.processEvents()
            app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            time.sleep(.004)

    def wait(condition, timeout=20):
        end = time.monotonic() + timeout
        while not condition():
            if time.monotonic() > end:
                raise RuntimeError('Native Live2D check timed out.')
            pump()

    def widget():
        return window.avatar.widget

    def ready():
        wait(lambda: widget().ready or widget().failed, 60)
        assert widget().ready, 'Restore the local model/runtime files.'
        pump(.25)

    def js(code):
        values = []
        widget().page.runJavaScript(code, lambda value: values.append(value))
        wait(lambda: bool(values), 5)
        return values[0]

    def state():
        result = json.loads(js('JSON.stringify(avatarDiagnostics())'))
        assert all(isinstance(v, (int, float)) and math.isfinite(v) for v in result['parameters'].values())
        if result['rig']:
            assert all(isinstance(v, (int, float)) and math.isfinite(v) for v in result['rig']['values'].values())
        return result

    def picture(name):
        raw = js("document.querySelector('canvas').toDataURL('image/png').split(',')[1]")
        (output / (name + '.png')).write_bytes(base64.b64decode(raw))

    try:
        with patch('companion.mesh_avatar.QWebEnginePage', LogPage):
            window.show_avatar.setChecked(True)
            window.avatar_size.setValue(480)
            ready()
            assert state()['renderer'] == 'live2d'
            assert not state()['rig']['missing']
            checks['rig'] = {key: state()['rig'][key] for key in ('parameters', 'drawables', 'physics', 'hairOutputs')}
            if args.physics:
                js((ROOT / 'dev/check_live2d_physics.js').read_text(encoding='utf-8'))
                wait(lambda: bool(js('Boolean(window.live2dPhysicsCheck)')), 30)
                result = json.loads(js('JSON.stringify(window.live2dPhysicsCheck)'))
                assert result.get('passed'), result
                checks['ribbon_timing'] = result
                print('Real-solver ribbon timing check:', json.dumps(result), flush=True)
                # Observe actual idle rendering as well as the isolated solver.
                end = time.monotonic() + 12
                idle_frames = state()['frames']
                while time.monotonic() < end:
                    state()  # Includes finite checks of every rendered rig parameter.
                    pump(.05)
                assert state()['frames'] > idle_frames
                checks['idle_physics_observation_seconds'] = 12
            picture('neutral')
            js("const stream=document.querySelector('canvas').captureStream(60);window.rigChunks=[];window.rigStream=stream;window.rigRecorder=new MediaRecorder(stream,{mimeType:'video/webm;codecs=vp8',videoBitsPerSecond:6000000});rigRecorder.ondataavailable=e=>{if(e.data.size)rigChunks.push(e.data)};rigRecorder.onstop=()=>{rigStream.getTracks().forEach(t=>t.stop());const reader=new FileReader();reader.onload=()=>window.rigVideo=reader.result.split(',')[1];reader.readAsDataURL(new Blob(rigChunks,{type:'video/webm'}));};rigRecorder.start();true;")
            window.preview_avatar_motion.click()
            wait(lambda: state()['motion']['preview'] is not None)
            captured = set()
            samples = []
            began = time.monotonic()
            while widget()._preview_active:
                value = state()
                samples.append(value)
                preview = value['motion']['preview']
                p = value['rig']['values']
                if preview and p['ParamEyeLOpen'] > .4:
                    label = preview['label']
                    targets = {
                        'Looking left': ('left', p['ParamAngleX'] < -22),
                        'Looking right': ('right', p['ParamAngleX'] > 22),
                        'Looking up': ('up', p['ParamAngleY'] > 17),
                        'Looking down': ('down', p['ParamAngleY'] < -17),
                        'Turning and tilting': ('diagonal', abs(p['ParamAngleZ']) > 8),
                    }
                    if label in targets:
                        name, reached = targets[label]
                        if reached and name not in captured:
                            picture(name)
                            captured.add(name)
                assert p['ParamMouthOpenY'] < .01, 'A silent preview must not open the mouth.'
                assert time.monotonic() - began < 100, 'Rig preview did not finish.'
                pump(.05)
            assert captured == {'left', 'right', 'up', 'down', 'diagonal'}, captured
            js('rigRecorder.stop();true;')
            wait(lambda: bool(js('Boolean(window.rigVideo)')))
            (output / 'rig-preview.webm').write_bytes(base64.b64decode(js('window.rigVideo')))
            checks['poses'] = sorted(captured)
            ranges = {key: max(s['rig']['values'][key] for s in samples) - min(s['rig']['values'][key] for s in samples)
                      for key in ('Param15', 'Param17', 'Param19') if key in samples[0]['rig']['values']}
            assert ranges and max(ranges.values()) > .05, ranges
            checks['hair_parameter_ranges'] = ranges
            print('Native rig turns and hair passed.', flush=True)

            window.avatar_blindfold.setChecked(True)
            wait(lambda: state()['rig']['values']['Param100'] == 0)
            picture('blindfold')
            window.avatar_blindfold.setChecked(False)
            wait(lambda: state()['rig']['values']['Param100'] == 1)
            window.avatar_framing.setCurrentIndex(window.avatar_framing.findData('full'))
            wait(lambda: state()['rig']['framing'] == 'full')
            picture('full-model')
            window.avatar_framing.setCurrentIndex(window.avatar_framing.findData('portrait'))
            checks['framing_and_blindfold'] = True

            # Exercise the same playback-only bridge used by TTS, with synthetic levels.
            speech.busy = True
            speech.state = 'speaking'
            speech.changed.emit('Speaking')
            for _ in range(20):
                speech.playback_level.emit(.7)
                pump(.04)
            assert state()['rig']['values']['ParamMouthOpenY'] > .4
            picture('playback-envelope')
            window._stop()
            wait(lambda: state()['rig']['values']['ParamMouthOpenY'] < .01)
            picture('stopped')
            checks['playback_bridge_and_stop'] = True

            widget().hide()
            pump(.15)
            count = state()['frames']
            pump(.3)
            assert state()['frames'] == count
            widget().show()
            wait(lambda: state()['frames'] > count)
            window.animate_avatar.setChecked(False)
            pump(.1)
            count = state()['frames']
            pump(.2)
            assert state()['frames'] == count
            window.animate_avatar.setChecked(True)
            checks['hide_pause_resume'] = True

            for _ in range(2):
                window.avatar_model.setCurrentIndex(window.avatar_model.findData('current'))
                ready()
                assert state()['renderer'] == 'mesh'
                picture('current-ai-portrait')
                window.avatar_model.setCurrentIndex(window.avatar_model.findData(model['id']))
                ready()
                assert state()['renderer'] == 'live2d'
            assert window.settings.system_prompt == settings.system_prompt
            assert window.settings.tts_enabled == settings.tts_enabled
            checks['switching_and_character_preserved'] = True
            window.avatar.reload_avatar()
            ready()
            assert state()['renderer'] == 'live2d'
            checks['reload'] = True
            assert not errors, errors
            checks['renderer_errors'] = errors
            (output / 'verification.json').write_text(json.dumps(checks, indent=2), encoding='utf-8')
            print(json.dumps(checks), flush=True)
    finally:
        window.avatar.shutdown()
        window.speech.shutdown()
        window.microphone.shutdown()
        window.deleteLater()
        pump(.4)
        store.close()
        temporary.cleanup()


if __name__ == '__main__':
    main()
