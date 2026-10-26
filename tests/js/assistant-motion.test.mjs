import test from 'node:test';
import assert from 'node:assert/strict';
import {AssistantMotion} from '../../companion/avatar/web/assistant-motion.js';
import {cursorTarget} from '../../companion/avatar/web/idle-attention.js';

function random(seed=37){let state=seed;return ()=>{state=(Math.imul(state,1664525)+1013904223)>>>0;return state/4294967296;};}
function harness(seed=37){
  const avatar={pose:null,expressions:[],talk:[],sway:[],
    setParameters(pose,weight){this.pose={...pose};assert.equal(weight,1);},
    setExpression(value){this.expressions.push(value);},
    setTalkGain(value){this.talk.push(value);},
    setSwayGain(value){this.sway.push(value);}};
  const motion=new AssistantMotion(avatar,random(seed));let now=0;
  return {motion,avatar,get now(){return now;},
    request(state){motion.request(state,now);},
    step(dt=1/30){now+=dt*1000;motion.update(dt,now);return avatar.pose;},
    advance(seconds,fps=30){let pose;for(let i=0;i<Math.round(seconds*fps);i++)pose=this.step(1/fps);return pose;}};
}
const bounds={angleX:12,angleY:4,angleZ:8,bodyAngleX:1.5,bodyAngleZ:1.2,gazeX:.6,gazeY:.3,browY:1};

test('seeded long runs retain bounded coordinated poses through activity and voice changes',()=>{
  const h=harness(),samples=[];let last=h.step(0);
  for(let i=0;i<180*30;i++){
    if(i%450===0)h.request(['ready','listening','thinking','speaking','ready','transcribing'][Math.floor(i/450)%6]);
    h.motion.setCursor({x:Math.sin(i/80),y:Math.cos(i/110)});
    h.motion.setVoice(i%120<70?.8:0);
    const pose=h.step();
    assert.deepEqual(Object.keys(pose).sort(),Object.keys(bounds).sort());
    for(const [key,bound] of Object.entries(bounds))assert.ok(Number.isFinite(pose[key])&&Math.abs(pose[key])<=bound+1e-9,`${i} ${key}`);
    assert.ok(Math.abs(pose.angleX-last.angleX)<.7,'a state or target change cannot snap the head');
    samples.push(pose.angleX);last=pose;
  }
  assert.ok(Math.max(...samples)>3&&Math.min(...samples)<-3,'idle can naturally look in both directions');
  assert.ok(h.avatar.sway.every(value=>value>=.2&&value<=.8));
});

test('180 ms state coalescing avoids flicker and focused states choose compatible eyes',()=>{
  const h=harness();h.request('thinking');h.advance(.1,100);h.request('replying');
  h.advance(.07,100);assert.equal(h.motion.snapshot().mode,'idle');
  h.advance(.02,100);assert.equal(h.motion.snapshot().mode,'thinking');
  assert.equal(h.motion.snapshot().expression,'halfLidded');
  const focused=h.advance(6);
  assert.ok(Math.abs(focused.gazeX)<.001&&Math.abs(focused.gazeY)<.001,'half-eye patches keep their embedded irises centered');
  h.request('listening');h.advance(.1,100);
  assert.equal(h.motion.snapshot().mode,'thinking');
  h.advance(.09,100);assert.equal(h.motion.snapshot().mode,'listening');
  assert.equal(h.motion.snapshot().expression,'neutral','listening restores the open-eye rig');
  const listening=h.advance(6);
  assert.ok(Math.abs(listening.angleX)<1.5&&Math.abs(listening.bodyAngleX)<.2,'listening greatly reduces idle head and shoulder wandering');
  assert.ok(Math.abs(listening.browY-.06)<.001);
  h.request('ready');h.advance(.1,100);h.request('thinking');h.advance(.1,100);h.request('ready');
  h.advance(.1,100);assert.equal(h.motion.snapshot().mode,'listening','rapid changes wait for the latest stable state');
  h.advance(.09,100);assert.equal(h.motion.snapshot().mode,'idle');
});

test('posture controller leaves mouth, eyelids, and breath with their existing owners',()=>{
  const h=harness();
  for(const state of ['ready','thinking','listening','speaking','suspended','error']){
    h.request(state);h.motion.setVoice(.8);h.advance(2);
    assert.deepEqual(Object.keys(h.avatar.pose).sort(),Object.keys(bounds).sort());
  }
  assert.ok(h.avatar.talk.every(value=>value===0),'runtime text-driven talk nods stay disabled');
  assert.ok(h.avatar.expressions.every(value=>['neutral','halfLidded'].includes(value)));
});

test('speech emphasis requires real voice level and reset clears any pending nod',()=>{
  const h=harness();h.request('speaking');h.advance(2);
  assert.equal(h.motion.snapshot().nod,0,'speaking state alone is silent');
  h.motion.setVoice(.8);h.advance(1);
  assert.ok(h.motion.snapshot().nod>.5,'actual playback creates a small nod');
  const before=h.avatar.pose.angleY;
  h.motion.resetVoice();assert.equal(h.motion.snapshot().nod,0);
  h.step();assert.ok(Math.abs(h.avatar.pose.angleY-before)<.4,'audio reset releases the pose without a head snap');
  h.advance(3);assert.equal(h.motion.snapshot().nod,0,'reset playback cannot retrigger a nod');
  h.request('ready');h.advance(.3);h.motion.setVoice(1);h.advance(2);
  assert.equal(h.motion.snapshot().nod,0,'voice outside the speaking state does not animate emphasis');
  h.request('speaking');h.advance(2);assert.ok(h.motion.snapshot().nod>.5);
  h.motion.suspend();assert.equal(h.motion.snapshot().nod,0);
});

test('conversation focus cancels cursor attention immediately and waits to notice it again',()=>{
  const h=harness(37);h.motion.idle.random=()=>0;
  h.motion.setCursor({x:1,y:.5});h.advance(3);
  assert.equal(h.motion.snapshot().attention.kind,'cursor');
  const notices=h.motion.snapshot().attention.notices;
  h.request('listening');
  assert.equal(h.motion.snapshot().attention.cursorEnabled,false);
  assert.equal(h.motion.snapshot().attention.kind,'return','focus cancels the glance before the state debounce ends');
  for(let i=0;i<30*25;i++){h.motion.setCursor({x:Math.sin(i/10),y:.6});h.step();}
  assert.equal(h.motion.snapshot().attention.notices,notices,'moving the pointer cannot interrupt listening');
  h.request('thinking');h.advance(6);
  assert.equal(h.motion.snapshot().attention.notices,notices);
  h.request('ready');h.advance(.3);
  assert.equal(h.motion.snapshot().attention.cursorEnabled,true);
  h.advance(10);assert.equal(h.motion.snapshot().attention.notices,notices,'cleared cursor data is not reused when idle returns');
});

test('movement, gaze and hair controls ease toward their settings and cursor off releases attention',()=>{
  const h=harness();h.motion.idle.random=()=>0;h.motion.setCursor({x:1,y:.7});h.advance(3.7);
  const before={...h.avatar.pose};assert.ok(before.angleX>2&&before.gazeX>.2);
  h.motion.setControls(0,0,.8,false);
  assert.equal(h.motion.snapshot().movement,1,'control changes do not snap existing transforms');
  assert.equal(h.motion.snapshot().hair,.45);
  assert.equal(h.motion.snapshot().attention.cursorEnabled,false);
  h.step();
  assert.ok(h.motion.snapshot().movement>0&&h.motion.snapshot().movement<1);
  assert.ok(h.motion.snapshot().gaze>0&&h.motion.snapshot().gaze<1);
  assert.ok(h.motion.snapshot().hair>.45&&h.motion.snapshot().hair<.8);
  assert.ok(Math.abs(h.avatar.pose.angleX-before.angleX)<2,'first eased frame stays near the current pose');
  const notices=h.motion.snapshot().attention.notices;h.advance(5);
  assert.equal(h.motion.snapshot().movement,0);assert.equal(h.motion.snapshot().gaze,0);
  assert.equal(h.motion.snapshot().hair,.8);
  for(const key of Object.keys(bounds).filter(key=>key!=='browY'))assert.equal(Math.abs(h.avatar.pose[key]),0);
  for(let i=0;i<30*15;i++){h.motion.setCursor({x:Math.sin(i),y:1});h.step();}
  assert.equal(h.motion.snapshot().attention.notices,notices);
  h.motion.setControls(1,0,.2,true);h.advance(6);
  assert.ok(Math.abs(h.avatar.pose.angleX)>0,'zero gaze does not disable head movement');
  assert.equal(Math.abs(h.avatar.pose.gazeX),0);assert.equal(Math.abs(h.avatar.pose.gazeY),0);
  assert.equal(h.motion.snapshot().hair,.2);
});

test('cursor geometry uses rig metadata and remains stable across scale and negative monitor origins',()=>{
  const rig={image:{width:100,height:200},view:{padSide:.1,padTop:.25,gazeCenter:[20,50]}};
  const rect={left:-300,top:100,width:300,height:500};
  assert.deepEqual(cursorTarget({x:-210,y:300},rect,rig),{x:0,y:0},'uses the source eye position within the contain-fit image');
  const point={x:-110,y:170},target=cursorTarget(point,rect,rig);
  assert.equal(target.x,4/9);assert.equal(target.y,.4);
  assert.deepEqual(cursorTarget({x:point.x+2000,y:point.y-500},{...rect,left:rect.left+2000,top:rect.top-500},rig),target);
  assert.deepEqual(cursorTarget({x:point.x*2,y:point.y*2},Object.fromEntries(Object.entries(rect).map(([key,value])=>[key,value*2])),rig),target);
  assert.deepEqual(cursorTarget(point,rect,{image:{width:200,height:400},view:{padSide:.1,padTop:.25,gazeCenter:[40,100]}}),target);
  assert.deepEqual(cursorTarget(point,rect,{image:rig.image,view:{padSide:.1,padTop:.25},head:{cx:20,cy:50}}),target,'head metadata is the fallback eye center');
  assert.deepEqual(cursorTarget({x:-1e6,y:-1e6},rect,rig),{x:-1,y:1});
  assert.deepEqual(cursorTarget({x:1e6,y:1e6},rect,rig),{x:1,y:-1});
});

test('invalid rig and viewport metadata produce no cursor target rather than corrupting a pose',()=>{
  const point={x:20,y:20},rect={left:0,top:0,width:300,height:500};
  const rig={image:{width:100,height:200},view:{gazeCenter:[20,50]}};
  const invalid=[undefined,null,{}, {...rig,image:{width:0,height:200}}, {...rig,image:{width:100,height:NaN}},
    {...rig,view:{gazeCenter:{x:20,y:50}}}, {...rig,view:{gazeCenter:[]}}, {...rig,view:{gazeCenter:[20]}},
    {...rig,view:{gazeCenter:[20,Infinity]}}, {...rig,view:{gazeCenter:[20,50],padSide:-.5}},
    {...rig,view:{gazeCenter:[20,50],padTop:-1}}, {...rig,view:{gazeCenter:[20,50],padSide:'0.1'}}];
  for(const bad of invalid)assert.equal(cursorTarget(point,rect,bad),null,JSON.stringify(bad));
  for(const [p,r] of [[null,rect],[{x:NaN,y:0},rect],[point,null],[point,{...rect,width:0}],[point,{...rect,height:Infinity}]])assert.equal(cursorTarget(p,r,rig),null);
});
