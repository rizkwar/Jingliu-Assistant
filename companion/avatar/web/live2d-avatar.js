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

const PORTRAIT_WIDTH=.78;

class Live2DAvatar {
  constructor(canvas,renderer,model,PIXI,hairIds,physicsDefinition){
    this.canvas=canvas;this.renderer=renderer;this.model=model;
    this.stage=new PIXI.Container();this.stage.addChild(model);
    this.internal=model.internalModel;this.core=this.internal.coreModel;
    const parameters=this.core.getModel().parameters;
    this.rig=new Live2DRig(Array.from(parameters.ids,(id,i)=>({id,
      min:parameters.minimumValues[i],max:parameters.maximumValues[i],default:parameters.defaultValues[i]})));
    this.pose={};this.expression='neutral';this.level=0;this.mouth=0;this.time=0;this.life=null;
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
      // The runtime restores saved parameters after each update; keep this frame's pose
      // so the wink's second render matches it exactly.
      this.frameValues=Float32Array.from(data.values);
    });
    this.wink=0;this.winkEye=this.findWinkEye(PIXI);
    // Advance once to initialize drawing geometry even if the user pauses immediately.
    this.advanceStable(.001);
  }
  // This rig closes both eyelids from one parameter. A wink is composited instead: a
  // second, eyes-closed render shows through a soft mask over the visible eye only.
  // Closing the eyes moves no geometry outside the eyes, so the blend has no seams.
  findWinkEye(PIXI){
    try{
      const id=['ParamEyeLOpen','ParamEyeROpen'].filter(name=>this.rig.parameters.has(name));
      if(!id.length)return null;
      const data=this.core.getModel().drawables,shape=open=>{
        for(const name of id)this.core.setParameterValueById(name,open);
        this.core.update();
        return Array.from({length:data.count},(_,i)=>Float32Array.from(this.internal.getDrawableVertices(i)));
      };
      const opened=shape(1),closed=shape(0);
      const moving=[];
      for(let i=0;i<data.count;i++){
        let delta=0,x=0;
        for(let j=0;j<opened[i].length;j+=2){delta=Math.max(delta,Math.abs(opened[i][j+1]-closed[i][j+1]));x+=opened[i][j];}
        if(delta>.5)moving.push({index:i,x:x/(opened[i].length/2)});
      }
      if(moving.length<2)return null;
      // Two clusters, one per eye. Her left eye (screen right) is clear of her fringe.
      const xs=moving.map(m=>m.x).sort((a,b)=>a-b);
      let gap=0,split=xs[0];
      for(let i=1;i<xs.length;i++)if(xs[i]-xs[i-1]>gap){gap=xs[i]-xs[i-1];split=(xs[i]+xs[i-1])/2;}
      const drawables=moving.filter(m=>m.x>split).map(m=>m.index);
      if(!drawables.length)return null;
      const target=PIXI.RenderTexture.create({width:2,height:2});
      const mask=document.createElement('canvas');mask.width=mask.height=128;
      const paint=mask.getContext('2d'),glow=paint.createRadialGradient(64,64,26,64,64,64);
      glow.addColorStop(0,'rgba(255,255,255,1)');glow.addColorStop(1,'rgba(255,255,255,0)');
      paint.fillStyle=glow;paint.fillRect(0,0,128,128);
      const overlay=new PIXI.Container(),sprite=new PIXI.Sprite(target),shade=new PIXI.Sprite(PIXI.Texture.from(mask));
      sprite.mask=shade;overlay.addChild(sprite,shade);
      // The painted-in blush never changes (ParamCheek moves no pixel on this rig), so a
      // soft pink glow under each eye adds a visible blush when an expression asks for one.
      const pink=document.createElement('canvas');pink.width=pink.height=128;
      const tint=pink.getContext('2d'),warm=tint.createRadialGradient(64,64,0,64,64,64);
      warm.addColorStop(0,'rgba(255,112,138,1)');warm.addColorStop(.55,'rgba(255,128,150,.55)');warm.addColorStop(1,'rgba(255,140,160,0)');
      tint.fillStyle=warm;tint.fillRect(0,0,128,128);
      const blush=new PIXI.Container(),texture=PIXI.Texture.from(pink);
      const cheeks=[drawables,moving.filter(m=>m.x<=split).map(m=>m.index)].map(group=>{
        const glow=new PIXI.Sprite(texture);blush.addChild(glow);return {group,glow};});
      return {drawables,ids:id,target,overlay,shade,sprite,blush,cheeks};
    }catch(error){console.warn('Wink compositing unavailable:',error.message);return null;}
  }
  eyeBox(group){
    let left=Infinity,right=-Infinity,top=Infinity,bottom=-Infinity;
    for(const i of group){
      const p=this.internal.getDrawableVertices(i);
      for(let j=0;j<p.length;j+=2){left=Math.min(left,p[j]);right=Math.max(right,p[j]);top=Math.min(top,p[j+1]);bottom=Math.max(bottom,p[j+1]);}
    }
    return [left,right,top,bottom].every(Number.isFinite)?{left,right,top,bottom}:null;
  }
  renderBlush(amount){
    const scale=this.model.scale.x;
    for(const [index,{group,glow}] of this.winkEye.cheeks.entries()){
      const box=this.eyeBox(group);
      if(!box){glow.visible=false;continue;}
      // Below and slightly outside each eye; the lower lid barely moves when eyes close.
      const width=box.right-box.left,outward=(index===0?1:-1)*width*.1;
      const cx=this.model.position.x+((box.left+box.right)/2+outward)*scale;
      const cy=this.model.position.y+(box.bottom+width*.42)*scale;
      glow.visible=true;glow.width=width*1.25*scale;glow.height=width*.62*scale;
      glow.position.set(cx-glow.width/2,cy-glow.height/2);glow.alpha=.34*amount;
    }
    this.renderer.render(this.winkEye.blush,{clear:false});
  }
  renderWink(){
    const eye=this.winkEye,core=this.core;
    const box=this.eyeBox(eye.drawables);
    if(!box)return;
    const {left,right,top,bottom}=box;
    const w=this.canvas.width,h=this.canvas.height;
    if(eye.target.width!==w||eye.target.height!==h)eye.target.resize(w,h);
    // Same frame, same physics: only the eyelids change for the second render.
    if(!this.frameValues)return;
    core.getModel().parameters.values.set(this.frameValues);
    const closed=this.eyeOpenValue*(1-this.wink);
    for(const id of eye.ids)core.setParameterValueById(id,closed);
    core.update();
    this.renderer.render(this.stage,{renderTexture:eye.target,clear:true});
    const scale=this.model.scale.x,cx=this.model.position.x+(left+right)/2*scale,cy=this.model.position.y+(top+bottom)/2*scale;
    const rx=(right-left)*scale*.95+8,ry=(bottom-top)*scale*1.6+10;
    eye.shade.position.set(cx-rx,cy-ry);eye.shade.width=rx*2;eye.shade.height=ry*2;
    this.renderer.render(eye.overlay,{clear:false});
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
    const {width:regionW,height:regionH}=this.region();
    const x=b.left+b.width/2-regionW/2,y=b.top-b.height*.025;
    const scale=Math.min(w/regionW,h/regionH);
    this.model.scale.set(scale);
    this.model.position.set((w-regionW*scale)/2-x*scale,(h-regionH*scale)/2-y*scale);
    // Cursor mapping follows the actual portrait crop and contain-fit margins.
    this.package.rig={image:{width:regionW,height:regionH},
      view:{gazeCenter:[regionW/2,portrait?regionH*.40:b.height*.16]}};
  }
  // The part of the model in view. A head-and-shoulders portrait is narrow: her hair and
  // shoulders fill it, so the desktop window (which follows aspect()) has no empty sides.
  region(){
    const b=this.bodyBounds;
    if(this.framing!=='portrait')return {width:b.width*1.12,height:b.height*1.08};
    const height=b.height*.27;
    return {width:Math.min(b.width*1.05,height*PORTRAIT_WIDTH),height};
  }
  aspect(){const r=this.region();return r.width/r.height;}
  applyPose(){
    const life=this.life;
    const eyeOpen=(life?1-life.blink:this.eyeOpen)*(this.expression==='halfLidded'?.72:1);
    const values=this.rig.pose(this.pose,{voice:this.mouth,eyeOpen,
      breath:life?life.breath:.5+Math.sin(this.time*1.55)*.3});
    if(life)this.applyLife(values,life,eyeOpen);
    for(const [id,value] of Object.entries(values))this.core.setParameterValueById(id,value);
    for(const [id,value] of Object.entries(this.appearance)){
      const p=this.rig.parameters.get(id);
      if(p&&Number.isFinite(value))this.core.setParameterValueById(id,Math.max(p.min,Math.min(p.max,value)));
    }
  }
  // Life offsets go in before physics, so hair and ribbons follow a yawn or a doze.
  applyLife(values,life,eyeOpen){
    const parameter=id=>this.rig.parameters.get(id);
    const put=(id,value)=>{const p=parameter(id);if(p)values[id]=Math.max(p.min,Math.min(p.max,value));};
    const add=(id,delta)=>{const p=parameter(id);if(p)put(id,(values[id]??p.default)+delta);};
    add('ParamAngleX',life.angleX);add('ParamAngleY',life.angleY);add('ParamAngleZ',life.angleZ);
    add('ParamBodyAngleX',life.bodyX);add('ParamBodyAngleY',life.bodyY);
    add('ParamEyeBallX',life.gazeX);add('ParamEyeBallY',life.gazeY);
    put('Param114',life.lift);put('Param13',life.arms);put('Param8',life.shoulders);
    const open=Math.max(0,Math.min(1.45,eyeOpen*(1+life.eyes)));
    for(const id of ['ParamEyeLOpen','ParamEyeROpen'])put(id,open);
    for(const id of ['ParamEyeLSmile','ParamEyeRSmile'])put(id,life.eyeSmile);
    this.wink=this.winkEye?Math.max(0,Math.min(1,life.wink??0)):0;
    this.eyeOpenValue=open;
    // Playback lip-sync keeps priority: an expression only fills the remaining opening.
    const mouth=parameter('ParamMouthOpenY');
    if(mouth){const voice=values[mouth.id]??mouth.min;put(mouth.id,voice+life.mouthOpen*(mouth.max-voice));}
    put('ParamMouthForm',life.mouthForm);put('ParamCheek',life.cheek);
    add('ParamBrowLY',life.browY);add('ParamBrowRY',life.browY);
    put('ParamBrowLAngle',life.browAngle);put('ParamBrowRAngle',life.browAngle);
  }
  // A point beside the crown, as a fraction of the canvas: where sleep "Zzz" drift.
  headAnchor(){
    const b=this.bodyBounds,scale=this.model.scale.x;
    const x=this.model.position.x+(b.left+b.width*.67)*scale,y=this.model.position.y+(b.top+b.height*.075)*scale;
    return {x:x/this.canvas.width,y:y/this.canvas.height,size:b.height*scale/this.canvas.height};
  }
  // Where petting counts: from the crown of her hair down to her eyes, as canvas fractions.
  headRegion(){
    const b=this.bodyBounds,scale=this.model.scale.x;
    const boxes=(this.winkEye?.cheeks??[]).map(c=>this.eyeBox(c.group)).filter(Boolean);
    let cx,eyes,half;
    if(boxes.length===2){
      const centers=boxes.map(e=>(e.left+e.right)/2);
      cx=(centers[0]+centers[1])/2;half=Math.abs(centers[0]-centers[1])*1.25;
      eyes=Math.max(...boxes.map(e=>e.bottom));
    }else{cx=b.left+b.width/2;half=b.width*.2;eyes=b.top+b.height*.1;}
    const x=v=>(this.model.position.x+v*scale)/this.canvas.width,y=v=>(this.model.position.y+v*scale)/this.canvas.height;
    return {left:x(cx-half),right:x(cx+half),top:y(b.top)-.04,bottom:y(eyes)};
  }
  setLife(layer){this.life=layer;}
  advanceStable(seconds){
    if(this.destroyed)return;
    const dt=Number.isFinite(seconds)?Math.max(0,Math.min(.1,seconds)):0;
    this.physicsSeconds=dt;
    this.time+=dt;this.eyeOpen=this.blink.update(dt);
    this.mouth+=(this.level-this.mouth)*(1-Math.exp(-dt*(this.level>this.mouth?24:18)));
    this.layout();
    this.model.update(Math.max(.001,dt*1000));
    this.renderer.render(this.stage);
    if(this.wink>.01&&this.winkEye)this.renderWink();
    const blush=Math.max(0,Math.min(1,this.life?.cheek??0));
    if(blush>.02&&this.winkEye)this.renderBlush(blush);
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
    physicsSteps:this.physicsClock?.steps??0,life:this.life?{state:this.life.state,zzz:this.life.zzz}:null,
    missing:this.rig.missing(),framing:this.framing,values:this.values};}
  destroy(){
    if(this.destroyed)return;
    this.destroyed=true;
    if(this.winkEye){this.winkEye.overlay.destroy({children:true});this.winkEye.blush.destroy({children:true});this.winkEye.target.destroy(true);}
    this.model.destroy({texture:true,baseTexture:true});
    this.stage.destroy();this.renderer.destroy(false);
  }
}
