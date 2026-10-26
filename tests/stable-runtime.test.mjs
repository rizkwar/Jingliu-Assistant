import test from 'node:test';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {readFileSync, existsSync} from 'node:fs';
import {execFileSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {advanceFrame} from '../companion/avatar_web/stable-step.js';

const root = fileURLToPath(new URL('..', import.meta.url));
const source = readFileSync(new URL('../companion/avatar_web/vendor/mesh-avatar.js', import.meta.url), 'utf8').replace(/\r\n/g, '\n');
const hash = text => createHash('sha256').update(text).digest('hex');
const stableImport = "import {advanceFrame} from './stable-step.js';\n";
const stableMethod = '    /** Bounded spring steps with a single mesh draw per elapsed frame. */\n    advanceStable(M) {\n      if (!z) advanceFrame(M, (dt, draw, total) => E(dt, draw, total));\n    },\n';
const hdImport = "import {drawingSize} from './render-quality.js';\n";
const hdResize = `const x = this.canvas, hd = x.dataset.renderQuality === "hd", [h, T] = drawingSize(x.clientWidth, x.clientHeight, window.devicePixelRatio, hd);
      if (this.hd !== hd) {
        this.gl.activeTexture(this.gl.TEXTURE0);
        for (const layer of this.layers) {
          this.gl.bindTexture(this.gl.TEXTURE_2D, layer.tex);
          this.gl.texParameteri(this.gl.TEXTURE_2D, this.gl.TEXTURE_MIN_FILTER, hd ? this.gl.LINEAR : this.gl.LINEAR_MIPMAP_LINEAR);
        }
        this.hd = hd;
      }`;
const originalResize = 'const x = this.canvas, o = Math.min(window.devicePixelRatio || 1, 2), h = Math.round(x.clientWidth * o), T = Math.round(x.clientHeight * o);';

// Remove precisely the reviewed modifications. Matching the original upstream
// hash also proves unrelated runtime code and its license notices are preserved.
const hd = source.replace(stableImport, '')
  .replace('function E(M, draw = true, visualDt = M) {', 'function E(M) {')
  .replace('\n    if (!draw) return;', '')
  .replace('$?.update(R, W, visualDt, Fn(', '$?.update(R, W, M, Fn(')
  .replace(stableMethod, '');
const pristine = hd.replace(hdImport, '').replace(hdResize, originalResize);

test('bundled runtime contains only the reviewed HD and stable-frame patch', () => {
  assert.equal(hash(source), '1576e6550bcc64860cd4d06921f9a9df067e553bb4bd6301e6a32ffc45086b7e');
  assert.equal(hash(hd), '188ffa03914eb5ed765d98b7aa3cd273bdc5760cc0755ed92dab2ec42e096326');
  assert.equal(hash(pristine), '691301e4a2a89779617de4f4bf6c407c3003dc27161f5e4a3665566dfcff8e87');
  assert.match(source, /advance\(M, R = 60\)/);
  assert.match(source, /Copyright \(c\) 2026 Arjun Barrett/);
});

test('Python patch reproduces the exact bundle from all supported versions and rejects unknown input', () => {
  const venv = fileURLToPath(new URL(process.platform === 'win32' ? '../.venv/Scripts/python.exe' : '../.venv/bin/python', import.meta.url));
  const python = existsSync(venv) ? venv : process.platform === 'win32' ? 'python' : 'python3';
  const apply = input => execFileSync(python, ['-c', 'import sys; from dev.patch_avatar_runtime import patch; sys.stdout.buffer.write(patch(sys.stdin.buffer.read()))'], {cwd: root, input, stdio: ['pipe', 'pipe', 'pipe']});
  for (const input of [pristine, hd, source, source.replace(/\n/g, '\r\n')]) {
    assert.equal(apply(input).toString(), source);
  }
  assert.throws(() => apply(source + '// unreviewed change\n'), /known pinned runtime/);
});

test('real runtime advanceStable substeps motion and physics, updates sprites and draws once', () => {
  const body = source.slice(source.indexOf('  function E(M, draw'), source.indexOf('  let k = 0,'));
  assert.ok(body.startsWith('  function E('));
  const method = source.match(/    advanceStable\(M\) \{\n([\s\S]*?)\n    \},/)[1];
  const calls = {physics: [], sprites: [], draws: 0};
  const step = new Function('advanceFrame', 'calls', `
    const z = false, U = {pos:[], rest:[]}, O = [], C = [], X = {pos:[], rest:[]}, D = [], g = [];
    let position = 0, velocity = 0, time = 0;
    const A = dt => {
      time += dt;
      const target = (Math.sin(time * 1.5) + 1) / 2;
      velocity += (120 * (target - position) - 2 * Math.sqrt(120) * .95 * velocity) * dt;
      position += velocity * dt;
      if (!Number.isFinite(position) || position < -.1 || position > 1.1) throw Error('unstable motion');
      return {angleX: position};
    };
    const H = {step: (R, dt) => {calls.physics.push(dt); return {};}, chains: []};
    const $ = {update: (R, W, dt) => {calls.sprites.push(dt); return null;}};
    const I = {draw: () => calls.draws++}, q = {name:'neutral'}, L = {mode:'manual'};
    const Fn = () => null, i = () => ({});
    ${body}
    return M => {${method}};
  `)(advanceFrame, calls);
  for (let index = 0; index < 600; index++) step(index % 3 === 0 ? .1 : 1 / 30);
  assert.equal(calls.draws, 600);
  assert.equal(calls.sprites.length, 600);
  assert.equal(calls.sprites.filter(dt => dt === .1).length, 200);
  assert.ok(calls.physics.every(dt => dt <= .02 && dt > 0));
  assert.equal(calls.physics.length, 200 * 5 + 400 * 2);
});
