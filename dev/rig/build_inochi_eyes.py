"""Add separated-eye keyforms to the saved Jingliu head experiment.

Artwork is prepared in PhotoCraft. This module only imports those pixels and
authors Inochi geometry, opacity bindings and clipping-mask references.
"""
import copy
import hashlib
import json
import math
import struct

from PySide6.QtGui import QImage
from avatar_rig_data import RigStore, walk


OPEN_POINTS=[0,.06,.16,.35,.65,1]
EYES={
    'L':{'upper':[(480,590),(490,588),(505,584),(521,582),(539,582),(557,584),(575,588),(592,594)],
         'lower':[(480,590),(487,596),(496,603),(507,611),(520,615),(537,617),(554,615),(570,610),(583,603),(592,594)],
         'closed':[(430,580),(465,590),(490,599),(520,602),(550,602),(580,599),(620,594)],'top':551,'bottom':633},
    'R':{'upper':[(680,582),(691,574),(707,569),(724,565),(741,565),(757,565),(774,566)],
         'lower':[(680,582),(686,589),(694,596),(704,602),(717,605),(732,604),(747,599),(759,591),(769,579),(774,566)],
         'closed':[(650,585),(680,591),(710,591),(740,588),(770,582),(830,563)],'top':533,'bottom':622},
}


def curve(points,x):
    if x<=points[0][0]:return points[0][1]
    for (a,b),(c,d) in zip(points,points[1:]):
        if x<=c:return b+(d-b)*(x-a)/(c-a)
    return points[-1][1]


def blink_offsets(part,side,component,opening):
    """Move lids and aperture; the round iris itself is never squashed."""
    eye=EYES[side];mesh=part['mesh'];tx,ty,_=part['transform']['trans']
    output=[]
    for x,y in zip(mesh['verts'][::2],mesh['verts'][1::2]):
        px,py=x+tx+627,y+ty+627
        upper,lower,closed=(curve(eye[k],px) for k in ('upper','lower','closed'))
        if component=='sclera aperture':
            # Leave positive area even at fully closed. Opacity hides the slit;
            # this also avoids degenerate meshes in the editor.
            dy=(closed-py)*.88*(1-opening)
        elif component=='upper lid':
            weight=max(0,min(1,(py-eye['top'])/max(1,upper-eye['top'])))
            dy=max(0,closed-upper)*(1-opening)*weight
        elif component=='lower lid':
            weight=max(0,min(1,(eye['bottom']-py)/max(1,eye['bottom']-lower)))
            dy=min(0,closed-lower)*(1-opening)*weight
        else:dy=0
        output.append([0,round(dy,6)])
    return output


def binding(node,kind,values):
    return {'node':node['uuid'],'param_name':kind,'values':values,
            'isSet':[[True for _ in row] for row in values],'interpolate_mode':'Linear'}


def build(store,file,output,manifest,images,encode_png):
    target=store.path(output)
    sidecar=target.with_suffix(target.suffix+'.verification.json')
    if target.exists() or sidecar.exists():
        raise ValueError('Choose a new output and verification filename.')
    data,tail=store.read(file)
    if len(data['nodes'].get('children',[]))!=23 or len(data.get('param') or [])!=3:
        raise ValueError('Start with the flat 23-part, three-control head checkpoint.')
    spec_path=store.path(manifest,extensions=('.json',))
    if spec_path.stat().st_size>32768:raise ValueError('Eye manifest is too large.')
    spec=json.loads(spec_path.read_text(encoding='utf8'))
    if not isinstance(spec,dict) or set(spec)!=set(EYES):raise ValueError('Manifest must contain L and R eye artwork.')
    components=('sclera aperture','iris','lower lid','upper lid')
    if any(not isinstance(spec[s],dict) or set(spec[s])!=set(components)|{'closed alternate'} for s in EYES):
        raise ValueError('Each eye needs sclera, iris, upper/lower lids and a closed alternate.')
    occupied={n['uuid'] for n in walk(data['nodes'])}|{p['uuid'] for p in data['param']}
    def uuid():
        candidate=910000
        while candidate in occupied:candidate+=1
        occupied.add(candidate)
        return candidate
    original_texture_count=store.texture_count(tail);offset=12;sections=[]
    for _ in range(original_texture_count):
        size=struct.unpack_from('>I',tail,offset)[0]
        sections.append(tail[offset:offset+5+size]);offset+=5+size
    extension=tail[offset:]
    old_parts={n['name']:n for n in data['nodes']['children']}
    eye_parts={};replacements={};art_hashes={}

    def texture(part,png):
        path=store.path(png,extensions=('.png',))
        if path.stat().st_size>16*1024*1024:raise ValueError('Eye PNG exceeds 16 MiB.')
        image=QImage(str(path))
        if image.isNull() or (image.width(),image.height())!=(1254,1254):
            raise ValueError('Eye parts must be full-canvas 1254x1254 PNGs exported by PhotoCraft.')
        original=images[part['textures'][0]]
        tx,ty,_=part['transform']['trans']
        x,y=round(tx+627-original.width()/2),round(ty+627-original.height()/2)
        if x<0 or y<0 or x+original.width()>1254 or y+original.height()>1254:
            raise ValueError('Eye source bounds escape the canvas.')
        cropped=image.copy(x,y,original.width(),original.height()).convertToFormat(QImage.Format.Format_RGBA8888_Premultiplied)
        cropped.reinterpretAsFormat(QImage.Format.Format_RGBA8888)
        blob=encode_png(cropped)
        part['textures']=[len(sections),2**32-1,2**32-1]
        sections.append(struct.pack('>IB',len(blob),0)+blob)
        art_hashes[png]=hashlib.sha256(path.read_bytes()).hexdigest()

    for side in EYES:
        original=old_parts[f'Eye {side} - open'];parts={}
        for i,component in enumerate(components):
            part=copy.deepcopy(original)
            part['uuid']=original['uuid'] if i==0 else uuid()
            part['name']=f'Eye {side} - {component}'
            part['enabled']=True;part['opacity']=1
            part['zsort']=original['zsort']+.3-i*.1
            texture(part,spec[side][component])
            parts[component]=part
            # New components share the exact source eye mesh and head keyforms.
            if i:
                for parameter in data['param']:
                    old=next(b for b in parameter['bindings'] if b['node']==original['uuid'] and b['param_name']=='deform')
                    cloned=copy.deepcopy(old);cloned['node']=part['uuid'];parameter['bindings'].append(cloned)
        parts['iris']['masks']=[{'source':parts['sclera aperture']['uuid'],'mode':'Mask'}]
        parts['sclera aperture']['mask_threshold']=.5
        closed=old_parts[f'Eye {side} - closed alternate']
        texture(closed,spec[side]['closed alternate'])
        closed['enabled']=True;closed['opacity']=1;closed['name']=f'Eye {side} - closed lash'
        parts['closed alternate']=closed
        replacements[original['uuid']]=list(parts.values())[:-1]
        eye_parts[side]=parts

    children=[]
    for part in data['nodes']['children']:
        children.extend(replacements.get(part['uuid'],[part]))
    data['nodes']['children']=children
    for side,parts in eye_parts.items():
        binds=[]
        for component,part in parts.items():
            if component in ('sclera aperture','upper lid','lower lid'):
                binds.append(binding(part,'deform',[[blink_offsets(part,side,component,o)] for o in OPEN_POINTS]))
            visibility=[0,0,1,1,1,1] if component!='closed alternate' else [1,1,0,0,0,0]
            binds.append(binding(part,'opacity',[[v] for v in visibility]))
        data['param'].append({'uuid':uuid(),'name':f'Eye {side} open','is_vec2':False,
            'min':[0,0],'max':[1,1],'defaults':[1,0],'axis_points':[OPEN_POINTS,[0]],
            'merge_mode':'Additive','bindings':binds})
    gaze=[]
    for parts in eye_parts.values():
        iris=parts['iris'];count=len(iris['mesh']['verts'])//2
        gaze.append(binding(iris,'deform',[[[[x*6,y*3] for _ in range(count)] for y in (-1,0,1)] for x in (-1,0,1)]))
    data['param'].append({'uuid':uuid(),'name':'Eye gaze XY','is_vec2':True,
        'min':[-1,-1],'max':[1,1],'defaults':[0,0],'axis_points':[[0,.5,1],[0,.5,1]],
        'merge_mode':'Additive','bindings':gaze})
    new_tail=b'TEX_SECT'+struct.pack('>I',len(sections))+b''.join(sections)+extension
    # Validate individual keyforms before running the combined-pose sampling.
    RigStore.validate_data(data,len(sections))
    report=check_combined(data,eye_parts)
    result=store.save_new(output,data,new_tail)
    result.update({'parts':len(children),'parameters':len(data['param']),'geometryChecks':report,
                   'originalTextureSlotsPreserved':original_texture_count,'newTextureSlots':len(sections)-original_texture_count})
    with sidecar.open('x',encoding='utf8') as stream:
        json.dump({**result,'source':file,'manifest':manifest,'artworkSha256':art_hashes,
                   'limits':['Standalone authoring rig; no assistant connection.',
                             'Small gaze shifts and exploratory head turns only.',
                             'Combined geometry samples do not establish visual quality.']},stream,indent=2)
    return result


def check_combined(data,eye_parts):
    from render_inochi_rig import interpolate
    tested=0;minimum=math.inf
    head,tilt=data['param'][:2]
    for side,parts in eye_parts.items():
        blink=next(p for p in data['param'] if p['name']==f'Eye {side} open')
        for part in parts.values():
            mesh=part['mesh'];n=len(mesh['verts'])//2;zero=[[0,0] for _ in range(n)]
            find=lambda p:next((b for b in p['bindings'] if b['node']==part['uuid'] and b['param_name']=='deform'),None)
            hb,tb,bb=find(head),find(tilt),find(blink)
            heads=[interpolate(head,hb,{head['name']:[x,y]}) for x in (-1,-.5,0,.5,1) for y in (-1,-.5,0,.5,1)]
            tilts=[interpolate(tilt,tb,{tilt['name']:[x,0]}) for x in (-1,0,1)]
            blinks=[interpolate(blink,bb,{blink['name']:[x,0]}) if bb else zero for x in (0,.06,.1,.16,.25,.35,.5,.65,.85,1)]
            verts=list(zip(mesh['verts'][::2],mesh['verts'][1::2]));indices=mesh['indices']
            def area(v,a,b,c):
                return (v[b][0]-v[a][0])*(v[c][1]-v[a][1])-(v[b][1]-v[a][1])*(v[c][0]-v[a][0])
            base=[area(verts,*indices[i:i+3]) for i in range(0,len(indices),3)]
            for h in heads:
                for t in tilts:
                    for b in blinks:
                        moved=[[v[0]+h[i][0]+t[i][0]+b[i][0],v[1]+h[i][1]+t[i][1]+b[i][1]] for i,v in enumerate(verts)]
                        for j,original in enumerate(base):
                            ratio=area(moved,*indices[j*3:j*3+3])/original
                            if ratio<=0:raise ValueError(f'Combined pose inverts {part["name"]}; reduce eye keyforms.')
                            minimum=min(minimum,ratio);tested+=1
    return {'testedEyeTriangleInstances':tested,'invertedTriangles':0,'minimumAreaRatio':minimum,
            'sampling':'25 head XY poses x 3 tilts x 10 eye openings; gaze is a rigid iris translation, sway has zero eye offsets.'}
