import {drawingSize} from './render-quality.js';
import {Live2DRig,RigBlink} from './live2d-rig.js';
import {RigPreview} from './rig-preview.js';
import {Live2DPhysics} from './live2d-physics.js';
import {drawGlasses,glassesLayout,faceLayout,headPose,latticeWarp,pinToMesh,pinned,outfitPlacement,pictureGrid}
  from './accessories.js';

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
    const partNames=new Map((metadata[0].Parts??[]).map(p=>[p.Id,p.Name]));
    renderer=new PIXI.Renderer({view:canvas,backgroundAlpha:0,antialias:true,preserveDrawingBuffer:true});
    return new Live2DAvatar(canvas,renderer,model,PIXI,hairIds,metadata[1],partNames);
  }catch(error){model.destroy({texture:true,baseTexture:true});renderer?.destroy(false);throw error;}
}

const PORTRAIT_WIDTH=.78;

class Live2DAvatar {
  constructor(canvas,renderer,model,PIXI,hairIds,physicsDefinition,partNames=new Map()){
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
    // Accessories are rigged like an art mesh in her face's deformer: pinned to her face mesh at rest,
    // carried by it every frame. Drawn after her, like the blush, then her fringe is drawn again over
    // them, so it falls in front of the glasses.
    this.accessories={};this.glasses=new PIXI.Graphics();
    this.hairOver=this.findHairOver(partNames);
    this.nose=this.findParts(partNames,/^鼻|鼻子|nose/i);
    this.faceBind=this.bindFace(partNames);
    // An outfit is a picture laid over her body in place of her own clothes (see putOn).
    this.PIXI=PIXI;this.partNames=partNames;this.outfit=null;this.outfitBind=undefined;
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
    if(!this.renderOutfit())this.renderer.render(this.stage);
    if(this.wink>.01&&this.winkEye)this.renderWink();
    const blush=Math.max(0,Math.min(1,this.life?.cheek??0));
    if(blush>.02&&this.winkEye)this.renderBlush(blush);
    if(this.accessories.glasses?.on&&this.winkEye)this.renderGlasses();
  }
  // Both eyes in canvas pixels, from this frame's geometry.
  eyesOnCanvas(){
    const scale=this.model.scale.x,x=this.model.position.x,y=this.model.position.y;
    const boxes=this.winkEye.cheeks.map(c=>this.eyeBox(c.group));
    if(boxes.some(box=>!box))return null;
    return boxes.map(b=>({left:x+b.left*scale,right:x+b.right*scale,top:y+b.top*scale,bottom:y+b.bottom*scale}));
  }
  renderGlasses(){
    const options=this.accessories.glasses,eyes=this.eyesOnCanvas();
    let layout;
    if(this.faceBind){
      const turn=headPose(eyes,this.headPose());
      layout=faceLayout(this.faceBind.eyes,options.style,this.followFace(),{yaw:turn?.yaw??0,pitch:turn?.pitch??0});
    }else layout=glassesLayout(eyes,options.style,this.headPose());
    if(!drawGlasses(this.glasses,layout,options))return;
    this.renderer.render(this.glasses,{clear:false});
    if(this.hairOver.length)this.renderOnly(this.hairOver);
  }
  // Her face at rest, and a grid over her eyes pinned to its mesh: the glasses' warp deformer. Only the
  // face's big meshes (her skin), not the eyes, brows or mouth, which move on their own.
  bindFace(partNames){
    try{
      if(!this.winkEye)return null;
      const model=this.core.getModel(),drawables=model.drawables,parameters=model.parameters;
      const own=new Set([...this.winkEye.cheeks.flatMap(c=>c.group),...this.hairOver]);
      let face=this.findParts(partNames,/脸|臉|顔|顏|face/i).filter(i=>!own.has(i)&&drawables.indices[i]?.length>=3);
      const saved=Float32Array.from(parameters.values);
      parameters.values.set(parameters.defaultValues);
      this.core.update();
      const eyes=this.winkEye.cheeks.map(c=>this.eyeBox(c.group));
      const area=i=>{const b=this.eyeBox([i]);return b?(b.right-b.left)*(b.bottom-b.top):0;};
      const largest=Math.max(0,...face.map(area));
      face=face.filter(i=>area(i)>=largest*.25);
      const meshes=face.map(i=>({vertices:Float32Array.from(this.internal.getDrawableVertices(i)),indices:drawables.indices[i]}));
      parameters.values.set(saved);this.core.update();
      const rest=headPose(eyes);
      if(!face.length||!rest)return null;
      const half=rest.scale,box={left:rest.origin.x-2.2*half,top:rest.origin.y-1.1*half,width:4.4*half,height:2.4*half};
      const pins=Array.from({length:5},(_,row)=>Array.from({length:9},(_,column)=>
        pinToMesh({x:box.left+box.width*column/8,y:box.top+box.height*row/4},meshes)));
      return {face,eyes,box,pins};
    }catch(error){console.warn('Face binding unavailable:',error.message);return null;}
  }
  // Where a point of her face at rest is now, on the canvas.
  followFace(){
    const bind=this.faceBind,vertices=bind.face.map(i=>this.internal.getDrawableVertices(i));
    const warp=latticeWarp(bind.box,bind.pins.map(row=>row.map(pin=>pinned(pin,vertices))));
    const scale=this.model.scale.x,x=this.model.position.x,y=this.model.position.y;
    return point=>{const p=warp(point);return {x:x+p.x*scale,y:y+p.y*scale};};
  }
  // How her head is turned, for things she wears: her nose's position on screen (the turn is measured
  // from it) and her head's pitch (looking up or down).
  headPose(){
    const pose={};
    const box=this.nose.length?this.eyeBox(this.nose):null;
    if(box){
      const scale=this.model.scale.x;
      pose.nose={x:this.model.position.x+(box.left+box.right)/2*scale,y:this.model.position.y+(box.top+box.bottom)/2*scale};
    }
    if(this.rig.parameters.has('ParamAngleY'))
      pose.pitch=this.core.getParameterValueById('ParamAngleY')/30*.35;
    return pose;
  }
  // Drawables of the parts with matching names (Cubism part names), including nested parts.
  findParts(partNames,pattern){
    try{
      const model=this.core.getModel(),parts=model.parts,drawables=model.drawables,chosen=new Set();
      for(let i=0;i<parts.count;i++){
        for(let j=i,depth=0;j>=0&&depth<16;j=parts.parentIndices[j],depth++)
          if(pattern.test(partNames.get(parts.ids[j])??'')){chosen.add(i);break;}
      }
      return Array.from({length:drawables.count},(_,i)=>i).filter(i=>chosen.has(drawables.parentPartIndices[i]));
    }catch(error){console.warn('Part lookup unavailable:',error.message);return [];}
  }
  // Her fringe (前发, bangs…): drawn again over her glasses. Side locks hang behind the frame's edges.
  findHairOver(partNames){
    return this.findParts(partNames,/前发|前髮|刘海|瀏海|前髪|bang|fringe|front.?hair/i);
  }
  // Draws only these drawables over what is on the canvas (or a cleared one): every other one is made
  // transparent for this pass. Clipping masks still work, as they ignore opacity.
  renderOnly(indices,clear=false){
    const opacities=this.core.getModel().drawables.opacities,saved=Float32Array.from(opacities),keep=new Set(indices);
    for(let i=0;i<opacities.length;i++)if(!keep.has(i))opacities[i]=0;
    try{this.renderer.render(this.stage,{clear});}
    finally{opacities.set(saved);}
  }
  // Runs `read` with her at rest (every parameter at its default), then puts this frame back.
  atRest(read,changes={}){
    const parameters=this.core.getModel().parameters,saved=Float32Array.from(parameters.values);
    parameters.values.set(parameters.defaultValues);
    for(const [id,value] of Object.entries(changes))this.core.setParameterValueById(id,value);
    this.core.update();
    try{return read();}
    finally{parameters.values.set(saved);this.core.update();}
  }
  // What an outfit needs from her model, found once: her own clothes (hidden under it), where it goes in
  // the drawing order, her eyes at rest (to line the picture up) and her torso's meshes (to carry it).
  bindOutfit(){
    try{
      const drawables=this.core.getModel().drawables,mine=new Set([...this.hairOver,...(this.faceBind?.face??[])]);
      const clothes=this.findParts(this.partNames,
        /上衣|衣服|衣装|衣|盔甲|装饰|蝴蝶结|领|袖|裙|臂|手|cloth|outfit|shirt|dress|armou?r|sleeve|skirt|ribbon|bow|arm|hand/i)
        .filter(i=>!mine.has(i));
      let torso=this.findParts(this.partNames,/上衣|衣服|脖子锁骨|锁骨|身体|胴体|body|torso|chest|neck/i)
        .filter(i=>drawables.indices[i]?.length>=3);
      if(!clothes.length)return null;
      if(!torso.length)torso=clothes.filter(i=>drawables.indices[i]?.length>=3);
      const vertices=()=>torso.map(i=>Float32Array.from(this.internal.getDrawableVertices(i)));
      const rest=this.atRest(()=>({meshes:vertices(),eyes:this.winkEye?.cheeks.map(c=>this.eyeBox(c.group))}));
      // Her irises: what moves when she looks aside. Their centres at rest are her eyes.
      let irises=null;
      if(this.rig.parameters.has('ParamEyeBallX')){
        const ahead=this.atRest(()=>Array.from({length:drawables.count},(_,i)=>Float32Array.from(this.internal.getDrawableVertices(i))));
        const aside=this.atRest(()=>Array.from({length:drawables.count},(_,i)=>Float32Array.from(this.internal.getDrawableVertices(i))),{ParamEyeBallX:1});
        const moving=ahead.map((p,i)=>p.some((v,j)=>Math.abs(v-aside[i][j])>.5)?i:-1).filter(i=>i>=0&&!mine.has(i));
        const centre=i=>{const p=ahead[i];let x=0,y=0;for(let j=0;j<p.length;j+=2){x+=p[j];y+=p[j+1];}return {x:x/(p.length/2),y:y/(p.length/2)};};
        const points=moving.map(i=>({i,...centre(i)})).sort((a,b)=>a.x-b.x);
        let gap=0,split=0;
        for(let k=1;k<points.length;k++)if(points[k].x-points[k-1].x>gap){gap=points[k].x-points[k-1].x;split=k;}
        if(points.length>=2&&split){
          const box=group=>this.atRest(()=>this.eyeBox(group.map(p=>p.i)));
          irises=[points.slice(0,split),points.slice(split)].map(box).map(b=>b&&{x:(b.left+b.right)/2,y:(b.top+b.bottom)/2});
          if(irises.some(e=>!e))irises=null;
        }
      }
      if(!irises&&rest.eyes?.every(Boolean))
        irises=rest.eyes.map(b=>({x:(b.left+b.right)/2,y:(b.top+b.bottom)/2})).sort((a,b)=>a.x-b.x);
      if(!irises)return null;
      // What her artist drew above her top (her face, the hair over her shoulders) goes above the
      // outfit; what lies under her top (skin, back hair) goes under it.
      const order=drawables.renderOrders,hidden=new Set(clothes),top=clothes.filter(i=>torso.includes(i));
      const split=Math.min(...(top.length?top:clothes).map(i=>order[i]));
      // Under her clothes only her body and hair are kept: anything else there is more of her clothing,
      // whatever its part is called.
      const body=new Set(this.findParts(this.partNames,/脖子|锁骨|颈|身体|胴体|胸|腿|脚|发|髪|skin|body|neck|chest|leg|foot|feet|hair/i));
      const all=Array.from({length:drawables.count},(_,i)=>i).filter(i=>!hidden.has(i));
      const below=all.filter(i=>order[i]<split&&body.has(i)),above=all.filter(i=>order[i]>=split);
      return {irises,torso,meshes:rest.meshes.map((vertices,k)=>({vertices,indices:drawables.indices[torso[k]]})),
              below,above,hidden:drawables.count-below.length-above.length};
    }catch(error){console.warn('Outfits unavailable:',error.message);return null;}
  }
  // Puts on an outfit ({id, url, eyes, fit}) or takes it off (null).
  async putOn(spec){
    const key=spec?spec.id+JSON.stringify(spec.fit??{}):'';
    if(key===(this.outfit?.key??''))return;
    if(this.outfitBind===undefined)this.outfitBind=this.bindOutfit();
    const bind=this.outfitBind;
    if(!spec||!bind){this.takeOff();return;}
    let texture=this.outfit?.id===spec.id?this.outfit.texture:null;
    if(!texture){
      try{texture=await this.PIXI.Texture.fromURL(spec.url);}
      catch(error){console.warn('Outfit picture unavailable:',error.message);return;}
      if(this.destroyed){texture.destroy(true);return;}
    }
    const place=outfitPlacement(spec.eyes,bind.irises,spec.fit);
    if(!place)return;
    const grid=pictureGrid(texture.width,texture.height);
    const rest=grid.pixels.map(([u,v])=>place(u,v));
    // Her torso carries the picture: a coarse grid over it, pinned to her torso's meshes at rest.
    const xs=rest.map(p=>p.x),ys=rest.map(p=>p.y);
    const box={left:Math.min(...xs),top:Math.min(...ys),width:Math.max(...xs)-Math.min(...xs),height:Math.max(...ys)-Math.min(...ys)};
    const pins=Array.from({length:9},(_,row)=>Array.from({length:7},(_,column)=>
      pinToMesh({x:box.left+box.width*column/6,y:box.top+box.height*row/8},bind.meshes)));
    const mesh=new this.PIXI.SimpleMesh(texture,new Float32Array(rest.length*2),grid.uvs,grid.indices);
    if(this.outfit&&this.outfit.texture!==texture)this.outfit.texture.destroy(true);
    this.outfit?.mesh.destroy();
    this.outfit={key,id:spec.id,texture,mesh,rest,box,pins};
  }
  takeOff(){
    if(!this.outfit)return;
    this.outfit.mesh.destroy();this.outfit.texture.destroy(true);this.outfit=null;
  }
  // Her, in her outfit: what lies under her clothes, the outfit carried by her torso, then all above.
  // Only in the head-and-shoulders portrait, which is what an outfit picture shows.
  renderOutfit(){
    const outfit=this.outfit,bind=this.outfitBind;
    if(!outfit||!bind||this.framing!=='portrait')return false;
    const vertices=bind.torso.map(i=>this.internal.getDrawableVertices(i));
    const warp=latticeWarp(outfit.box,outfit.pins.map(row=>row.map(pin=>pinned(pin,vertices))));
    const scale=this.model.scale.x,x=this.model.position.x,y=this.model.position.y,points=outfit.mesh.vertices;
    outfit.rest.forEach((point,k)=>{const p=warp(point);points[k*2]=x+p.x*scale;points[k*2+1]=y+p.y*scale;});
    this.renderOnly(bind.below,true);
    this.renderer.render(outfit.mesh,{clear:false});
    this.renderOnly(bind.above);
    return true;
  }
  setAccessories(values){this.accessories={...values};this.putOn(values.outfit??null);}
  supportsAccessories(){return Boolean(this.winkEye);}
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
    hairOver:this.hairOver.length,nose:this.nose.length,face:this.faceBind?.face.length??0,
    outfit:this.outfitBind?{hidden:this.outfitBind.hidden,below:this.outfitBind.below.length,above:this.outfitBind.above.length,torso:this.outfitBind.torso.length,on:Boolean(this.outfit)}:null,
    physics:Boolean(this.internal.physics),hairOutputs:this.hairIds.size,
    physicsSteps:this.physicsClock?.steps??0,life:this.life?{state:this.life.state,zzz:this.life.zzz}:null,
    missing:this.rig.missing(),framing:this.framing,values:this.values};}
  destroy(){
    if(this.destroyed)return;
    this.destroyed=true;
    if(this.winkEye){this.winkEye.overlay.destroy({children:true});this.winkEye.blush.destroy({children:true});this.winkEye.target.destroy(true);}
    this.glasses.destroy();this.takeOff();
    this.model.destroy({texture:true,baseTexture:true});
    this.stage.destroy();this.renderer.destroy(false);
  }
}
