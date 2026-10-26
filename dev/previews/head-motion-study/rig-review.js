import {HeadTurnStudy,REST} from './motion.js';

const step=(label,pose,hold=1.1,expression='neutral')=>Object.freeze({
  label,pose:Object.freeze({...REST,...pose}),travel:1.5,hold,expression});
export const RIG_SEQUENCE=Object.freeze([
  step('Rest: compare eye shape',{}),
  step('Open eyes: gaze left',{gazeX:-.6}),
  step('Open eyes: gaze right',{gazeX:.6}),
  step('Open eyes: gaze up',{gazeY:.3}),
  step('Open eyes: gaze down',{gazeY:-.3}),
  step('Combined left turn and tilt',{angleX:-12,angleY:-4,angleZ:-8,gazeX:-.3}),
  step('Blink during left turn',{angleX:-12,angleY:-4,angleZ:-8,gazeX:-.3,eyeLOpen:0,eyeROpen:0},.25),
  step('Reopen during left turn',{angleX:-12,angleY:-4,angleZ:-8,gazeX:-.3}),
  step('Combined right turn and tilt',{angleX:12,angleY:4,angleZ:8,gazeX:.3}),
  step('Blink during right turn',{angleX:12,angleY:4,angleZ:8,gazeX:.3,eyeLOpen:0,eyeROpen:0},.25),
  step('Reopen during right turn',{angleX:12,angleY:4,angleZ:8,gazeX:.3}),
  step('Half-closed eyes: gaze left',{gazeX:-.6},1.1,'halfLidded'),
  step('Half-closed eyes: gaze right',{gazeX:.6},1.1,'halfLidded'),
  step('Return and let hair settle',{},6),
]);

// Reuse the same elapsed-time interpolation and delayed body follow. Blink
// overrides exist only in this diagnostic sequence, never the motion controller.
export class RigReview extends HeadTurnStudy {
  constructor(){super(RIG_SEQUENCE);}
  update(dt){
    const state=super.update(dt);
    const blink=this.current.pose.eyeLOpen===0 && this.phaseTime>=this.current.travel;
    return {...state,pose:{...state.pose,eyeLOpen:blink?0:1,eyeROpen:blink?0:1}};
  }
}
