import {loadMeshAvatar} from '/mesh-avatar.js';
import {ConversationVisual} from '/conversation-state.js';
import {HeadTurnStudy,DURATION} from '/motion.js';

const canvases=[document.querySelector('#baseline'),document.querySelector('#experiment')];
const status=document.querySelector('#status'),progress=document.querySelector('#progress');
const speech=document.querySelector('#speech'),pause=document.querySelector('#pause');
let avatars=[],baseline,study=new HeadTurnStudy(),frame=0,previous=0,paused=false,disposed=false;
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
  lastState=study.update(dt);
  const talking=speech.checked;
  const level=talking && study.time%3<2.4 ? Math.max(0,Math.sin(study.time*9))*.75 : 0;
  const expression=lastState.expression;
  baseline.request(expression==='halfLidded'?'thinking':talking?'speaking':'ready',study.time*1000);
  baseline.update(dt,study.time*1000);
  // Only head, body and gaze are owned by the experiment. Never override breath,
  // eyelids or mouth. Existing runtime shading/deformation provides parallax.
  avatars[1].setParameters(lastState.pose,1);
  if(expression!==lastExpression){avatars[1].setExpression(expression);lastExpression=expression;}
  avatars.forEach(avatar=>{
    avatar.setSpeaking(level>0);avatar.setVoiceLevel(level);
    if(!talking)avatar.stopLipSync();
    avatar.advance(dt,dt>0?1/dt:30);
  });
  draws++;
  compose();progress.value=study.time/DURATION;
  status.textContent=`${lastState.label} · ${study.time.toFixed(1)} / ${DURATION.toFixed(1)} s${lastState.finished?' · Replay to watch again':''}`;
}
function tick(now) {
  frame=0;if(paused||document.hidden||disposed)return;
  if(previous && now-previous<1000/30-.5){frame=requestAnimationFrame(tick);return;}
  const dt=previous?Math.min(.1,(now-previous)/1000):1/30;
  previous=now;draw(dt);frame=requestAnimationFrame(tick);
}
function sync(){cancelAnimationFrame(frame);frame=0;previous=0;if(!paused&&!document.hidden&&!disposed)frame=requestAnimationFrame(tick);}
function setPaused(value){paused=value;pause.textContent=paused?'Resume':'Pause';pause.setAttribute('aria-pressed',String(paused));sync();}
function restart(){study.reset();lastExpression='';avatars.forEach(a=>{a.setSpeaking(false);a.setVoiceLevel(0);a.stopLipSync();});draw(0);setPaused(false);}
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
  document.querySelector('#checker').onchange=e=>document.body.classList.toggle('checker',e.target.checked);
  speech.onchange=()=>{if(!speech.checked)avatars.forEach(a=>{a.setSpeaking(false);a.setVoiceLevel(0);a.stopLipSync();});if(paused)draw(0);};
  new ResizeObserver(()=>{if(paused)draw(0);}).observe(canvases[0]);
  document.addEventListener('visibilitychange',sync);
  window.motionStudy={restart,setPaused,startRecording,stopRecording,
    snapshot:()=>({ready:true,paused,draws,time:study.time,duration:DURATION,label:lastState?.label,
      experiment:avatars[1].getParameters(),baseline:avatars[0].getParameters(),
      canvases:canvases.map(c=>[c.width,c.height])}),
    // Test-only local preview controls; this page has no bridge to the assistant.
    speech:value=>{speech.checked=value;speech.dispatchEvent(new Event('change'));},
  };
  restart();
}catch{status.textContent='Could not load the preview. Restore the local rig and check graphics support.';}
window.addEventListener('pagehide',()=>{disposed=true;cancelAnimationFrame(frame);if(recording?.recorder.state==='recording')recording.recorder.stop();avatars.forEach(a=>a.destroy());});
