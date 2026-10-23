// The pinned Cubism solver divides particle displacement by its time step.
// Never feed it the tiny remainder of a frame, or a redraw-only epsilon.
export class Live2DPhysics {
  constructor(evaluate,outputIds,fps=60){
    this.evaluate=evaluate;
    this.ids=[...new Set(outputIds)];
    this.step=1/(Number.isFinite(fps)&&fps>=30&&fps<=120?fps:60);
    this.remaining=0;this.previous=null;this.current=null;this.steps=0;
  }
  read(core){return this.ids.map(id=>core.getParameterValueById(id));}
  write(core,values){this.ids.forEach((id,i)=>core.setParameterValueById(id,values[i]));}
  update(core,seconds){
    if(!this.current){this.current=this.read(core);this.previous=[...this.current];}
    const dt=Number.isFinite(seconds)?Math.max(0,Math.min(.1,seconds)):0;
    this.remaining+=dt;
    while(this.remaining+1e-9>=this.step){
      // Cubism restores saved parameters after drawing. Reapply the raw solver
      // state, including outputs that feed other physics groups. Display gains
      // and interpolated values must not feed back into the next solver step.
      this.write(core,this.current);
      this.previous=this.current;
      this.evaluate(core,this.step);
      this.current=this.read(core);
      this.remaining=Math.max(0,this.remaining-this.step);this.steps++;
    }
    // Also restore on frames with no solver step: otherwise Cubism's parameter
    // restore makes the ribbons alternate between their resting and moving pose.
    const alpha=Math.min(1,this.remaining/this.step);
    this.write(core,this.current.map((value,i)=>this.previous[i]+(value-this.previous[i])*alpha));
  }
}
