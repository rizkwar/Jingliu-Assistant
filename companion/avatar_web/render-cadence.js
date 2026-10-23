// A consistent visible rate avoids coarse idle motion and a cadence change when
// conversation starts. requestAnimationFrame still limits slower displays.
export class RenderCadence {
  constructor() {
    this.restart();
  }

  restart() { this.previous = null; this.deadline = null; this.rate = 0; }

  frameRate() { return 60; }

  step(now) {
    if (!Number.isFinite(now)) return null;
    const rate = this.frameRate();
    // Preserve the deadline phase through small vsync jitter. Snapping every
    // late deadline to now would gradually lose frames on a busy UI thread.
    if (rate !== this.rate) { this.deadline = now; this.rate = rate; }
    if (this.deadline !== null && now + 0.5 < this.deadline) return null;
    const dt = this.previous === null ? 1 / rate : Math.max(.000001, Math.min((now - this.previous) / 1000, .1));
    this.previous = now;
    const interval = 1000 / rate;
    // A stalled window gets one bounded step, never a burst of catch-up draws.
    const periods = Math.max(1, Math.floor((now - this.deadline + .5) / interval) + 1);
    this.deadline += periods * interval;
    return dt;
  }
}
