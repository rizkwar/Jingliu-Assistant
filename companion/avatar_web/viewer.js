import {loadMeshAvatar} from './mesh-avatar.js';
import {ConversationVisual} from './conversation-state.js';
import {RenderCadence} from './render-cadence.js';

// This bridge carries lifecycle and bounded playback levels, never PCM or dialogue.
const bridge = await new Promise(resolve => new QWebChannel(qt.webChannelTransport,
  channel => resolve(channel.objects.renderer)));
let avatar, observer, frame = 0, paused = true, disposed = false, frames = 0;
const cadence = new RenderCadence();
let voiceSequence = -1, voiceAt = 0, voiceActive = false;
let visual, activity = 'ready', activitySequence = -1;
let visible = false, controlsSequence = -1, movement = 1, sensitivity = 1;
const canvas = document.querySelector('canvas');
canvas.dataset.renderQuality = 'hd';
bridge.qualityChanged.connect(hd => {
  canvas.dataset.renderQuality = hd ? 'hd' : 'balanced';
  cadence.boost(performance.now());
  if (paused) render();
});
function render(dt = 0) {
  if (avatar && visible && !document.hidden && !disposed) {
    avatar.advance(dt, dt > 0 ? 1/dt : 30); frames++;
  }
}
bridge.visibilityChanged.connect(value => { visible = value; sync(); });
bridge.controlsChanged.connect((motion, lipSensitivity, sequence) => {
  if (sequence <= controlsSequence || disposed) return;
  controlsSequence = sequence;
  movement = Math.max(0, Math.min(1, motion / 100));
  cadence.boost(performance.now());
  sensitivity = Math.max(0.25, Math.min(2, lipSensitivity / 100));
  if (visual) { visual.intensity = movement; visual.apply(); }
  avatar?.setSwayGain(0.45 * movement);
  if (paused) render();
});
bridge.activityChanged.connect((state, sequence) => {
  if (sequence <= activitySequence || disposed) return;
  activitySequence = sequence;
  activity = state;
  cadence.boost(performance.now());
  visual?.request(state, performance.now());
});
function resetVoice() {
  if (!avatar) return;
  voiceActive = false;
  avatar.setSpeaking(false); avatar.setVoiceLevel(0); avatar.stopLipSync();
  visual?.apply();
  render();
}
bridge.voiceChanged.connect((level, sequence, reset) => {
  if (sequence <= voiceSequence || disposed) return;
  voiceSequence = sequence;
  if (reset || paused || !visible || document.hidden) { resetVoice(); return; }
  voiceAt = performance.now();
  cadence.boost(voiceAt);
  voiceActive = true;
  visual?.apply();
  const value = Math.min(1, level * sensitivity);
  avatar?.setSpeaking(value > 0); avatar?.setVoiceLevel(value);
});
function tick(now) {
  frame = 0;
  if (!avatar || paused || !visible || document.hidden || disposed) return;
  const dt = cadence.step(now, activity, voiceActive);
  if (dt === null) {
    frame = requestAnimationFrame(tick); return;
  }
  visual.update(dt, now);
  if (voiceActive && now - voiceAt > 250) resetVoice();
  render(dt);
  frame = requestAnimationFrame(tick);
}
function sync() {
  cancelAnimationFrame(frame); frame = 0; cadence.restart();
  cadence.boost(performance.now());
  if (!paused && visible && !document.hidden && avatar && !disposed) frame = requestAnimationFrame(tick);
}
bridge.pauseChanged.connect(value => { paused = value; if (paused) resetVoice(); sync(); });
document.addEventListener('visibilitychange', () => { if (document.hidden) resetVoice(); sync(); });
window.addEventListener('pagehide', () => {
  disposed = true; cancelAnimationFrame(frame); observer?.disconnect(); avatar?.destroy();
});
document.querySelector('canvas').addEventListener('webglcontextlost', () => {
  paused = true; sync(); bridge.report('error');
});
try {
  avatar = await loadMeshAvatar(document.querySelector('canvas'), './avatar.mavatar', {manual:true, fit:'contain'});
  avatar.setAutoMotion(false); avatar.setAutoIdle(false); avatar.setSwayGain(0.45);
  visual = new ConversationVisual(avatar);
  visual.intensity = movement;
  avatar.setSwayGain(0.45 * movement);
  visual.request(activity, performance.now());
  visual.apply();
  avatar.stopLipSync(); avatar.setSpeaking(false); avatar.setVoiceLevel(0);
  avatar.setExpression('neutral');
  render();
  observer = new ResizeObserver(() => {
    cadence.boost(performance.now());
    if (paused) render();
  });
  observer.observe(document.querySelector('canvas'));
  // Read-only diagnostics for native rendering checks, no animation command API.
  window.avatarDiagnostics = () => ({frames, paused, visible, movement, sensitivity, activity, visualMode:visual.mode,
    quality:canvas.dataset.renderQuality,
    targetFps:cadence.frameRate(activity, voiceActive, performance.now()),
    expression:avatar.getExpression().name, parameters:avatar.getParameters(),
    canvas:[document.querySelector('canvas').width, document.querySelector('canvas').height]});
  bridge.report('ready');
} catch {
  bridge.report('error');
}
