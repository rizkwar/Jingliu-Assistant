import {loadMeshAvatar} from './mesh-avatar.js';

// This bridge carries renderer lifecycle only. No dialogue, audio or user data.
const bridge = await new Promise(resolve => new QWebChannel(qt.webChannelTransport,
  channel => resolve(channel.objects.renderer)));
let avatar, observer, frame = 0, previous = 0, paused = true, disposed = false, frames = 0;
function tick(now) {
  frame = 0;
  if (!avatar || paused || document.hidden || disposed) return;
  const dt = previous ? Math.max(0.000001, Math.min((now - previous) / 1000, 0.05)) : 1/60;
  previous = now;
  avatar.advance(dt, 1/dt); frames++;
  frame = requestAnimationFrame(tick);
}
function sync() {
  cancelAnimationFrame(frame); frame = 0; previous = 0;
  if (!paused && !document.hidden && avatar && !disposed) frame = requestAnimationFrame(tick);
}
bridge.pauseChanged.connect(value => { paused = value; sync(); });
document.addEventListener('visibilitychange', sync);
window.addEventListener('pagehide', () => {
  disposed = true; cancelAnimationFrame(frame); observer?.disconnect(); avatar?.destroy();
});
document.querySelector('canvas').addEventListener('webglcontextlost', () => {
  paused = true; sync(); bridge.report('error');
});
try {
  avatar = await loadMeshAvatar(document.querySelector('canvas'), './avatar.mavatar', {manual:true, fit:'contain'});
  avatar.setAutoMotion(false); avatar.setAutoIdle(true); avatar.setSwayGain(0.45);
  avatar.stopLipSync(); avatar.setSpeaking(false); avatar.setVoiceLevel(0);
  avatar.setExpression('neutral');
  avatar.advance(0);
  observer = new ResizeObserver(() => { if (paused && !disposed) avatar.advance(0); });
  observer.observe(document.querySelector('canvas'));
  // Read-only diagnostics for native rendering checks, no animation command API.
  window.avatarDiagnostics = () => ({frames, paused, parameters:avatar.getParameters(),
    canvas:[document.querySelector('canvas').width, document.querySelector('canvas').height]});
  bridge.report('ready');
} catch {
  bridge.report('error');
}
