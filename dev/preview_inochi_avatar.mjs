// Standalone, read-only, loopback-only inspection. No assistant imports.
import {createServer} from 'node:http';
import {readFile} from 'node:fs/promises';
import {execFile} from 'node:child_process';
import {promisify} from 'node:util';
import {fileURLToPath, pathToFileURL} from 'node:url';
import {resolve, join} from 'node:path';

const root = fileURLToPath(new URL('..', import.meta.url));
const run = promisify(execFile);

// Keep the bound port available without trusting request headers.
export function createViewerServer(assets) {
  const server = createServer((request, response) => handle(request, response));
  function handle(request, response) {
    const expected = `127.0.0.1:${server.address().port}`, origin = `http://${expected}`;
    response.setHeader('Cache-Control', 'no-store');
    response.setHeader('X-Content-Type-Options', 'nosniff');
    response.setHeader('Referrer-Policy', 'no-referrer');
    response.setHeader('Permissions-Policy', 'camera=(), microphone=(), geolocation=()');
    response.setHeader('Content-Security-Policy', "default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'");
    if (request.headers.host !== expected || !['GET', 'HEAD'].includes(request.method) || (request.headers.origin && request.headers.origin !== origin)) {
      response.writeHead(403).end('This preview is read-only and local.'); return;
    }
    if (request.url === '/favicon.ico') { response.writeHead(204).end(); return; }
    const asset = assets.get(request.url);
    if (!asset) { response.writeHead(404).end('Not found.'); return; }
    response.writeHead(200, {'Content-Type': asset.type, 'Content-Length': asset.body.length});
    response.end(request.method === 'HEAD' ? undefined : asset.body);
  }
  return server;
}

async function main() {
  const args = process.argv.slice(2);
  const known = new Set(['--port', '--model', '--open']);
  let port = 0, model = 'authoring/jingliu-v5-idle-test-v2.inx';
  for (let i = 0; i < args.length; i++) {
    if (!known.has(args[i])) throw Error('Use --port NUMBER, --model RELATIVE_INX, or --open.');
    if (args[i] === '--port') port = Number(args[++i]);
    else if (args[i] === '--model') model = args[++i];
  }
  if (!Number.isInteger(port) || (port !== 0 && (port < 1024 || port > 65535))) throw Error('Choose port 0 (automatic) or a port from 1024 to 65535.');
  if (typeof model !== 'string' || model.startsWith('-')) throw Error('Choose a relative saved rig path.');
  let output;
  try {
    output = await run(join(root, '.venv/Scripts/python.exe'), [join(root, 'dev/prepare_inochi_viewer.py'), '--model', model],
      {cwd: root, windowsHide: true, timeout: 90000, maxBuffer: 2 * 1024 * 1024});
  } catch (error) { throw Error(error.stderr?.trim() || 'Could not prepare the viewer. Check the saved rig and project Python environment.'); }
  const prepared = JSON.parse(output.stdout), bundle = prepared.bundle;
  const modelBytes = await readFile(join(bundle, 'model.json')), manifest = JSON.parse(modelBytes);
  const assets = new Map([['/model.json', {body: modelBytes, type: 'application/json'}]]);
  for (const [name, type] of [['index.html', 'text/html; charset=utf-8'], ['style.css', 'text/css; charset=utf-8'],
    ['model.js', 'text/javascript; charset=utf-8'], ['renderer.js', 'text/javascript; charset=utf-8'], ['viewer.js', 'text/javascript; charset=utf-8']]) {
    const asset = {body: await readFile(join(root, 'dev/inochi-viewer', name)), type};
    assets.set(name === 'index.html' ? '/' : `/${name}`, asset);
  }
  for (const name of manifest.textures) {
    if (!/^\/texture-\d{2}\.png$/.test(name)) throw Error('Invalid prepared texture filename.');
    assets.set(name, {body: await readFile(join(bundle, name.slice(1))), type: 'image/png'});
  }
  const server = createViewerServer(assets);
  server.on('error', error => { console.error(error.code === 'EADDRINUSE' ? `Port ${port} is in use. Stop the earlier preview or use --port.` : 'Could not start the local preview.'); process.exitCode = 1; });
  server.listen(port, '127.0.0.1', () => {
    const origin = `http://127.0.0.1:${server.address().port}`;
    console.log(`Jingliu saved-rig inspection: ${origin}`);
    console.log(`${prepared.parts} parts, ${prepared.parameters} controls. Source ${prepared.sourceSha256.slice(0, 12)} unchanged.`);
    console.log('WebGL inspection subset, separate from the assistant. Close this console or press Ctrl+C to stop.');
    if (args.includes('--open') && process.platform === 'win32') {
      execFile('powershell.exe', ['-NoProfile', '-NonInteractive', '-Command', `Start-Process '${origin}'`], {windowsHide: true},
        error => { if (error) console.log(`Open ${origin} in your browser.`); });
    }
  });
  for (const signal of ['SIGINT', 'SIGTERM']) process.on(signal, () => { server.close(); server.closeAllConnections(); });
}

if (process.argv[1] && pathToFileURL(resolve(process.argv[1])).href === import.meta.url) main().catch(error => { console.error(error.message); process.exitCode = 1; });
