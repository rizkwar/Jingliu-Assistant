import test from 'node:test';
import assert from 'node:assert/strict';
import {RenderCadence} from '../companion/avatar_web/render-cadence.js';

test('idle, previews and conversation share a smooth 60 FPS target', () => {
  const c=new RenderCadence();
  for(const state of ['ready','listening','opening_mic','transcribing','thinking',
    'replying','summarizing','preparing_voice','speaking','error']){
    for(const voice of [false,true])assert.equal(c.frameRate(state,voice,2000),60);
  }
});

test('slower and high-refresh displays preserve cadence and elapsed motion time', () => {
  for(const hz of [30,50,59.94,60,75,90,120,144,165]){
    const c=new RenderCadence();let count=0,elapsed=0;
    for(let i=0;i<Math.ceil(hz*10);i++){
      const now=i*1000/hz+(i%3)*.15;
      const dt=c.step(now);
      if(dt!==null){count++;elapsed+=dt;}
    }
    assert.ok(Math.abs(count-Math.min(hz,60)*10)<=2,`${hz} Hz drew ${count}`);
    assert.ok(Math.abs(elapsed-10)<.08,`${hz} Hz simulated ${elapsed}s`);
  }
});

test('small vsync jitter does not repeatedly drop idle frames',()=>{
  const c=new RenderCadence();let count=0;
  for(let i=0;i<600;i++){
    const now=i*1000/60+(i%2===0?.2:-.2);
    if(c.step(now)!==null)count++;
  }
  assert.equal(count,600);
});

test('stalls get one bounded update and resume discards hidden elapsed time', () => {
  const c=new RenderCadence();
  assert.equal(c.step(0),1/60);
  assert.equal(c.step(10),null);
  assert.equal(c.step(10000),.1);
  assert.equal(c.step(10000),null);
  assert.equal(c.step(10001),null);
  c.restart();
  assert.equal(c.step(20000),1/60);
});

test('invalid timestamps cannot poison deadlines or produce extra draws',()=>{
  const c=new RenderCadence();c.step(0);
  for(const now of [NaN,Infinity,-Infinity,undefined])assert.equal(c.step(now),null);
  assert.equal(c.step(0),null);
  assert.ok(c.step(1000/60)>0);
});
