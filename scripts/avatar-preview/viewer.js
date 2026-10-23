import {loadMeshAvatar, PARAMS} from '/mesh-avatar.js';

const canvas = document.querySelector('#avatar');
const status = document.querySelector('#status');
const mode = document.querySelector('#mode');
const pauseButton = document.querySelector('#pause');
const buttons = [...document.querySelectorAll('button')];
const defaults = Object.fromEntries(PARAMS.map(parameter => [parameter.id, parameter.def]));
let avatar, frame = 0, previous = 0, elapsed = 0, paused = false, frames = 0;
let test = null, disposed = false;
buttons.forEach(button => { button.disabled = true; });

function idle() {
  test = null;
  avatar.stopLipSync(); avatar.setSpeaking(false); avatar.setVoiceLevel(0);
  avatar.setExpression('neutral'); avatar.setParameters({}); avatar.setAutoIdle(true);
  mode.textContent = 'Idle · subtle breathing, blinking, and hair movement.';
  drawOnce();
}
function pose(parameters, label = 'Pose review') {
  test = null;
  avatar.setAutoIdle(false); avatar.setExpression('neutral');
  avatar.setParameters({...defaults, ...parameters});
  mode.textContent = label; drawOnce();
}
function drawOnce() {
  if (avatar && !disposed && !document.hidden) { avatar.advance(0); frames++; }
}
function beginTest(name) {
  idle(); avatar.setAutoIdle(false);
  test = {name, start: elapsed};
  mode.textContent = name === 'blink' ? 'Blink · open → closed → open.' : 'Mouth shapes · silent animation test.';
  if (paused) togglePause();
}
function tick(now) {
  frame = 0;
  if (paused || document.hidden || disposed) return;
  const dt = previous ? Math.max(0.000001, Math.min((now - previous) / 1000, 0.05)) : 1 / 60;
  previous = now; elapsed += dt;
  if (test) {
    const t = elapsed - test.start;
    if (test.name === 'blink') {
      const open = t < 0.16 ? 1 - t / 0.16 : t < 0.42 ? 0 : Math.min(1, (t - 0.42) / 0.24);
      avatar.setParameters({...defaults, eyeLOpen:open, eyeROpen:open});
      if (t > 0.75) idle();
    } else {
      const shapes = [{mouthOpen:0.8,mouthForm:0},{mouthOpen:0.45,mouthForm:0},
        {mouthOpen:0.55,mouthForm:-0.9},{mouthOpen:0.7,mouthForm:0.9}];
      const segment = Math.floor(t / 0.8);
      if (segment >= 8) idle();
      else {
        const phase = t % 0.8;
        avatar.setParameters({...defaults, ...shapes[segment % shapes.length],
          ...(phase > 0.64 ? {mouthOpen:0} : {})});
      }
    }
  }
  // advance() rounds seconds * fps to an integer. One actual elapsed-time step
  // avoids rounding to zero on displays whose refresh rate is above 120 Hz.
  avatar.advance(dt, 1 / dt); frames++;
  frame = requestAnimationFrame(tick);
}
function resumeLoop() {
  if (!frame && !paused && !document.hidden && !disposed) { previous = 0; frame = requestAnimationFrame(tick); }
}
function togglePause() {
  paused = !paused;
  pauseButton.textContent = paused ? 'Resume' : 'Pause';
  pauseButton.setAttribute('aria-pressed', String(paused));
  status.textContent = paused ? 'Paused' : 'Ready · v5 rig';
  if (paused) { cancelAnimationFrame(frame); frame = 0; }
  else resumeLoop();
}

const resizeObserver = new ResizeObserver(() => { if (paused) drawOnce(); });
try {
  avatar = await loadMeshAvatar(canvas, '/avatar.mavatar', {manual:true, fit:'contain'});
  avatar.setAutoMotion(false); avatar.setSwayGain(0.45); avatar.setTalkGain(0.35);
  idle(); status.textContent = 'Ready · v5 rig';
  buttons.forEach(button => { button.disabled = false; });
  const actions = {
    idle, blink:() => beginTest('blink'), mouth:() => beginTest('mouth'),
    smile:() => pose({eyeLOpen:0,eyeROpen:0,eyeSmile:1,eyeSmileL:1}, 'Gentle closed-eye smile.'),
    left:() => pose({angleX:-25}, 'Head turn · left.'),
    right:() => pose({angleX:25}, 'Head turn · right.'),
    pause:togglePause,
    background:() => {
      const checker = document.querySelector('#stage').classList.toggle('checker');
      document.querySelector('#background').setAttribute('aria-pressed', String(checker));
    },
  };
  buttons.forEach(button => button.addEventListener('click', () => actions[button.dataset.action]()));
  // Local review diagnostics; no link to the assistant, microphone, TTS or user data.
  window.avatarPreview = Object.freeze({
    pose, idle,
    getState:() => ({ready:true, paused, frames, test:test?.name ?? null,
      parameters:avatar.getParameters(), canvas:[canvas.width,canvas.height]}),
  });
  resizeObserver.observe(canvas); resumeLoop();
} catch (error) {
  status.textContent = 'Could not load the avatar';
  mode.textContent = 'Use Chrome or Edge with WebGL2 available, then restart the preview. See docs/avatar-stage3.md if the problem continues.';
  console.error('Avatar preview failed:', error);
}
document.addEventListener('visibilitychange', () => {
  if (document.hidden) { cancelAnimationFrame(frame); frame = 0; }
  else resumeLoop();
});
window.addEventListener('pagehide', () => {
  disposed = true; cancelAnimationFrame(frame); resizeObserver.disconnect(); avatar?.destroy();
});
