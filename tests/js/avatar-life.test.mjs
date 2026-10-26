import test from 'node:test';
import assert from 'node:assert/strict';
import {AvatarLife,GESTURES,REST} from '../../companion/avatar/web/avatar-life.js';
import {AssistantMotion} from '../../companion/avatar/web/assistant-motion.js';

function random(seed=7){let state=seed;return ()=>{state=(Math.imul(state,1664525)+1013904223)>>>0;return state/4294967296;};}
const afternoon=()=>new Date(2026,9,24,14,0);
function run(life,seconds,fps=30){let layer;for(let i=0;i<Math.round(seconds*fps);i++)layer=life.update(1/fps);return layer;}

test('gestures start and end at rest and stay finite',()=>{
  for(const [name,gesture] of Object.entries(GESTURES)){
    for(const side of [-1,1]){
      for(const t of [0,gesture.duration])
        for(const [key,value] of Object.entries(gesture.at(t,side))){
          // Waking from sleep begins with the eyes still closed, matching the sleeping face.
          if(name==='wakeGentle'&&key==='eyes'&&t===0){assert.equal(value,-1);continue;}
          assert.ok(Math.abs(value)<1e-6,`${name} ${key} at ${t} is not at rest`);
        }
      for(let t=0;t<=gesture.duration;t+=.05)
        for(const [key,value] of Object.entries(gesture.at(t,side))){
          assert.ok(Number.isFinite(value),`${name} ${key}`);
          assert.ok(key in REST||key==='eyes2',`${name} uses unknown channel ${key}`);
        }
    }
  }
});

test('left alone she grows drowsy, falls asleep, and activity wakes her at once',()=>{
  const life=new AvatarLife(random(),afternoon);life.setSleepDelay(2);
  run(life,60);assert.equal(life.state,'awake');
  run(life,20);assert.equal(life.state,'drowsy');
  assert.ok(life.takeEvents().includes('drowsy'));
  let layer=run(life,60);
  assert.equal(life.state,'asleep');
  layer=run(life,10);
  assert.ok(layer.eyes<-.95,'eyes closed while asleep');
  assert.ok(layer.angleY<-12,'head has drooped');
  assert.equal(layer.blink,0,'no blinking with closed eyes');
  assert.ok(layer.zzz>.9&&layer.alertness===0);
  life.setMode('listening');
  assert.equal(life.state,'awake');
  assert.ok(life.snapshot().gestures.includes('wakeStartled'),'a conversation wakes her quickly');
  layer=run(life,2);
  assert.ok(layer.eyes>-.2,'eyes are open again within two seconds');
});

test('night falls sooner and "never" keeps her awake',()=>{
  const night=new AvatarLife(random(),()=>new Date(2026,9,24,23,30));night.setSleepDelay(10);
  assert.equal(night.delay(),420);
  const never=new AvatarLife(random(),afternoon);never.setSleepDelay(0);
  run(never,3600,10);assert.equal(never.state,'awake');
});

test('hovering must dwell to wake her, and keeps her awake',()=>{
  const life=new AvatarLife(random(),afternoon);life.setSleepDelay(2);
  run(life,200,10);assert.equal(life.state,'asleep');
  life.hover(true);run(life,.4);life.hover(false);assert.equal(life.state,'asleep','a passing pointer does not wake her');
  life.hover(true);run(life,1.2);assert.equal(life.state,'awake');
  assert.ok(life.snapshot().gestures.includes('wakeGentle'));
  run(life,300,10);assert.equal(life.state,'awake','the pointer resting on her keeps her company');
});

test('pokes react, repeated pokes fluster, and a sleeping poke wakes gently',()=>{
  const life=new AvatarLife(random(),afternoon);
  assert.equal(life.poke(),'poke');run(life,.5);
  assert.equal(life.poke(),'poke');run(life,.5);
  assert.equal(life.poke(),'fluster');
  const layer=run(life,1.2);
  assert.ok(layer.cheek>.8&&layer.mouthForm<-.5,'flustered: blushing and pouting');
  life.setSleepDelay(2);run(life,200,10);assert.equal(life.state,'asleep');
  assert.equal(life.poke(),'wake');assert.equal(life.state,'awake');
});

test('voice keeps priority over expressions and lifts the brows on emphasis',()=>{
  const life=new AvatarLife(random(),afternoon);life.setMode('speaking');
  for(let i=0;i<60;i++){life.setVoice(i%10<3?.95:.2);life.update(1/30);}
  assert.ok(life.layer.browY>.2,'emphasis raises the brows');
  life.play('yawn');const layer=run(life,1.4);
  assert.ok(layer.mouthOpen<=1&&layer.mouthOpen>=0);
});

test('long seeded runs stay within rig bounds across every state',()=>{
  const life=new AvatarLife(random(3),afternoon);life.setSleepDelay(2);
  const modes=['idle','listening','thinking','speaking','idle','attention','idle'];
  for(let i=0;i<20*60*10;i++){
    if(i%3000===0)life.setMode(modes[(i/3000)%modes.length]);
    if(i%2777===0)life.poke();
    life.setVoice(life.mode==='speaking'&&i%9<5?.7:0);
    const layer=life.update(.1);
    for(const [key,value] of Object.entries(layer))if(typeof value==='number')assert.ok(Number.isFinite(value),key);
    assert.ok(layer.eyes>=-1&&layer.eyes<=.45&&layer.lift>=-14&&layer.lift<=16&&layer.blink>=0&&layer.blink<=1);
  }
});

test('cues show a mood that fades back, gestures play once, and unknown cues do nothing',()=>{
  const life=new AvatarLife(random(),afternoon);
  assert.equal(life.cue('nonsense'),false);
  assert.equal(life.cue('Blush'),true);
  let layer=run(life,2);
  assert.ok(layer.cheek>.9,'blushing');
  assert.equal(life.snapshot().mood,'blush');
  layer=run(life,14);
  assert.equal(life.snapshot().mood,null);
  assert.ok(layer.cheek<.1,'the blush fades after a while');
  life.cue('smile');run(life,1);life.cue('calm');layer=run(life,4);
  assert.ok(layer.mouthForm<.1,'calm clears a mood at once');
  life.cue('laugh');layer=run(life,.9);
  assert.ok(layer.eyeSmile>.8&&layer.eyes<-.8,'laughing with closed, smiling eyes');
  life.cue('wink');layer=run(life,.4);assert.ok(layer.wink>.9);
  life.setSleepDelay(2);run(life,200,10);assert.equal(life.state,'asleep');
  life.cue('smile');assert.equal(life.state,'awake','a cue wakes her');
});

test('neutral clears a mood, and tester commands reach every sleep stage at once',()=>{
  const life=new AvatarLife(random(),afternoon);
  life.cue('pout');run(life,2);assert.ok(life.layer.mouthForm<-.5);
  life.cue('neutral');const layer=run(life,4);
  assert.ok(Math.abs(layer.mouthForm)<.08&&layer.cheek<.08,'back to her usual face');
  assert.ok(life.test('drowsy'));assert.equal(life.state,'drowsy');
  assert.ok(life.snapshot().gestures.includes('yawn'));
  assert.ok(life.test('sleep'));run(life,8);assert.equal(life.state,'asleep');assert.ok(life.layer.eyes<-.9);
  assert.ok(life.test('wake'));assert.equal(life.state,'awake');assert.ok(life.snapshot().gestures.includes('wakeGentle'));
  run(life,5);
  assert.ok(life.test('wakeStartled'),'waking can be replayed while already awake');
  assert.ok(life.snapshot().gestures.includes('wakeStartled'));
  for(const name of ['greet','poke','fluster','nodOff'])assert.ok(life.test(name),name);
  assert.equal(life.test('unknown'),false);
});

test('petting closes her eyes happily, builds a blush, and lingers as a smile',()=>{
  const life=new AvatarLife(random(),afternoon);
  for(let i=0;i<120;i++){life.pet(true,.5+.3*Math.sin(i/3));life.update(1/30);}
  let layer=life.layer;
  assert.ok(layer.eyes<-.8&&layer.eyeSmile>.8,'eyes closed in a smile');
  assert.ok(layer.cheek>.6,'blushing after a few seconds');
  assert.equal(life.snapshot().petting,true);
  life.pet(false);
  assert.equal(life.snapshot().mood,'smile','a content smile lingers');
  layer=run(life,2);assert.ok(layer.eyes>-.6,'eyes open again');
});

test('petting a sleeping avatar keeps her asleep, smiling, and a drowsy one drifts off',()=>{
  const life=new AvatarLife(random(),afternoon);life.setSleepDelay(2);
  run(life,200,10);assert.equal(life.state,'asleep');
  life.hover(true);
  for(let i=0;i<90;i++){life.pet(true,.5);life.update(1/30);}
  assert.equal(life.state,'asleep','petting does not wake her, even with the pointer resting on her');
  assert.ok(life.layer.mouthForm>.4&&life.layer.eyes<-.9,'smiling in her sleep');
  const drowsy=new AvatarLife(random(),afternoon);drowsy.setSleepDelay(2);
  run(drowsy,80,10);assert.equal(drowsy.state,'drowsy');
  for(let i=0;i<60*30;i++){drowsy.pet(true,.5);drowsy.update(1/30);}
  assert.equal(drowsy.state,'asleep','petted while drowsy, she falls asleep');
  assert.ok(life.test('pet'));
});

test('assistant motion drives the life layer only for rigs that accept it',()=>{
  const frames=[];
  const avatar={setParameters(){},setExpression(){},setTalkGain(){},setSwayGain(){},setLife(layer){frames.push(layer);}};
  const motion=new AssistantMotion(avatar,random());let now=0;
  motion.life.setSleepDelay(2);
  for(let i=0;i<30*200;i++){now+=1000/30;motion.update(1/30,now);}
  assert.equal(motion.life.state,'asleep');
  assert.ok(frames.at(-1).alertness===0);
  motion.request('speaking',now);assert.equal(motion.life.state,'awake');
  const plain=new AssistantMotion({setParameters(){},setExpression(){},setTalkGain(){},setSwayGain(){}},random());
  assert.equal(plain.life,null);
});

test('working on a task: focused, varied by step, expectant while waiting, and a happy finish',()=>{
  const life=new AvatarLife(random(),afternoon);life.setSleepDelay(2);
  life.work('start');
  let layer=run(life,4.5);  // After her opening thinking glance.
  assert.ok(layer.focus>.9&&layer.working==='think','focused on the task');
  assert.ok(layer.browY<0&&layer.browAngle<0,'brows drawn in concentration');
  life.work('read');
  const sweep=[];for(let i=0;i<60;i++){life.update(1/30);sweep.push(life.layer.gazeX);}
  assert.ok(Math.max(...sweep)-Math.min(...sweep)>.4,'her eyes travel along the lines she reads');
  life.work('type');layer=run(life,1.5);
  assert.ok(layer.gazeY<-.2,'eyes lowered while writing');
  life.work('wait');layer=run(life,1.5);
  assert.ok(layer.browY>.15&&Math.abs(layer.gazeX)<.15,'looking at the person, waiting for their answer');
  run(life,400,10);
  assert.equal(life.state,'awake','she does not doze off while working');
  life.work('done');
  assert.ok(life.events.includes('sparkle'));
  assert.equal(life.snapshot().mood,'smile');
  assert.equal(life.snapshot().working,null);
  life.work('start');life.work('failed');
  assert.equal(life.snapshot().mood,'worried');
});

test('micro-moments keep long tasks from looking frozen',()=>{
  const life=new AvatarLife(random(5),afternoon);
  life.work('start');life.work('type');
  const seen=new Set();
  for(let i=0;i<60*30;i++){life.update(1/30);for(const name of life.snapshot().gestures)seen.add(name);}
  assert.ok(['focusHard','checkIn','lipPress'].filter(name=>seen.has(name)).length>=2,`varied moments: ${[...seen]}`);
  assert.ok(life.test('work:look')&&life.snapshot().working==='look');
});
