import {createHash} from 'node:crypto';

// Optional preview API only. Production vendor and its existing advance() stay
// unchanged. Verify the known HD bundle before adapting its private internals.
const HASH='188ffa03914eb5ed765d98b7aa3cd273bdc5760cc0755ed92dab2ec42e096326';
export function previewRuntime(input) {
  let source=input.toString('utf8').replace(/\r\n/g,'\n');
  if(createHash('sha256').update(source).digest('hex')!==HASH)throw new Error('Review the runtime adapter after updating the vendor bundle');
  const replacements=[
    ['function E(M) {','function E(M, draw = true, visualDt = M) {'],
    ['const R = A(M), W = H.step(R, M), Q = U.pos, ne = U.rest;',
      'const R = A(M), W = H.step(R, M), Q = U.pos, ne = U.rest;\n    if (!draw) return;'],
    ['$?.update(R, W, M, Fn(', '$?.update(R, W, visualDt, Fn('],
    ['    advanceParameters(M) {','    advanceStable(M) {\n      if (!z) advanceFrame(M, (dt, draw, total) => E(dt, draw, total));\n    },\n    advanceParameters(M) {'],
  ];
  for(const [before,after] of replacements){
    if(source.split(before).length!==2)throw new Error('Preview runtime patch did not match');
    source=source.replace(before,after);
  }
  return Buffer.from("import {advanceFrame} from './stable-step.js';\n"+source);
}
