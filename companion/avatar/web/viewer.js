import {loadMeshAvatar} from './mesh-avatar.js';
import {AssistantMotion} from './assistant-motion.js';
import {cursorTarget} from './idle-attention.js';
import {RenderCadence} from './render-cadence.js';

// This bridge carries lifecycle and bounded playback levels, never PCM or dialogue.
const bridge = await new Promise(resolve => new QWebChannel(qt.webChannelTransport,
  channel => resolve(channel.objects.renderer)));
let avatar, observer, frame = 0, paused = true, disposed = false, frames = 0;
const cadence = new RenderCadence();
let voiceSequence = -1, voiceAt = 0, voiceActive = false;
let visual, activity = 'ready', activitySequence = -1;
let visible = false, controlsSequence = -1, movement = 1, sensitivity = 1;
let cursorEnabled=true, gaze=1, hair=.45, attentionSequence=-1, cursorSequence=-1;
let previewSequence=-1, pointerAt=-1e9;
let framing='portrait';
let appearance={};
let accessories={};
let sleepMinutes=5, lifeSequence=-1, gestureSequence=-1, lifeState='awake';
const canvas = document.querySelector('canvas');
const zzz = document.getElementById('zzz');
const sparkles = document.getElementById('sparkles');
// A finished task: a ring of ice crystals scatters from beside her head.
function sparkleBurst() {
  const anchor = avatar?.headAnchor?.(); if (!anchor) return;
  const rect = canvas.getBoundingClientRect();
  sparkles.style.left = `${rect.left + (anchor.x - .08) * rect.width}px`;
  sparkles.style.top = `${rect.top + (anchor.y - .02) * rect.height}px`;
  const glyphs = ['✦', '✧', '❄', '✦', '⋆'];
  for (let i = 0; i < 16; i++) {
    const piece = document.createElement('span'), angle = (i / 16) * Math.PI * 2 + Math.random() * .3;
    const distance = 70 + Math.random() * 70;
    piece.textContent = glyphs[i % glyphs.length];
    piece.style.setProperty('--dx', `${Math.cos(angle) * distance}px`);
    piece.style.setProperty('--dy', `${Math.sin(angle) * distance - 18}px`);
    piece.style.setProperty('--size', `${13 + Math.random() * 12}px`);
    piece.style.setProperty('--spin', `${(Math.random() - .5) * 240}deg`);
    piece.style.setProperty('--life', `${1.1 + Math.random() * .7}s`);
    piece.style.setProperty('--delay', `${Math.random() * .25}s`);
    sparkles.appendChild(piece);
    setTimeout(() => piece.remove(), 2400);
  }
}
canvas.dataset.renderQuality = 'hd';
bridge.qualityChanged.connect(hd => {
  canvas.dataset.renderQuality = hd ? 'hd' : 'balanced';
  if (paused) render();
});
bridge.framingChanged.connect(value=>{
  framing=value;avatar?.setFraming?.(value);reportShape();if(paused)render();
});
// The window takes the shape of what is in view, so there is no empty margin around her.
function reportShape(){
  document.body.dataset.framing=framing;
  const aspect=avatar?.aspect?.();
  if(Number.isFinite(aspect)&&aspect>0)bridge.reportAspect?.(aspect);
}
bridge.appearanceChanged.connect(value=>{
  appearance=JSON.parse(value);avatar?.setAppearance?.(appearance);if(paused)render();
});
bridge.accessoriesChanged.connect(value=>{
  accessories=JSON.parse(value);avatar?.setAccessories?.(accessories);if(paused)render();
});
function render(dt = 0) {
  if (avatar && visible && !document.hidden && !disposed) {
    avatar.advanceStable(dt); frames++;
  }
}
function stopPreview() {
  if(visual?.preview){visual.stopPreview();bridge.finishPreview(previewSequence,false);}
}
bridge.visibilityChanged.connect(value => { visible = value; if(!visible)stopPreview(); sync(); });
bridge.controlsChanged.connect((motion, lipSensitivity, sequence) => {
  if (sequence <= controlsSequence || disposed) return;
  controlsSequence = sequence;
  movement = Math.max(0, Math.min(1, motion / 100));
  if(movement===0)stopPreview();
  sensitivity = Math.max(0.25, Math.min(2, lipSensitivity / 100));
  visual?.setControls(movement,gaze,hair,cursorEnabled);
  if (paused) render();
});
bridge.attentionChanged.connect((enabled,gazeIntensity,hairResponse,sequence)=>{
  if(sequence<=attentionSequence||disposed)return;
  attentionSequence=sequence;cursorEnabled=enabled;
  gaze=Math.max(0,Math.min(1,gazeIntensity/100));hair=Math.max(.2,Math.min(.8,hairResponse/100));
  visual?.setControls(movement,gaze,hair,cursorEnabled);
});
bridge.lifeChanged?.connect((seconds,sequence)=>{
  if(sequence<=lifeSequence||disposed)return;
  lifeSequence=sequence;sleepMinutes=seconds/60;visual?.life?.setSleepDelay(sleepMinutes);
});
bridge.gestureRequested?.connect((name,sequence)=>{
  if(sequence<=gestureSequence||disposed||paused||!visible)return;
  gestureSequence=sequence;
  if(name==='poke')visual?.poke();
  else if(name.startsWith('test:work:'))visual?.life?.work(name.slice(10));
  else if(name.startsWith('test:'))visual?.life?.test(name.slice(5));
  else visual?.life?.cue(name);
});
let petSequence=-1, petting=false;
// Pointer strokes over the avatar. She only counts it as petting on her head.
bridge.petChanged?.connect((x,y,active,sequence)=>{
  if(sequence<=petSequence||disposed)return;
  petSequence=sequence;
  const region=avatar?.headRegion?.();
  const onHead=Boolean(active&&region&&!paused&&visible&&x>=region.left&&x<=region.right&&y>=region.top&&y<=region.bottom);
  visual?.life?.pet(onHead,(x-(region?.left??0))/Math.max(.01,(region?.right??1)-(region?.left??0)));
  if(onHead!==petting){petting=onHead;bridge.reportPetting?.(petting);}
});
let workSequence=-1;
// A computer task's progress: start, each step's kind and words, then done or failed.
bridge.workChanged?.connect((state,text,sequence)=>{
  if(sequence<=workSequence||disposed)return;
  workSequence=sequence;
  visual?.life?.work(state);
});
bridge.cursorChanged.connect((x,y,valid,sequence)=>{
  if(valid)pointerAt=performance.now();
  if(sequence<=cursorSequence||disposed)return;
  cursorSequence=sequence;
  // Resting the pointer on her (not just passing by) can wake her gently.
  visual?.hover(valid&&x>.12&&x<.88&&y>.04&&y<.96);
  if(!valid||!cursorEnabled||paused||!visible||document.hidden){visual?.clearCursor();return;}
  const rect=canvas.getBoundingClientRect();
  visual?.setCursor(cursorTarget({x:rect.left+x*rect.width,y:rect.top+y*rect.height},rect,avatar?.package?.rig));
});
bridge.previewChanged.connect((enabled,sequence)=>{
  if(sequence<=previewSequence||disposed)return;
  previewSequence=sequence;
  if(enabled){
    if(paused||!visible||document.hidden||!visual?.startPreview())bridge.finishPreview(sequence,false);
  }else visual?.stopPreview();
});
bridge.activityChanged.connect((state, sequence) => {
  if (sequence <= activitySequence || disposed) return;
  activitySequence = sequence;
  activity = state;
  if(state!=='ready')stopPreview();
  visual?.request(state, performance.now());
});
function resetVoice(redraw = true) {
  if (!avatar) return;
  voiceActive = false;
  visual?.resetVoice();
  avatar.setSpeaking(false); avatar.setVoiceLevel(0); avatar.stopLipSync();
  visual?.apply();
  if(redraw)render();
}
bridge.voiceChanged.connect((level, sequence, reset) => {
  if (sequence <= voiceSequence || disposed) return;
  voiceSequence = sequence;
  stopPreview();
  if (reset || paused || !visible || document.hidden) { resetVoice(); return; }
  voiceAt = performance.now();
  voiceActive = true;
  visual?.apply();
  const value = Math.min(1, level * sensitivity);
  visual?.setVoice(Math.max(0,Math.min(1,level)));
  avatar?.setSpeaking(value > 0); avatar?.setVoiceLevel(value);
});
// How many frames she needs right now: smooth motion while anything lively happens,
// fewer while she only breathes and blinks (saves CPU and battery), fewest asleep.
function targetRate(now) {
  const life = visual?.life;
  const lively = activity !== 'ready' || voiceActive || visual?.preview || petting || now - pointerAt < 1500
    || (life && (life.gestures.length || life.working || life.petWeight > .01 || life.workWeight > .01
                 || Math.abs((life.moodWeight ?? 0) - (life.mood ? 1 : 0)) > .02));
  if (lively) return 60;
  return life?.state === 'asleep' ? 24 : 30;
}
function tick(now) {
  frame = 0;
  if (!avatar || paused || !visible || document.hidden || disposed) return;
  cadence.setTarget(targetRate(now));
  const dt = cadence.step(now);
  if (dt === null) {
    frame = requestAnimationFrame(tick); return;
  }
  if (voiceActive && now - voiceAt > 250) resetVoice(false);
  const previewWasActive=Boolean(visual.preview);
  visual.update(dt, now);
  if(previewWasActive&&!visual.preview)bridge.finishPreview(previewSequence,true);
  render(dt);
  showSleep();
  frame = requestAnimationFrame(tick);
}
function showSleep() {
  const life=visual?.life?.layer;
  if(visual?.life?.events?.includes('sparkle')){
    visual.life.events=visual.life.events.filter(event=>event!=='sparkle');sparkleBurst();
  }
  if(life?.state&&life.state!==lifeState){lifeState=life.state;bridge.reportLife?.(lifeState);}
  const amount=life?Math.max(0,Math.min(1,(life.zzz-.35)/.5)):0;
  zzz.style.opacity=amount.toFixed(3);
  if(amount>0&&avatar?.headAnchor){
    const rect=canvas.getBoundingClientRect(),anchor=avatar.headAnchor();
    zzz.style.left=`${rect.left+anchor.x*rect.width}px`;zzz.style.top=`${rect.top+anchor.y*rect.height}px`;
    zzz.style.fontSize=`${Math.max(15,Math.min(30,anchor.size*rect.height*.032))}px`;
  }
}
function sync() {
  cancelAnimationFrame(frame); frame = 0; cadence.restart();
  const running=!paused && visible && !document.hidden && avatar && !disposed;
  zzz.classList.toggle('paused',!running);
  if (running) frame = requestAnimationFrame(tick);
}
bridge.pauseChanged.connect(value => { paused = value; if (paused) {stopPreview();visual?.suspend();resetVoice();} sync(); });
function pageVisibility() {
  if(document.hidden){stopPreview();visual?.suspend();resetVoice();}
  bridge.reportVisibility(!document.hidden);sync();
}
document.addEventListener('visibilitychange',pageVisibility);
pageVisibility();
window.addEventListener('pagehide', () => {
  stopPreview();disposed = true; cancelAnimationFrame(frame); observer?.disconnect(); avatar?.destroy();
});
document.querySelector('canvas').addEventListener('webglcontextlost', () => {
  paused = true; sync(); bridge.report('error');
});
try {
  const configResponse=await fetch('./renderer.json');
  if(!configResponse.ok)throw new Error('Missing renderer configuration');
  const config=await configResponse.json();
  if(config.kind==='live2d'){
    const {loadLive2DAvatar}=await import('./live2d-avatar.js');
    avatar=await loadLive2DAvatar(canvas,'./model/model3.json');
    avatar.setFraming(framing);
    avatar.setAppearance(appearance);
    avatar.setAccessories(accessories);
    reportShape();
  }else if(config.kind==='layered'){
    const {loadLayeredAvatar}=await import('./layered-avatar.js');
    avatar=await loadLayeredAvatar(canvas,'./model/layered.json');
  }else if(config.kind==='mesh'){
    avatar=await loadMeshAvatar(canvas, './avatar.mavatar', {manual:true, fit:'contain'});
  }else throw new Error('Unknown renderer');
  avatar.setAutoMotion(false); avatar.setAutoIdle(false); avatar.setSwayGain(0.45);
  visual = new AssistantMotion(avatar);
  visual.setControls(movement,gaze,hair,cursorEnabled);
  visual.life?.setSleepDelay(sleepMinutes);
  // A small hello on arrival: a stretch in the morning, a yawn late at night.
  if(visual.life)setTimeout(()=>{if(!disposed&&activity==='ready')visual.life.greet();},1400);
  visual.request(activity, performance.now());
  visual.apply();
  avatar.stopLipSync(); avatar.setSpeaking(false); avatar.setVoiceLevel(0);
  avatar.setExpression('neutral');
  render();
  observer = new ResizeObserver(() => {
    if (paused) render();
  });
  observer.observe(document.querySelector('canvas'));
  // Read-only diagnostics for native rendering checks, no animation command API.
  window.avatarDiagnostics = () => ({frames, paused, visible, movement, sensitivity, activity, visualMode:visual.mode,
    renderer:config.kind, rig:avatar.rigDiagnostics?.()??null,
    quality:canvas.dataset.renderQuality, motion:visual.snapshot(),
    targetFps:cadence.frameRate(),
    expression:avatar.getExpression().name, parameters:avatar.getParameters(),
    canvas:[document.querySelector('canvas').width, document.querySelector('canvas').height]});
  window.avatarLayerPreviews=()=>avatar.inspectLayers?.()??[];
  bridge.report('ready');
} catch(error) {
  console.error('Avatar load failed:',error.message);
  bridge.report('error');
}
