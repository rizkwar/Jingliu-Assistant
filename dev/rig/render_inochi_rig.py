"""Render supported flat Inochi meshes from their saved keyforms, without GUI input.

This is an inspection renderer, not the Inochi runtime. It supports the flat,
Normal-blend, premultiplied 0.8 part rigs built by this project, and fails on
unsupported rendering features rather than approximating them silently.
"""
import bisect
import json
import os
from pathlib import Path
import struct
import sys

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontDatabase, QGuiApplication, QImage, QPainter, QPainterPath, QTransform
from avatar_rig_data import RigStore, finite_tree, walk


def decode_tga(blob):
    if len(blob)<18:
        raise ValueError('Truncated TGA header.')
    id_size,palette,kind,_,_,_,_,_,width,height,depth,flags=struct.unpack_from('<BBBHHBHHHHBB',blob)
    if palette or kind not in (2,10) or depth not in (24,32) or not 0<width<=4096 or not 0<height<=4096:
        raise ValueError('Unsupported TGA texture format.')
    stride=depth//8; expected=width*height*stride; offset=18+id_size; pixels=bytearray()
    if kind==2:
        pixels.extend(blob[offset:offset+expected])
    else:
        while len(pixels)<expected:
            if offset>=len(blob):
                raise ValueError('Truncated TGA packet.')
            packet=blob[offset];offset+=1;count=(packet&127)+1
            length=stride if packet&128 else stride*count
            chunk=blob[offset:offset+length];offset+=length
            if len(chunk)!=length:
                raise ValueError('Truncated TGA pixels.')
            pixels.extend(chunk*count if packet&128 else chunk)
    if len(pixels)!=expected:
        raise ValueError('Invalid TGA pixel count.')
    fmt=QImage.Format.Format_ARGB32_Premultiplied if stride==4 else QImage.Format.Format_BGR888
    image=QImage(bytes(pixels),width,height,width*stride,fmt).copy()
    if not flags&32:image=image.mirrored(False,True)
    if flags&16:image=image.mirrored(True,False)
    return image.convertToFormat(QImage.Format.Format_RGBA8888_Premultiplied)


def textures(tail):
    count = struct.unpack_from('>I', tail, 8)[0]
    offset, result = 12, []
    for _ in range(count):
        size = struct.unpack_from('>I', tail, offset)[0]
        codec = tail[offset+4]
        blob = tail[offset+5:offset+5+size]
        offset += 5+size
        if codec not in (0, 1):
            raise ValueError('Preview supports PNG/TGA textures only.')
        image = QImage.fromData(blob) if codec == 0 else decode_tga(blob)
        if image.isNull() or image.width() > 4096 or image.height() > 4096:
            raise ValueError('Invalid or oversized preview texture.')
        if codec==0:
            image = image.convertToFormat(QImage.Format.Format_RGBA8888)
        # Inochi's 0.8 writer saves GPU pixels already premultiplied. Reinterpret
        # those bytes; converting them would multiply alpha a second time.
            image.reinterpretAsFormat(QImage.Format.Format_RGBA8888_Premultiplied)
        result.append(image)
    return result


def encoded_png(image):
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    if not image.save(buffer, 'PNG'):
        raise ValueError('PNG encoding failed.')
    return bytes(data)


def interpolate(parameter, binding, requested):
    value = requested.get(parameter['name'], parameter['defaults'])
    if not isinstance(value, list) or len(value) != 2 or not finite_tree(value):
        raise ValueError('Pose values must be [x,y] finite pairs.')
    if any(not parameter['min'][i] <= value[i] <= parameter['max'][i] for i in range(2)):
        raise ValueError('Pose exceeds parameter range.')
    indices, weights = [], []
    for i, axis in enumerate(parameter['axis_points']):
        normalized = (value[i]-parameter['min'][i])/(parameter['max'][i]-parameter['min'][i])
        if len(axis) == 1:
            indices.append((0, 0)); weights.append(0)
        else:
            lower = max(0, min(len(axis)-2, bisect.bisect_right(axis, normalized)-1))
            indices.append((lower, lower+1))
            weights.append(max(0, min(1, (normalized-axis[lower])/(axis[lower+1]-axis[lower]))))
    (a,b),(c,d) = indices
    x,y = weights
    v = binding['values']
    def blend(aa,bb,cc,dd):
        return (aa*(1-x)+bb*x)*(1-y)+(cc*(1-x)+dd*x)*y
    if isinstance(v[a][c], (int,float)):
        return blend(v[a][c],v[b][c],v[a][d],v[b][d])
    return [[blend(v[a][c][k][i],v[b][c][k][i],v[a][d][k][i],v[b][d][k][i])
             for i in range(2)] for k in range(len(v[a][c]))]


def render(data, images, values, size=640, region=None):
    names = {p['name'] for p in data.get('param') or []}
    if set(values)-names:
        raise ValueError('Unknown pose parameter.')
    parts = list(walk(data['nodes']))
    root=data['nodes'].get('transform',{'trans':[0,0,0],'rot':[0,0,0],'scale':[1,1]})
    if any(root['trans']) or any(root['rot']) or root['scale'] != [1,1]:
        raise ValueError('Preview requires an identity root transform.')
    offsets, opacity = {}, {}
    for parameter in data.get('param') or []:
        if parameter.get('merge_mode','Additive')!='Additive':
            raise ValueError('Preview only supports additive parameters.')
        for binding in parameter.get('bindings') or []:
            if binding['param_name'] not in ('deform','opacity') or binding.get('interpolate_mode', 'Linear') != 'Linear':
                raise ValueError('Preview only supports linear deformation and opacity bindings.')
            current = interpolate(parameter, binding, values)
            if binding['param_name']=='opacity':
                # Part.setValue("opacity") multiplies offsetOpacity in Inochi 0.8.
                opacity[binding['node']]=opacity.get(binding['node'],1)*current
                continue
            target = offsets.setdefault(binding['node'], [[0,0] for _ in current])
            for i, delta in enumerate(current):
                target[i][0] += delta[0]; target[i][1] += delta[1]
    region=[0,0,1254,1254] if region is None else region
    if not isinstance(region,list) or len(region)!=4 or any(type(v) is not int for v in region):
        raise ValueError('Region must be integer [x,y,width,height].')
    rx,ry,rw,rh=region
    if min(rx,ry)<0 or min(rw,rh)<=0 or rx+rw>1254 or ry+rh>1254:
        raise ValueError('Preview region must stay inside the artwork canvas.')
    scale=size/max(rw,rh)
    pad_x,pad_y=(max(rw,rh)-rw)/2,(max(rw,rh)-rh)/2
    by_id={n['uuid']:n for n in parts}
    def drawable(part):
        if part['type'] == 'Node':
            if part is not data['nodes']:
                raise ValueError('Preview requires flat parts; nested transforms unsupported.')
            return None
        if part['type'] != 'Part':
            raise ValueError('Preview does not simulate driver or composite nodes.')
        if part.get('blend_mode', 'Normal') != 'Normal' or part.get('mask'):
            raise ValueError('Preview only supports Normal blending and explicit mask bindings.')
        transform = part['transform']
        if any(transform['rot']) or transform['scale'] != [1,1] or part['mesh'].get('origin', [0,0]) != [0,0]:
            raise ValueError('Preview requires unrotated, unit-scale source parts.')
        if part.get('tint', [1,1,1]) != [1,1,1] or any(part.get('screenTint', [0,0,0])):
            raise ValueError('Preview does not support color tinting.')
        image = images[part['textures'][0]]
        mesh = part['mesh']; verts=mesh['verts']; uvs=mesh['uvs']
        delta = offsets.get(part['uuid'], [[0,0] for _ in range(len(verts)//2)])
        tx,ty,_ = transform['trans']
        points = [((verts[2*i]+delta[i][0]+tx+627-rx+pad_x)*scale, (verts[2*i+1]+delta[i][1]+ty+627-ry+pad_y)*scale) for i in range(len(delta))]
        pixels = [(uvs[2*i]*image.width(),uvs[2*i+1]*image.height()) for i in range(len(delta))]
        surface=QImage(size,size,QImage.Format.Format_RGBA8888_Premultiplied)
        surface.fill(Qt.GlobalColor.transparent)
        painter=QPainter(surface)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        for j in range(0,len(mesh['indices']),3):
            ia,ib,ic = mesh['indices'][j:j+3]
            src=[pixels[i] for i in (ia,ib,ic)]; dst=[points[i] for i in (ia,ib,ic)]
            ux,uy=src[1][0]-src[0][0],src[1][1]-src[0][1]
            vx,vy=src[2][0]-src[0][0],src[2][1]-src[0][1]
            ax,ay=dst[1][0]-dst[0][0],dst[1][1]-dst[0][1]
            bx,by=dst[2][0]-dst[0][0],dst[2][1]-dst[0][1]
            det=ux*vy-uy*vx
            a=(ax*vy-bx*uy)/det; c=(-ax*vx+bx*ux)/det
            b=(ay*vy-by*uy)/det; d=(-ay*vx+by*ux)/det
            e=dst[0][0]-a*src[0][0]-c*src[0][1]; f=dst[0][1]-b*src[0][0]-d*src[0][1]
            clip=QPainterPath(QPointF(*dst[0]));clip.lineTo(QPointF(*dst[1]));clip.lineTo(QPointF(*dst[2]));clip.closeSubpath()
            painter.save();painter.setClipPath(clip)
            painter.setTransform(QTransform(a,b,c,d,e,f));painter.drawImage(0,0,image);painter.restore()
        painter.end()
        return surface
    stencil_cache={}
    def stencil(uuid):
        if uuid not in stencil_cache:
            source=by_id.get(uuid)
            if source is None or source['type']!='Part' or source.get('masks'):
                raise ValueError('Preview requires an existing, unmasked Part as mask source.')
            surface=drawable(source)
            threshold=source.get('mask_threshold',.5)
            if not isinstance(threshold,(int,float)) or not 0<=threshold<=1:
                raise ValueError('Invalid mask threshold.')
            # Inochi uses a binary stencil: alpha <= threshold is discarded.
            # Source visibility and opacity do not enter its mask shader.
            alpha=bytes(surface.constBits())[3::4].translate(bytes(255 if i/255>threshold else 0 for i in range(256)))
            stencil_cache[uuid]=QImage(alpha,size,size,size,QImage.Format.Format_Alpha8).copy()
        return stencil_cache[uuid]
    canvas=QImage(size,size,QImage.Format.Format_RGBA8888_Premultiplied)
    canvas.fill(QColor('#202227'))
    painter=QPainter(canvas)
    try:
        for part in sorted(parts,key=lambda n:n.get('zsort',0),reverse=True):
            if not part.get('enabled',True):continue
            surface=drawable(part)
            if surface is None:continue
            masks=part.get('masks',[])
            if masks:
                if len(masks)!=1 or masks[0].get('mode')!='Mask':
                    raise ValueError('Preview only supports one positive clipping mask per part.')
                mask=stencil(masks[0]['source'])
                p=QPainter(surface)
                p.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationIn)
                p.drawImage(0,0,mask);p.end()
            painter.setOpacity(max(0,min(1,part.get('opacity',1)*opacity.get(part['uuid'],1))))
            painter.drawImage(0,0,surface)
    finally:
        painter.end()
    return canvas


def process(request):
    store = RigStore(request['root'])
    data, tail = store.read(request['file'])
    output = request['output']
    mode = request.get('mode', 'preview')
    if mode=='eyes':
        from build_inochi_eyes import build
        return build(store,request['file'],output,request['manifest'],textures(tail),encoded_png)
    if mode=='mouth':
        from build_inochi_mouth import build
        return build(store,request['file'],output,request['manifest'],encoded_png)
    if mode=='idle':
        from inochi_idle_motion import add_idle
        return add_idle(store,request['file'],output)
    if mode=='motion_preview':
        from render_inochi_motion import render_motion
        return render_motion(store,request,textures(tail))
    if mode == 'texture':
        node = next(n for n in walk(data['nodes']) if n['uuid'] == request['node_uuid'])
        if node['type'] != 'Part':
            raise ValueError('Choose a texture-bearing part.')
        path = store.path(request['png'], extensions=('.png',))
        replacement = QImage(str(path))
        if replacement.isNull() or (replacement.width(),replacement.height()) != (1254,1254):
            raise ValueError('Replacement must be a full-canvas 1254x1254 PNG.')
        images = textures(tail)
        slot=node['textures'][0]; old=images[slot]; tx,ty,_=node['transform']['trans']
        if sum(n.get('textures',[None])[0]==slot for n in walk(data['nodes']))!=1:
            raise ValueError('Texture slot is shared; split it before replacing one part.')
        x,y=int(round(tx+627-old.width()/2)),int(round(ty+627-old.height()/2))
        if x < 0 or y < 0 or x+old.width()>1254 or y+old.height()>1254:
            raise ValueError('Part bounds escape the artwork canvas.')
        cropped=replacement.copy(x,y,old.width(),old.height()).convertToFormat(QImage.Format.Format_RGBA8888_Premultiplied)
        cropped.reinterpretAsFormat(QImage.Format.Format_RGBA8888)
        png=encoded_png(cropped)
        offset=12; sections=[]
        for i in range(len(images)):
            length=struct.unpack_from('>I',tail,offset)[0]
            section=tail[offset:offset+5+length];offset+=5+length
            sections.append(struct.pack('>IB',len(png),0)+png if i==slot else section)
        changed=tail[:12]+b''.join(sections)+tail[offset:]
        return store.save_new(output,data,changed)
    target=store.path(output,extensions=('.png',))
    if target.exists():
        raise ValueError('Preview output already exists.')
    images=textures(tail)
    poses=request.get('poses') or [{'label':'Rest','values':{}}]
    if not 1<=len(poses)<=12:
        raise ValueError('Render 1..12 inspection poses.')
    size=max(256,min(768,int(request.get('size',512))))
    cols=min(3,len(poses));rows=(len(poses)+cols-1)//cols;label=40
    sheet=QImage(cols*size,rows*(size+label),QImage.Format.Format_RGBA8888_Premultiplied);sheet.fill(QColor('#202227'))
    font_id=QFontDatabase.addApplicationFont('C:/Windows/Fonts/segoeui.ttf')
    fonts=QFontDatabase.applicationFontFamilies(font_id)
    if not fonts:
        raise ValueError('Preview label font is unavailable.')
    p=QPainter(sheet);p.setFont(QFont(fonts[0],12));p.setPen(QColor('#eceff4'))
    try:
        for i,pose in enumerate(poses):
            image=render(data,images,pose.get('values',{}),size,request.get('region'))
            x,y=(i%cols)*size,(i//cols)*(size+label)
            p.drawImage(x,y+label,image);p.drawText(QRectF(x+12,y,size-24,label),Qt.AlignmentFlag.AlignVCenter,pose['label'][:80])
    finally:
        p.end()
    encoded=encoded_png(sheet);target.parent.mkdir(parents=True,exist_ok=True)
    with target.open('xb') as stream:stream.write(encoded)
    return {'preview':output,'poses':len(poses),'width':sheet.width(),'height':sheet.height(),
            'renderer':'QPainter triangle inspection; not the Inochi runtime'}


if __name__ == '__main__':
    app=QGuiApplication.instance() or QGuiApplication([])
    print(json.dumps(process(json.load(sys.stdin))))
