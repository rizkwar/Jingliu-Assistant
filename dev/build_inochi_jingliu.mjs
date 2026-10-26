// Standalone authoring experiment for Inochi Creator 0.8.6. No app integration.
// Start with the actual PSD import saved by Creator, retaining its texture blob.
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import {authorPoint} from './jingliu_inochi_keyforms.mjs';

const args=process.argv.slice(2);
if(args.length!==2) throw Error('Usage: node dev/build_inochi_jingliu.mjs imported.inx output.inx');
const [source,output]=args.map(p=>path.resolve(p));
if(source===output || fs.existsSync(output)) throw Error('Choose a new output file; the imported master is preserved.');
const binary=fs.readFileSync(source);
if(binary.subarray(0,8).toString()!=='TRNSRTS\0') throw Error('Expected an Inochi INX puppet.');
const length=binary.readUInt32BE(8), tail=binary.subarray(12+length);
if(tail.subarray(0,8).toString()!=='TEX_SECT') throw Error('Missing embedded textures.');
const puppet=JSON.parse(binary.subarray(12,12+length).toString('utf8'));
const nodes=puppet.nodes.children;
if(nodes.length!==23 || nodes.some(n=>n.type!=='Part')) throw Error('Expected the flat 23-part PhotoCraft PSD import.');
if(puppet.param?.length) throw Error('The input already has parameters; refusing to replace authored work.');

const sha=b=>crypto.createHash('sha256').update(b).digest('hex');
const occupied=new Set([puppet.nodes.uuid,...nodes.map(n=>n.uuid)]);
function uuid(){let n=900001;while(occupied.has(n))n++;occupied.add(n);return n;}
function descriptor(n){
  const name=n.name, side=/right| R\b/.test(name)?1:/left| L\b/.test(name)?-1:0;
  const [tx,ty]=n.transform.trans;
  const d={cx:tx+627,cy:ty+627,side};
  if(name.startsWith('Hair')){
    d.type='hair';d.part=name.includes('side bang')?'side':name.includes('bang')?'bang':'long';
    d.root=d.part==='bang'?260:d.part==='side'?300:name.includes('crown')?240:560;
    d.tip=d.part==='bang'?650:d.part==='side'?740:1200;
  }else if(name.startsWith('Eye')){d.type='eye';d.component=name.includes('open')?'open':'closed';}
  else if(name.startsWith('Brow'))d.type='brow';
  else if(name.startsWith('Nose'))d.type='nose';
  else if(name.startsWith('Mouth'))d.type='mouth';
  else if(name.startsWith('Earring'))d.type='earring';
  else if(name==='Neck')d.type='neck';
  else if(name.startsWith('Torso'))d.type='body';
  else d.type='face';
  return d;
}

const parts=nodes.map(n=>{
  const original=n.mesh, xs=original.verts.filter((_,i)=>i%2===0),ys=original.verts.filter((_,i)=>i%2===1);
  const x0=Math.min(...xs),x1=Math.max(...xs),y0=Math.min(...ys),y1=Math.max(...ys);
  const detail=/^(Eye|Brow|Mouth|Nose|Earring)/.test(n.name)?10:28;
  const cols=Math.max(2,Math.ceil((x1-x0)/detail)),rows=Math.max(2,Math.ceil((y1-y0)/detail));
  const verts=[],uvs=[],indices=[],points=[];
  for(let j=0;j<=rows;j++)for(let i=0;i<=cols;i++){
    const x=x0+(x1-x0)*i/cols,y=y0+(y1-y0)*j/rows;
    verts.push(x,y);uvs.push(i/cols,j/rows);
    points.push([x+n.transform.trans[0]+627,y+n.transform.trans[1]+627]);
  }
  for(let j=0;j<rows;j++)for(let i=0;i<cols;i++){
    const a=j*(cols+1)+i,b=a+1,c=a+cols+1,d=c+1;
    // Same winding as Creator's imported rectangle (clockwise in screen Y).
    indices.push(a,c,b,b,c,d);
  }
  if(points.length>=65536)throw Error('INX meshes use 16-bit indices.');
  n.mesh={verts,uvs,indices,origin:original.origin??[0,0]};
  return {node:n,points,layer:descriptor(n)};
});

function deformation(part,pose,swing=0){
  return part.points.map(([x,y])=>{
    const [px,py]=authorPoint(x,y,part.layer,pose,swing);
    return [Number((px-x).toFixed(5)),Number((py-y).toFixed(5))];
  });
}
function parameter(name,xy,make){
  return {uuid:uuid(),name,is_vec2:xy,min:[-1,xy?-1:0],max:[1,xy?1:1],defaults:[0,0],
    axis_points:[ [0,.5,1],xy?[0,.5,1]:[0] ],merge_mode:'Additive',
    bindings:parts.map(part=>({node:part.node.uuid,param_name:'deform',
      values:[-1,0,1].map(x=>(xy?[-1,0,1]:[0]).map(y=>make(part,x,y))),
      isSet:[-1,0,1].map(()=>xy?[true,true,true]:[true]),interpolate_mode:'Linear'}))};
}
puppet.param=[
  parameter('Head XY - small turn',true,(p,x,y)=>deformation(p,{angleX:x*10,angleY:y*3})),
  parameter('Head tilt',false,(p,x)=>deformation(p,{angleZ:x*3})),
  parameter('Hair sway - manual test',false,(p,x)=>deformation(p,{},x*8)),
];

// Check real keyforms and their interpolation, including combined controls.
let minRatio=Infinity, flipped=0, triangles=0;
for(const p of parts){
  const bindings=puppet.param.map(param=>param.bindings.find(b=>b.node===p.node.uuid));
  function blend(binding,x,y=0){
    const i=x<=0?0:1,t=x<=0?x+1:x;
    const j=y<=0?0:1,s=y<=0?y+1:y;
    return p.points.map((_,k)=>[0,1].map(c=>{
      const a=binding.values[i][binding.values[i].length===1?0:j][k][c];
      const b=binding.values[i+1][binding.values[i+1].length===1?0:j][k][c];
      if(binding.values[i].length===1)return a*(1-t)+b*t;
      const cc=binding.values[i][j+1][k][c],d=binding.values[i+1][j+1][k][c];
      return (a*(1-t)+b*t)*(1-s)+(cc*(1-t)+d*t)*s;
    }));
  }
  const area=(v,a,b,c)=>(v[b][0]-v[a][0])*(v[c][1]-v[a][1])-(v[b][1]-v[a][1])*(v[c][0]-v[a][0]);
  for(const x of [-1,-.5,0,.5,1])for(const y of [-1,-.5,0,.5,1])for(const tilt of [-1,0,1])for(const sway of [-1,0,1]){
    const head=blend(bindings[0],x,y),roll=blend(bindings[1],tilt),hair=blend(bindings[2],sway);
    const moved=p.points.map(([px,py],k)=>[px+head[k][0]+roll[k][0]+hair[k][0],py+head[k][1]+roll[k][1]+hair[k][1]]);
    for(let i=0;i<p.node.mesh.indices.length;i+=3){
      const [a,b,c]=p.node.mesh.indices.slice(i,i+3);
      const ratio=area(moved,a,b,c)/area(p.points,a,b,c);
      minRatio=Math.min(minRatio,ratio);if(ratio<=0)flipped++;triangles++;
    }
  }
}
if(flipped)throw Error(`${flipped} inverted triangles; reduce or repair the keyforms.`);
const json=Buffer.from(JSON.stringify(puppet)),header=Buffer.alloc(12);
header.write('TRNSRTS\0');header.writeUInt32BE(json.length,8);
fs.mkdirSync(path.dirname(output),{recursive:true});
fs.writeFileSync(output,Buffer.concat([header,json,tail]),{flag:'wx'});
const report={format:'jingliu-inochi-rig-checkpoint',version:2,creatorVersion:'0.8.6',
  source:path.basename(source),output:path.basename(output),sourceSha256:sha(binary),textureSectionSha256:sha(tail),
  parts:parts.map(p=>({name:p.node.name,enabled:p.node.enabled,vertices:p.points.length,triangles:p.node.mesh.indices.length/3})),
  parameters:puppet.param.map(p=>({name:p.name,keyforms:p.is_vec2?9:3,bindings:p.bindings.length})),
  geometryChecks:{testedTriangleInstances:triangles,invertedTriangles:flipped,minimumAreaRatio:minRatio},
  limitations:['Small exploratory turns; no profile or newly painted side view.',
    'Manual hair-sway parameter only; no physics driver.',
    'Eye alternates remain hidden; blink, gaze and speech are not connected.',
    'Layer roots and hidden shoulder paint still require visual deformation review.',
    'Standalone authoring file; not loaded by the assistant.']};
fs.writeFileSync(output+'.verification.json',JSON.stringify(report,null,2));
console.log(JSON.stringify({output:path.basename(output),parts:parts.length,vertices:parts.reduce((n,p)=>n+p.points.length,0),...report.geometryChecks},null,2));
