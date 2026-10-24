import {drawingSize} from './render-quality.js';
import {RigBlink} from './live2d-rig.js';
import {RigPreview} from './rig-preview.js';
import {clamp,grid,projectPoint,StrandSpring,REST} from './layered-rig.js';

const SIZE=1254;
const sheet=()=>{const c=document.createElement('canvas');c.width=c.height=SIZE;return c;};
function image(url){return new Promise((resolve,reject)=>{
  const img=new Image();img.onload=()=>resolve(img);img.onerror=()=>reject(new Error('Missing layered artwork'));img.src=url;
});}
const polygon=(points)=>new Path2D('M'+points.map(p=>p.join(',')).join('L')+'Z');
const FRINGE=polygon([[421,570],[393,496],[445,350],[591,235],[655,262],[711,433],[664,570],[580,659],[499,712]]);
const SIDE_LEFT=new Path2D('M592,240 Q467,299 412,432 Q367,536 420,643 Q447,678 534,698 Q469,659 458,604 Q412,507 502,375 Q544,308 592,240 Z');
const SIDE_RIGHT=new Path2D('M701,257 Q827,326 867,450 Q904,588 813,671 L728,708 Q791,661 802,585 Q834,459 751,336 Z');
const BANG_CENTER=new Path2D('M648,252 Q713,309 691,454 Q670,580 554,653 Q631,566 627,468 Q651,347 648,252 Z');
const LEFT=polygon([[365,650],[530,650],[540,850],[510,950],[530,1010],[480,1120],[455,1170],[505,1220],[480,1254],[350,1254],[315,1140],[370,1040],[400,950],[405,840],[360,740]]);
const RIGHT=polygon([[785,650],[920,650],[980,880],[1030,1050],[985,1200],[930,1254],[760,1254],[770,1170],[860,1070],[850,1020],[795,970],[760,900],[790,800]]);
const FACE= new Path2D('M380,180 L900,180 L900,649 L819,674 Q802,717 778,740 Q716,791 641,804 Q615,806 550,762 Q505,731 477,682 L395,667 Z');
const NECK=new Path2D('M552,750 L721,750 L719,791 Q674,820 640,857 Q600,823 552,793 Z');
const EARRING=new Path2D('M467,672 Q478,673 482,685 Q482,695 474,700 L478,710 L475,721 Q487,733 482,757 Q477,779 469,778 Q455,773 455,751 Q452,734 463,720 L459,709 L464,699 Q456,692 459,683 Z');

function shader(gl,type,source){
  const s=gl.createShader(type);gl.shaderSource(s,source);gl.compileShader(s);
  if(!gl.getShaderParameter(s,gl.COMPILE_STATUS)){gl.deleteShader(s);throw new Error('Layered shader failed');}return s;
}
class CutoutRenderer {
  constructor(canvas){
    this.canvas=canvas;
    const gl=this.gl=canvas.getContext('webgl',{alpha:true,antialias:true,premultipliedAlpha:true,preserveDrawingBuffer:true});
    if(!gl)throw new Error('WebGL unavailable');
    const program=this.program=gl.createProgram();
    const shaders=[shader(gl,gl.VERTEX_SHADER,`attribute vec2 a_position;attribute vec2 a_uv;
      uniform vec2 u_size;uniform float u_scale;uniform vec2 u_offset;varying vec2 v_uv;
      void main(){vec2 p=(a_position*u_scale+u_offset)/u_size;gl_Position=vec4(p.x*2.-1.,1.-p.y*2.,0.,1.);v_uv=a_uv;}`),
      shader(gl,gl.FRAGMENT_SHADER,`precision mediump float;uniform sampler2D u_texture;uniform float u_opacity;varying vec2 v_uv;
      void main(){gl_FragColor=texture2D(u_texture,v_uv)*u_opacity;}`)];
    shaders.forEach(s=>gl.attachShader(program,s));gl.linkProgram(program);shaders.forEach(s=>gl.deleteShader(s));
    if(!gl.getProgramParameter(program,gl.LINK_STATUS))throw new Error('Layered program failed');
    gl.useProgram(program);this.locations=Object.fromEntries(['u_size','u_scale','u_offset','u_texture','u_opacity'].map(n=>[n,gl.getUniformLocation(program,n)]));
    this.position=gl.getAttribLocation(program,'a_position');this.uv=gl.getAttribLocation(program,'a_uv');
    gl.enable(gl.BLEND);gl.blendFunc(gl.ONE,gl.ONE_MINUS_SRC_ALPHA);gl.pixelStorei(gl.UNPACK_PREMULTIPLY_ALPHA_WEBGL,true);
    this.layers=[];
  }
  layer(name,canvas,definition,bounds=[0,0,SIZE,SIZE]){
    const gl=this.gl,mesh=grid(bounds,definition.spacing??18),data=new Float32Array(mesh.points.length*4);
    const x0=mesh.points[0][0],y0=mesh.points[0][1],[x1,y1]=mesh.points.at(-1);
    const crop=document.createElement('canvas');crop.width=x1-x0;crop.height=y1-y0;
    mesh.points.forEach(([x,y],i)=>{data[i*4+2]=(x-x0)/crop.width;data[i*4+3]=(y-y0)/crop.height;});
    const layer={name,...definition,...mesh,data,crop,x0,y0,art:canvas,opacity:1,texture:gl.createTexture(),vertices:gl.createBuffer(),elements:gl.createBuffer(),spring:new StrandSpring(definition.frequency??1.3),swing:0};
    gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER,layer.elements);gl.bufferData(gl.ELEMENT_ARRAY_BUFFER,mesh.indices,gl.STATIC_DRAW);
    gl.bindTexture(gl.TEXTURE_2D,layer.texture);
    gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MIN_FILTER,gl.LINEAR);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MAG_FILTER,gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_S,gl.CLAMP_TO_EDGE);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_T,gl.CLAMP_TO_EDGE);
    this.upload(layer,canvas);this.layers.push(layer);return layer;
  }
  upload(layer,canvas){
    const gl=this.gl,c=layer.crop,g=c.getContext('2d');g.clearRect(0,0,c.width,c.height);
    g.drawImage(canvas,layer.x0,layer.y0,c.width,c.height,0,0,c.width,c.height);
    gl.bindTexture(gl.TEXTURE_2D,layer.texture);gl.texImage2D(gl.TEXTURE_2D,0,gl.RGBA,gl.RGBA,gl.UNSIGNED_BYTE,c);
  }
  render(pose,breath,mouth){
    const gl=this.gl,c=this.canvas,r=c.getBoundingClientRect();
    const [w,h]=drawingSize(r.width,r.height,devicePixelRatio,c.dataset.renderQuality!=='balanced');
    if(c.width!==w||c.height!==h){c.width=w;c.height=h;}gl.viewport(0,0,w,h);
    gl.clearColor(0,0,0,0);gl.clear(gl.COLOR_BUFFER_BIT);gl.useProgram(this.program);
    const scale=Math.min(w/SIZE,h/SIZE);
    gl.uniform2f(this.locations.u_size,w,h);gl.uniform1f(this.locations.u_scale,scale);
    gl.uniform2f(this.locations.u_offset,(w-SIZE*scale)/2,(h-SIZE*scale)/2);gl.uniform1i(this.locations.u_texture,0);
    for(const layer of this.layers){
      if(layer.opacity<.001)continue;
      layer.points.forEach(([x,y],i)=>{const p=projectPoint(x,y,layer,pose,layer.swing,breath,mouth);layer.data[i*4]=p[0];layer.data[i*4+1]=p[1];});
      gl.bindTexture(gl.TEXTURE_2D,layer.texture);gl.bindBuffer(gl.ARRAY_BUFFER,layer.vertices);gl.bufferData(gl.ARRAY_BUFFER,layer.data,gl.DYNAMIC_DRAW);
      gl.uniform1f(this.locations.u_opacity,layer.opacity);
      gl.enableVertexAttribArray(this.position);gl.vertexAttribPointer(this.position,2,gl.FLOAT,false,16,0);
      gl.enableVertexAttribArray(this.uv);gl.vertexAttribPointer(this.uv,2,gl.FLOAT,false,16,8);
      gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER,layer.elements);gl.drawElements(gl.TRIANGLES,layer.indices.length,gl.UNSIGNED_SHORT,0);
    }
  }
  destroy(){const gl=this.gl;for(const l of this.layers){gl.deleteTexture(l.texture);gl.deleteBuffer(l.vertices);gl.deleteBuffer(l.elements);}gl.deleteProgram(this.program);this.layers=[];}
}

const oval=(x,y,cx,cy,rx,ry)=>clamp((1-Math.hypot((x-cx)/rx,(y-cy)/ry))/.22,0,1);
const FEATURES={
  'eye-left':[529,594,91,47],'eye-right':[740,583,91,48],
  'brow-left':[526,555,75,19],'brow-right':[733,531,76,20],
  nose:[633,660,33,39],mouth:[635,720,65,38],
};
function eyeOpening(e){
  const path=new Path2D();
  e.top.forEach((y,j)=>{const x=e.x0+(e.x1-e.x0)*j/(e.top.length-1);j?path.lineTo(x,y):path.moveTo(x,y);});
  for(let j=e.bot.length-1;j>=0;j--)path.lineTo(e.x0+(e.x1-e.x0)*j/(e.bot.length-1),e.bot[j]);
  path.closePath();return path;
}

// Fill removed feature drawings from their surrounding skin colors. A constant
// flesh-colored patch produces visible oval stamps when a feature moves.
function healedSkin(original,alpha,cuts,ctx){
  const count=SIZE*SIZE,valid=new Uint8Array(count),unknown=[],rgb=new Float32Array(count*3);
  let r=0,g=0,b=0,n=0;
  for(let i=0;i<count;i++){
    const p=i*4,q=i*3;rgb[q]=original[p];rgb[q+1]=original[p+1];rgb[q+2]=original[p+2];
    if(alpha.data[p+3]>190&&original[p+3]>190){
      valid[i]=1;
      if(cuts[i]>.001)unknown.push(i);
      else {r+=original[p];g+=original[p+1];b+=original[p+2];n++;}
    }
  }
  for(const i of unknown){const p=i*3;rgb[p]=r/n;rgb[p+1]=g/n;rgb[p+2]=b/n;}
  for(let iteration=0;iteration<160;iteration++)for(const i of unknown){
    let sr=0,sg=0,sb=0,total=0;
    for(const j of [i-1,i+1,i-SIZE,i+SIZE])if(valid[j]){
      sr+=rgb[j*3];sg+=rgb[j*3+1];sb+=rgb[j*3+2];total++;
    }
    if(total){const p=i*3;rgb[p]=sr/total;rgb[p+1]=sg/total;rgb[p+2]=sb/total;}
  }
  const result=ctx.createImageData(SIZE,SIZE);
  for(let i=0;i<count;i++){
    const p=i*4,q=i*3,w=cuts[i];
    for(let k=0;k<3;k++)result.data[p+k]=original[p+k]*(1-w)+rgb[q+k]*w;
    result.data[p+3]=alpha.data[p+3]*original[p+3]/255;
  }
  const canvas=sheet();canvas.getContext('2d').putImageData(result,0,0);return canvas;
}

// Cutouts use the existing calibrated hair mask. Runtime compositing retains the
// source pixels; underpainting is only exposed where a moving part uncovers it.
function prepare(images,manifest){
  const probe=sheet(),ctx=probe.getContext('2d',{willReadFrequently:true});
  ctx.drawImage(images.hairmask,0,0,SIZE,SIZE);const hair=ctx.getImageData(0,0,SIZE,SIZE).data;
  ctx.clearRect(0,0,SIZE,SIZE);ctx.drawImage(images.source,0,0,SIZE,SIZE);const original=ctx.getImageData(0,0,SIZE,SIZE).data;
  const hairNames=['back-left','back-right','crown','bang-left','bang-center','bang-right','side-left','side-right','lock-left','lock-right'];
  const names=[...hairNames,'skin','body-original','earring',...Object.keys(FEATURES)];
  const masks=Object.fromEntries(names.map(n=>[n,ctx.createImageData(SIZE,SIZE)]));
  const cuts=new Float32Array(SIZE*SIZE);
  const apertures=manifest.eyes.map(eyeOpening);
  for(let y=0;y<SIZE;y++)for(let x=0;x<SIZE;x++){
    const i=(y*SIZE+x)*4,alpha=original[i+3];if(!alpha)continue;
    // A narrow threshold avoids the wide glow of the physics weight mask.
    let amount=clamp((hair[i]-100)/55,0,1);
    // The old mask is a soft physics weight, not an exact art separation.
    // Repair its missed blue fringe pixels without classifying warm skin as hair.
    if(y<755&&original[i+2]>original[i]+18&&original[i+2]>original[i+1]+5)amount=1;
    if(original[i]>original[i+2]+15)amount=0;
    if(hair[i]<240&&Math.max(original[i],original[i+1],original[i+2])<110)amount=0;
    let part;
    if(y<700&&ctx.isPointInPath(BANG_CENTER,x+.5,y+.5))part='bang-center';
    else if(y<720&&ctx.isPointInPath(FRINGE,x+.5,y+.5))part=x<625?'bang-left':'bang-right';
    else if(y<760&&ctx.isPointInPath(SIDE_LEFT,x+.5,y+.5))part='side-left';
    else if(y<760&&ctx.isPointInPath(SIDE_RIGHT,x+.5,y+.5))part='side-right';
    else if(y<690)part='crown';
    else if(ctx.isPointInPath(LEFT,x+.5,y+.5))part='lock-left';
    else if(ctx.isPointInPath(RIGHT,x+.5,y+.5))part='lock-right';
    else part=x<632?'back-left':'back-right';
    const gem=((x-471)/11.5)**2+((y-747)/26)**2<1;
    const earring=ctx.isPointInPath(EARRING,x+.5,y+.5)&&(gem||original[i]>original[i+2]+12);
    // The old physics mask cuts a larger hole around this accessory. Remove
    // every original fragment there, not just the new pendant matte; otherwise
    // the leftover blue/white edge moves with the hair and looks duplicated.
    const accessoryHole=((x-471)/29)**2+((y-731)/59)**2<1;
    if(accessoryHole){
      if(earring)masks.earring.data[i+3]=255;
      continue;
    }
    if(earring)amount=0;
    masks[part].data[i+3]=Math.round(amount*255);
    const neck=x>550&&x<725&&y<860&&original[i]>original[i+1]*1.07&&original[i]>140&&original[i+2]>original[i]*.65;
    if(earring)masks.earring.data[i+3]=Math.round((1-amount)*255);
    else if(ctx.isPointInPath(FACE,x+.5,y+.5)){
      const skin=1-amount;
      let cut=0;
      for(const [name,[cx,cy,rx,ry]] of Object.entries(FEATURES)){
        if(Math.abs(x-cx)>rx||Math.abs(y-cy)>ry)continue;
        const w=oval(x,y,cx,cy,rx,ry);
        const brow=name.startsWith('brow');
        const r=original[i],g=original[i+1],b=original[i+2];
        const gray=r<205&&g<205&&b<210&&Math.abs(r-g)<32&&b-r<25;
        const red=clamp((r-g-28)/18,0,1),highlight=clamp(Math.min((g-232)/12,(b-218)/12),0,1);
        let ink;
        if(brow)ink=gray?1:0;
        else if(name.startsWith('eye')){
          const inside=ctx.isPointInPath(apertures[name==='eye-left'?0:1],x+.5,y+.5);
          const dark=b<=r+25?clamp((205-Math.max(r,g,b))/45,0,1):0;
          ink=inside?1:Math.max(dark,red*clamp((190-g)/45,0,1)*clamp((180-b)/35,0,1));
        }else ink=Math.max(clamp((r-g-37)/18,0,1),highlight);
        cut=Math.max(cut,w*ink);
        masks[name].data[i+3]=Math.round(skin*w*ink*255);
      }
      masks.skin.data[i+3]=Math.round(skin*255);cuts[y*SIZE+x]=cut;
    }
    else if(!neck)masks['body-original'].data[i+3]=Math.round((1-amount)*255);
  }
  // Small overlaps hide shared cuts while the individual bang meshes deform.
  // Intersect expansion with the original hair matte to retain its silhouette.
  const allHair=ctx.createImageData(SIZE,SIZE);
  for(const name of hairNames)for(let i=3;i<allHair.data.length;i+=4)allHair.data[i]=Math.min(255,allHair.data[i]+masks[name].data[i]);
  for(const name of hairNames){
    if(name==='crown'||name.startsWith('back'))continue;
    const c=sheet(),g=c.getContext('2d');g.putImageData(masks[name],0,0);
    const b=sheet(),bg=b.getContext('2d',{willReadFrequently:true});bg.filter='blur(4px)';bg.drawImage(c,0,0);
    const expanded=bg.getImageData(0,0,SIZE,SIZE);
    for(let i=3;i<expanded.data.length;i+=4)expanded.data[i]=Math.min(1,expanded.data[i]/10)*allHair.data[i];
    masks[name]=expanded;
  }
  const masked=(img,mask)=>{
    const c=sheet(),g=c.getContext('2d'),m=sheet();m.getContext('2d').putImageData(mask,0,0);
    g.drawImage(img,0,0,SIZE,SIZE);g.globalCompositeOperation='destination-in';g.drawImage(m,0,0);g.globalCompositeOperation='source-over';return c;
  };
  const parts=Object.fromEntries(names.map(n=>[n,masked(images.source,masks[n])]));
  parts.skin=healedSkin(original,masks.skin,cuts,ctx);
  const plate=sheet(),p=plate.getContext('2d');p.drawImage(images.underpaint,...manifest.underpaintOffset,SIZE,SIZE);
  // Hidden face does not carry a second set of eyes or a mouth.
  const cover=(x,y,rx,ry)=>{
    p.save();p.translate(x,y);p.scale(rx,ry);
    const g=p.createRadialGradient(0,0,.35,0,0,1);
    g.addColorStop(0,'#f9d8c4');g.addColorStop(.7,'#f9d8c4');g.addColorStop(1,'#f9d8c400');
    p.fillStyle=g;p.fillRect(-1,-1,2,2);p.restore();
  };
  // These areas remain covered by original skin/eye drawings at rest.
  cover(520,546,105,76);cover(742,531,105,84);
  cover(520,589,96,64);cover(742,583,96,64);cover(633,656,45,50);cover(635,719,68,38);
  const face=sheet(),f=face.getContext('2d');f.save();f.clip(FACE);f.drawImage(plate,0,0);f.drawImage(parts.skin,0,0);f.restore();
  const torso=sheet(),t=torso.getContext('2d');t.drawImage(plate,0,0);t.clearRect(0,0,SIZE,807);
  t.globalCompositeOperation='destination-out';t.fill(NECK);t.globalCompositeOperation='source-over';
  t.drawImage(parts['body-original'],0,0);
  const neck=sheet(),n=neck.getContext('2d');
  const color=p.getImageData(630,824,1,1).data;
  const shade=n.createLinearGradient(0,750,0,858);
  shade.addColorStop(0,`rgb(${color[0]*.98},${color[1]*.98},${color[2]*.98})`);
  shade.addColorStop(1,`rgb(${color[0]},${color[1]},${color[2]})`);
  // A neck surface must not carry the frontal painting's chin outline. Leaving
  // that outline on it would produce a second chin when the face looks up.
  n.fillStyle=shade;n.fill(NECK);
  const backing=sheet(),b=backing.getContext('2d');b.drawImage(images.backhair,0,0,SIZE,SIZE);
  // Keep the backing inside the approved silhouette, so generated edge wisps
  // cannot appear beside the original crown or shoulders.
  b.globalCompositeOperation='destination-in';b.drawImage(images.source,17,12,SIZE-34,SIZE-12);
  // Complete the hidden left brow from the original right brow's paint, so it
  // can emerge naturally when the covering bang moves. No extra face is drawn.
  const leftBrow=parts['brow-left'].getContext('2d');leftBrow.save();leftBrow.translate(1264,22);leftBrow.scale(-1,1);
  leftBrow.drawImage(parts['brow-right'],0,0);leftBrow.restore();
  const closed=[];
  for(let eye=0;eye<2;eye++){
    const c=sheet(),g=c.getContext('2d'),name=`eyes_closed_${eye}`;g.drawImage(images[name],...manifest.rects[name]);
    const pixels=g.getImageData(0,0,SIZE,SIZE);
    for(let j=0;j<pixels.data.length;j+=4){const [r,gg,b]=pixels.data.subarray(j,j+3);
      if(Math.max(r,gg,b)>170||r<gg*1.08||b>r*1.2)pixels.data[j+3]=0;
    }
    g.putImageData(pixels,0,0);closed.push(c);
  }
  const mouthSprites={};
  for(const name of ['mouth_a','mouth_a_half','mouth_i']){
    const c=sheet(),g=c.getContext('2d'),rect=manifest.rects[name];g.drawImage(images[name],...rect);
    const pixels=g.getImageData(...rect);
    for(let j=0;j<pixels.data.length;j+=4){
      const r=pixels.data[j],gg=pixels.data[j+1],b=pixels.data[j+2];
      const ink=Math.max(clamp((r-gg-37)/18,0,1),clamp(Math.min((gg-232)/12,(b-218)/12),0,1),
        clamp((130-Math.max(r,gg,b))/35,0,1));
      pixels.data[j+3]*=ink;
    }
    g.putImageData(pixels,rect[0],rect[1]);mouthSprites[name]=c;
  }
  return {...parts,face,torso,neck,backing,closed,mouthSprites};
}

export async function loadLayeredAvatar(canvas,url){
  const response=await fetch(url);if(!response.ok)throw new Error('Missing layered rig');
  const manifest=await response.json();
  if(manifest.format!=='assistant-layered'||manifest.version!==1)throw new Error('Unsupported layered rig');
  const base=new URL(url,location.href);
  const images=Object.fromEntries(await Promise.all(Object.entries(manifest.textures).map(async([key,path])=>[key,await image(new URL(path,base))])));
  const parts=prepare(images,manifest),renderer=new CutoutRenderer(canvas);
  try{return new LayeredAvatar(renderer,images,manifest,parts);}catch(e){renderer.destroy();throw e;}
}

class LayeredAvatar {
  constructor(renderer,images,manifest,parts){
    this.renderer=renderer;this.images=images;this.manifest=manifest;this.parts=parts;
    this.pose={...REST};this.expression='neutral';this.level=this.mouth=this.time=0;this.hair=.45;
    this.blink=new RigBlink();this.eyeOpen=1;this.destroyed=false;this.velocity=0;this.lastAngle=0;
    this.package={rig:{image:{width:SIZE,height:SIZE},view:{gazeCenter:[632,590]}}};
    const add=(n,part,type,extra={},bounds)=>renderer.layer(n,parts[part],{type,...extra},bounds);
    add('Hair underpainting','backing','hair',{root:590,tip:1254,frequency:1.15});
    add('Back hair left','back-left','hair',{root:690,tip:1254,frequency:1.15},[0,650,635,604]);
    add('Back hair right','back-right','hair',{root:690,tip:1254,frequency:1.1},[630,650,624,604]);
    add('Neck','neck','neck',{},[540,750,200,130]);
    add('Torso','torso','body',{},[0,780,SIZE,474]);
    this.face=add('Skin and jaw','face','face',{spacing:14},[380,180,525,635]);
    this.eyes=[];
    for(let i=0;i<2;i++){
      const side=i===0?-1:1,[cx,cy]=FEATURES[i===0?'eye-left':'eye-right'];
      const canvas=sheet(),bounds=[cx-105,cy-65,210,130];
      const open=renderer.layer(i===0?'Left eye and iris':'Right eye and iris',canvas,
        {type:'eye',component:'open',cx,cy,side,spacing:5},bounds);
      const closed=renderer.layer(i===0?'Left closed lashes':'Right closed lashes',parts.closed[i],
        {type:'eye',component:'closed',cx,cy,side,spacing:5},bounds);
      this.eyes.push({canvas,open,closed,index:i});
    }
    for(const [part,side] of [['brow-left',-1],['brow-right',1]]){
      const [cx,cy]=FEATURES[part];
      add(side<0?'Left eyebrow':'Right eyebrow',part,'brow',{cx,cy,side,spacing:5},[cx-90,cy-30,180,60]);
    }
    add('Nose','nose','nose',{cx:633,cy:660,spacing:5},[595,610,78,100]);
    this.mouthCanvas=sheet();
    this.mouthMask=sheet();
    const mg=this.mouthMask.getContext('2d');mg.save();mg.translate(635,720);mg.scale(65,38);
    const grad=mg.createRadialGradient(0,0,.78,0,0,1);grad.addColorStop(0,'#fff');grad.addColorStop(1,'#fff0');
    mg.fillStyle=grad;mg.fillRect(-1,-1,2,2);mg.restore();
    this.mouthLayer=renderer.layer('Mouth',this.mouthCanvas,{type:'mouth',cx:635,cy:720,spacing:5},[565,675,140,90]);
    add('Earring','earring','earring',{frequency:1.7},[447,670,51,122]);
    add('Crown','crown','hair',{root:690,tip:1254,frequency:1.55},[300,165,650,565]);
    add('Left front lock','lock-left','hair',{root:690,tip:1254,frequency:1.3},[285,670,295,584]);
    add('Right front lock','lock-right','hair',{root:690,tip:1254,frequency:1.2},[720,670,360,584]);
    add('Left side bang','side-left','hair',{part:'side',side:-1,root:315,tip:730,frequency:1.6,spacing:12},[345,220,265,560]);
    add('Right side bang','side-right','hair',{part:'side',side:1,root:315,tip:730,frequency:1.55,spacing:12},[680,235,255,545]);
    add('Left bang','bang-left','hair',{part:'bang',side:-1,root:310,tip:680,frequency:1.9,spacing:12},[375,220,350,515]);
    add('Right bang','bang-right','hair',{part:'bang',side:1,root:310,tip:680,frequency:1.8,spacing:12},[375,220,350,515]);
    add('Center bang','bang-center','hair',{part:'bang',side:0,root:310,tip:680,frequency:1.85,spacing:12},[530,235,205,455]);
    this.advanceStable(0);
  }
  paintFeatures(){
    const m=this.manifest,imgs=this.images;
    for(const eye of this.eyes){
      const i=eye.index,g=eye.canvas.getContext('2d');
      g.clearRect(0,0,SIZE,SIZE);g.drawImage(this.parts[i===0?'eye-left':'eye-right'],0,0);
      const e=m.eyes[i],p=eyeOpening(e);
      g.save();g.clip(p);const r=m.rects[`eye${i}_ball`];
      g.fillStyle='#fff4ed';g.fill(p);
      g.drawImage(imgs[`eye${i}_ball`],r[0]+clamp(this.pose.gazeX,-.6,.6)*7,r[1]-clamp(this.pose.gazeY,-.3,.3)*8,r[2],r[3]);g.restore();
      eye.open.opacity=clamp(this.eyeOpen/.35,0,1);
      eye.closed.opacity=clamp(1-this.eyeOpen/.45,0,1);
      this.renderer.upload(eye.open,eye.canvas);
    }
    const g=this.mouthCanvas.getContext('2d');g.clearRect(0,0,SIZE,SIZE);
    const alpha=clamp(this.mouth/.16,0,1);g.globalAlpha=1-alpha;g.drawImage(this.parts.mouth,0,0);g.globalAlpha=1;
    if(this.mouth>.025){
      const v=clamp(this.mouth,0,1);
      const name=v>.6?'mouth_a':v>.28?'mouth_a_half':'mouth_i';
      g.globalAlpha=alpha;g.drawImage(this.parts.mouthSprites[name],0,0);g.globalAlpha=1;
    }
    g.globalCompositeOperation='destination-in';g.drawImage(this.mouthMask,0,0);g.globalCompositeOperation='source-over';
    this.renderer.upload(this.mouthLayer,this.mouthCanvas);
  }
  advanceStable(seconds){
    if(this.destroyed)return;
    const dt=Number.isFinite(seconds)?clamp(seconds,0,.1):0;
    this.time+=dt;this.eyeOpen=this.blink.update(dt)*(this.expression==='halfLidded'?.62:1);
    this.mouth+=(this.level-this.mouth)*(1-Math.exp(-dt*(this.level>this.mouth?24:18)));
    if(dt>0){const velocity=clamp((this.pose.angleX-this.lastAngle)/dt,-90,90);this.velocity+=(velocity-this.velocity)*(1-Math.exp(-8*dt));this.lastAngle=this.pose.angleX;}
    for(const l of this.renderer.layers){
      if(l.type!=='hair'&&l.type!=='earring')continue;
      const fine=l.part==='bang'?.55:l.part==='side'?.75:l.name==='Crown'?.08:1;
      const target=(-this.velocity*.11+this.pose.angleZ*.7+Math.sin(this.time*.85+(l.root??0))*.65)*fine;
      l.swing=l.spring.update(dt,target)*clamp(this.hair/.45,0,1.8);
    }
    this.paintFeatures();this.renderer.render({...this.pose,eyeOpen:this.eyeOpen},Math.sin(this.time*1.55),this.mouth);
  }
  setParameters(pose){for(const key of Object.keys(this.pose))if(Number.isFinite(pose[key]))this.pose[key]=pose[key];}
  getParameters(){return {...this.pose,mouthOpen:this.mouth,eyeLOpen:this.eyeOpen,eyeROpen:this.eyeOpen};}
  setExpression(value){this.expression=value;}
  getExpression(){return {name:this.expression};}
  setVoiceLevel(value){this.level=Number.isFinite(value)?clamp(value,0,1):0;}
  setSpeaking(value){if(!value)this.level=0;}
  stopLipSync(){this.level=this.mouth=0;}
  setAutoMotion(){}
  setAutoIdle(){}
  setTalkGain(){}
  setSwayGain(value){this.hair=value;}
  createMotionPreview(pose){return new RigPreview(pose);}
  rigDiagnostics(){return {layers:this.renderer.layers.length,physics:true,approach:'part-specific-xy-warps',
    parts:this.renderer.layers.map(l=>({name:l.name,type:l.type,opacity:l.opacity})),
    landmarks:Object.fromEntries(this.renderer.layers.filter(l=>['eye','brow','nose','mouth'].includes(l.type)&&l.component!=='closed')
      .map(l=>[l.name,projectPoint(l.cx,l.cy,l,this.pose)])),
    values:Object.fromEntries(this.renderer.layers.filter(l=>l.type==='hair'||l.type==='earring').map(l=>[l.name,l.swing]))};}
  inspectLayers(){return this.renderer.layers.map(l=>({name:l.name,type:l.type,image:l.art.toDataURL('image/png')}));}
  destroy(){if(this.destroyed)return;this.destroyed=true;this.renderer.destroy();}
}
