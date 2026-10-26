// Independent of DOM and rendering. Posture/gaze only: blink, breath, mouth and
// hair retain their runtime owners. All limits fit the reviewed Jingliu rig.
const rest=()=>({angleX:0,angleY:0,angleZ:0,gazeX:0,gazeY:0});
const clamp=(value,limit=1)=>Math.max(-limit,Math.min(limit,value));
const ease=value=>{const x=Math.max(0,Math.min(1,value));return x*x*x*(10+x*(-15+6*x));};
const unit=value=>Number.isFinite(value)?Math.max(0,Math.min(1,value)):0;

// CSS client coordinates and DOMRect share one coordinate system, independent
// of backing-canvas DPR. Use the actual contain-fit portrait's eye center.
export function cursorTarget(point,rect,rig) {
  if(!point||!rect||!['x','y'].every(key=>Number.isFinite(point[key]))||
    !['left','top','width','height'].every(key=>Number.isFinite(rect[key]))||rect.width<=0||rect.height<=0)return null;
  const width=rig?.image?.width,height=rig?.image?.height;
  const side=rig?.view?.padSide??0,top=rig?.view?.padTop??0;
  const eye=rig?.view?.gazeCenter??[rig?.head?.cx,rig?.head?.cy];
  if(!Array.isArray(eye)||eye.length!==2||![width,height,side,top,...eye].every(Number.isFinite)||width<=0||height<=0||side<=-.5||top<=-1)return null;
  const scale=Math.min(rect.width/(width*(1+2*side)),rect.height/(height*(1+top)));
  const eyeX=rect.left+(rect.width-width*scale)/2+eye[0]*scale;
  const eyeY=rect.top+rect.height-height*scale+eye[1]*scale;
  return {x:clamp((point.x-eyeX)/(rect.width*.75)),y:clamp((eyeY-point.y)/(rect.height*.65))};
}

export class IdleAttention {
  constructor(random=Math.random){this.random=random;this.cursorEnabled=true;this.motion=1;this.gaze=1;this.reset();}
  reset(){
    this.time=0;this.duration=0;this.elapsed=0;this.travel=1;this.hold=1.5;
    this.kind='rest';this.head=rest();this.from=rest();this.target=rest();
    this.bodyX=0;this.bodyZ=0;this.cursor=null;this.movementAnchor=null;this.cursorMoved=-Infinity;this.nextNotice=0;
    this.notices=0;
  }
  setCursor(target){
    if(!target||!Number.isFinite(target.x)||!Number.isFinite(target.y)){
      this.cursor=null;this.movementAnchor=null;
      if(this.kind==='cursor')this.begin('return',rest(),1.8,2.5);
      return;
    }
    const next={x:clamp(target.x),y:clamp(target.y)};
    if(!this.movementAnchor||Math.hypot(next.x-this.movementAnchor.x,next.y-this.movementAnchor.y)>.035){
      this.cursorMoved=this.time;this.movementAnchor=next;
    }
    this.cursor=next;
  }
  setCursorEnabled(enabled){
    this.cursorEnabled=Boolean(enabled);
    if(!this.cursorEnabled)this.setCursor(null);
  }
  setIntensity(motion,gaze){this.motion=unit(motion);this.gaze=unit(gaze);}
  begin(kind,target,travel,hold){
    this.kind=kind;this.from={...this.head};this.target=target;this.elapsed=0;this.travel=travel;this.hold=hold;
  }
  plan(at){
    if(this.kind==='cursor'||this.kind==='idle'){
      this.begin('return',rest(),1.7+this.random()*.6,2.5+this.random()*2.5);return;
    }
    const cursor=this.cursor;
    if(this.cursorEnabled&&cursor&&at-this.cursorMoved<4&&at>=this.nextNotice&&
      Math.hypot(cursor.x,cursor.y)>.12&&this.random()<.8){
      // Snapshot attention once. Later mouse events cannot tug the active pose.
      this.begin('cursor',{angleX:cursor.x*12,angleY:cursor.y*4,angleZ:-cursor.x*3,
        gazeX:cursor.x*.55,gazeY:cursor.y*.28},1.7+this.random()*.4,.8+this.random()*.8);
      this.nextNotice=at+9+this.random()*5;this.notices++;return;
    }
    const side=this.random()<.5?-1:1;
    this.begin('idle',{angleX:side*(6+this.random()*6),angleY:(this.random()*2-1)*2,
      angleZ:-side*(2+this.random()*4),gazeX:side*(.12+this.random()*.16),gazeY:(this.random()*2-1)*.08},
      1.8+this.random()*.7,.8+this.random());
  }
  update(seconds){
    const dt=Number.isFinite(seconds)?Math.max(0,Math.min(.1,seconds)):0;
    if(dt>0){
      this.time+=dt;this.elapsed+=dt;
      if(this.elapsed>=this.travel+this.hold){
        const remainder=this.elapsed-this.travel-this.hold;
        this.plan(this.time-remainder);this.elapsed=remainder;
      }
      for(const key of Object.keys(this.head)){
        const duration=key.startsWith('gaze') ? .42 : this.travel;
        this.head[key]=this.from[key]+(this.target[key]-this.from[key])*ease(this.elapsed/duration);
      }
      this.bodyX+=(this.head.angleX*.1-this.bodyX)*(1-Math.exp(-2.2*dt));
      this.bodyZ+=(this.head.angleZ*.14-this.bodyZ)*(1-Math.exp(-1.8*dt));
    }
    const pose={...this.head,bodyAngleX:this.bodyX,bodyAngleZ:this.bodyZ};
    for(const key of Object.keys(pose))pose[key]*=this.motion*(key.startsWith('gaze')?this.gaze:1);
    const labels={rest:'Resting',idle:'A quiet glance',cursor:'Noticing the cursor',return:'Returning to rest'};
    return {label:labels[this.kind],expression:'neutral',pose,finished:false};
  }
  snapshot(){return {kind:this.kind,notices:this.notices,nextNotice:this.nextNotice,cursorEnabled:this.cursorEnabled};}
}
