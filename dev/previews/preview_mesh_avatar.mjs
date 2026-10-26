// Stage 3 only: a local, read-only review surface, separate from the assistant.
import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { resolve } from 'node:path';
import { execFile } from 'node:child_process';

const root = fileURLToPath(new URL('../..', import.meta.url));
const studio = resolve(root, '.cache/mesh-avatar-studio');
const project = resolve(studio, 'projects/jingliu');
const port = 8765;
const origin = `http://127.0.0.1:${port}`;
const files = new Map([
  ['/', [resolve(root, 'dev/previews/avatar-preview/index.html'), 'text/html; charset=utf-8']],
  ['/viewer.js', [resolve(root, 'dev/previews/avatar-preview/viewer.js'), 'text/javascript; charset=utf-8']],
  ['/style.css', [resolve(root, 'dev/previews/avatar-preview/style.css'), 'text/css; charset=utf-8']],
  ['/mesh-avatar.js', [resolve(studio, 'packages/runtime/dist/index.js'), 'text/javascript; charset=utf-8']],
  ['/avatar.mavatar', [resolve(project, 'exports/jingliu-playback.mavatar'), 'application/octet-stream']],
  ['/runtime-license.txt', [resolve(studio, 'packages/runtime/LICENSE'), 'text/plain; charset=utf-8']],
]);

try {
  // Explicit file allowlist: no directory browsing or access to the assistant's files.
  const assets = new Map(await Promise.all([...files].map(async ([url, [path, type]]) =>
    [url, {body: await readFile(path), type}])));
  const server = createServer((request, response) => {
    response.setHeader('Cache-Control', 'no-store');
    response.setHeader('X-Content-Type-Options', 'nosniff');
    response.setHeader('Referrer-Policy', 'no-referrer');
    response.setHeader('Permissions-Policy', 'camera=(), microphone=(), geolocation=()');
    response.setHeader('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self' blob:; img-src 'self' blob: data:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'");
    if (request.headers.host !== `127.0.0.1:${port}` || !['GET', 'HEAD'].includes(request.method)) {
      response.writeHead(403).end('This preview is read-only and local.');
      return;
    }
    const path = new URL(request.url, origin).pathname;
    if (path === '/favicon.ico') { response.writeHead(204).end(); return; }
    const asset = assets.get(path);
    if (!asset) { response.writeHead(404).end('Not found.'); return; }
    response.writeHead(200, {'Content-Type': asset.type, 'Content-Length': asset.body.length});
    response.end(request.method === 'HEAD' ? undefined : asset.body);
  });
  server.on('error', error => {
    console.error(error.code === 'EADDRINUSE'
      ? `Port ${port} is already in use. Close the previous preview before starting another.`
      : `Could not start the preview: ${error.code ?? 'unknown error'}`);
    process.exitCode = 1;
  });
  server.listen(port, '127.0.0.1', () => {
    console.log(`Jingliu v5 avatar preview: ${origin}`);
    console.log('This is the separate Stage 3 preview. Mouth tests are silent.');
    console.log('Close this console or press Ctrl+C to stop the preview server.');
    if (process.argv.includes('--open') && process.platform === 'win32') {
      execFile('powershell.exe', ['-NoProfile', '-NonInteractive', '-Command', `Start-Process '${origin}'`],
        {windowsHide: true}, error => { if (error) console.log(`Open ${origin} in your browser.`); });
    }
  });
  process.on('SIGINT', () => { server.close(); server.closeAllConnections(); });
  process.on('SIGTERM', () => { server.close(); server.closeAllConnections(); });
} catch (error) {
  console.error('The local avatar preview assets are missing or unreadable.');
  console.error('See dev/README.md for the prepared project and export locations.');
  console.error(`File error: ${error.code ?? 'unknown error'}`);
  process.exitCode = 1;
}
