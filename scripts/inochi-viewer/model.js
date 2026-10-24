// Inspection of our flat Inochi 0.8 rig subset. This is not the Inochi SDK.
export const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
const finite = v => typeof v === 'number' && Number.isFinite(v);

export function interpolate(parameter, binding, pose) {
  const value = pose[parameter.name] ?? parameter.defaults;
  const ranges = parameter.axis_points.map((axis, i) => {
    if (axis.length === 1) return [0, 0, 0];
    const t = clamp((value[i] - parameter.min[i]) / (parameter.max[i] - parameter.min[i]), 0, 1);
    let a = 0;
    while (a < axis.length - 2 && axis[a + 1] <= t) a++;
    return [a, a + 1, clamp((t - axis[a]) / (axis[a + 1] - axis[a]), 0, 1)];
  });
  const [[a, b, x], [c, d, y]] = ranges, v = binding.values;
  const blend = (aa, bb, cc, dd) => (aa * (1 - x) + bb * x) * (1 - y) + (cc * (1 - x) + dd * x) * y;
  if (typeof v[a][c] === 'number') return blend(v[a][c], v[b][c], v[a][d], v[b][d]);
  return v[a][c].map((_, k) => [0, 1].map(i => blend(v[a][c][k][i], v[b][c][k][i], v[a][d][k][i], v[b][d][k][i])));
}

export function laneValue(lane, frame) {
  const keys = lane.keyframes;
  let i = 0;
  while (i < keys.length && keys[i].frame < frame) i++;
  if (i === 0) return keys[0].value;
  if (i === keys.length) return keys.at(-1).value;
  const a = keys[i - 1], b = keys[i];
  let t = (frame - a.frame) / (b.frame - a.frame);
  if (lane.interpolation === 'Bezier') {
    const slope = 2 * (b.tension ?? .5);
    t = clamp(-2 * t ** 3 + 3 * t ** 2 + slope * (2 * t ** 3 - 3 * t ** 2 + t), 0, 1);
  } else if (lane.interpolation !== 'Linear') throw Error('Unsupported animation interpolation');
  return a.value + (b.value - a.value) * t;
}

export class Pendulum {
  constructor(anchor, length, gravity, damping, scale) {
    this.length = length; this.gravity = gravity; this.damping = damping; this.scale = scale;
    this.bob = [anchor[0], anchor[1] + length]; this.velocity = 0;
  }
  step(anchor, dt, rotation = 0) {
    if (!finite(dt) || dt < 0 || dt > .25) throw Error('Invalid physics step');
    let h = dt;
    while (h > 1e-10) {
      const s = Math.min(h, .01); h -= s;
      let a = Math.atan2(-(this.bob[0] - anchor[0]), this.bob[1] - anchor[1]);
      const ratio = this.gravity / this.length, damping = this.damping * 2 * Math.sqrt(ratio);
      const derivative = (angle, velocity) => [velocity, -ratio * Math.sin(angle) - damping * velocity];
      const v = this.velocity, k1 = derivative(a, v);
      const k2 = derivative(a + s * k1[0] / 2, v + s * k1[1] / 2);
      const k3 = derivative(a + s * k2[0] / 2, v + s * k2[1] / 2);
      const k4 = derivative(a + s * k3[0], v + s * k3[1]);
      a += s * (k1[0] + 2 * k2[0] + 2 * k3[0] + k4[0]) / 6;
      this.velocity += s * (k1[1] + 2 * k2[1] + 2 * k3[1] + k4[1]) / 6;
      this.bob = [anchor[0] - Math.sin(a) * this.length, anchor[1] + Math.cos(a) * this.length];
    }
    const dx = this.bob[0] - anchor[0], dy = this.bob[1] - anchor[1];
    return Math.atan2(-(dx * Math.cos(rotation) + dy * Math.sin(rotation)),
      -dx * Math.sin(rotation) + dy * Math.cos(rotation)) / Math.PI * this.scale;
  }
}

export class RigPlayer {
  constructor(model) {
    this.data = model.puppet;
    this.parameters = new Map(this.data.param.map(p => [p.name, p]));
    this.byId = new Map(this.data.param.map(p => [p.uuid, p]));
    this.driver = this.data.nodes.children.find(n => n.type === 'SimplePhysics');
    this.physics = this.driver.enabled !== false;
    this.clip = null; this.playing = false; this.time = 0;
    this.manual = this.defaults(); this.values = this.defaults(); this.resetPhysics();
  }
  defaults() { return Object.fromEntries(this.data.param.map(p => [p.name, [...p.defaults]])); }
  duration() { const c = this.data.animations[this.clip]; return c ? c.timestep * c.length : 0; }
  basePose() {
    const pose = structuredClone(this.manual), clip = this.data.animations[this.clip];
    if (clip) for (const lane of clip.lanes) {
      pose[this.byId.get(lane.uuid).name][lane.target] = laneValue(lane, (this.time / clip.timestep) % clip.length);
    }
    return pose;
  }
  anchor(pose) {
    const d = this.driver, xy = d.transform.trans.slice(0, 2);
    let rotation = d.transform.rot[2];
    for (const p of this.data.param) for (const b of p.bindings) if (b.node === d.uuid) {
      const value = interpolate(p, b, pose);
      if (b.param_name === 'transform.t.x') xy[0] += value;
      else if (b.param_name === 'transform.t.y') xy[1] += value;
      else if (b.param_name === 'transform.r.z') rotation += value;
      else throw Error('Unsupported driver input');
    }
    return {xy, rotation};
  }
  resetPhysics() {
    const d = this.driver, a = this.anchor(this.basePose()), world = this.data.physics;
    this.pendulum = new Pendulum(a.xy, d.length, world.gravity * world.pixelsPerMeter * d.gravity, d.angle_damping, d.output_scale[0]);
    this.evaluate(0);
  }
  evaluate(dt) {
    const pose = this.basePose();
    if (this.physics) {
      const a = this.anchor(pose), p = this.byId.get(this.driver.param);
      pose[p.name] = [clamp(this.pendulum.step(a.xy, dt, a.rotation), p.min[0], p.max[0]), 0];
    }
    this.values = pose; return pose;
  }
  tick(dt) {
    if (!finite(dt) || dt < 0 || dt > .25) throw Error('Invalid playback step');
    if (this.clip && !this.playing) return this.values;
    let remaining = dt;
    while (remaining > 1e-10) {
      const step = Math.min(remaining, 1 / 120); remaining -= step;
      if (this.clip) this.time = (this.time + step) % this.duration();
      this.evaluate(step);
    }
    return this.values;
  }
  selectClip(name) {
    if (name !== null && !Object.hasOwn(this.data.animations, name)) throw Error('Unknown animation');
    this.clip = name; this.time = 0; this.playing = false; this.manual = this.defaults(); this.resetPhysics();
  }
  setValue(name, axis, value) {
    const p = this.parameters.get(name);
    if (this.clip) throw Error('Choose Manual controls before changing a parameter');
    if (!p || !Number.isInteger(axis) || axis < 0 || axis > (p.is_vec2 ? 1 : 0) || !finite(value) || value < p.min[axis] || value > p.max[axis]) throw Error('Invalid parameter value');
    if (this.physics && p.uuid === this.driver.param) throw Error('Disable physics before moving hair manually');
    this.manual[name][axis] = value; this.evaluate(0);
  }
  setPhysics(enabled) { this.physics = Boolean(enabled); this.resetPhysics(); }
  seek(seconds) {
    if (!this.clip || !finite(seconds) || seconds < 0 || seconds > this.duration()) throw Error('Invalid clip time');
    this.playing = false; this.time = 0; this.resetPhysics();
    // Replay only the small parameter/physics system; draw once after seeking.
    const target = Math.min(seconds, this.duration() - 1e-7);
    while (this.time < target - 1e-10) {
      const dt = Math.min(1 / 120, target - this.time); this.time += dt; this.evaluate(dt);
    }
    return this.values;
  }
  reset() { this.selectClip(null); }
}

export function deformParts(model, values) {
  const data = model.puppet, parts = data.nodes.children.filter(n => n.type === 'Part');
  const offsets = new Map(), opacity = new Map();
  for (const p of data.param) for (const b of p.bindings) {
    if (b.node === data.nodes.children.find(n => n.type === 'SimplePhysics').uuid) continue;
    const value = interpolate(p, b, values);
    if (b.param_name === 'opacity') opacity.set(b.node, (opacity.get(b.node) ?? 1) * value);
    else {
      let target = offsets.get(b.node);
      if (!target) { target = value.map(() => [0, 0]); offsets.set(b.node, target); }
      value.forEach((v, i) => { target[i][0] += v[0]; target[i][1] += v[1]; });
    }
  }
  return parts.map(part => {
    const delta = offsets.get(part.uuid), t = part.transform.trans;
    const vertices = new Float32Array(part.mesh.verts.length);
    for (let i = 0; i < vertices.length; i += 2) {
      vertices[i] = part.mesh.verts[i] + (delta?.[i / 2][0] ?? 0) + t[0] + 627;
      vertices[i + 1] = part.mesh.verts[i + 1] + (delta?.[i / 2][1] ?? 0) + t[1] + 627;
    }
    return {part, vertices, opacity: clamp((part.opacity ?? 1) * (opacity.get(part.uuid) ?? 1), 0, 1)};
  });
}
