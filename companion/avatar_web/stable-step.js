// Keep explicit motion/hair springs stable after a slow frame. Simulate at most
// 100 ms in steps no larger than 20 ms, deforming and drawing the final state once.
// Sprite fades receive the full elapsed frame once, rather than one substep.
export function advanceFrame(seconds, step) {
  const elapsed = Number.isFinite(seconds) ? Math.max(0, Math.min(.1, seconds)) : 0;
  const count = Math.max(1, Math.ceil(elapsed / .02));
  for (let index = 0; index < count; index++) {
    step(elapsed / count, index === count - 1, elapsed);
  }
}
