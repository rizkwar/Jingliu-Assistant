import test from 'node:test';
import assert from 'node:assert/strict';
import {GLASSES_STYLES, headPose, glassesLayout, faceLayout, latticeWarp, pinToMesh, pinned, drawGlasses}
  from '../../companion/avatar/web/accessories.js';

const eye = (cx, bottom, width = 40) => ({left: cx - width / 2, right: cx + width / 2, top: bottom - 24, bottom});
const eyes = [eye(140, 200), eye(260, 200)];
const close = (a, b, slack = 1e-6) => Math.abs(a - b) < slack;

test('at rest the glasses sit evenly on both eyes, whichever order the eyes come in', () => {
  const layout = glassesLayout([eye(260, 200), eye(140, 200)], 'teacher');
  assert.equal(layout.yaw, 0);
  assert.equal(layout.roll, 0);
  const [left, right] = layout.lenses;
  assert.deepEqual(layout.lenses.map(lens => lens.side), [-1, 1]);
  assert.ok(close(200 - left.center.x, right.center.x - 200));  // Mirror images…
  assert.ok(close(left.width, right.width));
  assert.ok(left.width > 40);                                     // …wider than her eyes, anime style…
  assert.ok(left.center.x > 120 && right.center.x < 280);         // …one over each eye.
  assert.ok(close(layout.bridge[1].x, 200));                      // The bridge over her nose.
  assert.deepEqual(layout.arms, []);
});

test('without a face mesh, the nose says which way she turned', () => {
  const nose = {x: 220, y: 240};                   // Nose shifted to screen right: she turned toward it.
  assert.ok(headPose(eyes, {nose}).yaw > 0);
  const layout = glassesLayout(eyes, 'teacher', {nose});
  const [left, right] = layout.lenses;
  assert.ok(right.width < left.width);             // The lens on the far side is foreshortened.
  assert.ok(layout.bridge[1].x > 200);             // The bridge moves with her nose.
  assert.equal(layout.arms.length, 1);             // Only the near arm shows.
  assert.ok(layout.arms[0][1].x < left.center.x);
});

test('a lattice pinned to a mesh is a warp deformer', () => {
  // A square mesh of two triangles, then the same mesh squeezed on its right side, as a face turns.
  const rest = {vertices: Float32Array.from([0, 0, 100, 0, 0, 100, 100, 100]), indices: Uint16Array.from([0, 1, 2, 1, 3, 2])};
  const turned = Float32Array.from([10, 0, 80, 10, 10, 100, 80, 90]);
  const pin = pinToMesh({x: 25, y: 25}, [rest]);
  assert.equal(pin.miss, 0);
  assert.deepEqual(pinned(pin, [rest.vertices]), {x: 25, y: 25});
  const outside = pinToMesh({x: 120, y: 50}, [rest]);          // Beyond the mesh: carried by the nearest triangle.
  assert.ok(outside.miss > 0);
  const moved = pinned(outside, [turned]);
  assert.ok(moved.x < 120 && moved.x > 80);
  // Four pins make a grid; points between them are carried smoothly.
  const box = {left: 0, top: 0, width: 100, height: 100};
  const corners = [[{x: 0, y: 0}, {x: 100, y: 0}], [{x: 0, y: 100}, {x: 100, y: 100}]];
  const nodes = corners.map(row => row.map(p => pinned(pinToMesh(p, [rest]), [turned])));
  const follow = latticeWarp(box, nodes);
  assert.deepEqual(follow({x: 0, y: 0}), {x: 10, y: 0});
  assert.ok(close(follow({x: 100, y: 50}).x, 80));
  assert.ok(close(follow({x: 50, y: 50}).x, 45));
});

test('glasses carried by her face move with it, a little further for being in front', () => {
  const still = faceLayout(eyes, 'teacher', p => p);
  const rest = glassesLayout(eyes, 'teacher');
  assert.deepEqual(still.lenses.map(lens => lens.center), rest.lenses.map(lens => lens.center));
  assert.ok(close(still.line, rest.line));
  // Her face moved 30px right and shrank on the right as she turned: the glasses go with it.
  const follow = p => ({x: 30 + p.x - (p.x - 200) * .1, y: p.y});
  const turned = faceLayout(eyes, 'teacher', follow, {yaw: .3});
  assert.ok(turned.lenses[0].center.x > rest.lenses[0].center.x + 30);   // Parallax: further than her face.
  assert.equal(turned.arms.length, 1);                                    // The near arm.
  assert.ok(turned.arms[0][1].x < turned.lenses[0].center.x);
  assert.ok(close(turned.line, rest.line));                               // Turning does not thin the wire.
  assert.ok(faceLayout(eyes, 'teacher', p => p, {pitch: .3}).lenses[0].center.y < rest.lenses[0].center.y);
});

test('teacher glasses sit lower and finer than the others; blinking moves nothing', () => {
  const teacher = glassesLayout(eyes, 'teacher'), round = glassesLayout(eyes, 'round');
  assert.ok(teacher.lenses[0].center.y > round.lenses[0].center.y);
  assert.ok(teacher.line < round.line);
  assert.ok(teacher.lenses[0].height < round.lenses[0].height);
  const closed = glassesLayout([{...eye(140, 200), top: 190}, {...eye(260, 200), top: 190}]);
  assert.deepEqual(closed.lenses.map(lens => lens.center), teacher.lenses.map(lens => lens.center));
});

test('nothing is drawn without two eyes, and every style draws', () => {
  assert.equal(glassesLayout(null), null);
  assert.equal(glassesLayout([eye(140, 200)]), null);
  assert.equal(faceLayout([eye(140, 200)], 'teacher', p => p), null);
  const calls = [];
  const graphics = new Proxy({position: {set() {}}, visible: true}, {
    get: (target, name) => name in target ? target[name] : (...args) => calls.push(name),
    set: (target, name, value) => (target[name] = value, true)});
  assert.equal(drawGlasses(graphics, null), null);
  assert.equal(graphics.visible, false);
  for (const style of GLASSES_STYLES) {
    assert.ok(drawGlasses(graphics, faceLayout(eyes, style, p => p, {yaw: .2}), {frame: 'gold', lens: 'dark'}));
    assert.equal(graphics.visible, true);
  }
  assert.ok(calls.includes('drawPolygon') && calls.includes('quadraticCurveTo') && calls.includes('drawCircle'));
});
