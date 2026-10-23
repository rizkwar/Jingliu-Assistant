// Visual state is an app activity cue, never a guess about the user's emotions.
const BASE = Object.freeze({angleX:0, angleY:0, angleZ:0, gazeX:0, gazeY:0,
  browY:0, eyeSmile:0, eyeSmileL:0});
const style = (expression, pose, talkGain = 0) => Object.freeze({expression,
  pose:Object.freeze({...BASE, ...pose}), talkGain});
export const VISUALS = Object.freeze({
  idle:style('neutral', {angleY:-0.5}),
  listening:style('neutral', {angleY:-1.5, angleZ:-1.2, gazeY:0.08, browY:0.06}),
  thinking:style('halfLidded', {angleX:2, angleY:-1.8, angleZ:0.8, gazeX:0.12, gazeY:-0.12}),
  speaking:style('neutral', {angleY:-0.6, eyeSmile:0.06, eyeSmileL:0.06}, 0.12),
  attention:style('neutral', {angleY:-1, gazeY:-0.08}),
  paused:style('neutral', {}),
});
const STATES = Object.freeze({
  ready:'idle', opening_mic:'listening', listening:'listening',
  transcribing:'thinking', thinking:'thinking', replying:'thinking',
  summarizing:'thinking', preparing_voice:'thinking', speaking:'speaking',
  error:'attention', suspended:'paused', closing:'paused',
});
export const visualMode = state => Object.hasOwn(STATES, state) ? STATES[state] : 'idle';

export class ConversationVisual {
  constructor(avatar) {
    this.avatar = avatar;
    this.mode = 'idle';
    this.requested = 'idle';
    this.since = 0;
    this.pose = {...VISUALS.idle.pose};
    this.avatar.setExpression('neutral');
    this.avatar.setTalkGain(0);
  }

  request(state, now) {
    const mode = visualMode(state);
    if (mode !== this.requested) {
      this.requested = mode;
      this.since = now;
    }
  }

  update(dt, now) {
    // A short hold coalesces fast preparation/transcription transitions, without
    // delaying lip-sync or cancellation. Related states share the same style.
    if (this.mode !== this.requested && now - this.since >= 180) {
      this.mode = this.requested;
      this.avatar.setExpression(VISUALS[this.mode].expression);
    }
    const target = VISUALS[this.mode];
    const blend = 1 - Math.exp(-Math.max(0, dt) * 5);
    for (const key of Object.keys(this.pose)) this.pose[key] += (target.pose[key] - this.pose[key]) * blend;
    this.avatar.setTalkGain(target.talkGain);
    this.apply();
  }

  apply() {
    // Retain a little of the runtime's natural idle motion and blinking. No mouth
    // parameter or expression with an open mouth can override playback lip-sync.
    this.avatar.setParameters(this.pose, 0.75);
  }
}
