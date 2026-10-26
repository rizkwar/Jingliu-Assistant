"""Opt-in native check of the v5 layered rig, using temporary preferences/chats.

Captures only the avatar canvas. No microphone, TTS or response providers.
"""
import base64
import argparse
import json
import math
from pathlib import Path
import sys
import tempfile
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from PySide6.QtCore import QEvent, Qt
from PySide6.QtCore import QRectF
from PySide6.QtGui import QColor, QFont, QImage, QPainter
from PySide6.QtWidgets import QApplication
from PySide6.QtWebEngineCore import QWebEnginePage
from companion.avatar.models import AvatarModels
from companion.core.config import DEFAULT_MODEL, Settings
from companion.core.preferences import Preferences
from companion.core.storage import Store
from companion.ui.window import CompanionWindow
from check_live2d import Speech, Microphone


def layer_sheet(directory, output):
    """Inspection montage only; installed art is never edited by this helper."""
    names=['05-skin-and-jaw','06-left-eye-and-iris','08-right-eye-and-iris',
           '10-left-eyebrow','11-right-eyebrow','12-nose','13-mouth',
           '18-left-side-bang','19-right-side-bang','20-left-bang','21-right-bang','22-center-bang']
    canvas=QImage(720,1144,QImage.Format.Format_ARGB32);canvas.fill(QColor('#20232d'))
    painter=QPainter(canvas);painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    painter.setFont(QFont('Segoe UI',10));painter.setPen(QColor('#f0f0f5'))
    for i,name in enumerate(names):
        x=(i%3)*240;y=(i//3)*286
        painter.drawText(QRectF(x+8,y+5,224,28),Qt.AlignmentFlag.AlignCenter,name[3:].replace('-',' ').title())
        painter.drawImage(QRectF(x+6,y+35,228,251),QImage(str(directory/(name+'.png'))),QRectF(350,160,600,660))
    painter.end();canvas.save(str(output))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--poses-only', action='store_true', help='Capture an art revision after lifecycle checks have already passed.')
    parser.add_argument('--layers', action='store_true', help='Also save individual rendered part artwork for inspection.')
    args = parser.parse_args()
    installed = AvatarModels()
    profile = str(ROOT / 'character.toml')
    original = next(m for m in reversed(installed.models(profile)) if m['kind'] == 'layered')
    output = ROOT / '.cache/layered-avatar-qa'
    output.mkdir(parents=True, exist_ok=True)
    errors = []
    class LogPage(QWebEnginePage):
        def javaScriptConsoleMessage(self, level, message, line, source):
            if level == QWebEnginePage.JavaScriptConsoleMessageLevel.ErrorMessageLevel:
                errors.append(message[:300])
    app = QApplication([])
    temporary = tempfile.TemporaryDirectory()
    models = AvatarModels(Path(temporary.name))
    model = models.import_layered(profile, installed.model_path(original), original['name'])
    models.select(profile, model['id'])
    settings = Settings('', DEFAULT_MODEL, 'Jingliu', 'Offline visual check', character_path=profile, tts_enabled=False)
    speech, microphone, store = Speech(), Microphone(), Store(':memory:')
    window = CompanionWindow(settings, speech=speech, microphone=microphone, store=store,
        preferences=Preferences(Path(temporary.name) / 'preferences.json'), models=models)
    window.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
    window.setWindowFlag(Qt.WindowType.WindowDoesNotAcceptFocus)
    checks = {}

    def pump(seconds=.01):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            app.processEvents();app.sendPostedEvents(None, QEvent.Type.DeferredDelete);time.sleep(.004)

    def wait(condition, timeout=40):
        end = time.monotonic() + timeout
        while not condition():
            if time.monotonic() > end:
                raise RuntimeError('Layered check timed out. ' + str(errors))
            pump()

    def widget():
        return window.avatar.widget

    def ready():
        wait(lambda: widget().ready or widget().failed)
        assert widget().ready, errors
        pump(.2)

    def js(code):
        values = []
        widget().page.runJavaScript(code, lambda value: values.append(value))
        wait(lambda: bool(values), 8)
        return values[0]

    def state():
        value = json.loads(js('JSON.stringify(avatarDiagnostics())'))
        for numbers in (value['parameters'], (value['rig'] or {}).get('values', {})):
            assert all(isinstance(v, (float, int)) and math.isfinite(v) for v in numbers.values()), value
        return value

    def picture(name):
        raw = js("document.querySelector('canvas').toDataURL('image/png').split(',')[1]")
        (output / (name + '.png')).write_bytes(base64.b64decode(raw))

    try:
        with patch('companion.avatar.mesh.QWebEnginePage', LogPage):
            window.show_avatar.setChecked(True)
            window.avatar_size.setValue(560)
            ready();assert state()['renderer'] == 'layered'
            picture('neutral')
            checks['layers'] = state()['rig']['layers']
            checks['approach'] = state()['rig']['approach']
            names={p['name'] for p in state()['rig'].get('parts', [])}
            required={'Left eye and iris','Right eye and iris','Left eyebrow','Right eyebrow',
                      'Left bang','Center bang','Right bang','Left side bang','Right side bang'}
            assert required <= names, names
            checks['independent_parts'] = sorted(required)
            if args.layers:
                parts=json.loads(js('JSON.stringify(avatarLayerPreviews())'))
                directory=output/'parts';directory.mkdir(exist_ok=True)
                for number,part in enumerate(parts):
                    filename=f'{number:02d}-'+part['name'].lower().replace(' ','-')+'.png'
                    (directory/filename).write_bytes(base64.b64decode(part['image'].split(',')[1]))
                (directory/'parts.json').write_text(json.dumps([{k:v for k,v in p.items() if k!='image'} for p in parts],indent=2),encoding='utf-8')
                layer_sheet(directory,output/'separated-parts.png')
            js("window.eyeCaptureDeadline=performance.now()+30000;window.eyeCapture=null;const watchEyes=()=>{const d=avatarDiagnostics();if(d.parameters.eyeLOpen<.12){window.eyeCapture=document.querySelector('canvas').toDataURL('image/png').split(',')[1]}else if(performance.now()<eyeCaptureDeadline)requestAnimationFrame(watchEyes);};requestAnimationFrame(watchEyes);true;")
            js("const stream=document.querySelector('canvas').captureStream(60);window.rigChunks=[];window.rigStream=stream;window.rigRecorder=new MediaRecorder(stream,{mimeType:'video/webm;codecs=vp8',videoBitsPerSecond:6000000});rigRecorder.ondataavailable=e=>{if(e.data.size)rigChunks.push(e.data)};rigRecorder.onstop=()=>{rigStream.getTracks().forEach(t=>t.stop());const reader=new FileReader();reader.onload=()=>window.rigVideo=reader.result.split(',')[1];reader.readAsDataURL(new Blob(rigChunks,{type:'video/webm'}));};rigRecorder.start();true;")
            window.preview_avatar_motion.click()
            wait(lambda: state()['motion']['preview'] is not None)
            captures = set();samples = [];began = time.monotonic()
            while widget()._preview_active:
                value = state();samples.append(value);p = value['parameters']
                if p['eyeLOpen'] > .99:
                    for name, condition in [('left', p['angleX'] < -10), ('right', p['angleX'] > 10),
                                            ('up', p['angleY'] > 3.5), ('down', p['angleY'] < -3.5),
                                            ('diagonal', p['angleZ'] > 5.5)]:
                        if condition and name not in captures:
                            picture(name);captures.add(name)
                assert p['mouthOpen'] == 0
                assert time.monotonic() - began < 100
                pump(.05)
            assert captures == {'left', 'right', 'up', 'down', 'diagonal'}, captures
            js('rigRecorder.stop();true;');wait(lambda: bool(js('Boolean(window.rigVideo)')))
            (output / 'layered-preview.webm').write_bytes(base64.b64decode(js('window.rigVideo')))
            picture('settled')
            blink=js('window.eyeCapture')
            assert blink, 'Expected an observed natural blink during the preview.'
            (output/'blink.png').write_bytes(base64.b64decode(blink));checks['observed_blink']=True
            checks['poses'] = sorted(captures)
            checks['strand_ranges'] = {key: max(s['rig']['values'][key] for s in samples) - min(s['rig']['values'][key] for s in samples)
                                      for key in samples[0]['rig']['values']}
            print('Native poses captured:', sorted(captures), flush=True)
            speech.busy = True;speech.state = 'speaking';speech.changed.emit('Speaking')
            for _ in range(20):
                speech.playback_level.emit(.7);pump(.04)
            assert state()['parameters']['mouthOpen'] > .4
            picture('speech')
            window._stop();wait(lambda: state()['parameters']['mouthOpen'] < .01)
            checks['playback_stop'] = True
            widget().set_activity('thinking');pump(1)
            assert state()['expression']=='halfLidded';picture('thinking')
            widget().set_activity('ready');pump(.4)
            if args.poses_only:
                assert not errors, errors
                (output / 'art-verification.json').write_text(json.dumps(checks, indent=2), encoding='utf-8')
                print(json.dumps(checks), flush=True)
                return
            widget().hide();pump(.2);frames = state()['frames'];pump(.25);assert state()['frames'] == frames
            widget().show();wait(lambda: state()['frames'] > frames)
            window.animate_avatar.setChecked(False);pump(.15);frames = state()['frames'];pump(.25);assert state()['frames'] == frames
            window.animate_avatar.setChecked(True)
            widget().resize(360, 390);pump(.2);picture('resized')
            for _ in range(2):
                window.avatar_model.setCurrentIndex(window.avatar_model.findData('current'));ready();assert state()['renderer'] == 'mesh'
                window.avatar_model.setCurrentIndex(window.avatar_model.findData(model['id']));ready();assert state()['renderer'] == 'layered'
            window.avatar.reload_avatar();ready()
            assert state()['renderer'] == 'layered'
            assert window.settings == settings
            assert not errors, errors
            checks.update(lifecycle=True, model_switching=True, character_unchanged=True, errors=errors)
            (output / 'verification.json').write_text(json.dumps(checks, indent=2), encoding='utf-8')
            (output / 'samples.json').write_text(json.dumps(samples), encoding='utf-8')
            print(json.dumps(checks), flush=True)
    finally:
        window.avatar.shutdown();speech.shutdown();microphone.shutdown();window.deleteLater();pump(.4)
        store.close();temporary.cleanup()


if __name__ == '__main__':
    main()
