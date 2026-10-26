// Part-specific XY keyforms. These are drawing deformations, not the projection
// of a flat card in 3D. Input angles remain the app's bounded control units.
export const clamp=(x,a,b)=>Math.max(a,Math.min(b,x));
const smooth=(a,b,x)=>{const t=clamp((x-a)/(b-a),0,1);return t*t*(3-2*t);};
export const REST={angleX:0,angleY:0,angleZ:0,bodyAngleX:0,bodyAngleZ:0,gazeX:0,gazeY:0,browY:0};

const gaussian=(x,c,r)=>Math.exp(-(((x-c)/r)**2));
function faceXY(x,y,u,v){
  const nx=clamp((x-632)/220,-1.6,1.6),jaw=smooth(685,805,y),forehead=1-smooth(350,550,y);
  // The facial center travels farther than the silhouette. The far cheek
  // compresses while the near cheek retains width; the chin has its own key.
  const travel=48-19*jaw-20*forehead;
  const dx=u*(travel-23*nx*nx)-u*u*(x-632)*.055+v*jaw*(x-632)*.035;
  const dy=-v*(25-8*jaw)+v*jaw*nx*nx*12+u*nx*4*gaussian(y,620,210);
  return [x+dx,y+dy];
}

export function projectPoint(x,y,layer,pose={},swing=0,breath=0,mouth=0){
  const u=clamp(pose.angleX||0,-12,12)/12,v=clamp(pose.angleY||0,-4,4)/4;
  const roll=clamp(pose.angleZ||0,-8,8)*.75*Math.PI/180;
  const hair=layer.type==='hair',body=layer.type==='body';
  let weight=body?0:1;
  if(hair)weight=1-smooth(680,1370,y)*.8;
  if(layer.type==='neck')weight=1-smooth(755,870,y);
  let [px,py]=faceXY(x,y,u,v);
  if(hair){
    const nx=clamp((x-632)/320,-2,2),free=smooth(layer.root,layer.tip,y);
    px=x+u*(27-10*nx*nx)-u*u*(x-632)*.025;
    py=y-v*(26+14*gaussian(y,365,215))+u*nx*3;
    // Different silhouettes and overlap for central bangs and cheek locks.
    const side=layer.side??0;
    if(layer.part==='bang'){
      px+=free*(u*14-side*Math.abs(u)*5);
      py+=free*(v*8+side*u*5);
    }else if(layer.part==='side'){
      px+=free*(u*6-side*Math.abs(u)*8);
      py+=free*(v*10+side*u*4);
    }
  }
  if(['eye','brow','nose','mouth'].includes(layer.type)){
    const cx=layer.cx,cy=layer.cy,side=layer.side??0;
    const center=faceXY(cx,cy,u,v),a=x-cx,b=y-cy;
    const squeeze=layer.type==='eye'||layer.type==='brow'?
      1-.14*side*u-.055*Math.abs(u):1-.12*Math.abs(u);
    px=center[0]+a*squeeze;
    py=center[1]+b*(1+v*.055)+a*side*u*.025;
    if(layer.type==='eye'&&layer.component==='open'){
      const openness=clamp(pose.eyeOpen??1,0,1);
      py=center[1]+(py-center[1])*(.32+.68*openness)+(1-openness)*5;
    }
    if(layer.type==='brow')py-=clamp(pose.browY||0,-1,1)*25;
    if(layer.type==='nose'){px+=u*15;py-=v*6;}
    if(layer.type==='mouth'){px+=u*5;py-=v*7;}
  }
  // Rotation around the neck rather than the middle of the picture.
  const a=px-632,b=py-805;
  px=632+a*Math.cos(roll)-b*Math.sin(roll);
  py=805+a*Math.sin(roll)+b*Math.cos(roll);
  px=x+(px-x)*weight;py=y+(py-y)*weight;
  if(hair){
    const free=smooth(layer.root,layer.tip,y);
    px+=swing*free;
    py+=Math.abs(swing)*.10*free;
  }
  if(layer.type==='earring'){
    const free=clamp((y-684)/100,0,1);px+=swing*free;
    py+=Math.abs(swing)*.08*free;
  }
  // Torso follows more slowly, keeping shoulders and collar together.
  const torso=smooth(790,1254,y),bx=clamp(pose.bodyAngleX||0,-1.5,1.5);
  const br=clamp(pose.bodyAngleZ||0,-1.2,1.2)*Math.PI/180;
  px+=torso*(bx*5-(y-1254)*br);
  py+=torso*((x-632)*br-breath*3);
  if(layer.type==='face')py+=mouth*1.8*smooth(715,800,y);
  // The portrait is cropped at the bust. Tilting that crop advertises a flat
  // rectangular sheet, so the last rows blend into a fixed horizontal base.
  const base=1-smooth(1150,1254,y);
  px=x+(px-x)*base;py=y+(py-y)*base;
  return [px,py];
}

// Exact damped spring solution, advanced in bounded steps. No division by dt:
// redraws and sub-frame leftovers cannot kick the hair into fast oscillations.
export class StrandSpring {
  constructor(frequency=1.35,damping=.8){this.x=0;this.v=0;this.w=frequency*2*Math.PI;this.damping=damping;}
  update(seconds,target){
    let left=Number.isFinite(seconds)?clamp(seconds,0,.1):0;
    target=Number.isFinite(target)?clamp(target,-22,22):0;
    while(left>1e-9){
      const dt=Math.min(left,1/120),a=this.w*this.damping;
      const b=this.w*Math.sqrt(1-this.damping*this.damping),e=Math.exp(-a*dt),q=this.x-target;
      const c=Math.cos(b*dt),s=Math.sin(b*dt),u=(this.v+a*q)/b;
      this.x=target+e*(q*c+u*s);
      this.v=e*(this.v*c-(a*this.v+this.w*this.w*q)*s/b);
      left-=dt;
    }
    return this.x;
  }
}

export function grid(bounds,spacing=22){
  const [bx,by,bw,bh]=bounds,x=Math.floor(bx/spacing)*spacing,y=Math.floor(by/spacing)*spacing;
  const w=Math.min(1254,Math.ceil((bx+bw)/spacing)*spacing)-x;
  const h=Math.min(1254,Math.ceil((by+bh)/spacing)*spacing)-y;
  const cols=Math.ceil(w/spacing),rows=Math.ceil(h/spacing),points=[],indices=[];
  for(let j=0;j<=rows;j++)for(let i=0;i<=cols;i++)points.push([Math.min(x+i*spacing,x+w),Math.min(y+j*spacing,y+h)]);
  for(let j=0;j<rows;j++)for(let i=0;i<cols;i++){
    const a=j*(cols+1)+i,b=a+1,c=a+cols+1,d=c+1;indices.push(a,b,c,b,d,c);
  }
  return {points,indices:new Uint16Array(indices)};
}
