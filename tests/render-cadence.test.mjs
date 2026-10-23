import test from 'node:test';
import assert from 'node:assert/strict';
import {RenderCadence} from '../companion/avatar_web/render-cadence.js';

test('quiet idle reduces draws while every active conversation phase keeps 30 FPS', () => {
  const c = new RenderCadence();
  assert.equal(c.frameRate('ready', false, 2000), 20);
  for (const state of ['listening', 'opening_mic', 'transcribing', 'thinking',
    'replying', 'summarizing', 'preparing_voice', 'speaking', 'error']) {
    assert.equal(c.frameRate(state, false, 2000), 30);
  }
  assert.equal(c.frameRate('ready', true, 2000), 30);
  c.boost(2000);
  assert.equal(c.frameRate('ready', false, 2999), 30);
  assert.equal(c.frameRate('ready', false, 3000), 20);
});

test('jittery high-refresh frames preserve the target cadence and elapsed animation time', () => {
  for (const hz of [60, 144]) {
    for (const [state, expected] of [['ready', 20], ['speaking', 30]]) {
      const c = new RenderCadence();
      let count = 0, elapsed = 0;
      for (let now = 0, i = 0; now < 10000; i++, now = i * 1000 / hz + (i % 3) * .2) {
        const dt = c.step(now, state, false);
        if (dt !== null) { count++; elapsed += dt; }
      }
      assert.ok(Math.abs(count - expected * 10) <= 1, `${hz} Hz: ${state} drew ${count}`);
      assert.ok(Math.abs(elapsed - 10) < .06);
    }
  }
});

test('speech and resume respond immediately without catching up hidden or stalled time', () => {
  const c = new RenderCadence();
  c.step(0, 'ready', false);
  assert.equal(c.step(10, 'ready', false), null);
  assert.notEqual(c.step(11, 'ready', true), null);
  assert.equal(c.step(10000, 'speaking', false), .1);
  assert.equal(c.step(10000, 'speaking', false), null);
  c.restart();
  assert.equal(c.step(20000, 'ready', false), 1 / 20);
});
