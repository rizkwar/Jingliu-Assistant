import test from 'node:test';
import assert from 'node:assert/strict';
import {authorPoint} from '../scripts/jingliu_inochi_keyforms.mjs';

test('abutting hair parts share a continuous head and sway field',()=>{
  for(const pose of [{angleX:-10,angleY:3,angleZ:-3},{angleX:10,angleY:-3,angleZ:3}]){
    for(const [x,y] of [[410,690],[830,690],[632,400],[530,600]]){
      const crown=authorPoint(x,y,{type:'hair',part:'long',root:240,tip:1200},pose,8);
      for(const part of ['bang','side','long'])assert.deepEqual(authorPoint(x,y,{type:'hair',part,root:260,tip:700},pose,8),crown);
    }
  }
});

test('neutral keyform preserves the drawing and bust crop stays fixed',()=>{
  for(const [x,y] of [[400,690],[650,340],[850,1050]])assert.deepEqual(authorPoint(x,y,{type:'hair'},{}),[x,y]);
  assert.deepEqual(authorPoint(850,1254,{type:'hair'},{angleX:10,angleY:3,angleZ:3},8),[850,1254]);
});

test('sway keeps crown roots still and bends the lower hair on both sides',()=>{
  assert.deepEqual(authorPoint(632,240,{type:'hair'},{},8),[632,240]);
  const l=authorPoint(400,850,{type:'hair'},{},8),r=authorPoint(850,850,{type:'hair'},{},8);
  assert(l[0]>400 && r[0]>850);
  assert.notEqual(l[0]-400,r[0]-850);
  assert(Math.abs(l[0]-400)<=8 && Math.abs(r[0]-850)<=8);
});
