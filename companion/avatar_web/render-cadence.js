import {visualMode} from './conversation-state.js';

// Keep full-rate expressions and lips during interaction; waiting needs fewer
// expensive mesh deformations and GL draws, at the same pixel resolution.
export class RenderCadence {
  constructor() {
    this.until = 0;
    this.restart();
  }

  boost(now) { this.until = now + 1000; }

  restart() { this.previous = null; this.deadline = null; this.rate = 0; }

  frameRate(activity, voiceActive, now) {
    return voiceActive || visualMode(activity) !== 'idle' || now < this.until ? 30 : 20;
  }

  step(now, activity, voiceActive) {
    const rate = this.frameRate(activity, voiceActive, now);
    // A rate change takes effect on the next display frame, especially when
    // speech begins. Deadlines avoid quantizing 30 FPS to 20 on jittery displays.
    if (rate !== this.rate) { this.deadline = now; this.rate = rate; }
    if (this.deadline !== null && now + 0.5 < this.deadline) return null;
    const dt = this.previous === null ? 1 / rate : Math.max(.000001, Math.min((now - this.previous) / 1000, .1));
    this.previous = now;
    const interval = 1000 / rate;
    this.deadline = Math.max((this.deadline ?? now) + interval, now);
    // A stalled window gets one bounded step, never a burst of catch-up draws.
    if (this.deadline <= now) this.deadline = now + interval;
    return dt;
  }
}
