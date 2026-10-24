"""Author a standalone mouth rig from native PhotoCraft artwork exports."""
import copy
import hashlib
import json
import math
import struct

from PySide6.QtGui import QImage
from avatar_rig_data import RigStore, walk
from build_inochi_eyes import binding


BOUNDS=(596,702,84,64)
OPEN_POINTS=[0,.04,.12,.35,.7,1]
COMPONENTS=('cavity','tongue','teeth','lower lip','upper lip')


def mesh_for(part,spacing=4):
    x,y,w,h=BOUNDS;cols=math.ceil(w/spacing);rows=math.ceil(h/spacing)
    tx,ty,_=part['transform']['trans'];verts=[];uvs=[];indices=[]
    for j in range(rows+1):
        for i in range(cols+1):
            verts.extend([x+w*i/cols-tx-627,y+h*j/rows-ty-627]);uvs.extend([i/cols,j/rows])
    for j in range(rows):
        for i in range(cols):
            a=j*(cols+1)+i;indices.extend([a,a+cols+1,a+1,a+1,a+cols+1,a+cols+2])
    return {'verts':verts,'uvs':uvs,'indices':indices,'origin':[0,0]}


def points(part):
    tx,ty,_=part['transform']['trans'];v=part['mesh']['verts']
    return [(x+tx+627,y+ty+627) for x,y in zip(v[::2],v[1::2])]


def transfer_affine(source,values,target):
    """Extend a saved affine mouth keyform onto the larger artwork rectangle.

    Check the actual saved source offsets rather than assuming the head field
    is affine. Reject sculpted/non-affine sources instead of approximating them.
    """
    original=points(source);x0=min(x for x,y in original);x1=max(x for x,y in original)
    y0=min(y for x,y in original);y1=max(y for x,y in original)
    if x1<=x0 or y1<=y0:raise ValueError('Source mouth mesh has no area.')
    def corner(x,y):return next(i for i,p in enumerate(original) if abs(p[0]-x)<1e-5 and abs(p[1]-y)<1e-5)
    a,b,c=(values[corner(x,y)] for x,y in ((x0,y0),(x1,y0),(x0,y1)))
    def sample(x,y):return [a[k]+(b[k]-a[k])*(x-x0)/(x1-x0)+(c[k]-a[k])*(y-y0)/(y1-y0) for k in (0,1)]
    if any(abs(v[k]-sample(x,y)[k])>5e-4 for (x,y),v in zip(original,values) for k in (0,1)):
        raise ValueError('Mouth head keyform is not affine; it needs a dedicated mesh transfer.')
    return [[round(v,6) for v in sample(x,y)] for x,y in points(target)]


def open_offsets(part,opening):
    factor=.08+.92*opening
    return [[0,round((y-723)*(factor-1),6)] for x,y in points(part)]


def form_offsets(part,form):
    scale=1+form*(.4 if form<0 else .15)
    return [[round((x-638)*(scale-1),6),0] for x,y in points(part)]


def jaw_offsets(face,opening):
    def smooth(a,b,x):
        t=max(0,min(1,(x-a)/(b-a)));return t*t*(3-2*t)
    return [[0,round(opening*2*math.exp(-((x-638)/165)**2)*smooth(714,757,y)*(1-smooth(785,835,y)),6)]
            for x,y in points(face)]


def build(store,file,output,manifest,encode_png):
    target=store.path(output);sidecar=target.with_suffix(target.suffix+'.verification.json')
    if target.exists() or sidecar.exists():raise ValueError('Choose a new output and verification filename.')
    data,tail=store.read(file)
    if len(data['nodes'].get('children',[]))!=29 or len(data.get('param') or [])!=6:
        raise ValueError('Start with the 29-part, six-control separated-eye checkpoint.')
    params={p['name']:p for p in data['param']}
    if not {'Head XY - small turn','Head tilt','Hair sway - manual test','Eye L open','Eye R open','Eye gaze XY'}<=params.keys():
        raise ValueError('The expected Jingliu head and eye controls are missing.')
    source=next(n for n in data['nodes']['children'] if n['name']=='Mouth - resting')
    face=next(n for n in data['nodes']['children'] if n['name']=='Face - clean base')
    spec_path=store.path(manifest,extensions=('.json',))
    if spec_path.stat().st_size>16384:raise ValueError('Mouth manifest is too large.')
    spec=json.loads(spec_path.read_text(encoding='utf8'))
    if not isinstance(spec,dict) or set(spec)!=set(COMPONENTS):
        raise ValueError('Manifest requires cavity, tongue, teeth, lower lip and upper lip PNG paths.')
    count=store.texture_count(tail);offset=12;sections=[]
    for _ in range(count):
        length=struct.unpack_from('>I',tail,offset)[0];sections.append(tail[offset:offset+length+5]);offset+=length+5
    extension=tail[offset:];art_hashes={}
    occupied={n['uuid'] for n in walk(data['nodes'])}|{p['uuid'] for p in data['param']}
    def uuid():
        value=920000
        while value in occupied:value+=1
        occupied.add(value);return value
    parts=[]
    for i,component in enumerate(COMPONENTS):
        png=store.path(spec[component],extensions=('.png',))
        if png.stat().st_size>16*1024*1024:raise ValueError('Mouth PNG exceeds 16 MiB.')
        image=QImage(str(png))
        if image.isNull() or (image.width(),image.height())!=(1254,1254):
            raise ValueError('Mouth artwork must be full-canvas 1254x1254 PhotoCraft PNG exports.')
        cropped=image.copy(*BOUNDS).convertToFormat(QImage.Format.Format_RGBA8888_Premultiplied)
        cropped.reinterpretAsFormat(QImage.Format.Format_RGBA8888)
        blob=encode_png(cropped);art_hashes[spec[component]]=hashlib.sha256(png.read_bytes()).hexdigest()
        part=copy.deepcopy(source);part.update(uuid=uuid(),name='Mouth - '+component,enabled=True,opacity=1,
            zsort=source['zsort']+.5-i*.08,textures=[len(sections),2**32-1,2**32-1])
        part.pop('masks',None);part['mesh']=mesh_for(part);parts.append(part)
        sections.append(struct.pack('>IB',len(blob),0)+blob)
        for parameter in data['param']:
            saved=next((b for b in parameter['bindings'] if b['node']==source['uuid'] and b['param_name']=='deform'),None)
            if saved:
                values=[[transfer_affine(source,key,part) for key in row] for row in saved['values']]
                parameter['bindings'].append(binding(part,'deform',values))
    cavity=parts[0];cavity['mask_threshold']=.5
    for part in parts[1:3]:part['masks']=[{'source':cavity['uuid'],'mode':'Mask'}]
    position=data['nodes']['children'].index(source)
    data['nodes']['children'][position:position]=parts
    binds=[binding(source,'opacity',[[v] for v in (1,.8,0,0,0,0)]),
           binding(face,'deform',[[jaw_offsets(face,o)] for o in OPEN_POINTS])]
    for component,part in zip(COMPONENTS,parts):
        binds.append(binding(part,'deform',[[open_offsets(part,o)] for o in OPEN_POINTS]))
        alpha=(0,0,.3,.85,1,1) if component=='teeth' else (0,0,.2,.7,1,1) if component=='tongue' else (0,.2,1,1,1,1)
        binds.append(binding(part,'opacity',[[v] for v in alpha]))
    data['param'].append({'uuid':uuid(),'name':'Mouth open','is_vec2':False,'min':[0,0],'max':[1,1],
        'defaults':[0,0],'axis_points':[OPEN_POINTS,[0]],'merge_mode':'Additive','bindings':binds})
    data['param'].append({'uuid':uuid(),'name':'Mouth form','is_vec2':False,'min':[-1,0],'max':[1,1],
        'defaults':[0,0],'axis_points':[[0,.5,1],[0]],'merge_mode':'Additive',
        'bindings':[binding(part,'deform',[[form_offsets(part,f)] for f in (-1,0,1)]) for part in parts]})
    new_tail=b'TEX_SECT'+struct.pack('>I',len(sections))+b''.join(sections)+extension
    RigStore.validate_data(data,len(sections))
    geometry=check_combined(data,parts+[face])
    result=store.save_new(output,data,new_tail)
    result.update(parts=len(data['nodes']['children']),parameters=len(data['param']),geometryChecks=geometry,
                  originalTextureSlotsPreserved=count,newTextureSlots=len(parts))
    with sidecar.open('x',encoding='utf8') as stream:
        json.dump({**result,'source':file,'manifest':manifest,'artworkSha256':art_hashes,
            'limits':['Standalone manual controls; no playback connection or phoneme recognition.',
                      'Rounded-to-wide shape control is not a phoneme classifier.',
                      'Sampled geometry does not prove continuous animation quality.']},stream,indent=2)
    return result


def check_combined(data,parts):
    from render_inochi_rig import interpolate
    params={p['name']:p for p in data['param']};tested=0;minimum=math.inf
    for part in parts:
        mesh=part['mesh'];verts=list(zip(mesh['verts'][::2],mesh['verts'][1::2]));zero=[[0,0] for _ in verts]
        def values(name,poses):
            p=params[name];b=next((b for b in p['bindings'] if b['node']==part['uuid'] and b['param_name']=='deform'),None)
            return [interpolate(p,b,{name:v}) if b else zero for v in poses]
        heads=values('Head XY - small turn',[[x,y] for x in (-1,-.5,0,.5,1) for y in (-1,-.5,0,.5,1)])
        tilts=values('Head tilt',[[x,0] for x in (-1,0,1)])
        opens=values('Mouth open',[[x,0] for x in (0,.04,.08,.12,.35,.7,1)])
        forms=values('Mouth form',[[x,0] for x in (-1,0,1)])
        indices=mesh['indices']
        def area(v,a,b,c):return (v[b][0]-v[a][0])*(v[c][1]-v[a][1])-(v[b][1]-v[a][1])*(v[c][0]-v[a][0])
        base=[area(verts,*indices[i:i+3]) for i in range(0,len(indices),3)]
        for head in heads:
            for tilt in tilts:
                for opening in opens:
                    for form in forms:
                        moved=[[v[k]+head[i][k]+tilt[i][k]+opening[i][k]+form[i][k] for k in (0,1)] for i,v in enumerate(verts)]
                        for j,original in enumerate(base):
                            ratio=area(moved,*indices[j*3:j*3+3])/original
                            if ratio<=0:raise ValueError(f'Combined mouth pose inverts {part["name"]}.')
                            minimum=min(minimum,ratio);tested+=1
    return {'testedTriangleInstances':tested,'invertedTriangles':0,'minimumAreaRatio':minimum,
            'sampling':'25 head XY x 3 tilts x 7 mouth openings x 3 mouth forms; mouth parts and face/jaw.'}
