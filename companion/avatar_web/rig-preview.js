// A separate showcase for authored head keyforms; the current mesh demo is unchanged.
const ease=t=>{t=Math.max(0,Math.min(1,t));return t*t*t*(10+t*(-15+t*6));};
const STEPS=[
  ['Settling',{},.9,.5],
  ['Looking left',{angleX:-11,angleY:0,angleZ:1,gazeX:-.35},1.8,1],
  ['Looking right',{angleX:11,angleY:0,angleZ:-1,gazeX:.35},2.4,1],
  ['Looking up',{angleX:0,angleY:3.8,gazeY:.22},2,1],
  ['Looking down',{angleY:-3.8,gazeY:-.22},2,1],
  ['Turning and tilting',{angleX:-8,angleY:2.5,angleZ:6,gazeX:-.3},2,1],
  ['Returning to rest',{},2,1.5],
];
const zero=()=>({angleX:0,angleY:0,angleZ:0,gazeX:0,gazeY:0,bodyAngleX:0,bodyAngleZ:0});
export class RigPreview {
  constructor(pose={}){
    this.time=0;this.elapsed=0;this.index=0;this.finished=false;
    this.duration=STEPS.reduce((n,s)=>n+s[2]+s[3],0);
    this.from={...zero(),...pose};this.head={...this.from};this.bodyX=0;this.bodyZ=0;
  }
  update(seconds){
    const dt=Number.isFinite(seconds)?Math.max(0,Math.min(.1,seconds)):0;
    if(!this.finished){
      this.time=Math.min(this.duration,this.time+dt);this.elapsed+=dt;
      while(this.elapsed>=STEPS[this.index][2]+STEPS[this.index][3]-1e-9){
        this.head={...zero(),...STEPS[this.index][1]};
        if(this.index===STEPS.length-1){this.finished=true;break;}
        this.elapsed-=STEPS[this.index][2]+STEPS[this.index][3];
        this.index++;this.from={...this.head};
      }
      const [,values,travel]=STEPS[this.index],target={...zero(),...values};
      for(const key of Object.keys(this.head))this.head[key]=this.from[key]+(target[key]-this.from[key])*
        ease(this.elapsed/(key.startsWith('gaze')?.4:travel));
      this.bodyX+=(this.head.angleX*.1-this.bodyX)*(1-Math.exp(-2*dt));
      this.bodyZ+=(this.head.angleZ*.14-this.bodyZ)*(1-Math.exp(-1.8*dt));
    }
    return {pose:{...this.head,bodyAngleX:this.bodyX,bodyAngleZ:this.bodyZ},
      label:STEPS[this.index][0],finished:this.finished};
  }
}
