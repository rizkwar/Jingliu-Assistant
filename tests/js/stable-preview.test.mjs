import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {advanceFrame} from '../../companion/avatar/web/stable-step.js';
import {previewRuntime} from '../../dev/previews/head-motion-study/preview-runtime.mjs';

test('lagged frames keep runtime-style explicit springs stable while drawing once',()=>{
  let position=0,velocity=0,draws=0,time=0;
  for(let frame=0;frame<600;frame++){
    const interval=frame%3===0?.1:1/30;
    let frameDraws=0;
    advanceFrame(interval,(dt,draw,total)=>{
      const target=(Math.sin(time*1.5)+1)/2;
      velocity+=(120*(target-position)-2*Math.sqrt(120)*.95*velocity)*dt;
      position+=velocity*dt;time+=dt;
      assert.ok(Number.isFinite(position)&&position>=-.1&&position<=1.1);
      if(draw){frameDraws++;draws++;assert.equal(total,interval);}
    });
    assert.equal(frameDraws,1);
  }
  assert.equal(draws,600);
  assert.ok(Math.abs(time-(200*.1+400/30))<.000001);
});
test('long stalls and invalid elapsed time cannot replay an unbounded backlog',()=>{
  for(const seconds of [0,NaN,Infinity,-1,100]){
    const calls=[];advanceFrame(seconds,(dt,draw,total)=>calls.push({dt,draw,total}));
    assert.ok(calls.length<=5);assert.equal(calls.filter(c=>c.draw).length,1);
    assert.ok(calls.every(c=>Number.isFinite(c.dt)&&c.dt>=0&&c.dt<=.02));
    assert.ok(calls.at(-1).total<=.1);
  }
});
test('preview adapter accepts the pinned stable runtime without changing its code',()=>{
  const path=new URL('../../companion/avatar/web/vendor/mesh-avatar.js',import.meta.url);
  const before=readFileSync(path),after=previewRuntime(before);
  assert.match(after.toString(),/advanceStable\(M\)/);
  assert.match(after.toString(),/advance\(M, R = 60\)/);
  assert.equal(after.toString(),before.toString().replace(/\r\n/g,'\n'));
  assert.deepEqual(readFileSync(path),before);
  assert.throws(()=>previewRuntime(Buffer.from('unexpected update')),/runtime adapter/);
});
