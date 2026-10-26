"""Render a bounded, local MP4 inspection of saved Inochi motion data."""
import hashlib
import json
import math
import shutil
import subprocess

from PySide6.QtCore import QRectF,Qt
from PySide6.QtGui import QColor,QFont,QFontDatabase,QImage,QPainter
from inochi_idle_motion import MotionPlayer,inspection_data


def render_motion(store,request,images):
    from render_inochi_rig import render,encoded_png
    seconds=request.get('seconds',6);fps=request.get('fps',30);size=request.get('size',512)
    if not isinstance(seconds,(int,float)) or not math.isfinite(seconds) or not 2<=seconds<=12:
        raise ValueError('Choose 2..12 seconds of motion.')
    if type(fps) is not int or not 12<=fps<=60 or type(size) is not int or not 256<=size<=640 or size%2:
        raise ValueError('Choose 12..60 fps and an even size of 256..640 pixels.')
    output=store.path(request['output'],extensions=('.mp4',))
    sheet_path=output.with_suffix('.frames.png');report_path=output.with_suffix('.verification.json')
    if any(p.exists() for p in (output,sheet_path,report_path)):raise ValueError('Choose new video, sheet and verification filenames.')
    ffmpeg=shutil.which('ffmpeg')
    if not ffmpeg:raise ValueError('Install FFmpeg or use the native Creator animation preview.')
    data,_=store.read(request['file']);name=request.get('animation','Idle - blink and hair')
    if name not in (data.get('animations') or {}):raise ValueError('Choose an animation saved in this rig.')
    player=MotionPlayer(data,name,request.get('physics',True));view=inspection_data(data)
    font_id=QFontDatabase.addApplicationFont('C:/Windows/Fonts/segoeui.ttf')
    families=QFontDatabase.applicationFontFamilies(font_id)
    if not families:raise ValueError('Preview label font is unavailable.')
    font=QFont(families[0],10);count=round(seconds*fps);frames={};values=[]
    # Choose moments from the real sampled controls, including a blink and hair extrema.
    for i in range(count):values.append(player.pose(i/fps))
    hair=[v['Hair sway - manual test'][0] for v in values]
    eye=[v['Eye L open'][0] for v in values]
    picks=sorted({0,count//3,2*count//3,count-1,min(range(count),key=eye.__getitem__),
                  min(range(count),key=hair.__getitem__),max(range(count),key=hair.__getitem__)})
    output.parent.mkdir(parents=True,exist_ok=True)
    args=[ffmpeg,'-v','error','-n','-f','rawvideo','-pixel_format','rgba','-video_size',f'{size}x{size}',
          '-framerate',str(fps),'-i','pipe:0','-an','-c:v','libx264','-preset','fast','-crf','18',
          '-pix_fmt','yuv420p','-movflags','+faststart',str(output)]
    process=subprocess.Popen(args,stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,
                             creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    try:
        for i,pose in enumerate(values):
            image=render(view,images,pose,size)
            if i in picks:frames[i]=image.copy()
            p=QPainter(image);p.setFont(font);p.fillRect(0,size-27,size,27,QColor('#202227'))
            p.setPen(QColor('#eef0f3'))
            p.drawText(QRectF(8,size-27,size-16,27),Qt.AlignmentFlag.AlignVCenter,
                       f'Inspection | {i/fps:.2f}s | hair {hair[i]:+.3f}')
            p.end()
            process.stdin.write(bytes(image.constBits()))
        process.stdin.close();process.stdin=None
        _,errors=process.communicate(timeout=45)
        if process.returncode:raise ValueError('FFmpeg failed: '+errors.decode(errors='replace')[-700:])
    except BaseException:
        process.kill();process.communicate()
        output.unlink(missing_ok=True)
        raise
    cols=3;rows=math.ceil(len(picks)/cols);tile=320;label=32
    sheet=QImage(cols*tile,rows*(tile+label),QImage.Format.Format_RGBA8888_Premultiplied)
    sheet.fill(QColor('#202227'));p=QPainter(sheet);p.setFont(font);p.setPen(QColor('#eef0f3'))
    for n,i in enumerate(picks):
        x=(n%cols)*tile;y=(n//cols)*(tile+label)
        p.drawText(QRectF(x+8,y,tile-16,label),Qt.AlignmentFlag.AlignVCenter,f'{i/fps:.2f}s | hair {hair[i]:+.3f}')
        p.drawImage(QRectF(x,y+label,tile,tile),frames[i])
    p.end()
    with sheet_path.open('xb') as stream:stream.write(encoded_png(sheet))
    report={'video':request['output'],'rig':request['file'],
            'rigSha256':hashlib.sha256(store.path(request['file']).read_bytes()).hexdigest(),
            'animation':name,'seconds':count/fps,'frames':count,'fps':fps,'size':size,
            'physics':bool(request.get('physics',True)),'hairMin':min(hair),'hairMax':max(hair),
            'maximumHairStep':max(abs(b-a) for a,b in zip(hair,hair[1:])),
            'closedEyeFrames':sum(v<.05 for v in eye),
            'contactSheet':sheet_path.relative_to(store.root).as_posix(),
            'renderer':'Saved mesh/keyforms with configured animation and pendulum subset; not an Inochi runtime recording.'}
    with report_path.open('x',encoding='utf8') as stream:json.dump(report,stream,indent=2)
    return report
