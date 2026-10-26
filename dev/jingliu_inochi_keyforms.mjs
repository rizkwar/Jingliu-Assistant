// Authoring-only fields. The assistant's existing renderer is unchanged.
import {projectPoint} from '../companion/avatar_web/layered-rig.js';
const smooth=(a,b,x)=>{const t=Math.max(0,Math.min(1,(x-a)/(b-a)));return t*t*(3-2*t);};

export function authorPoint(x,y,layer,pose={},swing=0){
  if(layer.type==='hair'){
    // The crown, fringe and rear hair have adjoining cut edges. Give coincident
    // coordinates the same head keyform so those cuts cannot pull apart just
    // because a vertex belongs to a differently named drawable.
    const common={...layer,part:'long',root:560,tip:1200};
    const [px,py]=projectPoint(x,y,common,pose,0);
    const pinned=1-smooth(760,1140,y);
    const free=smooth(280,650,y)*(1-smooth(1000,1254,y));
    // Curved, spatially varying sway, with fixed crown roots and bust crop.
    // Both sides respond; the continuous field also preserves abutting cuts.
    const bend=free*(.8+.2*Math.sin((x-632)/165));
    return [x+(px-x)*pinned+swing*bend,y+(py-y)*pinned+Math.abs(swing)*.035*bend];
  }
  return projectPoint(x,y,layer,pose,layer.type==='earring'?swing*.3:0);
}
