// Read-only localhost preview. Uses the exact assistant runtime and profile-free assets.
import {createServer} from 'node:http';
import {readFile} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import {resolve} from 'node:path';
import {execFile} from 'node:child_process';
import {previewRuntime} from './head-motion-study/preview-runtime.mjs';
const root=fileURLToPath(new URL('..',import.meta.url));
const web=resolve(root,'companion/avatar_web'),study=resolve(root,'scripts/head-motion-study');
const port=8766,origin=`http://127.0.0.1:${port}`;
const routes=new Map([
  ['/',[resolve(study,'index.html'),'text/html; charset=utf-8']],
  ...['study.js','motion.js','rig-review.js','idle-attention.js'].map(name=>['/'+name,[resolve(study,name),'text/javascript; charset=utf-8']]),
  ['/style.css',[resolve(study,'style.css'),'text/css; charset=utf-8']],
  ['/companion/avatar_web/idle-attention.js',[resolve(web,'idle-attention.js'),'text/javascript; charset=utf-8']],
  ...['conversation-state.js','render-quality.js','stable-step.js'].map(name=>['/'+name,[resolve(web,name),'text/javascript; charset=utf-8']]),
  ['/mesh-avatar.js',[resolve(web,'vendor/mesh-avatar.js'),'text/javascript; charset=utf-8']],
  ['/license.txt',[resolve(web,'vendor/LICENSE'),'text/plain; charset=utf-8']],
  ['/avatar.mavatar',[resolve(root,'.cache/mesh-avatar-studio/projects/jingliu/exports/jingliu-playback.mavatar'),'application/octet-stream']],
]);
try {
  const assets=new Map(await Promise.all([...routes].map(async([route,[path,type]])=>[route,{body:await readFile(path),type}])));
  assets.get('/mesh-avatar.js').body=previewRuntime(assets.get('/mesh-avatar.js').body);
  const server=createServer((request,response)=>{
    response.setHeader('Cache-Control','no-store');response.setHeader('X-Content-Type-Options','nosniff');
    response.setHeader('Referrer-Policy','no-referrer');response.setHeader('Permissions-Policy','camera=(), microphone=(), geolocation=()');
    response.setHeader('Content-Security-Policy',"default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self' blob:; img-src 'self' blob: data:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'");
    if(request.headers.host!==`127.0.0.1:${port}`||!['GET','HEAD'].includes(request.method)){response.writeHead(403).end();return;}
    const asset=assets.get(request.url);
    if(!asset){response.writeHead(404).end('Not found');return;}
    response.writeHead(200,{'Content-Type':asset.type,'Content-Length':asset.body.length});
    response.end(request.method==='HEAD'?undefined:asset.body);
  });
  server.on('error',error=>{console.error(error.code==='EADDRINUSE'?'Preview port 8766 is in use. Close the earlier preview.':'Could not start the local preview.');process.exitCode=1;});
  server.listen(port,'127.0.0.1',()=>{
    console.log(`Head motion study: ${origin}`);console.log('Close this console to stop. Speech tests are silent; this preview does not change assistant settings.');
    if(process.argv.includes('--open')&&process.platform==='win32')execFile('powershell.exe',['-NoProfile','-NonInteractive','-Command',`Start-Process '${origin}'`],{windowsHide:true},()=>{});
  });
  for(const signal of ['SIGINT','SIGTERM'])process.on(signal,()=>{server.close();server.closeAllConnections();});
}catch{console.error('Preview assets are missing. See docs/avatar-motion-checkpoint2.md.');process.exitCode=1;}
