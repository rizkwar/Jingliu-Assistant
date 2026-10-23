import test from 'node:test';
import assert from 'node:assert/strict';
import {drawingSize} from '../companion/avatar_web/render-quality.js';

test('HD adds supersampling at fractional desktop scaling; balanced preserves native scale',()=>{
  assert.deepEqual(drawingSize(320,332,1.25,false),[400,415]);
  assert.deepEqual(drawingSize(320,332,1.25,true),[600,623]);
});
test('quality stays bounded for large windows and high display scale',()=>{
  const size=drawingSize(640,700,4,true);
  assert.ok(Math.max(...size)<=2048);
  assert.ok(Math.min(...size)>0);
  assert.deepEqual(drawingSize(320,332,NaN,false),[320,332]);
});
