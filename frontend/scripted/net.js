// Network layer of the scripted tour. Two fetch wrappers, never both at once:
//  · replay(): Scripted mode. /api/* calls are answered from a recording of a real run (fixtures/<branch>/chNN.json);
//    nothing reaches a server. JSON comes back as a Response; SSE streams are rebuilt frame by frame with the
//    recorded gaps (compressed), so the app's own streaming code runs unchanged.
//  · record(): Live mode with ?record. Every /api/* request and response (SSE frames with timing) is teed into
//    a recording, cut into chapters by the director, with a snapshot of the project at each chapter start.
// Project and session ids are normalised to {pid} so a recording replays into any demo project.
const realFetch = window.fetch.bind(window);
const API = /\/api\//;
const VOLATILE = new Set(['session_id', 'chat_turns', 'conversation_summary', 'research_file', 'active_thinker', 'project_id']);

export const net = { mode: 'off', pid: null, speed: 1 };

// ---------- shared helpers ----------
function pathOf(url) {
  const u = new URL(typeof url === 'string' ? url : url.url, location.href);
  return u.pathname + u.search;
}
// While recording, the project is created mid-chapter, so its id is read live (net.pidOf).
const pidNow = () => (net.pidOf && net.pidOf()) || net.pid;
const norm = (s) => { const pid = pidNow(); return pid ? String(s).split(encodeURIComponent(pid)).join('{pid}').split(pid).join('{pid}') : String(s); };
const denorm = (s) => { const pid = pidNow(); return pid ? String(s).split('{pid}').join(pid) : String(s); };
function stable(v) {
  if (Array.isArray(v)) return `[${v.map(stable).join(',')}]`;
  if (v && typeof v === 'object') return `{${Object.keys(v).sort().filter((k) => !VOLATILE.has(k)).map((k) => `${JSON.stringify(k)}:${stable(v[k])}`).join(',')}}`;
  return JSON.stringify(v);
}
function sigOf(body) {
  if (!body) return '';
  try { return norm(stable(JSON.parse(body))); } catch (_) { return ''; }
}
function parseFrames(buffer, onFrame) {
  let idx;
  while ((idx = buffer.indexOf('\n\n')) >= 0) {
    const frame = buffer.slice(0, idx);
    buffer = buffer.slice(idx + 2);
    const data = frame.split('\n').filter((l) => l.startsWith('data: ')).map((l) => l.slice(6)).join('\n');
    if (data) { try { onFrame(JSON.parse(data)); } catch (_) { /* keep-alive */ } }
  }
  return buffer;
}

// ---------- replay (Scripted) ----------
let book = null; // { chapters: [{ calls: [...] }], cursor: chapterIndex }
const used = new WeakSet();

export function replay(chapters, startAt = 0) {
  book = { chapters, cursor: startAt };
  net.mode = 'replay';
  window.fetch = replayFetch;
}
export function setChapter(i) { if (book) book.cursor = i; }

function findCall(method, path, sig) {
  const pools = [book.chapters[book.cursor], book.chapters[book.cursor + 1]].filter(Boolean).map((c) => c.calls || []);
  for (const strict of [true, false]) {
    for (const calls of pools) {
      const hit = calls.find((c) => !used.has(c) && c.method === method && c.path === path && (!strict || c.sig === sig));
      if (hit) return hit;
    }
  }
  // GETs may be asked again (panels reload): answer with the last matching one, used or not.
  if (method === 'GET') for (const calls of pools) { const hit = [...calls].reverse().find((c) => c.method === 'GET' && c.path === path); if (hit) return hit; }
  return null;
}

async function replayFetch(input, init = {}) {
  const url = typeof input === 'string' ? input : input.url;
  if (!API.test(url)) return realFetch(input, init);
  const method = (init.method || 'GET').toUpperCase();
  const path = norm(pathOf(url));
  const call = findCall(method, path, sigOf(init.body));
  if (call) used.add(call);
  await wait((method === 'GET' ? 120 : 900) / net.speed);
  if (!call) return offScript(path, init);
  if (call.sse) return sseResponse(call.sse);
  return new Response(denorm(JSON.stringify(call.json ?? {})), { status: call.status || 200, headers: { 'Content-Type': 'application/json' } });
}

// Something the recording does not contain (the viewer went off-script). Say so honestly; never invent.
function offScript(path, init) {
  const accept = (init.headers && (init.headers.Accept || init.headers.accept)) || '';
  const note = 'This is the scripted demo, replaying a recorded run, and that step was not recorded. Switch the tour to Live to try anything you like.';
  if (/event-stream/.test(accept)) return sseResponse([{ dt: 0, event: 'direct_answer', payload: { answer: note, degraded: true } }, { dt: 50, event: 'complete', payload: {} }]);
  return new Response(JSON.stringify({ error: note }), { status: 404, headers: { 'Content-Type': 'application/json' } });
}

function sseResponse(frames) {
  const enc = new TextEncoder();
  const stream = new ReadableStream({
    async start(ctl) {
      for (const f of frames) {
        // Real gaps, compressed: a 40-second paper read becomes a beat, not a wait.
        await wait(Math.min(f.dt || 0, f.cap || 650) / net.speed);
        ctl.enqueue(enc.encode(`data: ${denorm(JSON.stringify({ event: f.event, payload: f.payload }))}\n\n`));
      }
      ctl.close();
    },
  });
  return new Response(stream, { status: 200, headers: { 'Content-Type': 'text/event-stream' } });
}

// ---------- record (Live + ?record) ----------
export const tape = { meta: {}, chapters: [] };

export function record(meta) {
  tape.meta = { ...meta, recorded_at: new Date().toISOString() };
  tape.chapters = [];
  net.mode = 'record';
  window.fetch = recordFetch;
}
export function cut(id, snapshot) { tape.chapters.push({ id, snapshot, calls: [] }); }

async function recordFetch(input, init = {}) {
  const url = typeof input === 'string' ? input : input.url;
  const res = await realFetch(input, init);
  if (!API.test(url) || !tape.chapters.length) return res;
  const entry = { method: (init.method || 'GET').toUpperCase(), path: norm(pathOf(url)), sig: sigOf(init.body), status: res.status };
  tape.chapters[tape.chapters.length - 1].calls.push(entry);
  if (!/event-stream/.test(res.headers.get('content-type') || '') || !res.body) {
    try {
      const body = await res.clone().json();
      // The project is created inside the first chapter: learn its id before normalising anything.
      if (entry.method === 'POST' && entry.path === '/api/projects') net.pid = body.project?.project_id || body.project?.id || net.pid;
      entry.json = JSON.parse(norm(JSON.stringify(body)));
    } catch (_) { entry.json = null; }
    return res;
  }
  const [mine, theirs] = res.body.tee();
  entry.sse = [];
  (async () => {
    const reader = mine.getReader(); const dec = new TextDecoder();
    let buf = ''; let last = performance.now();
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buf = parseFrames(buf + dec.decode(value, { stream: true }).replace(/\r\n/g, '\n'), (evt) => {
        const now = performance.now();
        entry.sse.push({ dt: Math.round(now - last), event: evt.event, payload: JSON.parse(norm(JSON.stringify(evt.payload || {}))) });
        last = now;
      });
    }
  })();
  return new Response(theirs, { status: res.status, headers: res.headers });
}

// One file per chapter, so seeking loads only what it needs.
export function chapterFiles() {
  return tape.chapters.map((c, i) => ({ name: `ch${String(i).padStart(2, '0')}.json`, body: JSON.stringify({ meta: tape.meta, ...c }) }));
}

export function stop() { window.fetch = realFetch; net.mode = 'off'; net.pidOf = null; book = null; }

const wait = (ms) => new Promise((r) => setTimeout(r, ms));
