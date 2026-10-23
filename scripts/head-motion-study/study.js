import {loadMeshAvatar} from '/mesh-avatar.js';
import {ConversationVisual} from '/conversation-state.js';
import {HeadTurnStudy} from '/motion.js';
import {RigReview} from '/rig-review.js';
import {IdleAttention,cursorTarget} from '/idle-attention.js';

const canvases=[document.querySelector('#baseline'),document.querySelector('#experiment')];
const status=document.querySelector('#status'),progress=document.querySelector('#progress');
const speech=document.querySelector('#speech'),pause=document.querySelector('#pause');
const review=document.querySelector('#review');
const idle=document.querySelector('#idle'),cursor=document.querySelector('#cursor');
const motion=document.querySelector('#motion'),gaze=document.querySelector('#gaze'),hair=document.querySelector('#hair');
let avatars=[],baseline,study=new IdleAttention(),frame=0,previous=0,paused=false,disposed=false;
let draws=0,lastState=null,lastExpression='',recording=null;
// Recording only the two canvases avoids collecting the desktop or user data.
const capture=document.createElement('canvas');capture.width=960;capture.height=544;
const context=capture.getContext('2d');
function compose() {
  context.fillStyle='#142033';context.fillRect(0,0,960,544);
  context.fillStyle='#e6edfa';context.font='16px sans-serif';
  context.fillText('Current assistant',20,26);context.fillText('Head and gaze experiment',500,26);
  canvases.forEach((canvas,i)=>{
    const scale=Math.min(480/canvas.width,480/canvas.height);
    const width=canvas.width*scale,height=canvas.height*scale;
    context.drawImage(canvas,i*480+(480-width)/2,40+(480-height)/2,width,height);
  });
  context.font='13px sans-serif';context.fillText((lastState?.label ?? 'Loading')+(speech.checked?' / silent speech test':''),20,530);
}
function draw(dt) {
  if(study instanceof IdleAttention)study.setIntensity(motion.value/100,gaze.value/100);
  lastState=study.update(dt);
  const talking=speech.checked;
  const level=talking && study.time%3<2.4 ? Math.max(0,Math.sin(study.time*9))*.75 : 0;
  const expression=lastState.expression;
  baseline.request(expression==='halfLidded'?'thinking':talking?'speaking':'ready',study.time*1000);
  baseline.update(dt,study.time*1000);
  // Only head, body and gaze are owned by the experiment. Never override breath,
  // eyelids or mouth. Existing runtime shading/deformation provides parallax.
  const pose={...lastState.pose};
  if(!(study instanceof IdleAttention))for(const key of Object.keys(pose))if(/^(angle|bodyAngle|gaze)/.test(key))pose[key]*=motion.value/100*(key.startsWith('gaze')?gaze.value/100:1);
  avatars[1].setParameters(pose,1);
  avatars[1].setSwayGain(hair.value/100);
  if(expression!==lastExpression){avatars[1].setExpression(expression);lastExpression=expression;}
  // Preview adapter substeps motion/physics, then deforms and draws once.
  avatars.forEach(avatar=>{
    avatar.setSpeaking(level>0);avatar.setVoiceLevel(level);
    if(!talking)avatar.stopLipSync();
    avatar.advanceStable(dt);
  });
  draws++;
  compose();progress.hidden=!study.duration;progress.value=study.duration?study.time/study.duration:0;
  status.textContent=`${lastState.label} · ${study.time.toFixed(1)}${study.duration?' / '+study.duration.toFixed(1):''} s${lastState.finished?' · Replay to watch again':''}`;
}
function tick(now) {
  frame=0;if(paused||document.hidden||disposed)return;
  if(previous && now-previous<1000/30-.5){frame=requestAnimationFrame(tick);return;}
  const dt=previous?Math.min(.1,(now-previous)/1000):1/30;
  previous=now;draw(dt);frame=requestAnimationFrame(tick);
}
function sync(){cancelAnimationFrame(frame);frame=0;previous=0;if(!paused&&!document.hidden&&!disposed)frame=requestAnimationFrame(tick);}
function clearCursor(){if(study instanceof IdleAttention)study.setCursor(null);}
function setPaused(value){paused=value;if(paused)clearCursor();pause.textContent=paused?'Resume':'Pause';pause.setAttribute('aria-pressed',String(paused));sync();}
function restart(){study.reset();if(study instanceof IdleAttention)study.setCursorEnabled(cursor.checked);lastExpression='';avatars.forEach(a=>{a.setSpeaking(false);a.setVoiceLevel(0);a.stopLipSync();});draw(0);setPaused(false);}
function selectStudy(){
  study=review.checked?new RigReview():idle.checked?new IdleAttention():new HeadTurnStudy();
  cursor.disabled=!(study instanceof IdleAttention);
  document.querySelector('#replay').textContent=study instanceof IdleAttention?'Restart idle':'Replay sequence';
  restart();
}
async function startRecording(){
  if(recording)throw new Error('Recording already active');
  const stream=capture.captureStream(30),chunks=[];
  const recorder=new MediaRecorder(stream,{mimeType:'video/webm;codecs=vp8',videoBitsPerSecond:4000000});
  const done=new Promise(resolve=>{
    recorder.ondataavailable=e=>{if(e.data.size)chunks.push(e.data)};
    recorder.onstop=()=>{stream.getTracks().forEach(t=>t.stop());const reader=new FileReader();reader.onload=()=>resolve(reader.result.split(',')[1]);reader.readAsDataURL(new Blob(chunks,{type:'video/webm'}));};
  });
  recording={recorder,done};recorder.start();return true;
}
async function stopRecording(){if(!recording)return null;const active=recording;active.recorder.stop();const data=await active.done;recording=null;return data;}
try {
  for(const canvas of canvases){
    canvas.dataset.renderQuality='hd';
    const avatar=await loadMeshAvatar(canvas,'/avatar.mavatar',{manual:true,fit:'contain'});
    avatar.setAutoIdle(false);avatar.setAutoMotion(false);avatar.setSwayGain(.45);avatar.setTalkGain(0);
    avatar.setExpression('neutral');avatars.push(avatar);
  }
  baseline=new ConversationVisual(avatars[0]);
  document.querySelector('#replay').disabled=false;pause.disabled=false;
  document.querySelector('#replay').onclick=restart;pause.onclick=()=>setPaused(!paused);
  review.onchange=()=>{if(review.checked)idle.checked=false;selectStudy();};
  idle.onchange=()=>{if(idle.checked)review.checked=false;selectStudy();};
  cursor.onchange=()=>{if(study instanceof IdleAttention)study.setCursorEnabled(cursor.checked);};
  for(const [input,label] of [[motion,'motion-value'],[gaze,'gaze-value'],[hair,'hair-value']])input.oninput=()=>{
    document.querySelector('#'+label).value=input.value+'%';if(paused)draw(0);
  };
  document.addEventListener('pointermove',event=>{
    if(study instanceof IdleAttention&&cursor.checked&&!paused&&!document.hidden&&(!event.pointerType||event.pointerType==='mouse'))
      study.setCursor(cursorTarget({x:event.clientX,y:event.clientY},canvases[1].getBoundingClientRect()));
  });
  document.documentElement.addEventListener('pointerleave',clearCursor);
  window.addEventListener('blur',clearCursor);
  document.querySelector('#checker').onchange=e=>document.body.classList.toggle('checker',e.target.checked);
  speech.onchange=()=>{if(!speech.checked)avatars.forEach(a=>{a.setSpeaking(false);a.setVoiceLevel(0);a.stopLipSync();});if(paused)draw(0);};
  new ResizeObserver(()=>{if(paused)draw(0);}).observe(canvases[0]);
  document.addEventListener('visibilitychange',()=>{if(document.hidden)clearCursor();sync();});
  window.motionStudy={restart,setPaused,startRecording,stopRecording,
    snapshot:()=>({ready:true,paused,draws,time:study.time,duration:study.duration,label:lastState?.label,review:review.checked,
      idle:study instanceof IdleAttention,attention:study instanceof IdleAttention?study.snapshot():null,
      holding:study.phaseTime!==undefined&&study.current?study.phaseTime>=study.current.travel:study.elapsed>=study.travel,
      experiment:avatars[1].getParameters(),baseline:avatars[0].getParameters(),
      canvases:canvases.map(c=>[c.width,c.height])}),
    // Test-only local preview controls; this page has no bridge to the assistant.
    speech:value=>{speech.checked=value;speech.dispatchEvent(new Event('change'));},
    review:value=>{review.checked=value;review.dispatchEvent(new Event('change'));},
    idle:value=>{idle.checked=value;idle.dispatchEvent(new Event('change'));},
    cursor:value=>{cursor.checked=value;cursor.dispatchEvent(new Event('change'));},
    // Exact canvas crops for the local pose review, captured in the same task
    // as the WebGL draw. This does not capture any desktop surface.
    frame:()=>{draw(0);return canvases.map(canvas=>canvas.toDataURL('image/png').split(',')[1]);},
  };
  restart();
}catch{status.textContent='Could not load the preview. Restore the local rig and check graphics support.';}
window.addEventListener('pagehide',()=>{disposed=true;cancelAnimationFrame(frame);if(recording?.recorder.state==='recording')recording.recorder.stop();avatars.forEach(a=>a.destroy());});
