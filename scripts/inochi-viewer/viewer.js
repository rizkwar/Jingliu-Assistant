import {RigPlayer} from './model.js';
import {RigRenderer} from './renderer.js';

const $ = id => document.getElementById(id), inputs = [];
let model, player, renderer, zoom = 1, onlyPart = null, raf = 0, last = null;
let frames = 0, fpsStart = null, fps = 0, failure = null, renderedFrames = 0;
const friendly = {'Head XY - small turn': 'Head', 'Hair sway - manual test': 'Hair sway', 'Eye gaze XY': 'Gaze', 'Eye L open': 'Left eye open', 'Eye R open': 'Right eye open'};

function fail(message) {
  failure = message; cancelAnimationFrame(raf); raf = 0; last = null;
  if (player) player.playing = false;
  $('loading').hidden = true; $('error').hidden = false; $('error-message').textContent = message;
  $('status').textContent = 'Preview stopped';
  document.querySelectorAll('aside input, aside button, aside select').forEach(e => e.disabled = true);
}

function sync() {
  const clip = Boolean(player.clip), driven = player.byId.get(player.driver.param).name;
  for (const c of inputs) {
    c.input.disabled = clip || (player.physics && c.name === driven);
    c.input.value = player.values[c.name][c.axis];
    c.output.textContent = Number(c.input.value).toFixed(2);
  }
  $('clip').value = player.clip ?? ''; $('play').disabled = !clip || player.playing;
  $('pause').disabled = !player.playing; $('timeline').disabled = !clip;
  $('timeline').max = player.duration() || 1; $('timeline').value = player.time;
  $('time').textContent = `${player.time.toFixed(2)} s`;
  $('physics').checked = player.physics;
  $('status').textContent = player.clip ? `${player.playing ? 'Playing' : 'Paused'} · ${player.clip}` : 'Manual controls · silent';
  $('stats').textContent = `${renderer.meshes.size} parts · ${model.puppet.param.length} controls${fps ? ` · ${fps.toFixed(0)} fps` : ''}`;
  $('pose-hint').textContent = clip ? 'Animation owns these controls. Choose Manual controls to pose freely.' :
    player.physics ? 'Pose freely. Disable Hair follow-through to move hair manually.' : 'Pose freely, including manual hair sway.';
}

function render() { renderer.draw(player.values, zoom, onlyPart); renderedFrames++; sync(); }
function frame(now) {
  raf = 0;
  if (document.hidden || failure) { last = null; fpsStart = null; return; }
  try {
    if (last !== null) player.tick(Math.min(Math.max((now - last) / 1000, 0), .05));
    last = now; render(); frames++;
    if (fpsStart === null) { fpsStart = now; frames = 0; }
    else if (now - fpsStart >= 1000) { fps = frames * 1000 / (now - fpsStart); frames = 0; fpsStart = now; }
    raf = requestAnimationFrame(frame);
  } catch (e) { fail(e.message); }
}
function schedule() { if (!raf && !failure && !document.hidden) { last = null; raf = requestAnimationFrame(frame); } }
function act(callback) {
  if (!player || failure) return;
  try { callback(); last = null; render(); } catch (e) { fail(e.message); }
}

function controls() {
  for (const p of model.puppet.param) for (let axis = 0; axis < (p.is_vec2 ? 2 : 1); axis++) {
    const id = `parameter-${p.uuid}-${axis}`, wrapper = document.createElement('div'); wrapper.className = 'parameter';
    const label = document.createElement('label'); label.htmlFor = id;
    label.textContent = `${friendly[p.name] ?? p.name}${p.is_vec2 ? (axis ? ' · Y' : ' · X') : ''}`;
    const output = document.createElement('output'); output.htmlFor = id; label.append(output);
    const input = document.createElement('input'); input.type = 'range'; input.id = id;
    input.min = p.min[axis]; input.max = p.max[axis]; input.step = .01; input.value = p.defaults[axis];
    input.addEventListener('input', () => act(() => player.setValue(p.name, axis, Number(input.value))));
    wrapper.append(label, input); $('parameters').append(wrapper); inputs.push({name: p.name, axis, input, output});
  }
  for (const name of Object.keys(model.puppet.animations)) { const option = new Option(name, name); $('clip').add(option); }
  for (const p of model.puppet.nodes.children.filter(n => n.type === 'Part')) $('part').add(new Option(p.name, String(p.uuid)));
  document.querySelectorAll('aside input, aside button, aside select').forEach(e => e.disabled = false);
  $('clip').addEventListener('change', () => act(() => player.selectClip($('clip').value || null)));
  $('play').addEventListener('click', () => act(() => { player.playing = true; }));
  $('pause').addEventListener('click', () => act(() => { player.playing = false; }));
  $('reset').addEventListener('click', () => act(() => { player.reset(); }));
  $('reset-physics').addEventListener('click', () => act(() => player.resetPhysics()));
  $('physics').addEventListener('change', () => act(() => player.setPhysics($('physics').checked)));
  $('timeline').addEventListener('input', () => act(() => player.seek(Number($('timeline').value))));
  $('zoom').addEventListener('input', () => act(() => { zoom = Number($('zoom').value); $('zoom-value').textContent = `${Math.round(zoom * 100)}%`; }));
  $('part').addEventListener('change', () => act(() => { onlyPart = $('part').value ? Number($('part').value) : null; }));
}

$('retry').addEventListener('click', () => location.reload());
$('avatar').addEventListener('webglcontextlost', event => { event.preventDefault(); fail('The graphics context was lost. Reload the viewer to restore it.'); });
document.addEventListener('visibilitychange', () => {
  cancelAnimationFrame(raf); raf = 0; last = null; fpsStart = null; frames = 0;
  if (!document.hidden) schedule();
});
window.addEventListener('pagehide', () => { cancelAnimationFrame(raf); raf = 0; renderer?.destroy(); });
window.addEventListener('pageshow', e => { if (e.persisted) location.reload(); });
window.rigViewerDiagnostics = () => ({ready: Boolean(renderer) && !failure, error: failure,
  renderer: 'Inochi 0.8 subset inspection / WebGL', sourceSha256: model?.sourceSha256,
  renderedFrames, hidden: document.hidden, clip: player?.clip, playing: player?.playing,
  time: player?.time, physics: player?.physics, fps, zoom, onlyPart,
  values: player ? structuredClone(player.values) : {}, glError: renderer?.gl.getError()});

try {
  const response = await fetch('/model.json');
  if (!response.ok) throw Error('The prepared rig bundle is unavailable. Restart the preview launcher.');
  model = await response.json();
  if (model.format !== 'jingliu-inochi-inspection-1') throw Error('This viewer cannot read that bundle format.');
  const images = await Promise.all(model.textures.map(url => new Promise((resolve, reject) => {
    const image = new Image(); image.onload = () => resolve(image); image.onerror = () => reject(Error('A model texture is missing or invalid. Restart the launcher.')); image.src = url;
  })));
  player = new RigPlayer(model); renderer = new RigRenderer($('avatar'), model, images);
  controls(); $('loading').hidden = true; render(); schedule();
} catch (e) { fail(e.message || 'The saved rig could not be loaded.'); }
