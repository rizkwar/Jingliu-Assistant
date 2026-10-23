// Step runtime springs at a stable cadence, drawing only the final state.
// A bounded stall is simulated, never replayed as many expensive mesh draws.
export function advanceFrame(seconds,step) {
  const elapsed=Number.isFinite(seconds)?Math.max(0,Math.min(.1,seconds)):0;
  const count=Math.max(1,Math.ceil(elapsed/.02));
  for(let index=0;index<count;index++)step(elapsed/count,index===count-1,elapsed);
}
