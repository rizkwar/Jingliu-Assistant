import {drawingSize} from './render-quality.js';
import {Live2DRig,RigBlink} from './live2d-rig.js';
import {RigPreview} from './rig-preview.js';
import {Live2DPhysics} from './live2d-physics.js';

function script(url){return new Promise((resolve,reject)=>{
  const element=document.createElement('script');element.src=url;
  element.onload=resolve;element.onerror=()=>reject(new Error('Missing local Live2D runtime'));
  document.head.appendChild(element);
});}

export async function loadLive2DAvatar(canvas,url){
  for(const name of ['live2dcubismcore.min.js','pixi.min.js','unsafe-eval.min.js','cubism4.min.js'])
    await script('./runtime/'+name);
  const PIXI=window.PIXI;
  const model=await PIXI.live2d.Live2DModel.from(url,{autoUpdate:false,autoInteract:false,
    motionPreload:'NONE',idleMotionGroup:'__assistant_disabled__'});
  let renderer;
  try{
    const definition=await (await fetch(url)).json(),refs=definition.FileReferences;
    const metadata=await Promise.all(['DisplayInfo','Physics'].map(async key=>
      refs[key]?await (await fetch(new URL(refs[key],new URL(url,location.href)))).json():{}));
    const names=new Map((metadata[0].Parameters??[]).map(p=>[p.Id,p.Name]));
    const outputs=(metadata[1].PhysicsSettings??[]).flatMap(group=>group.Output??[]);
    const hairIds=new Set(outputs.map(o=>o.Destination?.Id).filter(id=>/hair|bang|fringe|髪|发/i.test(names.get(id)??'')));
    renderer=new PIXI.Renderer({view:canvas,backgroundAlpha:0,antialias:true,preserveDrawingBuffer:true});
    return new Live2DAvatar(canvas,renderer,model,PIXI,hairIds,metadata[1]);
  }catch(error){model.destroy({texture:true,baseTexture:true});renderer?.destroy(false);throw error;}
}

class Live2DAvatar {
  constructor(canvas,renderer,model,PIXI,hairIds,physicsDefinition){
    this.canvas=canvas;this.renderer=renderer;this.model=model;
    this.stage=new PIXI.Container();this.stage.addChild(model);
    this.internal=model.internalModel;this.core=this.internal.coreModel;
    const parameters=this.core.getModel().parameters;
    this.rig=new Live2DRig(Array.from(parameters.ids,(id,i)=>({id,
      min:parameters.minimumValues[i],max:parameters.maximumValues[i],default:parameters.defaultValues[i]})));
    this.pose={};this.expression='neutral';this.level=0;this.mouth=0;this.time=0;
    this.blink=new RigBlink();this.eyeOpen=1;this.hair=.45;this.framing='portrait';this.destroyed=false;this.appearance={};
    this.values={};this.bodyBounds=this.bounds();
    const b=this.bodyBounds;
    this.package={rig:{image:{width:b.width,height:b.height},
      view:{gazeCenter:[b.width/2,b.height*.23]},head:{cx:b.width/2,cy:b.height*.23}}};
    // One controller owns the head/gaze. Apply its parameters before the rig's
    // authored physics, allowing hair and accessories to respond to the turn.
    this.internal.updateFocus=()=>this.applyPose();
    this.internal.updateNaturalMovements=()=>{};
    this.internal.eyeBlink=undefined;
    this.internal.motionManager.stopAllMotions();
    this.hairIds=hairIds;
    if(this.internal.physics){
      const physics=this.internal.physics,evaluate=physics.evaluate.bind(physics);
      const outputIds=(physicsDefinition.PhysicsSettings??[]).flatMap(group=>group.Output??[])
        .map(output=>output.Destination?.Id).filter(id=>this.rig.parameters.has(id));
      this.physicsClock=new Live2DPhysics(evaluate,outputIds,physicsDefinition.Meta?.Fps);
      physics.evaluate=core=>this.physicsClock.update(core,this.physicsSeconds);
    }
    this.internal.on('beforeModelUpdate',()=>{
      const data=this.core.getModel().parameters;
      for(const id of this.hairIds){
        const p=this.rig.parameters.get(id);
        if(!p)continue;
        const value=this.core.getParameterValueById(id);
        this.core.setParameterValueById(id,Math.max(p.min,Math.min(p.max,p.default+(value-p.default)*this.hair/.45)));
      }
      this.values=Object.fromEntries(Array.from(data.ids,(id,i)=>[id,data.values[i]]));
    });
    // Advance once to initialize drawing geometry even if the user pauses immediately.
    this.advanceStable(.001);
  }
  bounds(){
    const data=this.core.getModel().drawables;
    const info=this.core.getModel().canvasinfo;
    let left=Infinity,right=-Infinity,top=Infinity,bottom=-Infinity;
    for(let i=0;i<data.count;i++){
      if(data.opacities[i]<.01)continue;
      const p=this.internal.getDrawableVertices(i);
      for(let j=0;j<p.length;j+=2){left=Math.min(left,p[j]);right=Math.max(right,p[j]);
        top=Math.min(top,p[j+1]);bottom=Math.max(bottom,p[j+1]);}
    }
    if(![left,right,top,bottom].every(Number.isFinite)||right<=left||bottom<=top)
      return {left:0,top:0,width:info.CanvasWidth,height:info.CanvasHeight};
    return {left,top,width:right-left,height:bottom-top};
  }
  layout(){
    const rect=this.canvas.getBoundingClientRect();
    const [w,h]=drawingSize(rect.width,rect.height,devicePixelRatio,this.canvas.dataset.renderQuality!=='balanced');
    if(this.canvas.width!==w||this.canvas.height!==h)this.renderer.resize(w,h);
    const b=this.bodyBounds,portrait=this.framing==='portrait';
    const regionH=b.height*(portrait?.27:1.08),regionW=portrait?Math.min(b.width*1.05,regionH*.95):b.width*1.12;
    const x=b.left+b.width/2-regionW/2,y=b.top-b.height*.025;
    const scale=Math.min(w/regionW,h/regionH);
    this.model.scale.set(scale);
    this.model.position.set((w-regionW*scale)/2-x*scale,(h-regionH*scale)/2-y*scale);
    // Cursor mapping follows the actual portrait crop and contain-fit margins.
    this.package.rig={image:{width:regionW,height:regionH},
      view:{gazeCenter:[regionW/2,portrait?regionH*.40:b.height*.16]}};
  }
  applyPose(){
    const values=this.rig.pose(this.pose,{voice:this.mouth,
      eyeOpen:this.eyeOpen*(this.expression==='halfLidded'?.72:1),
      breath:.5+Math.sin(this.time*1.55)*.3});
    for(const [id,value] of Object.entries(values))this.core.setParameterValueById(id,value);
    for(const [id,value] of Object.entries(this.appearance)){
      const p=this.rig.parameters.get(id);
      if(p&&Number.isFinite(value))this.core.setParameterValueById(id,Math.max(p.min,Math.min(p.max,value)));
    }
  }
  advanceStable(seconds){
    if(this.destroyed)return;
    const dt=Number.isFinite(seconds)?Math.max(0,Math.min(.1,seconds)):0;
    this.physicsSeconds=dt;
    this.time+=dt;this.eyeOpen=this.blink.update(dt);
    this.mouth+=(this.level-this.mouth)*(1-Math.exp(-dt*(this.level>this.mouth?24:18)));
    this.layout();
    this.model.update(Math.max(.001,dt*1000));
    this.renderer.render(this.stage);
  }
  setParameters(pose){this.pose={...this.pose,...pose};}
  getParameters(){return {...this.pose,mouthOpen:this.mouth,breath:.5+Math.sin(this.time*1.55)*.3};}
  setExpression(value){this.expression=value;}
  getExpression(){return {name:this.expression};}
  setVoiceLevel(value){this.level=Number.isFinite(value)?Math.max(0,Math.min(1,value)):0;}
  setSpeaking(value){if(!value)this.level=0;}
  stopLipSync(){this.level=0;this.mouth=0;}
  setAutoMotion(){}
  setAutoIdle(){}
  setTalkGain(){}
  setSwayGain(value){this.hair=value;}
  setFraming(value){this.framing=value==='full'?'full':'portrait';}
  setAppearance(values){this.appearance={...values};}
  createMotionPreview(pose){return new RigPreview(pose);}
  rigDiagnostics(){return {parameters:this.rig.parameters.size,drawables:this.core.getModel().drawables.count,
    physics:Boolean(this.internal.physics),hairOutputs:this.hairIds.size,
    physicsSteps:this.physicsClock?.steps??0,
    missing:this.rig.missing(),framing:this.framing,values:this.values};}
  destroy(){
    if(this.destroyed)return;
    this.destroyed=true;this.model.destroy({texture:true,baseTexture:true});
    this.stage.destroy();this.renderer.destroy(false);
  }
}
