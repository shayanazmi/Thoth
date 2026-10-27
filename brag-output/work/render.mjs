// Renders composition/index.html frame by frame through headless Chrome (raw CDP, no npm deps).
// usage: node render.mjs <outDir> [fps=30] [duration=18] [onlyTimes=comma,list]
import { spawn } from 'node:child_process';
import { mkdirSync, writeFileSync, rmSync } from 'node:fs';
import { join, dirname, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const outDir = resolve(process.argv[2] || join(here, 'frames'));
const fps = Number(process.argv[3] || 30);
const duration = Number(process.argv[4] || 18);
const only = process.argv[5] ? process.argv[5].split(',').map(Number) : null;
const page = pathToFileURL(join(here, '..', 'composition', 'index.html')).href;
const CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const PORT = 9333;
const profile = join(here, 'chrome-profile');

mkdirSync(outDir, { recursive: true });
const chrome = spawn(CHROME, ['--headless=new', `--remote-debugging-port=${PORT}`, `--user-data-dir=${profile}`,
  '--allow-file-access-from-files', '--hide-scrollbars', '--force-device-scale-factor=1', '--window-size=1080,1920', 'about:blank'],
  { stdio: 'ignore' });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

try {
  let target;
  for (let i = 0; i < 50 && !target; i++) {
    try { target = await (await fetch(`http://127.0.0.1:${PORT}/json/new?${page}`, { method: 'PUT' })).json(); }
    catch { await sleep(200); }
  }
  const ws = new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((r) => ws.addEventListener('open', r, { once: true }));
  let id = 0; const pending = new Map();
  ws.addEventListener('message', (ev) => { const m = JSON.parse(ev.data); if (m.id && pending.has(m.id)) { pending.get(m.id)(m); pending.delete(m.id); } });
  const send = (method, params = {}) => new Promise((res, rej) => {
    const i = ++id; pending.set(i, (m) => (m.error ? rej(new Error(JSON.stringify(m.error))) : res(m.result)));
    ws.send(JSON.stringify({ id: i, method, params }));
  });
  const evalJs = (expression) => send('Runtime.evaluate', { expression, awaitPromise: true, returnByValue: true });

  await send('Emulation.setDeviceMetricsOverride', { width: 1080, height: 1920, deviceScaleFactor: 1, mobile: false });
  await send('Page.enable');
  await send('Page.navigate', { url: page });
  for (let i = 0; i < 100; i++) { const r = await evalJs('document.readyState'); if (r.result.value === 'complete') break; await sleep(100); }
  await evalJs(`document.fonts.ready.then(() => Promise.all([...document.querySelectorAll('[style*=url],#bust,.bust2')].map(() => 0)))`);
  await evalJs(`new Promise((r) => { const i = new Image(); i.onload = i.onerror = r; i.src = '../../frontend/assets/thoth_bust.jpg'; })`);
  const fonts = await evalJs(`[...document.fonts].filter(f => f.status === 'loaded').map(f => f.family).join(',')`);
  console.log('fonts loaded:', fonts.result.value || '(none: fallbacks in use)');

  const times = only ?? Array.from({ length: Math.round(fps * duration) }, (_, f) => f / fps);
  for (let k = 0; k < times.length; k++) {
    const t = times[k];
    await evalJs(`seek(${t}); new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))`);
    const shot = await send('Page.captureScreenshot', { format: 'png', clip: { x: 0, y: 0, width: 1080, height: 1920, scale: 1 } });
    const name = only ? `t${t.toFixed(2)}.png` : `f${String(k).padStart(5, '0')}.png`;
    writeFileSync(join(outDir, name), Buffer.from(shot.data, 'base64'));
    if (!only && k % 60 === 0) console.log(`frame ${k}/${times.length}`);
  }
  ws.close();
} finally {
  chrome.kill();
  await sleep(300);
  try { rmSync(profile, { recursive: true, force: true }); } catch {}
}
