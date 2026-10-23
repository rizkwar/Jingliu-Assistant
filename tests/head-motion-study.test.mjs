import test from 'node:test';
import assert from 'node:assert/strict';
import {HeadTurnStudy,DURATION,SEQUENCE} from '../scripts/head-motion-study/motion.js';

test('study reaches both directions, vertical looks, combined tilts and settled rest',()=>{
  const study=new HeadTurnStudy(),samples=[];
  for(let i=0;i<Math.ceil(DURATION*30)+120;i++)samples.push(study.update(1/30));
  for(const [key,bound] of [['angleX',12],['angleY',4],['angleZ',8],['gazeX',.28],['gazeY',.16]]){
    assert.ok(Math.min(...samples.map(s=>s.pose[key]))<=-bound+.001);
    assert.ok(Math.max(...samples.map(s=>s.pose[key]))>=bound-.001);
    assert.ok(samples.every(s=>Math.abs(s.pose[key])<=bound+.00001));
  }
  assert.ok(samples.some(s=>s.expression==='halfLidded'));
  assert.ok(samples.at(-1).finished);
  for(const v of Object.values(samples.at(-1).pose))assert.ok(Math.abs(v)<.01);
});
test('eyes anticipate head movement, and the body follows rather than moving as a flat card',()=>{
  const study=new HeadTurnStudy();
  for(let i=0;i<45;i++)study.update(.05);
  const state=study.update(0);
  assert.equal(state.label,'Look left');
  assert.ok(Math.abs(state.pose.gazeX/.28)>.5);
  assert.ok(Math.abs(state.pose.angleX/12)<.1);
  assert.ok(Math.abs(state.pose.bodyAngleX)<Math.abs(state.pose.angleX*.1));
});
test('elapsed time is consistent across 20, 30 and 60 FPS without abrupt head jumps',()=>{
  function run(fps){const study=new HeadTurnStudy(),out=[];let last=study.update(0);for(let i=1;i<=fps*36;i++){
    const value=study.update(1/fps);
    assert.ok(Math.abs(value.pose.angleX-last.pose.angleX)<1);
    if(i%fps===0)out.push(value.pose);last=value;
  }return out;}
  const baseline=run(20);
  for(const fps of [30,60])run(fps).forEach((pose,i)=>{
    for(const key of ['angleX','angleY','angleZ','gazeX','gazeY'])assert.ok(Math.abs(pose[key]-baseline[i][key])<.00001);
    assert.ok(Math.abs(pose.bodyAngleX-baseline[i].bodyAngleX)<.05);
  });
});
test('invalid times and stalls cannot jump forward through the sequence',()=>{
  const study=new HeadTurnStudy(),before=study.update(0);
  for(const value of [NaN,undefined,Infinity,-1])assert.deepEqual(study.update(value),before);
  study.update(100);assert.equal(study.time,.1);
  study.reset();assert.deepEqual(study.update(0),before);
});
test('pose experiment never owns breath, eyelids, mouth or expression tags in speech',()=>{
  const study=new HeadTurnStudy();
  for(let i=0;i<400;i++){
    const state=study.update(.1);
    assert.deepEqual(Object.keys(state.pose).sort(),['angleX','angleY','angleZ','bodyAngleX','bodyAngleZ','gazeX','gazeY'].sort());
    assert.ok(Object.values(state.pose).every(Number.isFinite));
  }
  assert.ok(SEQUENCE.every(s=>s.travel>0&&s.hold>0));
});
