import test from 'node:test';
import assert from 'node:assert/strict';
import {Live2DPhysics} from '../companion/avatar_web/live2d-physics.js';

function harness(fps=60){
  const values={ribbon:0,hair:0,head:0,mouth:.5},calls=[];
  const core={getParameterValueById:id=>values[id],setParameterValueById:(id,v)=>{values[id]=v;}};
  const clock=new Live2DPhysics((model,dt)=>{
    calls.push(dt);
    // Stateful solver with a dependent output and a meaningful minimum step.
    assert.ok(dt>=1/120-1e-12,'Tiny remainder steps destabilize particle velocities');
    model.setParameterValueById('ribbon',model.getParameterValueById('ribbon')+dt);
    model.setParameterValueById('hair',2*model.getParameterValueById('ribbon'));
  },['ribbon','hair'],fps);
  return {values,core,clock,calls,frame(dt){
    // The real Cubism renderer restores these saved values after every draw.
    values.ribbon=0;values.hair=0;
    clock.update(core,dt);return values.ribbon;
  }};
}

test('near-60-Hz jitter never sends tiny remainder steps into the solver',()=>{
  const h=harness();let seconds=0;
  for(let i=0;i<2400;i++){
    const dt=[.0166667,.000001,.0333334,.0166667][i%4];seconds+=dt;h.frame(dt);
  }
  assert.ok(h.calls.every(dt=>dt===1/60));
  assert.equal(h.calls.length,Math.floor((seconds+1e-9)*60));
  assert.ok(Math.abs(h.values.ribbon-(seconds-1/60))<1e-9);
});

test('redraws preserve the visible pose without advancing physics or touching mouth/head',()=>{
  const h=harness();h.frame(1/60);const shown=h.frame(1/120),steps=h.clock.steps;
  assert.ok(shown>0);
  for(let i=0;i<100;i++)assert.equal(h.frame(0),shown);
  assert.equal(h.clock.steps,steps);
  assert.equal(h.values.head,0);assert.equal(h.values.mouth,.5);
});

test('high-refresh frames interpolate retained output instead of flickering to rest',()=>{
  const h=harness();let previous=0;
  for(let i=0;i<240;i++){
    const shown=h.frame(1/120);
    assert.ok(shown>=previous);
    assert.ok(shown-previous<=1/120+1e-9);
    assert.ok(Math.abs(h.values.hair-2*shown)<1e-9);
    previous=shown;
  }
  assert.equal(h.clock.steps,120);
});

test('display scaling cannot feed back and amplify a later solver step',()=>{
  const h=harness();h.frame(1/60);
  for(let i=0;i<120;i++){
    h.values.ribbon*=100;h.values.hair*=100;
    h.clock.update(h.core,1/60);
  }
  assert.ok(Math.abs(h.values.ribbon-2)<1e-9);
  assert.ok(Math.abs(h.values.hair-4)<1e-9);
});

test('the same elapsed motion is preserved across 30, 60 and 120 FPS',()=>{
  const results=[30,60,120].map(rate=>{
    const h=harness();for(let i=0;i<rate*3;i++)h.frame(1/rate);
    return {steps:h.clock.steps,output:h.values.ribbon};
  });
  assert.ok(results.every(r=>r.steps===180));
  assert.ok(results.every(r=>Math.abs(r.output-(3-1/60))<1e-9));
});

test('hidden-time stalls and invalid clocks cannot replay an unbounded backlog',()=>{
  const h=harness();h.frame(60);
  assert.equal(h.clock.steps,6);
  for(const dt of [NaN,Infinity,-1,undefined])h.frame(dt);
  assert.equal(h.clock.steps,6);
  assert.ok(Number.isFinite(h.values.ribbon));
  const fallback=harness(NaN);fallback.frame(1/60);assert.equal(fallback.clock.steps,1);
});
