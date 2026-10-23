import test from 'node:test';
import assert from 'node:assert/strict';
import {Live2DRig,RigBlink} from '../companion/avatar_web/live2d-rig.js';
import {RigPreview} from '../companion/avatar_web/rig-preview.js';
const parameter=(id,min=-30,max=30,defaultValue=0)=>({id,min,max,default:defaultValue});

test('authored head keyforms turn in both directions and pitch independently',()=>{
  const rig=new Live2DRig(['ParamAngleX','ParamAngleY','ParamAngleZ'].map(id=>parameter(id)));
  const left=rig.pose({angleX:-12,angleY:4}),right=rig.pose({angleX:12,angleY:-4});
  assert.ok(left.ParamAngleX<-20&&right.ParamAngleX>20);
  assert.ok(left.ParamAngleY>15&&right.ParamAngleY<-15);
  assert.equal(left.ParamAngleZ,0);
  const extreme=rig.pose({angleX:Infinity,angleY:999});
  assert.ok(Object.values(extreme).every(Number.isFinite));
  assert.ok(extreme.ParamAngleY<=30);
});

test('playback mouth and eyelids obey actual model bounds without phantom parameters',()=>{
  const rig=new Live2DRig([parameter('ParamMouthOpenY',0,1),parameter('ParamEyeLOpen',0,1,1)]);
  const open=rig.pose({},{voice:.8,eyeOpen:.25});
  assert.equal(open.ParamMouthOpenY,.8);assert.equal(open.ParamEyeLOpen,.25);
  assert.equal(rig.pose({},{voice:0}).ParamMouthOpenY,0);
  assert.equal('ParamEyeROpen' in open,false);
  assert.ok(rig.missing().includes('ParamAngleX'));
});

test('paired blink closes and reopens, with no elapsed time while paused',()=>{
  const blink=new RigBlink(()=>0);let low=1,last=1;
  for(let i=0;i<200;i++){last=blink.update(1/60);low=Math.min(low,last);}
  assert.ok(low<.05);assert.equal(last,1);
  const time=blink.time;blink.update(0);assert.equal(blink.time,time);
});

test('rig preview includes left, right, up, down, a diagonal and a settled ending',()=>{
  const preview=new RigPreview();const labels=new Set();let left=0,right=0,up=0,down=0,previous=0,sample;
  for(let i=0;i<2000&&!preview.finished;i++){
    sample=preview.update(1/60);labels.add(sample.label);
    assert.ok(Math.abs(sample.pose.angleX-previous)<.5);
    previous=sample.pose.angleX;left=Math.min(left,previous);right=Math.max(right,previous);
    up=Math.max(up,sample.pose.angleY);down=Math.min(down,sample.pose.angleY);
    assert.equal('mouthOpen' in sample.pose,false);
  }
  assert.equal(preview.finished,true);assert.equal(labels.size,7);
  assert.ok(left<-10&&right>10&&up>3.5&&down<-3.5);
  assert.ok(Object.values(sample.pose).every(value=>Math.abs(value)<.02));
});
