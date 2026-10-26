// A finite pose study, deliberately separate from the assistant's behavior.
// Values are normalized rig controls, not physical angles.
export const REST = Object.freeze({angleX:0, angleY:0, angleZ:0, gazeX:0, gazeY:0});
const pose = overrides => Object.freeze({...REST, ...overrides});
export const SEQUENCE = Object.freeze([
  {label:'Rest', pose:pose({}), travel:1, hold:1},
  {label:'Look left', pose:pose({angleX:-12, gazeX:-.28}), travel:1.8, hold:1},
  {label:'Return to center', pose:pose({}), travel:1.8, hold:.7},
  {label:'Look right', pose:pose({angleX:12, gazeX:.28}), travel:1.8, hold:1},
  {label:'Return to center', pose:pose({}), travel:1.8, hold:.7},
  {label:'Look up', pose:pose({angleY:4, gazeY:.16}), travel:1.8, hold:1},
  {label:'Look down', pose:pose({angleY:-4, gazeY:-.16}), travel:2.1, hold:1},
  {label:'Return to center', pose:pose({}), travel:1.8, hold:.7},
  {label:'Turn and tilt left', pose:pose({angleX:-10, angleY:-2, angleZ:-8, gazeX:-.24}), travel:2, hold:1.2},
  {label:'Return to center', pose:pose({}), travel:1.8, hold:.7},
  {label:'Turn and tilt right', pose:pose({angleX:10, angleY:2, angleZ:8, gazeX:.24}), travel:2, hold:1.2},
  {label:'Half-closed eyes: check gaze limitation', pose:pose({angleX:8, gazeX:.24}), travel:1.8, hold:1.5, expression:'halfLidded'},
  {label:'Settle at rest', pose:pose({}), travel:2, hold:3},
].map(Object.freeze));
export const DURATION = SEQUENCE.reduce((sum, step) => sum+step.travel+step.hold, 0);
const ease = value => {const x=Math.max(0,Math.min(1,value));return x*x*x*(10+x*(-15+6*x));};

export class HeadTurnStudy {
  constructor(sequence=SEQUENCE) {
    this.sequence=sequence;
    this.duration=sequence.reduce((sum,step)=>sum+step.travel+step.hold,0);
    this.reset();
  }
  reset() {this.time=0;this.bodyX=0;this.bodyZ=0;this.head={...REST};}
  update(seconds) {
    const dt=Number.isFinite(seconds) ? Math.max(0,Math.min(.1,seconds)) : 0;
    this.time=Math.min(this.duration,this.time+dt);
    let local=this.time, from=REST, step=this.sequence.at(-1);
    for (const item of this.sequence) {
      step=item;
      if(local<=item.travel+item.hold) break;
      local-=item.travel+item.hold;
      from=item.pose;
    }
    this.current=step;
    this.phaseTime=local;
    for(const key of Object.keys(REST)) {
      // A short eye lead, without changing eyelids or the iris clipping shader.
      const duration=key.startsWith('gaze') ? .45 : step.travel;
      this.head[key]=from[key]+(step.pose[key]-from[key])*ease(local/duration);
    }
    this.bodyX+=(this.head.angleX*.1-this.bodyX)*(1-Math.exp(-2.2*dt));
    this.bodyZ+=(this.head.angleZ*.14-this.bodyZ)*(1-Math.exp(-1.8*dt));
    return {label:step.label, expression:step.expression ?? 'neutral', finished:this.time>=this.duration,
      pose:{...this.head,bodyAngleX:this.bodyX,bodyAngleZ:this.bodyZ}};
  }
}
