import test from 'node:test';
import assert from 'node:assert/strict';
import {ConversationVisual, VISUALS, visualMode} from '../companion/avatar_web/conversation-state.js';

function fixture() {
  const calls = {expressions:[], parameters:[]};
  const avatar = {setExpression:name => calls.expressions.push(name),
    setTalkGain:value => { calls.talkGain = value; },
    setParameters:(pose, weight) => calls.parameters.push([{...pose}, weight])};
  return {visual:new ConversationVisual(avatar), calls};
}

test('all app activities map to restrained styles, unknown states default to idle', () => {
  const expected = {ready:'idle', opening_mic:'listening', listening:'listening',
    transcribing:'thinking', thinking:'thinking', replying:'thinking',
    summarizing:'thinking', preparing_voice:'thinking', speaking:'speaking',
    error:'attention', suspended:'paused', closing:'paused'};
  for (const [state, mode] of Object.entries(expected)) assert.equal(visualMode(state), mode);
  assert.equal(visualMode('*smiles*'), 'idle');
  assert.equal(visualMode('__proto__'), 'idle');
  assert.equal(visualMode('constructor'), 'idle');
});

test('brief state changes coalesce and related preparation states do not restart the hold', () => {
  const {visual, calls} = fixture();
  visual.request('thinking', 0);
  visual.update(.02, 100);
  assert.equal(visual.mode, 'idle');
  visual.request('transcribing', 100);
  visual.update(.02, 180);
  assert.equal(visual.mode, 'thinking');
  assert.deepEqual(calls.expressions, ['neutral', 'halfLidded']);
  visual.request('ready', 200);
  visual.request('listening', 250);
  visual.update(.02, 400);
  assert.equal(visual.mode, 'thinking');
  visual.update(.02, 430);
  assert.equal(visual.mode, 'listening');
});

test('pose changes interpolate instead of jumping and converge to a small target', () => {
  const {visual} = fixture();
  const original = visual.pose.angleX;
  visual.request('thinking', 0);
  visual.update(.02, 200);
  assert.ok(visual.pose.angleX > original && visual.pose.angleX < VISUALS.thinking.pose.angleX);
  for (let i = 0; i < 200; i++) visual.update(.02, 220 + i*20);
  assert.ok(Math.abs(visual.pose.angleX - VISUALS.thinking.pose.angleX) < .001);
});

test('visual styles cannot animate the mouth or request unprepared expressive drawings', () => {
  for (const style of Object.values(VISUALS)) {
    assert.ok(['neutral', 'halfLidded'].includes(style.expression));
    assert.ok(!Object.keys(style.pose).some(key => key.startsWith('mouth')));
    assert.ok(style.talkGain <= .12);
    for (const [key,value] of Object.entries(style.pose)) {
      assert.ok(Number.isFinite(value));
      if (key.startsWith('angle')) assert.ok(Math.abs(value) <= 2);
    }
  }
});

test('rapid reversal discards the previous pending cue', () => {
  const {visual, calls} = fixture();
  visual.request('thinking', 0);
  visual.request('ready', 100);
  visual.update(.02, 1000);
  assert.equal(visual.mode, 'idle');
  assert.deepEqual(calls.expressions, ['neutral']);
});

test('speaking style never calls speech or lip-sync methods and drops its talk gain on return', () => {
  const {visual, calls} = fixture();
  visual.request('speaking', 0);
  visual.update(.02, 200);
  assert.equal(calls.talkGain, .12);
  visual.request('ready', 250);
  visual.update(.02, 450);
  assert.equal(calls.talkGain, 0);
});

test('zero movement pins head/body/gaze while retaining facial expressions and lip-sync isolation', () => {
  const {visual, calls} = fixture();
  visual.intensity = 0;
  visual.request('speaking', 0);
  visual.update(.1, 200);
  const [pose, weight] = calls.parameters.at(-1);
  assert.equal(weight, 1);
  assert.equal(calls.talkGain, 0);
  for (const [key, value] of Object.entries(pose)) {
    if (/^(angle|bodyAngle|gaze)/.test(key)) assert.equal(Math.abs(value), 0);
  }
  assert.ok(!Object.keys(pose).some(key => key.startsWith('mouth')));
});
