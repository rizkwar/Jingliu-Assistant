import {loadMeshAvatar} from './mesh-avatar.js';
import {ConversationVisual} from './conversation-state.js';

// This bridge carries lifecycle and bounded playback levels, never PCM or dialogue.
const bridge = await new Promise(resolve => new QWebChannel(qt.webChannelTransport,
  channel => resolve(channel.objects.renderer)));
let avatar, observer, frame = 0, previous = 0, paused = true, disposed = false, frames = 0;
let voiceSequence = -1, voiceAt = 0, voiceActive = false;
let visual, activity = 'ready', activitySequence = -1;
bridge.activityChanged.connect((state, sequence) => {
  if (sequence <= activitySequence || disposed) return;
  activitySequence = sequence;
  activity = state;
  visual?.request(state, performance.now());
});
function resetVoice() {
  if (!avatar) return;
  voiceActive = false;
  avatar.setSpeaking(false); avatar.setVoiceLevel(0); avatar.stopLipSync();
  visual?.apply();
  if (!disposed) avatar.advance(0);
}
bridge.voiceChanged.connect((level, sequence, reset) => {
  if (sequence <= voiceSequence || disposed) return;
  voiceSequence = sequence;
  if (reset || paused || document.hidden) { resetVoice(); return; }
  voiceAt = performance.now();
  voiceActive = true;
  visual?.apply();
  avatar?.setSpeaking(level > 0); avatar?.setVoiceLevel(level);
});
function tick(now) {
  frame = 0;
  if (!avatar || paused || document.hidden || disposed) return;
  const dt = previous ? Math.max(0.000001, Math.min((now - previous) / 1000, 0.05)) : 1/60;
  previous = now;
  visual.update(dt, now);
  if (voiceActive && now - voiceAt > 250) resetVoice();
  avatar.advance(dt, 1/dt); frames++;
  frame = requestAnimationFrame(tick);
}
function sync() {
  cancelAnimationFrame(frame); frame = 0; previous = 0;
  if (!paused && !document.hidden && avatar && !disposed) frame = requestAnimationFrame(tick);
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
  visual.request(activity, performance.now());
  visual.apply();
  avatar.stopLipSync(); avatar.setSpeaking(false); avatar.setVoiceLevel(0);
  avatar.setExpression('neutral');
  avatar.advance(0);
  observer = new ResizeObserver(() => { if (paused && !disposed) avatar.advance(0); });
  observer.observe(document.querySelector('canvas'));
  // Read-only diagnostics for native rendering checks, no animation command API.
  window.avatarDiagnostics = () => ({frames, paused, activity, visualMode:visual.mode,
    expression:avatar.getExpression().name, parameters:avatar.getParameters(),
    canvas:[document.querySelector('canvas').width, document.querySelector('canvas').height]});
  bridge.report('ready');
} catch {
  bridge.report('error');
}
