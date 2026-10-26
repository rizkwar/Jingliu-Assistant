const KEYS=['angleX','angleY','angleZ','gazeX','gazeY'];
const rest=()=>Object.fromEntries(KEYS.map(key=>[key,0]));
const ease=value=>{const x=Math.max(0,Math.min(1,value));return x*x*x*(10+x*(-15+6*x));};
const sequence=[
  {label:'Settling',pose:{},travel:.8,hold:.4},
  {label:'Looking left',pose:{angleX:-10,angleY:1,angleZ:3,gazeX:-.45,gazeY:.04},travel:1.8,hold:.6},
  {label:'Looking right',pose:{angleX:10,angleY:1,angleZ:-3,gazeX:.45,gazeY:.04},travel:2.2,hold:.6},
  {label:'A small head tilt',pose:{angleY:-3,angleZ:6,gazeY:-.16},travel:1.8,hold:.6},
  {label:'Returning to rest',pose:{},travel:1.8,hold:1.7},
];

// Silent posture-only sample, within the reviewed rig range. Eyes anticipate
// the head; shoulders lag. The runtime owns blinking, breath, hair and mouth.
export class MotionPreview {
  constructor(startPose={}){
    this.time=0;this.elapsed=0;this.index=0;this.finished=false;
    this.duration=sequence.reduce((sum,step)=>sum+step.travel+step.hold,0);
    this.from=rest();
    for(const key of KEYS)if(Number.isFinite(startPose[key]))this.from[key]=startPose[key];
    this.head={...this.from};
    this.bodyX=Number.isFinite(startPose.bodyAngleX)?startPose.bodyAngleX:0;
    this.bodyZ=Number.isFinite(startPose.bodyAngleZ)?startPose.bodyAngleZ:0;
  }
  update(seconds){
    const dt=Number.isFinite(seconds)?Math.max(0,Math.min(.1,seconds)):0;
    if(!this.finished&&dt>0){
      this.time=Math.min(this.duration,this.time+dt);this.elapsed+=dt;
      while(this.elapsed>=sequence[this.index].travel+sequence[this.index].hold-1e-9){
        this.head={...rest(),...sequence[this.index].pose};
        if(this.index===sequence.length-1){this.finished=true;break;}
        this.elapsed-=sequence[this.index].travel+sequence[this.index].hold;
        this.index++;this.from={...this.head};
      }
      const step=sequence[this.index],target={...rest(),...step.pose};
      for(const key of KEYS)this.head[key]=this.from[key]+(target[key]-this.from[key])*ease(this.elapsed/(key.startsWith('gaze')?.42:step.travel));
      this.bodyX+=(this.head.angleX*.1-this.bodyX)*(1-Math.exp(-2.2*dt));
      this.bodyZ+=(this.head.angleZ*.14-this.bodyZ)*(1-Math.exp(-1.8*dt));
    }
    return {pose:{...this.head,bodyAngleX:this.bodyX,bodyAngleZ:this.bodyZ},
      label:sequence[this.index].label,finished:this.finished};
  }
}
