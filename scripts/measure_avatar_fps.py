"""Offline native FPS/pacing check with isolated settings and no audio requests."""
import argparse
import json
import os
from pathlib import Path
import sys
import tempfile
import time

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
from PySide6.QtCore import QEvent,Qt
from PySide6.QtWidgets import QApplication
from companion.config import DEFAULT_MODEL,Settings
from companion.preferences import Preferences
from companion.storage import Store
from companion.ui import CompanionWindow
from windows_process_metrics import sample_tree


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--label',choices=['before','after'],required=True)
    parser.add_argument('--width',type=int,choices=[320,640],default=320)
    args=parser.parse_args()
    app=QApplication([])
    folder=tempfile.TemporaryDirectory()
    store=Store(':memory:')
    height=round(args.width*350/320)
    settings=Settings('',DEFAULT_MODEL,'FPS verification','Offline check',
                      character_path=str(ROOT/'character.toml'),tts_enabled=False,
                      avatar_width=args.width,avatar_height=height)
    window=CompanionWindow(settings,store=store,preferences=Preferences(Path(folder.name)/'preferences.json'))
    window.setWindowTitle('Avatar FPS verification (closes automatically)')
    window.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
    window.setWindowFlag(Qt.WindowType.WindowDoesNotAcceptFocus)
    window.show()
    window.show_avatar.setChecked(True)
    widget=window.avatar.widget
    widget.setFixedSize(args.width,height)
    output=ROOT/'.cache/avatar-fps'
    output.mkdir(parents=True,exist_ok=True)
    report={'label':args.label,'logical_cpus':os.cpu_count(),'phases':[],
            'voice_loaded':False,'hd':True,'window_logical_pixels':[args.width,height],
            'display_scale_ratios':[screen.devicePixelRatio() for screen in app.screens()]}

    def wait(condition,timeout=25):
        end=time.monotonic()+timeout
        while not condition():
            app.processEvents()
            app.sendPostedEvents(None,QEvent.Type.DeferredDelete)
            time.sleep(.002)
            if time.monotonic()>end:raise RuntimeError('FPS check timed out')

    def delay(seconds):
        end=time.monotonic()+seconds
        wait(lambda:time.monotonic()>=end,seconds+2)

    def js(code):
        values=[]
        widget.page.runJavaScript(code,lambda value:values.append(value))
        wait(lambda:bool(values),5)
        return values[0]

    def state():return json.loads(js('JSON.stringify(avatarDiagnostics())'))

    def measure(name,seconds=6):
        initial=state()
        before=sample_tree()
        # Observe actual draw-count changes at rAF boundaries. Bounded probe only
        # exists in this QA renderer; no telemetry leaves the local process.
        js("window.fpsProbe={intervals:[],last:null,frames:avatarDiagnostics().frames};window.fpsProbeActive=true;function fpsProbeTick(t){if(!fpsProbeActive)return;const n=avatarDiagnostics().frames;if(n!==fpsProbe.frames){if(fpsProbe.last!==null&&fpsProbe.intervals.length<2000)fpsProbe.intervals.push(t-fpsProbe.last);fpsProbe.last=t;fpsProbe.frames=n;}requestAnimationFrame(fpsProbeTick);}requestAnimationFrame(fpsProbeTick);true;")
        start=time.monotonic()
        memory=[]
        while time.monotonic()-start<seconds:
            memory.append(sum(v[1] for v in sample_tree().values())/1024**2)
            delay(.2)
        end=time.monotonic()
        final=state()
        after=sample_tree()
        js('fpsProbeActive=false;true;')
        intervals=json.loads(js('JSON.stringify(fpsProbe.intervals)'))
        ordered=sorted(intervals)
        percentile=lambda part:round(ordered[min(len(ordered)-1,int((len(ordered)-1)*part))],2) if ordered else None
        cpu=sum(max(0,v[0]-before.get(pid,(0,0))[0]) for pid,v in after.items())
        duration=end-start
        row={'phase':name,'seconds':round(duration,2),
             'draws_per_second':round((final['frames']-initial['frames'])/duration,2),
             'target_fps':final['targetFps'],'cpu_machine_percent':round(cpu/duration*100/(os.cpu_count() or 1),2),
             'mean_working_set_mib':round(sum(memory)/len(memory),1),'canvas':final['canvas'],
             'observed_frame_spacing_ms':{'p50':percentile(.5),'p95':percentile(.95),'max':max(ordered) if ordered else None}}
        report['phases'].append(row)
        print(json.dumps(row),flush=True)
        return row

    try:
        wait(lambda:getattr(widget,'ready',False) or getattr(widget,'failed',False))
        assert widget.ready,'Restore local avatar and Qt WebEngine before measuring'
        delay(1.5)
        measure('idle')
        window.preview_avatar_motion.click()
        wait(lambda:widget._preview_active,3)
        measure('movement_preview')
        if widget._preview_active:window.preview_avatar_motion.click()
        widget.set_activity('thinking')
        delay(1.2)
        measure('thinking')
        widget.set_activity('ready')
        window.show_avatar.setChecked(False)
        delay(.3)
        hidden=measure('hidden',3)
        assert hidden['draws_per_second']==0
    finally:
        window.request_quit()
        window.deleteLater()
        app.sendPostedEvents(None,QEvent.Type.DeferredDelete)
        app.processEvents()
        store.close()
        folder.cleanup()
        import shiboken6
        shiboken6.delete(app)
        suffix='' if args.width==320 else '-'+str(args.width)
        (output/(args.label+suffix+'.json')).write_text(json.dumps(report,indent=2),encoding='utf-8')


if __name__=='__main__':main()
