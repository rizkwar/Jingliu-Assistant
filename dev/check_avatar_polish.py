"""Opt-in native check of motion presets and the silent movement preview.

Uses temporary settings/chat data and local avatar files. No model, microphone or
speech requests. Records only the avatar canvas under ignored .cache/.
"""
import base64
import json
import math
from pathlib import Path
import sys
import tempfile
import time
from unittest.mock import patch

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
from PySide6.QtCore import QEvent,Qt
from PySide6.QtWidgets import QApplication,QScrollArea
from companion.config import DEFAULT_MODEL,Settings
from companion.preferences import Preferences
from companion.storage import Store
from companion.ui import CompanionWindow


def main():
    app=QApplication([])
    app.setStyle('Fusion')
    folder=tempfile.TemporaryDirectory()
    store=Store(':memory:')
    settings=Settings('',DEFAULT_MODEL,'Motion preview check','Offline check',
                      character_path=str(ROOT/'character.toml'),tts_enabled=False)
    window=CompanionWindow(settings,store=store,preferences=Preferences(Path(folder.name)/'preferences.json'))
    window.setWindowTitle('Avatar polish verification (closes automatically)')
    window.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
    window.setWindowFlag(Qt.WindowType.WindowDoesNotAcceptFocus)
    window.settings_dialog.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
    window.settings_dialog.setWindowFlag(Qt.WindowType.WindowDoesNotAcceptFocus)
    window.show()
    window.show_avatar.setChecked(True)
    widget=window.avatar.widget
    out=ROOT/'.cache/avatar-polish'
    out.mkdir(parents=True,exist_ok=True)
    checks={}
    samples=[]

    def wait(condition,timeout=25):
        end=time.monotonic()+timeout
        while not condition():
            app.processEvents()
            app.sendPostedEvents(None,QEvent.Type.DeferredDelete)
            time.sleep(.005)
            if time.monotonic()>end:raise RuntimeError('Native polish check timed out')

    def delay(seconds):
        end=time.monotonic()+seconds
        wait(lambda:time.monotonic()>=end,seconds+2)

    def js(code):
        values=[]
        widget.page.runJavaScript(code,lambda value:values.append(value))
        wait(lambda:bool(values),5)
        return values[0]

    def state():
        value=json.loads(js('JSON.stringify(avatarDiagnostics())'))
        assert all(math.isfinite(v) for v in value['parameters'].values())
        assert 0<=value['parameters']['breath']<=1.15
        return value

    def picture(name):
        data=js("document.querySelector('canvas').toDataURL('image/png').split(',')[1]")
        (out/(name+'.png')).write_bytes(base64.b64decode(data))

    def start():
        assert window.preview_avatar_motion.isEnabled(),window.avatar_preview_status.text()
        window.preview_avatar_motion.click()
        wait(lambda:state()['motion']['preview'] is not None,3)
        assert widget._preview_active and not widget.cursor_timer.isActive()
        assert window.preview_avatar_motion.text()=='Stop preview'

    def assert_stopped():
        wait(lambda:not widget._preview_active and state()['motion']['preview'] is None,3)
        assert window.preview_avatar_motion.text()=='Preview movement'

    def activity(value):
        window.activity=value
        window.activity_changed.emit(value)
        delay(.3)

    try:
        wait(lambda:getattr(widget,'ready',False) or getattr(widget,'failed',False))
        assert widget.ready,'Restore local avatar and Qt WebEngine dependencies'
        delay(.3)
        js("window.previewCheckErrors=[];window.addEventListener('error',()=>previewCheckErrors.push('script error'));window.addEventListener('unhandledrejection',()=>previewCheckErrors.push('unhandled rejection'));true;")
        with patch.object(window.speech,'speak') as speech,patch.object(window.microphone,'start') as mic:
            for name,values in [('Calm',(45,55,30)),('Lively',(100,100,65)),('Natural',(100,100,45))]:
                window.avatar_preset.setCurrentText(name)
                assert (window.avatar_motion.value(),window.avatar_gaze.value(),window.avatar_hair.value())==values
            js("const stream=document.querySelector('canvas').captureStream(60);window.previewChunks=[];window.previewStream=stream;window.previewRecorder=new MediaRecorder(stream,{mimeType:'video/webm;codecs=vp8',videoBitsPerSecond:4000000});previewRecorder.ondataavailable=e=>{if(e.data.size)previewChunks.push(e.data)};previewRecorder.onstop=()=>{previewStream.getTracks().forEach(t=>t.stop());const r=new FileReader();r.onload=()=>window.previewVideo=r.result.split(',')[1];r.readAsDataURL(new Blob(previewChunks,{type:'video/webm'}));};previewRecorder.start();true;")
            start()
            last_label=None
            began=time.monotonic()
            while widget._preview_active:
                value=state()
                samples.append(value)
                preview=value['motion']['preview']
                if preview and preview['label']!=last_label:
                    last_label=preview['label']
                # Capture after reaching each turn, not its first transition frame.
                if preview:
                    t=preview['time']
                    if 3.3<t<3.5:picture('left')
                    if 6.1<t<6.3:picture('right')
                    if 8.5<t<8.7:picture('tilt')
                assert value['parameters']['mouthOpen']<.01,'Silent preview animated the mouth'
                # state() pumps events; natural completion may already have
                # acknowledged and resumed cursor polling in that same call.
                if widget._preview_active:
                    assert not widget.cursor_timer.isActive()
                delay(.06)
                assert time.monotonic()-began<25,'Preview did not finish naturally'
            assert_stopped()
            assert 'finished' in window.avatar_preview_status.text().lower()
            wait(lambda:widget.cursor_timer.isActive(),2)
            checks['preset_values_and_finite_silent_demo']=True
            print('PASS: finite silent preview and normal completion.',flush=True)
            js('previewRecorder.stop();true;')
            wait(lambda:bool(js('Boolean(window.previewVideo)')),5)
            (out/'movement-preview.webm').write_bytes(base64.b64decode(js('window.previewVideo')))
            # Presets remain editable and save their existing numeric settings.
            window.avatar_preset.setCurrentText('Calm')
            delay(.4)
            start()
            delay(.5)
            window.preview_avatar_motion.click()
            assert_stopped()
            window.avatar_motion.setValue(63)
            assert window.avatar_preset.currentText()=='Custom'
            window._save_preferences()
            loaded=window.preferences.load(settings)
            assert (loaded.avatar_motion,loaded.avatar_gaze,loaded.avatar_hair)==(63,55,30)
            checks['manual_stop_custom_and_persistence']=True
            window.avatar_preset.setCurrentText('Natural')
            delay(.3)
            for current in ['listening','thinking','speaking']:
                start()
                activity(current)
                assert_stopped()
                assert not window.preview_avatar_motion.isEnabled()
                assert state()['parameters']['mouthOpen']<.01
                activity('ready')
            checks['conversation_states_cancel_preview']=True
            start()
            window.speech.playback_level.emit(.6)
            assert_stopped()
            window.speech.playback_reset.emit()
            delay(.3)
            assert state()['parameters']['mouthOpen']<.01
            start()
            assert window.stop_button.isEnabled()
            window.stop_button.click()
            assert_stopped()
            checks['actual_playback_signal_and_stop_cancel_preview']=True
            print('PASS: conversation, playback and main Stop cancellation.',flush=True)
            for control in ['animate','visibility','zero']:
                start()
                if control=='animate':window.animate_avatar.setChecked(False)
                elif control=='visibility':window.show_avatar.setChecked(False)
                else:window.avatar_motion.setValue(0)
                assert_stopped()
                assert not window.preview_avatar_motion.isEnabled()
                if control=='animate':window.animate_avatar.setChecked(True)
                elif control=='visibility':window.show_avatar.setChecked(True)
                else:window.avatar_motion.setValue(100)
                delay(.3)
            checks['pause_hide_and_zero_movement_cancel_preview']=True
            start()
            widget.showMinimized()
            assert_stopped()
            assert not widget.cursor_timer.isActive()
            before=state()['frames']
            delay(.4)
            assert state()['frames']==before
            widget.showNormal()
            delay(.4)
            assert state()['frames']>before
            start()
            widget.view.hide()
            assert_stopped()
            assert not widget.cursor_timer.isActive()
            widget.view.show()
            delay(.4)
            assert window.preview_avatar_motion.isEnabled()
            checks['minimize_and_hidden_page_cancel_preview']=True
            window.open_settings()
            window.settings_dialog.findChild(QScrollArea).ensureWidgetVisible(window.preview_avatar_motion)
            delay(.2)
            window.settings_dialog.grab().save(str(out/'settings.png'))
            window.settings_dialog.hide()
            assert js('JSON.stringify(previewCheckErrors)')=='[]'
            checks['no_renderer_errors']=True
            start()
            old=widget
            window.avatar.reload_avatar()
            widget=window.avatar.widget
            wait(lambda:widget.ready or widget.failed)
            assert widget.ready and old._disposed and not old._preview_active
            wait(lambda:bool(js('window.avatarDiagnostics && avatarDiagnostics().frames>0')),3)
            assert state()['motion']['preview'] is None
            checks['reload_cancels_and_does_not_resume_demo']=True
            speech.assert_not_called()
            mic.assert_not_called()
            checks['no_speech_or_recording_requests']=True
    finally:
        window.request_quit()
        window.deleteLater()
        app.sendPostedEvents(None,QEvent.Type.DeferredDelete)
        app.processEvents()
        store.close()
        folder.cleanup()
        checks['shutdown']=window.avatar._shutdown and window.avatar.widget is None
        (out/'verification.json').write_text(json.dumps({'checks':checks,'samples':len(samples)},indent=2),encoding='utf-8')
        (out/'samples.json').write_text(json.dumps(samples,indent=2),encoding='utf-8')
        import shiboken6
        shiboken6.delete(app)
    print(json.dumps(checks),flush=True)


if __name__=='__main__':
    main()
