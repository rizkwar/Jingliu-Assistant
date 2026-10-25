import {IdleAttention} from './idle-attention.js';
import {visualMode} from './conversation-state.js';
import {MotionPreview} from './motion-preview.js';
import {AvatarLife} from './avatar-life.js';

const clamp=(x,low,high)=>Math.max(low,Math.min(high,x));
const unit=x=>Number.isFinite(x)?clamp(x,0,1):0;
const STYLES={
  idle:{amount:1,y:-.5,z:0,brow:0},
  listening:{amount:.08,y:-1.5,z:-1.2,brow:.06},
  thinking:{amount:.1,y:-1.8,z:.8,brow:0},
  speaking:{amount:.32,y:-.6,z:0,brow:0},
  attention:{amount:0,y:-1,z:0,brow:0},
  paused:{amount:0,y:0,z:0,brow:0},
};

// A single owner for head/body/gaze. The runtime still owns eyes, breath, hair
// physics and playback lip-sync. No dialogue, emotion tags or model calls here.
export class AssistantMotion {
  constructor(avatar,random=Math.random){
    this.avatar=avatar;this.idle=new IdleAttention(random);
    this.mode=this.requested='idle';this.since=0;
    this.intensity=1;this.gaze=1;this.hair=.45;this.cursorEnabled=true;
    this.settings={motion:1,gaze:1,hair:.45};this.amount=1;
    this.pose={angleX:0,angleY:-.5,angleZ:0,bodyAngleX:0,bodyAngleZ:0,gazeX:0,gazeY:0,browY:0};
    this.level=0;this.nod=0;this.expression='neutral';
    this.preview=null;
    // Rigs with expressive parameters also get a sleep cycle, reactions and idle moments.
    this.life=avatar.setLife?new AvatarLife(random):null;
    avatar.setExpression('neutral');avatar.setTalkGain(0);
  }
  request(state,now){
    const next=visualMode(state);
    if(next!==this.requested){this.requested=next;this.since=now;}
    this.life?.setMode(next);
    // Stop idle cursor attention immediately when a conversation needs focus.
    this.idle.setCursorEnabled(this.cursorEnabled&&next==='idle');
    if(next!=='idle')this.stopPreview();
  }
  setControls(motion,gaze,hair,cursor){
    this.settings={motion:unit(motion),gaze:unit(gaze),hair:clamp(Number.isFinite(hair)?hair:.45,.2,.8)};
    this.cursorEnabled=Boolean(cursor);
    this.idle.setCursorEnabled(this.cursorEnabled&&this.requested==='idle');
    if(this.settings.motion===0)this.stopPreview();
  }
  setCursor(target){this.idle.setCursor(!this.preview&&this.cursorEnabled&&this.requested==='idle'?target:null);}
  clearCursor(){this.idle.setCursor(null);}
  setVoice(level){this.level=unit(level);this.life?.setVoice(this.level);if(this.level>0)this.stopPreview();}
  resetVoice(){this.level=0;this.nod=0;this.nodDrive=0;this.life?.setVoice(0);}
  suspend(){this.clearCursor();this.resetVoice();this.stopPreview();}
  poke(){return this.life?.poke()??null;}
  hover(inside){this.life?.hover(inside);}
  startPreview(){
    if(this.mode!=='idle'||this.requested!=='idle'||this.level>0||this.settings.motion===0||this.preview)return false;
    this.life?.wake('gentle');
    this.clearCursor();this.preview=this.avatar.createMotionPreview?.(this.pose)??new MotionPreview(this.pose);return true;
  }
  stopPreview(){this.preview=null;}
  update(seconds,now){
    const dt=Number.isFinite(seconds)?clamp(seconds,0,.1):0;
    if(this.mode!==this.requested&&now-this.since>=180)this.mode=this.requested;
    const style=STYLES[this.mode],blend=1-Math.exp(-dt*4);
    for(const [key,value] of Object.entries(this.settings)){
      const name=key==='motion'?'intensity':key;
      this[name]+=(value-this[name])*blend;
      if(Math.abs(value-this[name])<.0001)this[name]=value;
    }
    const life=this.life?.update(dt*(this.settings.motion>0?1:0));
    // A dozing avatar stops glancing around; she is woken by activity instead.
    // Focused on a task, she stops glancing around; her work motion takes over.
    const alert=life?life.alertness*(1-.85*(life.focus??0)):1;
    this.amount+=(style.amount*alert-this.amount)*(1-Math.exp(-dt*3));
    if(life){
      const allow=alert>=.99&&this.cursorEnabled&&this.requested==='idle';
      if(allow!==this.idle.cursorEnabled)this.idle.setCursorEnabled(allow);
    }
    const idle=this.idle.update(dt).pose;
    const sample=this.preview?.update(dt);
    const target=sample?{...sample.pose}:{...idle};
    if(!sample)for(const key of Object.keys(target))target[key]*=this.amount;
    // Speech emphasis: a soft nod following the voice's rhythm rather than each syllable.
    // Its pace drifts, so some stretches have quicker nods and others slower, gentler ones.
    this.nodClock=(this.nodClock??0)+dt;
    const pace=1+.45*Math.sin(this.nodClock*.37)*Math.sin(this.nodClock*.23+1);
    const nodTarget=this.mode==='speaking'?this.level*1.6:0;
    this.nodDrive=(this.nodDrive??0)+(nodTarget-(this.nodDrive??0))*(1-Math.exp(-dt*7*pace));
    this.nod+=(this.nodDrive-this.nod)*(1-Math.exp(-dt*(this.nodDrive>this.nod?4.5:2.4)*pace));
    if(!sample){target.angleY+=style.y-this.nod;target.angleZ+=style.z;}
    target.browY=style.brow;
    // Opaque half-eye patches include their irises. Keep them centered while
    // thinking; listening, speaking and cursor attention use the open-eye rig.
    if(this.mode==='thinking'){target.gazeX=0;target.gazeY=0;}
    const expression=this.mode==='thinking'?'halfLidded':'neutral';
    if(expression!==this.expression){this.expression=expression;this.avatar.setExpression(expression);}
    for(const key of Object.keys(this.pose))this.pose[key]+=(target[key]-this.pose[key])*(1-Math.exp(-dt*5));
    this.apply();
    if(life)this.avatar.setLife(this.scaledLife(life));
    if(sample?.finished)this.preview=null;
  }
  // Movement intensity scales body language; facial expression and eyelids stay whole.
  scaledLife(life){
    const scaled={...life};
    for(const key of ['angleX','angleY','angleZ','bodyX','bodyY','lift','arms','shoulders'])scaled[key]*=this.intensity;
    for(const key of ['gazeX','gazeY'])scaled[key]*=this.intensity*this.gaze;
    return scaled;
  }
  apply(){
    const pose={...this.pose};
    const limits={angleX:12,angleY:4,angleZ:8,bodyAngleX:1.5,bodyAngleZ:1.2,gazeX:.6,gazeY:.3};
    for(const [key,limit] of Object.entries(limits))pose[key]=clamp(pose[key],-limit,limit)*this.intensity*(key.startsWith('gaze')?this.gaze:1);
    this.avatar.setTalkGain(0);this.avatar.setSwayGain(this.hair);
    this.avatar.setParameters(pose,1);
  }
  snapshot(){return {mode:this.mode,requested:this.requested,expression:this.expression,life:this.life?.snapshot()??null,
    movement:this.intensity,gaze:this.gaze,hair:this.hair,nod:this.nod,attention:this.idle.snapshot(),
    preview:this.preview?{label:this.preview.update(0).label,time:this.preview.time,duration:this.preview.duration}:null};}
}
