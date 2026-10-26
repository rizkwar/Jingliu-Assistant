import test from 'node:test';
import assert from 'node:assert/strict';
import {RigReview} from '../../dev/previews/head-motion-study/rig-review.js';

test('rig review covers gaze limits and combined head poses while staying finite',()=>{
  const review=new RigReview(),samples=[];
  while(review.time<review.duration)samples.push(review.update(.05));
  assert.equal(Math.min(...samples.map(s=>s.pose.gazeX)),-.6);
  assert.equal(Math.max(...samples.map(s=>s.pose.gazeX)),.6);
  assert.ok(samples.some(s=>s.pose.angleX<=-11.99 && s.pose.angleY<=-3.99 && s.pose.angleZ<=-7.99));
  assert.ok(samples.some(s=>s.pose.angleX>=11.99 && s.pose.angleY>=3.99 && s.pose.angleZ>=7.99));
  assert.ok(samples.every(s=>Object.values(s.pose).every(Number.isFinite)));
  assert.ok(samples.at(-1).finished);
  assert.ok(Math.abs(samples.at(-1).pose.bodyAngleZ)<.001);
});
test('two brief drawn blinks close both eyes at a fixed turned pose',()=>{
  const review=new RigReview();let count=0,windows=0,closed=false;
  while(review.time<review.duration){
    const {pose}=review.update(.01),next=pose.eyeLOpen===0;
    assert.equal(pose.eyeLOpen,pose.eyeROpen);
    if(next){count++;assert.equal(Math.abs(pose.angleX),12);if(!closed)windows++;}
    closed=next;
  }
  assert.equal(windows,2);
  assert.ok(count>=48 && count<=52,`unexpected closed duration ${count/100}s`);
});
test('half-eye left/right probes use the same head position to expose sprite limitations',()=>{
  const review=new RigReview(),probes=[];
  while(review.time<review.duration){const value=review.update(.05);
    if(value.expression==='halfLidded'&&review.phaseTime>=review.current.travel)probes.push(value);
  }
  assert.ok(probes.some(s=>s.pose.gazeX<-.59));assert.ok(probes.some(s=>s.pose.gazeX>.59));
  assert.ok(probes.every(s=>s.pose.angleX===0&&s.pose.angleY===0&&s.pose.angleZ===0));
});
