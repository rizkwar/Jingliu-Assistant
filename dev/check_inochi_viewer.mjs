// Numeric comparison against the Python inspection evaluator, using local data.
import {RigPlayer, deformParts} from './inochi-viewer/model.js';
let text = ''; for await (const chunk of process.stdin) text += chunk;
const input = JSON.parse(text);
let samples = 0, maximumPoseError = 0, maximumVertexError = 0;
for (const reference of input.clips) {
  const p = new RigPlayer(input.model); p.selectClip(reference.name); p.playing = true;
  for (let i = 0; i < reference.poses.length; i++) {
    if (i) p.tick(1 / reference.fps);
    for (const [name, pair] of Object.entries(reference.poses[i])) for (let axis = 0; axis < 2; axis++) {
      maximumPoseError = Math.max(maximumPoseError, Math.abs(pair[axis] - p.values[name][axis]));
    }
    samples++;
  }
}
for (const reference of input.geometry) {
  const parts = deformParts(input.model, reference.values);
  for (const part of parts) {
    const expected = reference.parts[String(part.part.uuid)];
    for (let i = 0; i < part.vertices.length; i++) maximumVertexError = Math.max(maximumVertexError, Math.abs(part.vertices[i] - expected[i]));
  }
}
if (!Number.isFinite(maximumPoseError) || maximumPoseError > 1e-8 || !Number.isFinite(maximumVertexError) || maximumVertexError > .00013) throw Error('Viewer numerical comparison failed');
console.log(JSON.stringify({samples, clips: input.clips.length, combinedPoses: input.geometry.length, maximumPoseError, maximumVertexError}));
