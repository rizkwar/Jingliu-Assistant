import test from 'node:test';
import assert from 'node:assert/strict';
import {MotionPreview} from '../companion/avatar_web/motion-preview.js';
import {AssistantMotion} from '../companion/avatar_web/assistant-motion.js';

const bounds={angleX:12,angleY:4,angleZ:8,bodyAngleX:1.5,bodyAngleZ:1.2,gazeX:.6,gazeY:.3};
const keys=Object.keys(bounds).sort();
function random(seed=37){let state=seed;return ()=>{state=(Math.imul(state,1664525)+1013904223)>>>0;return state/4294967296;};}
function harness(){
  // Only posture-owned avatar APIs exist. A preview that attempts to synthesize
  // audio or to take over lip-sync, breath or blinking fails at the call site.
  const avatar={pose:null,expressions:[],talk:[],sway:[],
    setParameters(pose,weight){this.pose={...pose};assert.equal(weight,1);},
    setExpression(value){this.expressions.push(value);},
    setTalkGain(value){this.talk.push(value);},
    setSwayGain(value){this.sway.push(value);}};
  const motion=new AssistantMotion(avatar,random());let now=0;
  return {motion,avatar,
    request(state){motion.request(state,now);},
    step(dt=1/30){now+=dt*1000;motion.update(dt,now);return {...avatar.pose};},
    advance(seconds,fps=30){let pose;for(let i=0;i<Math.round(seconds*fps);i++)pose=this.step(1/fps);return pose;}};
}

test('silent finite preview reaches both turns, a tilt and a settled resting pose',()=>{
  const preview=new MotionPreview(),samples=[];
  assert.ok(preview.duration>=10&&preview.duration<=15,'a short sample can finish without a separate stop action');
  assert.equal(preview.time,0);assert.equal(preview.finished,false);
  for(let i=0;i<Math.ceil(preview.duration*30)+90;i++){
    const value=preview.update(1/30);samples.push(value);
    assert.deepEqual(Object.keys(value.pose).sort(),keys);
    assert.ok(typeof value.label==='string'&&value.label.length>0);
    for(const [key,bound] of Object.entries(bounds))assert.ok(Number.isFinite(value.pose[key])&&Math.abs(value.pose[key])<=bound+1e-9,key);
  }
  assert.ok(Math.min(...samples.map(s=>s.pose.angleX))<=-9.9);
  assert.ok(Math.max(...samples.map(s=>s.pose.angleX))>=9.9);
  assert.ok(Math.max(...samples.map(s=>Math.abs(s.pose.angleZ)))>=5.9);
  const final=samples.at(-1);assert.equal(final.finished,true);assert.equal(preview.finished,true);
  assert.ok(Math.abs(preview.time-preview.duration)<1e-9);
  for(const [key,value] of Object.entries(final.pose))assert.ok(Math.abs(value)<.01,`${key} rests at ${value}`);
  assert.deepEqual(preview.update(1/30),final,'a completed sample does not start over');
});

test('preview eases from the current posture with eye lead and delayed shoulders',()=>{
  const initial={angleX:4,angleY:-1,angleZ:-2,bodyAngleX:.3,bodyAngleZ:-.2,gazeX:.12,gazeY:-.08};
  const fromCurrent=new MotionPreview(initial);
  assert.deepEqual(fromCurrent.update(0).pose,initial);
  const first=fromCurrent.update(1/30).pose;
  assert.ok(Math.abs(first.angleX-initial.angleX)<.1,'starting a sample preserves the current head position');
  const preview=new MotionPreview();let value;
  for(let i=0;i<45;i++)value=preview.update(1/30);
  assert.ok(value.pose.gazeX<-.25,'eyes are already looking toward the first target');
  assert.ok(Math.abs(value.pose.angleX)<1,'the head is only beginning to follow');
  assert.ok(Math.abs(value.pose.bodyAngleX)<Math.abs(value.pose.angleX*.1),'shoulders follow the head');
});

test('preview time, poses and labels remain consistent at 20, 30 and 60 FPS',()=>{
  function run(fps){
    const preview=new MotionPreview(),samples=[];let last=preview.update(0);
    for(let i=1;i<=fps*15;i++){
      const value=preview.update(1/fps);
      assert.ok(Math.abs(value.pose.angleX-last.pose.angleX)<1.1,'a turn is gradual rather than a frame jump');
      if(i%fps===0)samples.push({value,time:preview.time});last=value;
    }
    return samples;
  }
  const baseline=run(20);
  for(const fps of [30,60])run(fps).forEach(({value,time},i)=>{
    assert.ok(Math.abs(time-baseline[i].time)<1e-8);
    assert.equal(value.label,baseline[i].value.label);assert.equal(value.finished,baseline[i].value.finished);
    for(const key of ['angleX','angleY','angleZ','gazeX','gazeY'])assert.ok(Math.abs(value.pose[key]-baseline[i].value.pose[key])<1e-8,`${fps} FPS ${key}`);
    for(const key of ['bodyAngleX','bodyAngleZ'])assert.ok(Math.abs(value.pose[key]-baseline[i].value.pose[key])<.05,`${fps} FPS ${key}`);
  });
});

test('invalid time inputs do not advance a preview and a stalled frame stays bounded',()=>{
  const preview=new MotionPreview(),before=preview.update(0);
  for(const value of [undefined,null,NaN,Infinity,-Infinity,-1]){
    assert.deepEqual(preview.update(value),before);assert.equal(preview.time,0);
  }
  preview.update(60);assert.equal(preview.time,.1,'resuming a hidden or stalled view cannot skip the entire preview');
});

test('preview is gated by activity, actual playback and disabled movement',()=>{
  for(const state of ['opening_mic','listening','transcribing','thinking','replying','summarizing','preparing_voice','speaking','error','suspended','closing']){
    const h=harness();h.request(state);
    assert.equal(h.motion.startPreview(),false,`${state} blocks before state coalescing`);
    h.advance(.3);assert.equal(h.motion.startPreview(),false,`${state} blocks after state coalescing`);
    assert.equal(h.motion.snapshot().preview,null);
  }
  const voice=harness();voice.motion.setVoice(.2);assert.equal(voice.motion.startPreview(),false);
  voice.motion.resetVoice();assert.equal(voice.motion.startPreview(),true);
  const disabled=harness();disabled.motion.setControls(0,1,.45,true);
  assert.equal(disabled.motion.startPreview(),false,'target movement zero blocks while the slider still eases down');
  const transition=harness();transition.request('thinking');transition.advance(.3);transition.request('ready');
  assert.equal(transition.motion.startPreview(),false,'the previous focused pose must release before previewing');
  transition.advance(.3);assert.equal(transition.motion.startPreview(),true);
});

test('real activity, playback, suspension and movement off cancel a preview immediately',()=>{
  const actions=[
    h=>h.request('listening'),h=>h.request('thinking'),h=>h.request('speaking'),
    h=>h.motion.setVoice(.5),h=>h.motion.suspend(),h=>h.motion.setControls(0,1,.45,true),
  ];
  for(const action of actions){
    const h=harness();assert.equal(h.motion.startPreview(),true);const before=h.advance(2);
    assert.ok(h.motion.snapshot().preview);action(h);assert.equal(h.motion.snapshot().preview,null);
    const after=h.step();assert.ok(Math.abs(after.angleX-before.angleX)<1,'canceling hands the current pose back smoothly');
    h.advance(.5);assert.equal(h.motion.snapshot().preview,null,'cancellation does not queue a restart');
  }
});

test('preview preserves existing mouth, breath, blinking and cursor ownership',()=>{
  const h=harness();h.motion.idle.random=()=>0;
  h.motion.setCursor({x:1,y:.8});h.advance(3);assert.equal(h.motion.snapshot().attention.kind,'cursor');
  assert.equal(h.motion.startPreview(),true);const notices=h.motion.snapshot().attention.notices;
  for(let i=0;i<30*10;i++){
    h.motion.setCursor({x:Math.sin(i/10),y:.8});const pose=h.step();
    assert.deepEqual(Object.keys(pose).sort(),[...keys,'browY'].sort());
  }
  assert.equal(h.motion.snapshot().attention.notices,notices,'cursor motion cannot compete with a sample');
  assert.equal(h.motion.snapshot().expression,'neutral','open eye rig remains available for the gaze demonstration');
  assert.ok(h.avatar.expressions.every(value=>value==='neutral'));
  assert.ok(h.avatar.talk.every(value=>value===0),'no text-driven or synthetic audio emphasis is introduced');
  assert.ok(h.avatar.sway.every(value=>value>=.2&&value<=.8),'existing hair physics gains remain bounded');
});

test('movement and gaze settings still scale the sample instead of being bypassed',()=>{
  const full=harness(),reduced=harness();reduced.motion.setControls(.5,.4,.8,true);
  full.advance(5);reduced.advance(5);
  assert.equal(full.motion.startPreview(),true);assert.equal(reduced.motion.startPreview(),true);
  full.advance(3);reduced.advance(3);
  for(const key of keys){
    const multiplier=key.startsWith('gaze')?.2:.5;
    assert.ok(Math.abs(reduced.avatar.pose[key]-full.avatar.pose[key]*multiplier)<1e-7,key);
  }
  assert.equal(reduced.motion.snapshot().hair,.8);
  const before={...reduced.avatar.pose};reduced.motion.setControls(.7,0,.2,false);
  reduced.step();assert.ok(reduced.motion.snapshot().preview,'adjusting a nonzero preset preserves the active sample');
  assert.ok(Math.abs(reduced.avatar.pose.angleX-before.angleX)<1,'live controls ease instead of snapping');
  reduced.advance(3);assert.ok(reduced.motion.snapshot().preview);
  assert.equal(reduced.motion.snapshot().movement,.7);assert.equal(reduced.motion.snapshot().gaze,0);
  assert.equal(Math.abs(reduced.avatar.pose.gazeX),0);assert.equal(Math.abs(reduced.avatar.pose.gazeY),0);
  assert.equal(reduced.motion.snapshot().hair,.2);
});

test('sample completion returns to normal idle, and repeat clicks do not restart or queue it',()=>{
  const h=harness();assert.equal(h.motion.startPreview(),true);h.advance(2);
  const before=h.motion.snapshot().preview;
  assert.equal(h.motion.startPreview(),false);assert.deepEqual(h.motion.snapshot().preview,before);
  h.advance(15);assert.equal(h.motion.snapshot().preview,null);assert.equal(h.motion.snapshot().mode,'idle');
  const samples=[];for(let i=0;i<30*12;i++)samples.push(h.step().angleX);
  assert.ok(Math.max(...samples)-Math.min(...samples)>1,'ordinary idle movement resumes after the sample');
  assert.equal(h.motion.startPreview(),true);h.motion.stopPreview();h.motion.stopPreview();
  assert.equal(h.motion.snapshot().preview,null);assert.equal(h.motion.startPreview(),true,'the user can start another sample after stopping');
});
