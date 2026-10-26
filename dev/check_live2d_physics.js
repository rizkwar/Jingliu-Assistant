// Injected only by the opt-in native check, never loaded by the assistant.
(async()=>{
  const {Live2DPhysics}=await import(new URL('./live2d-physics.js',location.href).href);
  const definition=await (await fetch('./model/model3.json')).json();
  const refs=definition.FileReferences;
  const resource=async name=>await fetch(new URL(name,new URL('./model/',location.href)));
  const physicsDefinition=await (await resource(refs.Physics)).json();
  const display=refs.DisplayInfo?await (await resource(refs.DisplayInfo)).json():{};
  const moc=Live2DCubismCore.Moc.fromArrayBuffer(await (await resource(refs.Moc)).arrayBuffer());
  const scratchModel=Live2DCubismCore.Model.fromMoc(moc);
  const parameters=scratchModel.parameters,indexes=new Map(Array.from(parameters.ids,(id,i)=>[id,i]));
  const outputIds=[...new Set(physicsDefinition.PhysicsSettings.flatMap(group=>
    group.Output.map(output=>output.Destination.Id)))].filter(id=>indexes.has(id));
  const names=new Map((display.Parameters??[]).map(p=>[p.Id,p.Name]));
  const ribbons=outputIds.filter(id=>/ribbon|band|带/i.test(names.get(id)??''));
  const measured=ribbons.length?ribbons:outputIds;
  function simulate(previousTiming){
    const values=new Float32Array(parameters.defaultValues);
    const data={...parameters,values};
    const core={getModel:()=>({parameters:data}),
      getParameterIndex:id=>indexes.get(typeof id==='string'?id:id.getString()),
      getParameterValueById:id=>values[indexes.get(id)],
      setParameterValueById:(id,value)=>{values[indexes.get(id)]=value;}};
    const physics=PIXI.live2d.CubismPhysics.create(physicsDefinition);
    const fixed=new Live2DPhysics(physics.evaluate.bind(physics),outputIds,physicsDefinition.Meta?.Fps);
    let time=0,last=null,maxJump=0,saturations=0,nonFinite=0;
    for(let frame=0;frame<2400;frame++){
      // About 40 seconds of gentle turns, mixing ordinary frames, near-exact
      // substep boundaries, and tiny redraws. Same inputs for both solvers.
      const dt=[.0166667,.000001,.0333334,.0166667][frame%4];time+=dt;
      values.set(parameters.defaultValues);
      for(const [id,value] of Object.entries({ParamAngleX:20*Math.sin(time*.4),
        ParamAngleY:3*Math.sin(time*.28),ParamAngleZ:4*Math.sin(time*.3),
        ParamBreath:.5+Math.sin(time*1.55)*.3})){
        if(indexes.has(id))values[indexes.get(id)]=value;
      }
      if(previousTiming){
        let remaining=dt;
        while(remaining>1e-8){const step=Math.min(remaining,1/60);physics.evaluate(core,step);remaining-=step;}
      }else fixed.update(core,dt);
      nonFinite+=Array.from(values).filter(v=>!Number.isFinite(v)).length;
      const now=measured.map(id=>values[indexes.get(id)]);
      if(last)for(let i=0;i<now.length;i++){
        const index=indexes.get(measured[i]);
        const min=parameters.minimumValues[index],max=parameters.maximumValues[index],range=max-min;
        if(range<=0)continue;
        maxJump=Math.max(maxJump,Math.abs(now[i]-last[i])/range);
        if(Math.abs(now[i]-min)<1e-5||Math.abs(now[i]-max)<1e-5)saturations++;
      }
      last=now;
    }
    return {frames:2400,seconds:time,ribbonParameters:measured.length,maxJump,saturations,nonFinite};
  }
  const before=simulate(true),after=simulate(false);
  window.live2dPhysicsCheck={before,after,
    passed:after.nonFinite===0&&after.saturations===0&&after.maxJump<.05};
})().catch(error=>window.live2dPhysicsCheck={error:String(error),passed:false});
