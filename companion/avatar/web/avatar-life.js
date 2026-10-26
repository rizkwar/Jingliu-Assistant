// A "life" layer for rigged avatars: a sleep cycle, reactions and small idle
// moments, expressed as offsets in Live2D rig units. It never opens the mouth
// over playback lip-sync and owns no dialogue: activity cues only.
const clamp=(v,a,b)=>Math.max(a,Math.min(b,Number.isFinite(v)?v:0));
const smooth=t=>{const x=clamp(t,0,1);return x*x*(3-2*x);};
const ramp=(t,a,b)=>smooth((t-a)/(b-a));
// Rises over a..b, holds, then falls over c..d.
const pulse=(t,a,b,c,d)=>ramp(t,a,b)*(1-ramp(t,c,d));

// Angles in degrees (rig ranges are ±30 head, ±10 body). lift: Param114 body
// up/down (±30). arms: Param13 (0..1). shoulders: Param8 (±10). eyes: added
// to an open eye (−1 closes, + widens). Others are the rig's own −1..1 / 0..1.
export const REST=Object.freeze({angleX:0,angleY:0,angleZ:0,bodyX:0,bodyY:0,lift:0,arms:0,shoulders:0,
  gazeX:0,gazeY:0,eyes:0,wink:0,eyeSmile:0,mouthOpen:0,mouthForm:0,cheek:0,browY:0,browAngle:0});
const BOUNDS={angleX:[-18,18],angleY:[-22,14],angleZ:[-12,12],bodyX:[-6,6],bodyY:[-6,6],lift:[-12,14],
  arms:[0,1],shoulders:[-8,8],gazeX:[-.9,.9],gazeY:[-.8,.9],eyes:[-1,.45],wink:[0,1],eyeSmile:[0,1],mouthOpen:[0,1],
  mouthForm:[-1,1],cheek:[0,1],browY:[-1,1],browAngle:[-1,1]};

const BASE={
  awake:{},
  drowsy:{eyes:-.26,angleY:-4,angleZ:2.5,browY:-.15,lift:-1.5,mouthForm:.05},
  asleep:{eyes:-1,angleY:-15,angleZ:5,angleX:-3,bodyY:-2.5,lift:-3,mouthOpen:.05,mouthForm:.18,cheek:.35,browY:.08},
};
const MODE={
  idle:{},listening:{eyes:.1,browY:.22,mouthForm:.08},thinking:{mouthForm:-.15,browAngle:.18},
  speaking:{mouthForm:.18},attention:{browAngle:-.45,browY:.2,mouthForm:-.3},paused:{eyes:-.2},
};
// Breathing: radians per second and depth of the rig's ParamBreath swing.
const BREATH={awake:[1.55,.3],drowsy:[1.1,.36],asleep:[.78,.46]};

// Each gesture returns partial offsets for time t (seconds); all start and end at rest.
export const GESTURES={
  yawn:{duration:3.4,at(t){const k=pulse(t,.2,1.1,2.3,3.2);
    const gape=pulse(t,.45,1.2,2.0,2.8);
    return {eyes:-.92*k,angleY:7*k,angleZ:3*k,mouthOpen:gape,mouthForm:-.6*gape,arms:.3*k,lift:4*k,browY:.35*k,eyeSmile:.5*k};}},
  stretch:{duration:4.4,at(t){const k=pulse(t,.3,1.5,2.7,3.7),exhale=pulse(t,3.4,3.7,3.85,4.4);
    return {arms:k,lift:11*k-3*exhale,angleY:8*k,angleZ:-2.5*k,shoulders:6*k,eyes:-k,eyeSmile:.8*k,mouthOpen:.12*k,cheek:.2*k};}},
  nodOff:{duration:5.2,at(t){const droop=ramp(t,0,3.6)**2*(1-ramp(t,3.6,3.82)),after=pulse(t,3.65,3.8,4.2,5.0);
    return {angleY:-12*droop+2*after,angleZ:3*droop,eyes:-.7*droop+.38*after,lift:-2*droop+3*pulse(t,3.6,3.7,3.8,4.3),browY:.35*after};}},
  wakeGentle:{duration:4.2,at(t){
    // Eyelids flutter open while the head lifts, then a small yawn and a soft smile.
    const flutter=t<.55?1:t<.85?.45:t<1.15?.9:t<1.6?.25:t<1.75?.9:0;
    const smile=pulse(t,2.4,2.9,3.6,4.2);
    return {eyes:-flutter*(1-ramp(t,1.75,2.1)),mouthOpen:.32*pulse(t,1.5,2.0,2.3,2.8),angleZ:4*pulse(t,1.0,1.8,3.0,4.2),
      angleY:2*pulse(t,1.6,2.1,2.4,2.9),lift:2.5*pulse(t,1.5,2.0,2.4,3.0),eyes2:-.3*smile,eyeSmile:.85*smile,mouthForm:.8*smile,cheek:.5*smile};}},
  wakeStartled:{duration:1.9,at(t){
    return {eyes:.38*pulse(t,0,.1,.55,1.0)-pulse(t,.75,.82,.86,.95),browY:.65*pulse(t,0,.12,.6,1.3),lift:7*pulse(t,0,.1,.22,.6),
      angleY:3*pulse(t,0,.15,.45,1.1),mouthOpen:.22*pulse(t,.05,.15,.35,.65)};}},
  poke:{duration:1.7,at(t,side){const s=pulse(t,.45,.75,1.15,1.7);
    return {eyes:-pulse(t,0,.05,.1,.18)+.2*pulse(t,.18,.25,.4,.7),lift:4.5*pulse(t,0,.08,.2,.55),angleZ:5*side*pulse(t,.2,.6,1.1,1.7),
      browY:.4*pulse(t,.1,.2,.5,.9),eyeSmile:.85*s,mouthForm:.8*s,cheek:.55*s,eyes2:-.3*s};}},
  fluster:{duration:3.3,at(t,side){const k=pulse(t,.1,.45,2.4,3.2);
    return {angleX:-10*side*k,gazeX:-.6*side*k,angleZ:-3*side*k,mouthForm:-.9*k,browAngle:-.8*k,browY:-.45*k,cheek:k,eyes:-.18*k};}},
  greet:{duration:2.8,at(t){const k=pulse(t,.2,.7,1.8,2.7);
    return {angleZ:5*k,angleY:-3.5*pulse(t,.55,.85,1.0,1.45),eyeSmile:.9*k,mouthForm:.85*k,cheek:.55*k,eyes:-.36*k};}},
  sigh:{duration:3.5,at(t){
    return {lift:3*pulse(t,0,.9,1.0,1.4)-4*pulse(t,1.2,1.8,2.2,3.3),eyes:-.55*pulse(t,1.0,1.5,2.4,3.3),
      angleY:-3*pulse(t,1.2,1.8,2.4,3.4),shoulders:-4*pulse(t,1.2,1.8,2.3,3.4),browY:-.2*pulse(t,1.0,1.6,2.4,3.3)};}},
  content:{duration:5.2,at(t){const k=pulse(t,.3,1.1,4.0,5.1);
    return {eyeSmile:.9*k,mouthForm:.8*k,cheek:.6*k,angleZ:3*Math.sin(t*1.7)*k,eyes:-.42*k};}},
  moonGaze:{duration:5.6,at(t,side){const k=pulse(t,.2,1.4,4.2,5.5);
    return {gazeY:.7*k,gazeX:.25*side*k,angleY:6*k,angleX:4*side*k,browY:.3*k,mouthForm:.12*k,eyes:.05*k};}},
  doubleBlink:{duration:.75,at(t){return {eyes:-pulse(t,0,.06,.1,.18)-pulse(t,.32,.38,.42,.52)};}},
  ponder:{duration:4.2,at(t,side){const k=pulse(t,.15,.7,3.2,4.1);
    return {gazeX:.5*side*k,gazeY:.55*k,angleX:3*side*k,angleZ:-2*side*k,mouthForm:-.2*k,browAngle:.2*k};}},
  ack:{duration:1.1,at(t){return {angleY:-3*pulse(t,0,.25,.35,.8),eyeSmile:.2*pulse(t,.1,.3,.6,1.0),browY:.15*pulse(t,0,.2,.5,1.0)};}},
};
Object.assign(GESTURES,{
  laugh:{duration:2.8,at(t){const k=pulse(t,.05,.3,1.9,2.7),shake=Math.max(0,Math.sin(t*15))*(1-ramp(t,.2,2.0));
    return {eyes:-k,eyeSmile:k,mouthForm:k,cheek:.6*k,lift:2.5*shake*k+2*k,angleY:-2*k,angleZ:3*k};}},
  wink:{duration:1.3,at(t){const w=pulse(t,.1,.22,.6,.8),k=pulse(t,.05,.3,.9,1.3);
    return {wink:w,eyeSmile:.5*k,mouthForm:.8*k,cheek:.35*k,angleZ:4*k};}},
  surprised:{duration:2.2,at(t){const k=pulse(t,0,.12,1.0,2.1);
    return {eyes:.42*k,browY:.85*k,lift:5*pulse(t,0,.1,.25,.7),angleY:3*k,mouthOpen:.3*pulse(t,.03,.15,.7,1.3)};}},
  nod:{duration:1.3,at(t){return {angleY:-5.2*pulse(t,0,.22,.32,.65)-2.6*pulse(t,.6,.8,.9,1.25),eyes:-.15*pulse(t,0,.2,.6,1.2)};}},
  shake:{duration:1.6,at(t){const k=pulse(t,0,.2,1.1,1.6);return {angleX:8*Math.sin(t*11)*k,eyes:-.2*k,browY:-.2*k};}},
  tilt:{duration:2.6,at(t,side){const k=pulse(t,.1,.6,1.8,2.5);return {angleZ:9*side*k,angleX:3*side*k,browY:.25*k,eyes:.06*k};}},
});
Object.assign(GESTURES,{
  focusHard:{duration:2.4,at(t){const k=pulse(t,.15,.5,1.7,2.35);return {eyes:-.2*k,browY:-.3*k,browAngle:-.25*k,mouthForm:-.15*k};}},
  checkIn:{duration:1.9,at(t){const k=pulse(t,.1,.35,1.2,1.8);
    return {gazeX:-.5*k,gazeY:.32*k,angleY:2*k,eyeSmile:.3*k,mouthForm:.3*k,eyes:.05*k};}},
  lipPress:{duration:1.6,at(t){const k=pulse(t,.1,.3,1.0,1.5);return {mouthForm:-.35*k,angleZ:-1.5*k};}},
  taskDone:{duration:2.6,at(t){const k=pulse(t,.1,.45,1.6,2.5);
    return {angleY:-4*pulse(t,.15,.35,.45,.8)+1.5*k,eyeSmile:.85*k,eyes:-.32*k,mouthForm:.8*k,cheek:.35*k,lift:1.5*k};}},
});
// While she works on a computer task: a composed, focused face, with motion for each kind of step.
const VARIED=new Set(['nod','ack']);
const WORK_FACE={eyes:-.14,browY:-.12,browAngle:-.2,mouthForm:-.1,angleY:-2.5};
export const WORK_KINDS=['think','read','type','command','look','wait'];
const WORK_MOMENTS=[['focusHard',.4],['checkIn',.35],['lipPress',.25]];

// Sustained expressions: they fade in, last a while, then fade back to her calm face.
export const MOODS={
  smile:{eyes:-.42,eyeSmile:.9,mouthForm:.8,cheek:.45},
  blush:{cheek:1,eyes:-.2,eyeSmile:.4,mouthForm:.35,gazeY:-.35,angleY:-2.5},
  shy:{cheek:1,eyes:-.25,eyeSmile:.3,mouthForm:.25,angleX:-8,gazeX:-.55,gazeY:-.45,angleY:-3,angleZ:-3},
  sad:{eyes:-.32,browY:-.4,browAngle:.6,mouthForm:-.75,angleY:-4.5,gazeY:-.45},
  pout:{mouthForm:-1,cheek:.75,browAngle:-.8,browY:-.4,angleX:6,gazeX:.4,angleZ:2},
  worried:{browY:.35,browAngle:.55,mouthForm:-.45,eyes:.05},
  calm:{},
};
// Cue names the reply model may use, mapped to a gesture and/or a mood.
export const CUES={
  smile:{mood:'smile'},happy:{mood:'smile',gesture:'greet'},blush:{mood:'blush'},shy:{mood:'shy'},
  laugh:{gesture:'laugh',mood:'smile'},wink:{gesture:'wink'},surprised:{gesture:'surprised'},
  sad:{mood:'sad'},pout:{mood:'pout'},annoyed:{mood:'pout'},worried:{mood:'worried'},
  think:{gesture:'ponder'},nod:{gesture:'nod'},shake:{gesture:'shake'},tilt:{gesture:'tilt'},
  sigh:{gesture:'sigh'},yawn:{gesture:'yawn'},stretch:{gesture:'stretch'},moon:{gesture:'moonGaze'},
  calm:{mood:'calm'},neutral:{mood:'calm'},
};
const IDLE_MOMENTS=[['content',.28],['moonGaze',.22],['doubleBlink',.18],['sigh',.14],['stretch',.1],['yawn',.08]];

export class AvatarLife {
  constructor(random=Math.random,clock=()=>new Date()){
    this.random=random;this.clock=clock;
    this.state='awake';this.mode='idle';this.voice=0;this.voicePeak=0;this.voiceAverage=0;
    this.sleepDelay=300;this.quiet=0;this.hoverTime=0;this.hovering=false;
    this.base={...REST};this.layer={...REST};this.gestures=[];
    this.rate=2.5;this.breathPhase=0;this.breathRate=BREATH.awake[0];this.breathDepth=BREATH.awake[1];
    this.blinkAt=2.5+random()*2.5;this.blinkAge=-1;this.blinkLength=.24;
    this.nextMoment=20+random()*20;this.nextNod=6;this.nextModeGesture=2;this.pokes=[];this.time=0;
    this.side=1;this.events=[];this.mood=null;this.moodWeight=0;this.moodOffsets={};
    this.petActive=false;this.petWeight=0;this.petTime=0;this.petX=.5;this.petDemo=0;
    this.working=null;this.workWeight=0;this.waitWeight=0;this.nextWorkMoment=6;
  }
  // 0 never sleeps. Night hours (23:00–05:00) shorten the delay: she is the moon's.
  setSleepDelay(minutes){this.sleepDelay=Number.isFinite(minutes)&&minutes>0?minutes*60:0;}
  delay(){
    const hour=this.clock().getHours();
    return this.sleepDelay*(hour>=23||hour<5?.7:1);
  }
  setMode(mode){
    if(!MODE[mode])mode='idle';
    if(mode===this.mode)return;
    const previous=this.mode;this.mode=mode;
    if(mode!=='idle'&&mode!=='paused'){
      this.quiet=0;
      if(this.state!=='awake')this.wake('startled');
      if(mode==='listening'&&previous==='idle')this.play('ack');
      this.nextModeGesture=1.5+this.random()*2;
    }
  }
  setVoice(level){this.voice=clamp(level,0,1);if(this.voice>0){this.quiet=0;if(this.state!=='awake')this.wake('startled');}}
  // A click on the avatar. Repeated pokes become mildly flustered.
  poke(){
    this.quiet=0;
    if(this.state!=='awake'){this.wake('gentle');return 'wake';}
    this.pokes=this.pokes.filter(at=>this.time-at<8);this.pokes.push(this.time);
    this.side=this.random()<.5?-1:1;
    const name=this.pokes.length>=3?'fluster':'poke';
    if(name==='fluster')this.pokes=[];
    this.play(name,{replace:true});return name;
  }
  // Being petted: the pointer stroking her head. x is its position across the avatar (0..1).
  // A sleeping avatar is not woken by petting; she smiles in her sleep instead.
  pet(active,x){
    const was=this.petActive;this.petActive=Boolean(active);
    if(!this.petActive){
      if(was&&this.state==='awake'&&this.petTime>1)this.mood={name:'smile',time:0,duration:4.5};  // A lingering, content smile.
      return;
    }
    if(Number.isFinite(x))this.petX=clamp(x,0,1);
    this.hoverTime=0;
    if(this.state==='awake')this.quiet=0;  // Drowsy and petted, she is allowed to drift off.
    if(!was)this.events.push('petted');
  }
  // The pointer resting over her. Waking needs a short dwell, not a passing sweep.
  hover(inside){this.hovering=Boolean(inside);if(!this.hovering)this.hoverTime=0;}
  greet(){
    const hour=this.clock().getHours();
    this.play(hour>=23||hour<5?'yawn':hour<11?'stretch':'greet');
  }
  // An expression cue from the conversation (or the avatar menu). Unknown names are ignored.
  cue(name){
    const cue=CUES[String(name).toLowerCase()];
    if(!cue)return false;
    if(this.state!=='awake')this.wake('gentle');
    this.quiet=0;
    if(cue.mood)this.mood={name:cue.mood,time:0,duration:cue.mood==='calm'?0:7+this.random()*3};
    if(cue.gesture){this.side=this.random()<.5?-1:1;this.play(cue.gesture,{replace:cue.gesture!=='ponder'});}
    return true;
  }
  // A computer task: 'start', a step kind (think, read, type, command, look, wait), then 'done' or 'failed'.
  work(kind){
    if(kind==='done'||kind==='failed'||kind==='stop'){
      this.working=null;
      if(kind==='done'){this.play('taskDone',{replace:true});this.mood={name:'smile',time:0,duration:4};this.events.push('sparkle');}
      else{this.play('sigh',{replace:true});if(kind==='failed')this.mood={name:'worried',time:0,duration:4};}
      return;
    }
    if(kind==='start'){
      if(this.state!=='awake')this.wake('startled');
      this.working={kind:'think',time:0};this.nextWorkMoment=6+this.random()*4;this.quiet=0;
      this.side=this.random()<.5?-1:1;this.play('ponder');
      return;
    }
    if(!WORK_KINDS.includes(kind))return;
    if(!this.working){this.work('start');}
    if(this.working.kind!==kind)this.working={kind,time:0};
    if(kind==='think'){this.side=-this.side;this.play('ponder');}
  }
  // Animation tester commands: jump straight to a state instead of waiting minutes.
  test(name){
    if(name.startsWith('work:')){this.work(name.slice(5));return true;}
    if(name==='drowsy'){this.wake('gentle');this.gestures=[];this.state='drowsy';this.quiet=0;this.play('yawn');
      this.nextNod=6;this.events.push('drowsy');return true;}
    if(name==='sleep'){this.gestures=[];this.state='asleep';this.quiet=0;this.events.push('asleep');return true;}
    if(name==='wake'||name==='wakeStartled'){
      if(this.state==='awake'){this.state='asleep';this.base={...REST,...BASE.asleep};this.sleepWeight=1;}
      this.wake(name==='wake'?'gentle':'startled');return true;}
    if(name==='greet'){this.wake('startled');this.greet();return true;}
    if(name==='poke'){this.poke();return true;}
    if(name==='fluster'){this.wake('startled');this.side=this.random()<.5?-1:1;this.play('fluster',{replace:true});return true;}
    if(name==='nodOff'){this.play('nodOff',{replace:true});return true;}
    if(name==='pet'){this.petDemo=3.5;return true;}
    return false;
  }
  wake(kind='gentle'){
    if(this.state==='awake')return;
    const from=this.state;this.state='awake';this.quiet=0;this.nextMoment=25+this.random()*25;
    this.gestures=this.gestures.filter(g=>g.name!=='nodOff');
    this.rate=kind==='startled'?9:from==='asleep'?1.5:3;
    this.play(kind==='startled'?'wakeStartled':from==='asleep'?'wakeGentle':'doubleBlink',{replace:true});
    this.events.push('wake');
  }
  play(name,{replace=false}={}){
    if(!GESTURES[name])return;
    if(replace)this.gestures=[];
    if(this.gestures.some(g=>g.name===name))return;
    // Nods vary like a person's: some quick and light, some slow and a little deeper.
    const varied=VARIED.has(name),speed=varied?.75+this.random()*.6:1;
    this.gestures.push({name,time:0,side:this.side,speed,depth:varied?.82+.18*(1.35-speed)/.6+this.random()*.08:1});
  }
  update(seconds){
    const dt=Number.isFinite(seconds)?clamp(seconds,0,.1):0;
    this.time+=dt;
    this.updateState(dt);this.updateMoments(dt);
    const target={...REST,...BASE[this.state],...(this.state==='awake'?MODE[this.mode]:{})};
    // Settle quickly between ordinary states, slowly while falling asleep.
    const rate=this.state==='asleep'?.55:this.state==='drowsy'?.9:this.rate;
    this.rate+=(2.5-this.rate)*(1-Math.exp(-dt*.5));
    for(const key of Object.keys(REST))this.base[key]+=(target[key]-this.base[key])*(1-Math.exp(-dt*rate));
    const layer={...this.base};
    this.applyMood(dt,layer);
    this.applyPetting(dt,layer);
    this.applyWork(dt,layer);
    for(const gesture of this.gestures){
      gesture.time+=dt*(gesture.speed??1);
      const offsets=GESTURES[gesture.name].at(gesture.time,gesture.side),depth=gesture.depth??1;
      // 'eyes2' lets a gesture add a smile's squint on top of its own eyelid motion.
      for(const [key,value] of Object.entries(offsets))layer[key==='eyes2'?'eyes':key]+=value*depth;
    }
    this.gestures=this.gestures.filter(g=>g.time<GESTURES[g.name].duration);
    this.expressVoice(dt,layer);
    for(const [key,[low,high]] of Object.entries(BOUNDS))layer[key]=clamp(layer[key],low,high);
    const [rate2,depth]=BREATH[this.state];
    this.breathRate+=(rate2-this.breathRate)*(1-Math.exp(-dt*.8));
    this.breathDepth+=(depth-this.breathDepth)*(1-Math.exp(-dt*.8));
    this.breathPhase+=dt*this.breathRate;
    const sleep=this.state==='asleep'?1:0;
    this.sleepWeight=(this.sleepWeight??0)+(sleep-(this.sleepWeight??0))*(1-Math.exp(-dt*.7));
    // Visible sleeping breath: the shoulders rise and settle with each breath.
    layer.lift+=Math.sin(this.breathPhase)*1.6*this.sleepWeight;
    this.layer={...layer,blink:this.blink(dt),breath:clamp(.5+Math.sin(this.breathPhase)*this.breathDepth,0,1),
      alertness:this.state==='awake'?1:this.state==='drowsy'?.45:0,zzz:this.sleepWeight,state:this.state,
      focus:this.workWeight,working:this.working?.kind??null};
    return this.layer;
  }
  applyMood(dt,layer){
    const mood=this.mood;
    if(mood){mood.time+=dt;if(mood.time>=mood.duration)this.mood=null;else this.moodOffsets=MOODS[mood.name];}
    // Sleep and waking take over the face; a mood waits for her to be awake.
    const target=this.mood&&this.state==='awake'&&this.mood.name!=='calm'?1:0;
    this.moodWeight+=(target-this.moodWeight)*(1-Math.exp(-dt*(target>this.moodWeight?3.2:1.4)));
    for(const [key,value] of Object.entries(this.moodOffsets))layer[key]+=value*this.moodWeight;
  }
  applyWork(dt,layer){
    const working=this.working;
    if(working){working.time+=dt;this.quiet=0;}
    this.workWeight+=((working?1:0)-this.workWeight)*(1-Math.exp(-dt*(working?2.6:1.2)));
    this.waitWeight+=((working?.kind==='wait'?1:0)-this.waitWeight)*(1-Math.exp(-dt*3));
    const w=this.workWeight;
    if(w<.002)return;
    const t=working?.time??0,kind=working?.kind??'think',focus=w*(1-this.waitWeight);
    for(const [key,value] of Object.entries(WORK_FACE))layer[key]+=value*focus;
    if(kind==='read'){
      // Reading a page: eyes sweep along a line, flick back, and step down line by line.
      const line=t%1.7,sweep=line<1.45?-.36+.72*smooth(line/1.45):.36-.72*smooth((line-1.45)/.25);
      layer.gazeX+=sweep*focus;layer.gazeY+=(-.18-.07*(Math.floor(t/1.7)%5))*focus;layer.angleX+=sweep*2.5*focus;
    }else if(kind==='type'||kind==='command'){
      // Typing: eyes lowered, bursts of small rhythmic movement, a glance up now and then.
      const burst=smooth((Math.sin(t*.9)+.3)*1.6),tap=Math.sin(t*15)*burst,glance=pulse(t%4.6,3.7,3.9,4.2,4.5);
      layer.gazeY+=(-.42+.55*glance)*focus;layer.gazeX+=(.1*Math.sin(t*1.3)+(kind==='command'?.12:0))*focus;
      layer.angleY+=.45*tap*focus;layer.shoulders+=.6*tap*focus;layer.angleZ+=(kind==='command'?-1.5:1)*focus;
    }else if(kind==='look'){
      // Using an app on screen: looking off to the side, a small nod with each click.
      const click=pulse(t%1.6,0,.08,.14,.35);
      layer.gazeX+=.42*focus;layer.gazeY+=-.04*focus;layer.angleX+=5*focus;layer.eyes+=.08*focus;layer.angleY-=1.4*click*focus;
    }else if(kind==='think'){
      layer.gazeY+=.12*focus;layer.angleZ+=-1.5*focus;
    }
    // Waiting for the person's approval: she looks at them, brows lifted, leaning in a little.
    const wait=w*this.waitWeight,pulseBrow=.12*Math.max(0,Math.sin(t*2.4));
    layer.browY+=(.32+pulseBrow)*wait;layer.eyes+=.1*wait;layer.angleZ+=5*wait;layer.lift+=1.5*wait;
    layer.mouthForm+=.05*wait;layer.gazeX-=layer.gazeX*.8*wait;layer.gazeY-=layer.gazeY*.8*wait;
    if(working&&kind!=='wait'){
      this.nextWorkMoment-=dt;
      if(this.nextWorkMoment<=0&&!this.gestures.length){this.play(this.pick(WORK_MOMENTS));this.nextWorkMoment=6+this.random()*6;}
    }
  }
  pick(options){
    let choice=this.random()*options.reduce((sum,[,weight])=>sum+weight,0);
    for(const [name,weight] of options){choice-=weight;if(choice<=0)return name;}
    return options[0][0];
  }
  applyPetting(dt,layer){
    if(this.petDemo>0){
      this.petDemo-=dt;
      this.pet(this.petDemo>0,.5+.22*Math.sin(this.time*7));
    }
    const target=this.petActive?1:0;
    this.petWeight+=(target-this.petWeight)*(1-Math.exp(-dt*(target?3.5:1.3)));
    this.petTime=this.petActive?this.petTime+dt:Math.max(0,this.petTime-dt*2);
    const w=this.petWeight;
    if(w<.002)return;
    // Lean into the hand, bob gently with the pats, and blush more the longer it lasts.
    const lean=clamp((this.petX-.5)*2,-1,1),bob=Math.sin(this.petTime*8.5)*(this.petActive?1:0);
    const warmth=.45+.45*clamp(this.petTime/5,0,1);
    if(this.state==='asleep'){
      layer.eyeSmile+=.6*w;layer.mouthForm+=.5*w;layer.cheek+=.5*w;layer.angleZ+=3*lean*w;
      return;
    }
    layer.eyes+=-.92*w;layer.eyeSmile+=.95*w;layer.mouthForm+=.65*w;layer.cheek+=warmth*w;
    layer.angleY+=(-3.5+1.3*bob)*w;layer.angleZ+=5*lean*w;layer.angleX+=3*lean*w;layer.lift+=(-1.5+.8*bob)*w;
  }
  updateState(dt){
    const delay=this.delay();
    if(this.hovering&&!this.petActive){
      this.hoverTime+=dt;
      if(this.state==='awake')this.quiet=0;  // Being looked after keeps her awake.
      else if(this.hoverTime>(this.state==='asleep'?.9:.4)){this.hoverTime=0;this.wake('gentle');}
    }
    const resting=this.mode==='idle'&&this.voice===0;
    if(!resting||!delay){if(this.state!=='awake'&&!resting)this.wake('startled');this.quiet=resting?this.quiet:0;return;}
    this.quiet+=dt;
    if(this.state==='awake'&&this.quiet>=delay*.6&&!this.gestures.length){
      this.state='drowsy';this.play('yawn');this.nextNod=7+this.random()*4;this.events.push('drowsy');
    }else if(this.state==='drowsy'&&this.quiet>=delay&&!this.gestures.length){
      this.state='asleep';this.events.push('asleep');
    }
  }
  updateMoments(dt){
    if(this.state==='drowsy'){
      this.nextNod-=dt;
      if(this.nextNod<=0&&!this.gestures.length){this.play('nodOff');this.nextNod=9+this.random()*6;}
      return;
    }
    if(this.state!=='awake')return;
    if(this.working)return;
    if(this.mode==='idle'){
      this.nextMoment-=dt;
      if(this.nextMoment<=0&&!this.gestures.length&&this.quiet>8){
        this.side=this.random()<.5?-1:1;this.play(this.chooseMoment());this.nextMoment=18+this.random()*27;
      }
    }else if(this.mode==='thinking'||this.mode==='listening'){
      this.nextModeGesture-=dt;
      if(this.nextModeGesture<=0&&!this.gestures.length){
        this.side=-this.side;this.play(this.mode==='thinking'?'ponder':'ack');
        this.nextModeGesture=this.mode==='thinking'?3+this.random()*3:5+this.random()*4;
      }
    }
  }
  chooseMoment(){
    const options=IDLE_MOMENTS.filter(([name])=>(name!=='stretch'||this.quiet>90)&&(name!=='yawn'||this.quiet>this.delay()*.35));
    const total=options.reduce((sum,[,weight])=>sum+weight,0);
    let pick=this.random()*total;
    for(const [name,weight] of options){pick-=weight;if(pick<=0)return name;}
    return options[0][0];
  }
  // Speech: brows lift on emphasis and a slight warmth settles in; never the mouth.
  expressVoice(dt,layer){
    this.voiceAverage+=(this.voice-this.voiceAverage)*(1-Math.exp(-dt*1.2));
    const emphasis=Math.max(0,this.voice-this.voiceAverage-.12);
    this.voicePeak+=(emphasis-this.voicePeak)*(1-Math.exp(-dt*(emphasis>this.voicePeak?10:2.5)));
    layer.browY+=this.voicePeak*1.1;
    if(this.mode==='speaking')layer.eyeSmile+=.12*clamp(this.voiceAverage*2,0,1);
  }
  // Heavier, slower blinks when drowsy; none while asleep (eyes are already closed).
  blink(dt){
    if(this.state==='asleep'){this.blinkAge=-1;return 0;}
    if(this.blinkAge<0){
      this.blinkAt-=dt;
      if(this.blinkAt<=0){this.blinkAge=0;this.blinkLength=this.state==='drowsy'?.55:.24;}
      return 0;
    }
    this.blinkAge+=dt;
    const close=this.blinkLength*.32;
    if(this.blinkAge>=this.blinkLength){
      this.blinkAge=-1;this.blinkAt=this.state==='drowsy'?1.6+this.random()*2.2:2.8+this.random()*4;
      if(this.random()<.12)this.blinkAt=.18;  // An occasional natural double blink.
      return 0;
    }
    const t=this.blinkAge<close?this.blinkAge/close:1-(this.blinkAge-close)/(this.blinkLength-close);
    return Math.sin(clamp(t,0,1)*Math.PI/2);
  }
  takeEvents(){const events=this.events;this.events=[];return events;}
  snapshot(){return {state:this.state,mode:this.mode,quiet:this.quiet,gestures:this.gestures.map(g=>g.name),
    delay:this.delay(),zzz:this.layer.zzz??0,mood:this.mood?.name??null,petting:this.petActive,
    working:this.working?.kind??null};}
}
