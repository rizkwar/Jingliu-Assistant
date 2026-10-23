import {createHash} from 'node:crypto';

// The reviewed production bundle already exposes advanceStable(). Preserve the
// old HD-only adapter for earlier preview checkouts, guarded by exact hashes.
const HASH='188ffa03914eb5ed765d98b7aa3cd273bdc5760cc0755ed92dab2ec42e096326';
export function previewRuntime(input) {
  let source=input.toString('utf8').replace(/\r\n/g,'\n');
  if(createHash('sha256').update(source).digest('hex')==='1576e6550bcc64860cd4d06921f9a9df067e553bb4bd6301e6a32ffc45086b7e')return Buffer.from(source);
  if(createHash('sha256').update(source).digest('hex')!==HASH)throw new Error('Review the runtime adapter after updating the vendor bundle');
  const replacements=[
    ['function E(M) {','function E(M, draw = true, visualDt = M) {'],
    ['const R = A(M), W = H.step(R, M), Q = U.pos, ne = U.rest;',
      'const R = A(M), W = H.step(R, M), Q = U.pos, ne = U.rest;\n    if (!draw) return;'],
    ['$?.update(R, W, M, Fn(', '$?.update(R, W, visualDt, Fn('],
    ['    /** Update motion and lip sync without drawing a hidden preview. */\n    advanceParameters(M) {','    /** Bounded spring steps with a single mesh draw per elapsed frame. */\n    advanceStable(M) {\n      if (!z) advanceFrame(M, (dt, draw, total) => E(dt, draw, total));\n    },\n    /** Update motion and lip sync without drawing a hidden preview. */\n    advanceParameters(M) {'],
  ];
  for(const [before,after] of replacements){
    if(source.split(before).length!==2)throw new Error('Preview runtime patch did not match');
    source=source.replace(before,after);
  }
  return Buffer.from("import {advanceFrame} from './stable-step.js';\n"+source);
}
