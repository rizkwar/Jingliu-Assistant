import test from 'node:test';
import assert from 'node:assert/strict';
import {once} from 'node:events';
import {request} from 'node:http';
import {laneValue, interpolate, Pendulum, RigPlayer, deformParts} from '../../dev/rig/inochi-viewer/model.js';
import {createViewerServer} from '../../dev/rig/preview_inochi_avatar.mjs';

function fixture() {
  const head = {uuid: 4, name: 'Head', is_vec2: false, min: [-1, 0], max: [1, 1], defaults: [0, 0], axis_points: [[0, 1], [0]], bindings: [
    {node: 3, param_name: 'transform.t.x', values: [[-20], [20]]},
    {node: 2, param_name: 'deform', values: [[[[-10, 0], [-10, 0], [-10, 0]]], [[[10, 0], [10, 0], [10, 0]]]]}]};
  const hair = {uuid: 5, name: 'Hair', is_vec2: false, min: [-1, 0], max: [1, 1], defaults: [0, 0], axis_points: [[0, 1], [0]], bindings: []};
  return {puppet: {param: [head, hair], physics: {gravity: 9.8, pixelsPerMeter: 1000}, nodes: {children: [
    {uuid: 2, type: 'Part', transform: {trans: [0, 0, 0]}, mesh: {verts: [0, 0, 10, 0, 0, 10]}},
    {uuid: 3, type: 'SimplePhysics', param: 5, enabled: true, transform: {trans: [0, 0, 0], rot: [0, 0, 0]}, length: 180, gravity: .15, angle_damping: .85, output_scale: [5, 0]}]},
    animations: {Turn: {length: 600, timestep: 1 / 60, lanes: [{uuid: 4, target: 0, interpolation: 'Bezier', keyframes: [
      {frame: 0, value: 0, tension: 0}, {frame: 60, value: .7, tension: 0}, {frame: 120, value: 0, tension: 0}, {frame: 599, value: 0, tension: 0}]}]}}}};
}

test('bilinear keyforms and asymmetric blink interpolation stay bounded', () => {
  const p = {name: 'P', min: [-1, -1], max: [1, 1], defaults: [0, 0], axis_points: [[0, 1], [0, 1]]};
  const b = {values: [[[[0, 0]], [[0, 10]]], [[[10, 0]], [[10, 10]]]]};
  assert.deepEqual(interpolate(p, b, {'P': [.5, -.5]}), [[7.5, 2.5]]);
  const blink = {interpolation: 'Bezier', keyframes: [[0, 1], [90, 1], [94, 0], [96, 0], [104, 1], [599, 1]].map(([frame, value]) => ({frame, value, tension: 0}))};
  assert.equal(laneValue(blink, 95), 0); assert.equal(laneValue(blink, 599), 1);
  assert.ok(1 - laneValue(blink, 92) > laneValue(blink, 98));
});

test('damped pendulum follows an anchor and settles without length drift', () => {
  const p = new Pendulum([0, 0], 180, 1470, .85, 5); let maximum = 0, value;
  for (let i = 0; i < 1440; i++) {
    const a = [i >= 60 ? 30 : 0, 0]; value = p.step(a, 1 / 120); maximum = Math.max(maximum, Math.abs(value));
    assert.ok(Math.abs(Math.hypot(p.bob[0] - a[0], p.bob[1] - a[1]) - 180) < 1e-8);
  }
  assert.ok(maximum > .1); assert.ok(Math.abs(value) < 1e-7);
  for (const dt of [NaN, -1, 1]) assert.throws(() => p.step([0, 0], dt));
});

test('play, pause, seek, physics ownership and reset have distinct stable states', () => {
  const model = fixture(), original = structuredClone(model), p = new RigPlayer(model);
  assert.throws(() => p.setValue('Hair', 0, .5), /Disable physics/);
  for (const [name, axis, value] of [['Head', 0, NaN], ['Head', 0, 2], ['Head', 1, .5], ['unknown', 0, 0]]) assert.throws(() => p.setValue(name, axis, value));
  p.setPhysics(false); p.setValue('Hair', 0, .5); p.tick(.1); assert.equal(p.values.Hair[0], .5);
  p.selectClip('Turn'); p.playing = true; for (let i = 0; i < 120; i++) p.tick(1 / 120);
  assert.ok(Math.abs(p.values.Head[0] - .7) < 1e-9);
  p.playing = false; const paused = structuredClone(p.values), time = p.time;
  p.tick(.2); assert.deepEqual(p.values, paused); assert.equal(p.time, time);
  assert.throws(() => p.setValue('Head', 0, .1), /Manual/);
  p.seek(2); assert.ok(Math.abs(p.values.Head[0]) < 1e-8);
  p.setPhysics(true); p.seek(9); assert.ok(Math.abs(p.values.Hair[0]) < 1e-7);
  assert.throws(() => p.seek(Infinity)); assert.throws(() => p.selectClip('missing'));
  p.reset(); assert.equal(p.clip, null); assert.equal(p.playing, false); assert.equal(p.time, 0);
  for (const [name, expected] of Object.entries(p.defaults())) {
    assert.ok(p.values[name].every((v, axis) => Math.abs(v - expected[axis]) < 1e-12));
  }
  assert.deepEqual(model, original);
});

test('mesh deformation comes from saved offsets and uses source translation', () => {
  const model = fixture(), p = new RigPlayer(model); p.setValue('Head', 0, .5);
  const [part] = deformParts(model, p.values);
  assert.equal(part.vertices[0], 632); assert.equal(part.vertices[1], 627);
  assert.equal(part.opacity, 1);
});

test('loopback server exposes only allowlisted GET/HEAD assets and rejects hostile headers', async () => {
  const server = createViewerServer(new Map([['/', {body: Buffer.from('test'), type: 'text/plain'}]]));
  server.listen(0, '127.0.0.1'); await once(server, 'listening');
  const port = server.address().port;
  const get = (path, headers = {}, method = 'GET') => new Promise((resolve, reject) => {
    const req = request({host: '127.0.0.1', port, path, method, headers}, res => {
      let body = ''; res.on('data', b => body += b); res.on('end', () => resolve({status: res.statusCode, body, headers: res.headers}));
    }); req.on('error', reject); req.end();
  });
  try {
    const valid = await get('/'); assert.equal(valid.status, 200); assert.equal(valid.body, 'test');
    assert.ok(valid.headers['content-security-policy'].includes("default-src 'none'"));
    assert.equal((await get('/', {}, 'HEAD')).body, '');
    for (const path of ['/.env', '/../.env', '/%2e%2e/.env', '/model.json?path=.env', '/verification.json']) assert.equal((await get(path)).status, 404);
    assert.equal((await get('/', {}, 'POST')).status, 403);
    assert.equal((await get('/', {host: 'attacker.example.com'})).status, 403);
    assert.equal((await get('/', {origin: 'https://attacker.example.com'})).status, 403);
  } finally { server.closeAllConnections(); await new Promise(resolve => server.close(resolve)); }
});
