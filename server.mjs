import http from 'node:http';
import { readFile, stat } from 'node:fs/promises';
import { dirname, resolve, extname, sep } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawn } from 'node:child_process';

const root = dirname(fileURLToPath(import.meta.url));
const portArg = process.argv.indexOf('--port');
const port = portArg < 0 ? 8765 : Number(process.argv[portArg + 1]);
if (!Number.isInteger(port) || port < 1024 || port > 65535) throw new Error('port must be 1024–65535');
const types = { '.html': 'text/html; charset=utf-8', '.css': 'text/css; charset=utf-8', '.mjs': 'text/javascript; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.json': 'application/json; charset=utf-8', '.svg': 'image/svg+xml', '.png': 'image/png', '.md': 'text/plain; charset=utf-8', '.csv': 'text/csv; charset=utf-8' };
const server = http.createServer(async (req, res) => {
  if (!['GET', 'HEAD'].includes(req.method)) { res.writeHead(405); return res.end(); }
  try {
    const pathname = decodeURIComponent(new URL(req.url, 'http://localhost').pathname);
    const path = resolve(root, `.${pathname === '/' ? '/index.html' : pathname}`);
    if (!path.startsWith(root + sep) || pathname.includes('\\') || pathname.includes('\0')) { res.writeHead(403); return res.end('Forbidden'); }
    const info = await stat(path); if (!info.isFile()) throw new Error('not a file');
    const contents = await readFile(path);
    res.writeHead(200, { 'Content-Type': types[extname(path)] || 'application/octet-stream', 'Content-Length': contents.length, 'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff', 'Referrer-Policy': 'no-referrer' }); res.end(req.method === 'HEAD' ? undefined : contents);
  } catch { res.writeHead(404); res.end('Not found'); }
});
server.on('error', err => { console.error(err.code === 'EADDRINUSE' ? `ポート ${port} は使用中です。node server.mjs --port 8766 で別ポートを指定できます。` : err.message); process.exitCode = 1; });
server.listen(port, '127.0.0.1', () => {
  const url = `http://127.0.0.1:${port}`; console.log(`GEAR / LAB: ${url}\n終了: Ctrl+C`);
  if (process.argv.includes('--open') && process.platform === 'win32') { const browser = spawn('explorer.exe', [url], { windowsHide: true, stdio: 'ignore' }); browser.on('error', () => console.log(`ブラウザで ${url} を開いてください。`)); }
});
