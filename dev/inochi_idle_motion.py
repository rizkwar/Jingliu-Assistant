"""Native Inochi 0.8 idle tracks and one damped hair pendulum.

The preview evaluator implements the configured subset for inspection; Creator
runs its own animation player and SimplePhysics driver from the saved INX.
"""
import bisect
import copy
import hashlib
import json
import math

from avatar_rig_data import RigStore, walk

IDLE='Idle - blink and hair'
HAIR_TEST='Hair response test'
BLINK='Blink only'


def lane(parameter,axis,keys):
    return {'interpolation':'Bezier','uuid':parameter['uuid'],'target':axis,'merge_mode':'Forced',
            'keyframes':[{'frame':int(frame),'value':value,'tension':0} for frame,value in keys]}


def blink_keys(length,starts):
    keys={0:1,length-1:1}
    for start in starts:
        for offset,value in ((0,1),(4,0),(6,0),(14,1)):
            keys[start+offset]=value
    return sorted(keys.items())


def animation(length,lanes):
    return {'timestep':1/60,'additive':False,'animationWeight':1,'length':length,
            'leadIn':-1,'leadOut':-1,'lanes':lanes}


def add_idle(store,file,output):
    target=store.path(output);sidecar=target.with_suffix(target.suffix+'.verification.json')
    if target.exists() or sidecar.exists():raise ValueError('Choose a new output and verification filename.')
    data,tail=store.read(file)
    if len(data['nodes'].get('children',[]))!=34 or len(data.get('param') or [])!=8:
        raise ValueError('Start with the 34-part mouth checkpoint.')
    if data.get('animations'):raise ValueError('Preserve existing animations in a separate authoring pass.')
    parameters={p['name']:p for p in data['param']}
    required={'Head XY - small turn','Head tilt','Hair sway - manual test','Eye L open','Eye R open'}
    if not required<=parameters.keys():raise ValueError('Expected Jingliu motion controls are missing.')
    ids={n['uuid'] for n in walk(data['nodes'])}|{p['uuid'] for p in data['param']}
    uuid=930000
    while uuid in ids:uuid+=1
    crown=next(n for n in data['nodes']['children'] if n['name']=='Hair - crown')
    tx,ty,_=crown['transform']['trans'];verts=crown['mesh']['verts']
    point=min(range(len(verts)//2),key=lambda i:(verts[i*2]+tx+627-632)**2+(verts[i*2+1]+ty+627-400)**2)
    driver={'uuid':uuid,'name':'Hair follow-through - pendulum','type':'SimplePhysics','enabled':True,'zsort':0,
            'transform':{'trans':[verts[point*2]+tx,verts[point*2+1]+ty,0],'rot':[0,0,0],'scale':[1,1]},
            'lockToRoot':False,'param':parameters['Hair sway - manual test']['uuid'],
            'model_type':'Pendulum','map_mode':'AngleLength','gravity':.15,'length':180,
            'frequency':1,'angle_damping':.85,'length_damping':1,'output_scale':[5,0],'local_only':False}
    data['nodes']['children'].append(driver)
    for name in ('Head XY - small turn','Head tilt'):
        p=parameters[name]
        source=next(b for b in p['bindings'] if b['node']==crown['uuid'] and b['param_name']=='deform')
        for axis,key in ((0,'transform.t.x'),(1,'transform.t.y')):
            p['bindings'].append({'node':uuid,'param_name':key,'interpolate_mode':'Linear',
                'values':[[form[point][axis] for form in row] for row in source['values']],
                'isSet':copy.deepcopy(source['isSet'])})
    parameters['Head tilt']['bindings'].append({'node':uuid,'param_name':'transform.r.z','interpolate_mode':'Linear',
        'values':[[-math.pi/80],[0],[math.pi/80]],'isSet':[[True],[True],[True]]})
    def eye_lanes(length,starts):
        keys=blink_keys(length,starts)
        return [lane(parameters[name],0,keys) for name in ('Eye L open','Eye R open')]
    head=parameters['Head XY - small turn'];tilt=parameters['Head tilt']
    data['animations']={
        IDLE:animation(1080,eye_lanes(1080,[108,301,492,532,785,989])+[
            lane(head,0,[(0,0),(100,.12),(176,.12),(226,.42),(302,.42),(370,-.08),(440,-.08),
                         (515,-.30),(615,-.30),(740,.05),(820,.05),(915,.24),(1000,-.06),(1079,0)]),
            lane(head,1,[(0,0),(120,.05),(250,-.07),(390,.02),(500,.12),(640,.08),(790,-.02),(920,-.08),(1079,0)]),
            lane(tilt,0,[(0,0),(220,-.10),(420,.06),(620,.12),(820,-.08),(1079,0)])]),
        BLINK:animation(600,eye_lanes(600,[90,282,476])),
        HAIR_TEST:animation(720,eye_lanes(720,[])+[
            lane(head,0,[(0,0),(60,0),(90,.7),(150,.7),(186,-.7),(246,-.7),(282,0),(719,0)]),
            lane(head,1,[(0,0),(719,0)]),lane(tilt,0,[(0,0),(719,0)])])}
    result=store.save_new(output,data,tail)
    sampled=motion_samples(data,HAIR_TEST,12,120)
    result.update(drawableParts=34,physicsDrivers=1,parameters=8,animations=list(data['animations']),
                  textureSectionUnchanged=True,motionSamples=sampled['summary'])
    with sidecar.open('x',encoding='utf8') as stream:
        json.dump({**result,'source':file,'sourceSha256':hashlib.sha256(store.path(file).read_bytes()).hexdigest(),
            'limits':['Clips play after selecting them and pressing Play in Creator.',
                      'One shared pendulum drives the existing hair/earring keyforms.',
                      'Offline preview is a subset evaluator, not the Inochi runtime.',
                      'No assistant, cursor or voice playback connection.']},stream,indent=2)
    return result


def lane_value(lane,frame):
    keys=lane['keyframes'];frames=[k['frame'] for k in keys]
    i=bisect.bisect_left(frames,frame)
    if i==0:return keys[0]['value']
    if i==len(keys):return keys[-1]['value']
    a,b=keys[i-1],keys[i];t=(frame-a['frame'])/(b['frame']-a['frame'])
    if lane['interpolation']=='Bezier':
        # Inochi 0.8 uses Hermite endpoints with slope = 2 * arriving tension.
        slope=2*b.get('tension',.5)
        t=max(0,min(1,(-2*t**3+3*t**2)+slope*(2*t**3-3*t**2+t)))
    elif lane['interpolation']!='Linear':raise ValueError('Motion preview supports Linear/Bezier lanes only.')
    return a['value']+(b['value']-a['value'])*t


class Pendulum:
    """Configured rigid-pendulum/RK4 subset of Inochi2D 0.8.6 for inspection."""
    def __init__(self,anchor,length,gravity,damping,output_scale):
        self.length=length;self.gravity=gravity;self.damping=damping;self.output_scale=output_scale
        self.bob=[anchor[0],anchor[1]+length];self.velocity=0

    def step(self,anchor,dt,rotation=0):
        if not math.isfinite(dt) or not 0<=dt<=.25:raise ValueError('Use bounded 0..0.25 second preview steps.')
        h=dt
        while h>1e-10:
            step=min(h,.01);h-=step
            angle=math.atan2(-(self.bob[0]-anchor[0]),self.bob[1]-anchor[1])
            ratio=self.gravity/self.length;damp=self.damping*2*math.sqrt(ratio)
            def derivative(a,v):return (v,-ratio*math.sin(a)-damp*v)
            v=self.velocity;k1=derivative(angle,v)
            k2=derivative(angle+step*k1[0]/2,v+step*k1[1]/2)
            k3=derivative(angle+step*k2[0]/2,v+step*k2[1]/2)
            k4=derivative(angle+step*k3[0],v+step*k3[1])
            angle+=step*(k1[0]+2*k2[0]+2*k3[0]+k4[0])/6
            self.velocity+=step*(k1[1]+2*k2[1]+2*k3[1]+k4[1])/6
            self.bob=[anchor[0]-math.sin(angle)*self.length,anchor[1]+math.cos(angle)*self.length]
        dx,dy=self.bob[0]-anchor[0],self.bob[1]-anchor[1]
        x=dx*math.cos(rotation)+dy*math.sin(rotation);y=-dx*math.sin(rotation)+dy*math.cos(rotation)
        return math.atan2(-x,y)/math.pi*self.output_scale


class MotionPlayer:
    def __init__(self,data,animation,physics=True):
        self.data=data;self.clip=data['animations'][animation];self.parameters={p['uuid']:p for p in data['param']}
        self.driver=next(n for n in walk(data['nodes']) if n['type']=='SimplePhysics')
        d=self.driver;self.physics=physics and d.get('enabled',True)
        if d['model_type']!='Pendulum' or d['map_mode']!='AngleLength' or d.get('local_only'):
            raise ValueError('Preview supports the configured global angle-length pendulum only.')
        g=data['physics']['gravity']*data['physics']['pixelsPerMeter']*d['gravity']
        self.pendulum=Pendulum(d['transform']['trans'][:2],d['length'],g,d['angle_damping'],d['output_scale'][0])
        self.last_time=0

    def pose(self,seconds):
        from render_inochi_rig import interpolate
        if seconds<self.last_time or seconds-self.last_time>.25:raise ValueError('Sample motion chronologically in bounded steps.')
        values={p['name']:p['defaults'][:] for p in self.parameters.values()}
        # Native loops reset to frame zero; this preserves fractional frames for review.
        frame=(seconds/self.clip['timestep'])%self.clip['length']
        for l in self.clip['lanes']:
            p=self.parameters[l['uuid']];values[p['name']][l['target']]=lane_value(l,frame)
        anchor=self.driver['transform']['trans'][:2];rotation=self.driver['transform']['rot'][2]
        for p in self.parameters.values():
            for b in p.get('bindings',[]):
                if b['node']!=self.driver['uuid']:continue
                value=interpolate(p,b,values)
                if b['param_name']=='transform.t.x':anchor[0]+=value
                elif b['param_name']=='transform.t.y':anchor[1]+=value
                elif b['param_name']=='transform.r.z':rotation+=value
                else:raise ValueError('Unsupported motion-driver input binding.')
        target=self.parameters[self.driver['param']]
        output=self.pendulum.step(anchor,seconds-self.last_time,rotation) if self.physics else 0
        values[target['name']]=[max(target['min'][0],min(target['max'][0],output)),0]
        self.last_time=seconds
        return values


def inspection_data(data):
    """Remove only physics drivers/inputs after their outputs have been sampled."""
    ids={n['uuid'] for n in walk(data['nodes']) if n['type']=='SimplePhysics'}
    result={**data,'nodes':{**data['nodes'],'children':[n for n in data['nodes']['children'] if n['uuid'] not in ids]},
            'param':[{**p,'bindings':[b for b in p['bindings'] if b['node'] not in ids]} for p in data['param']]}
    return result


def motion_samples(data,animation,seconds=12,fps=60,physics=True):
    player=MotionPlayer(data,animation,physics);poses=[]
    for i in range(round(seconds*fps)+1):poses.append(player.pose(i/fps))
    hair=[v['Hair sway - manual test'][0] for v in poses]
    blink=[v['Eye L open'][0] for v in poses]
    return {'poses':poses,'summary':{'frames':len(poses),'hairMin':min(hair),'hairMax':max(hair),
        'hairEnd':hair[-1],'maximumHairStep':max(abs(b-a) for a,b in zip(hair,hair[1:])),
        'closedEyeSamples':sum(v<.05 for v in blink),'seconds':seconds,'sampleFps':fps}}
