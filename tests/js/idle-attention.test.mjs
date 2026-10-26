import test from 'node:test';
import assert from 'node:assert/strict';
import {IdleAttention,cursorTarget} from '../../dev/previews/head-motion-study/idle-attention.js';

function random(seed=37){let state=seed;return ()=>{state=(Math.imul(state,1664525)+1013904223)>>>0;return state/4294967296;};}
function advance(controller,seconds,fps=30){let out;for(let i=0;i<Math.round(seconds*fps);i++)out=controller.update(1/fps);return out;}

test('idle remains bounded and finite through varied turns and periods of stillness',()=>{
  const c=new IdleAttention(random()),bounds={angleX:12,angleY:4,angleZ:6,gazeX:.55,gazeY:.28,bodyAngleX:1.2,bodyAngleZ:.84};
  const headSamples=[],holds=[];let stationary=0,last=c.update(0).pose;
  for(let i=0;i<30*180;i++){
    const {pose,expression}=c.update(1/30);
    assert.equal(expression,'neutral');
    assert.deepEqual(Object.keys(pose).sort(),Object.keys(bounds).sort());
    for(const [key,bound] of Object.entries(bounds))assert.ok(Number.isFinite(pose[key])&&Math.abs(pose[key])<=bound+1e-9,key);
    assert.ok(Math.abs(pose.angleX-last.angleX)<.7,'head never jumps between planned poses');
    if(Math.abs(pose.angleX-last.angleX)<1e-8)stationary++;
    else if(stationary){if(stationary>15)holds.push(stationary/30);stationary=0;}
    headSamples.push(pose.angleX);last=pose;
  }
  assert.ok(Math.min(...headSamples)<-6&&Math.max(...headSamples)>6,'both viewing directions occur');
  assert.ok(holds.length>10&&Math.max(...holds)-Math.min(...holds)>1,'varied holds include real stillness');
});

test('seeded idle follows the same timing at 20, 30 and 60 FPS',()=>{
  function run(fps){const c=new IdleAttention(random()),out=[];for(let i=1;i<=fps*90;i++){const s=c.update(1/fps);if(i%fps===0)out.push(s.pose);}return out;}
  const baseline=run(20);
  for(const fps of [30,60])run(fps).forEach((pose,i)=>{
    for(const key of ['angleX','angleY','angleZ','gazeX','gazeY'])assert.ok(Math.abs(pose[key]-baseline[i][key])<1e-7,`${fps} ${i} ${key}`);
    for(const key of ['bodyAngleX','bodyAngleZ'])assert.ok(Math.abs(pose[key]-baseline[i][key])<.04,`${fps} ${i} ${key}`);
  });
});

test('cursor glance moves eyes first and shoulders follow the head',()=>{
  const c=new IdleAttention(()=>0);c.setCursor({x:1,y:.7});
  const s=advance(c,2.8,20);
  assert.equal(c.snapshot().kind,'cursor');
  assert.ok(s.pose.gazeX/.55>.8);
  assert.ok(s.pose.angleX/12<.1);
  assert.ok(Math.abs(s.pose.bodyAngleX)<Math.abs(s.pose.angleX*.1));
});

test('moving cursor cannot tug a glance, and attention disengages before a cooldown allows another',()=>{
  const c=new IdleAttention(()=>0);c.setCursor({x:1,y:.7});advance(c,2.7,20);
  const chosen={...c.target},notice=c.snapshot().notices,firstTime=c.time;
  let returned=false,againAt=null;
  for(let i=0;i<20*18;i++){
    c.setCursor({x:Math.sin(i*.3),y:Math.cos(i*.3)});
    c.update(.05);
    if(c.snapshot().kind==='cursor'&&c.snapshot().notices===notice)assert.deepEqual(c.target,chosen,'active glance target is held');
    if(c.snapshot().kind==='return')returned=true;
    if(c.snapshot().notices>notice){againAt=c.time;break;}
  }
  assert.ok(returned,'looks away even with continued pointer motion');
  assert.ok(againAt!==null&&againAt-firstTime>8,'continuous events respect cooldown');
});

test('disabled and stale cursors do not attract attention and disabling glances returns smoothly',()=>{
  const c=new IdleAttention(()=>0);c.setCursor({x:1,y:1});advance(c,3,20);
  const before=c.update(0).pose;c.setCursorEnabled(false);
  assert.deepEqual(c.update(0).pose,before,'disable does not snap the pose');
  advance(c,20,20);assert.equal(c.snapshot().notices,1);
  for(const key of ['angleX','angleY','angleZ'])assert.ok(Math.abs(c.update(0).pose[key])<=12);
  const stale=new IdleAttention(()=>.99);stale.setCursor({x:1,y:1});advance(stale,10,20);
  stale.random=()=>0;advance(stale,30,20);assert.equal(stale.snapshot().notices,0);
});

test('slow cumulative pointer movement can refresh attention without requiring a large single mouse event',()=>{
  const c=new IdleAttention(()=>.99);
  for(let i=0;i<30*35;i++){
    if(i===300)c.random=()=>0;
    c.setCursor({x:.5+.2*Math.sin(i/30*.7),y:.2});
    c.update(1/30);
  }
  assert.ok(c.snapshot().notices>0,'slow fresh movement is recognized after the initial glance opportunity');
});

test('snapshot updates and invalid elapsed times cannot advance time or consume randomness',()=>{
  let draws=0;const c=new IdleAttention(()=>{draws++;return .5;});c.setCursor({x:1,y:1});
  const before=c.update(0),time=c.time;
  for(const dt of [0,NaN,Infinity,-1,undefined])assert.deepEqual(c.update(dt),before);
  assert.equal(c.time,time);assert.equal(draws,0);
  c.update(50);assert.equal(c.time,.1);
  c.setIntensity(0,1);assert.ok(Object.values(c.update(0).pose).every(v=>v===0));
});

test('cursor normalization handles translated/scaled viewports, directions, bounds and invalid geometry',()=>{
  const rect={left:-800,top:100,width:500,height:600},point={x:-250,y:350};
  const a=cursorTarget(point,rect),b=cursorTarget({x:point.x+1200,y:point.y-400},{...rect,left:rect.left+1200,top:rect.top-400});
  assert.deepEqual(a,b,'negative monitor origins and window translation preserve direction');
  const scaled=cursorTarget({x:point.x*2,y:point.y*2},Object.fromEntries(Object.entries(rect).map(([k,v])=>[k,v*2])));
  assert.deepEqual(a,scaled,'CSS geometry scaling remains consistent');
  assert.equal(cursorTarget({x:-10000,y:-10000},rect).x,-1);
  assert.equal(cursorTarget({x:10000,y:10000},rect).x,1);
  assert.equal(cursorTarget({x:0,y:-10000},rect).y,1);
  assert.equal(cursorTarget({x:0,y:10000},rect).y,-1);
  for(const [p,r] of [[null,rect],[{x:NaN,y:0},rect],[point,{...rect,width:0}],[point,{...rect,height:Infinity}],[point,null]])assert.equal(cursorTarget(p,r),null);
});
