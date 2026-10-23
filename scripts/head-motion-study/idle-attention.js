// Independent of DOM and rendering. Posture/gaze only: blink, breath, mouth and
// hair retain their runtime owners. All limits fit the reviewed Jingliu rig.
const rest=()=>({angleX:0,angleY:0,angleZ:0,gazeX:0,gazeY:0});
const clamp=(value,limit=1)=>Math.max(-limit,Math.min(limit,value));
const ease=value=>{const x=Math.max(0,Math.min(1,value));return x*x*x*(10+x*(-15+6*x));};
const unit=value=>Number.isFinite(value)?Math.max(0,Math.min(1,value)):0;

// CSS client coordinates and DOMRect share one coordinate system, independent
// of backing-canvas DPR. Use the actual contain-fit portrait's eye center.
export function cursorTarget(point,rect) {
  if(!point||!rect||!['x','y'].every(key=>Number.isFinite(point[key]))||
    !['left','top','width','height'].every(key=>Number.isFinite(rect[key]))||rect.width<=0||rect.height<=0)return null;
  const scale=Math.min(rect.width/(1254*1.05),rect.height/(1254*1.015));
  const eyeX=rect.left+(rect.width-1254*scale)/2+631*scale;
  const eyeY=rect.top+rect.height-1254*scale+594*scale;
  return {x:clamp((point.x-eyeX)/(rect.width*.75)),y:clamp((eyeY-point.y)/(rect.height*.65))};
}

export {IdleAttention} from '../../companion/avatar_web/idle-attention.js';
