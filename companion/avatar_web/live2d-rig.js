// Parameter ownership for a real Cubism rig. No portrait-wide deformation here.
const clamp=(v,a,b)=>Math.max(a,Math.min(b,Number.isFinite(v)?v:0));
export const CONTROL_IDS={
  angleX:'ParamAngleX',angleY:'ParamAngleY',angleZ:'ParamAngleZ',
  bodyAngleX:'ParamBodyAngleX',bodyAngleZ:'ParamBodyAngleZ',
  gazeX:'ParamEyeBallX',gazeY:'ParamEyeBallY',
};

export class Live2DRig {
  constructor(parameters){
    this.parameters=new Map(parameters.map(p=>[p.id,p]));
    this.last={};
  }
  value(id,value){
    const p=this.parameters.get(id);
    if(!p)return;
    this.last[id]=clamp(value,p.min,p.max);
  }
  normalized(id,value){
    const p=this.parameters.get(id);
    if(!p)return;
    const unit=clamp(value,-1,1);
    this.value(id,p.default+unit*(unit<0?p.default-p.min:p.max-p.default));
  }
  pose(pose,{voice=0,eyeOpen=1,breath=.5}={}){
    this.last={};
    // Existing motion units are deliberately small for the old mesh. Map them
    // onto the authored head keyforms, with a margin before extreme endpoints.
    for(const [key,limit,gain] of [
      ['angleX',12,.85],['angleY',4,.70],['angleZ',8,.42],
      ['bodyAngleX',1.5,.16],['bodyAngleZ',1.2,.15],
      ['gazeX',.6,.7],['gazeY',.3,.55],
    ])this.normalized(CONTROL_IDS[key],clamp((pose[key]??0)/limit,-1,1)*gain);
    for(const id of ['ParamEyeLOpen','ParamEyeROpen']){
      const p=this.parameters.get(id);
      if(p)this.value(id,p.min+clamp(eyeOpen,0,1)*(p.default-p.min));
    }
    const mouth=this.parameters.get('ParamMouthOpenY');
    if(mouth)this.value(mouth.id,mouth.min+clamp(voice,0,1)*(mouth.max-mouth.min));
    this.normalized('ParamBrowLY',pose.browY??0);
    this.normalized('ParamBrowRY',pose.browY??0);
    const breathing=this.parameters.get('ParamBreath');
    if(breathing)this.value(breathing.id,breathing.min+clamp(breath,0,1)*(breathing.max-breathing.min));
    return {...this.last};
  }
  missing(){return ['ParamAngleX','ParamAngleY','ParamAngleZ','ParamEyeLOpen','ParamEyeROpen','ParamMouthOpenY']
    .filter(id=>!this.parameters.has(id));}
}

export class RigBlink {
  constructor(random=Math.random){this.random=random;this.time=0;this.next=2.5+random()*2.5;}
  update(dt){
    this.time+=clamp(dt,0,.1);
    const age=this.time-this.next;
    if(age<0)return 1;
    if(age>=.24){this.next=this.time+2.8+this.random()*4;return 1;}
    const t=age<.075?age/.075:1-(age-.075)/.165;
    return 1-Math.sin(clamp(t,0,1)*Math.PI/2);
  }
}
