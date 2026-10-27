// The director: plays tour.js like a film over the real app, and lets the viewer step through it.
//  Scripted: net.js replays a recorded real run; the director types, clicks and waits like a person would.
//  Live:     requests reach the real backend; the director never acts. It frames the control, explains it,
//            and waits for the real state change (approvals are always the viewer's).
//  ?record:  Live, plus every chapter is cut into fixtures with a snapshot of the project at its start.
// Chapters are self-contained: entering one loads its snapshot, so seeking, replaying and reels just work.
import { CHAPTERS, REELS, GLOSSARY, QUIZ } from './tour.js';
import { net, replay, setChapter, record, cut, chapterFiles, stop as stopNet } from './net.js';
import * as progress from './progress.js';

const DEMO = 'demo_thoth_tour';
const PREF_KEYS = ['thoth.theme', 'thoth.ws', 'thoth.sb', 'thoth.layout'];
const STORE = 'thoth.ui.v2';
const $ = (s, r = document) => r.querySelector(s);
const wait = (ms) => new Promise((r) => setTimeout(r, ms));
const reduced = () => matchMedia('(prefers-reduced-motion: reduce)').matches;

let ctx = null;            // core hooks from install()
let T = null;              // the running tour, null when idle
let branches = [];

export function init(core, branchList) { ctx = core; branches = branchList; }
export const running = () => !!T;

// ---------- Entry / exit ----------
export async function start({ branch = null, chapter = 0, mode = 'scripted', reel = null, autoplay = false, clean = false, recording = false, autopilot = false } = {}) {
  if (T) await exit(true);
  const b = branches.find((x) => x.id === branch);
  if (!b) return pickHunch({ mode, reel, autoplay, clean, recording, chapter, autopilot });
  const files = mode === 'scripted' ? await loadManifest(b) : null;
  if (mode === 'scripted' && !files) return pickHunch({ mode, reel, autoplay, clean, recording, chapter }, `"${b.title}" hasn't been recorded yet.`);
  const steps = reel ? REELS.find((r) => r.id === reel)?.chapters : null;
  T = {
    b, files, mode, recording, autoplay, clean, autopilot: mode === 'live' && autopilot, playing: true, speed: progress.get().speed || 1, cc: progress.get().cc !== false,
    order: steps || CHAPTERS.map((_, i) => i), at: 0, ci: -1, token: 0, prev: snapshotPrefs(), cache: {},
  };
  net.speed = T.speed;
  if (recording) { net.pidOf = () => ctx.state.projectId; record({ branch: b.id, hunch: b.hunch }); }
  mount();
  // The film needs both the conversation and the research file on screen (exit puts the layout back).
  $('#app').classList.remove('ws-collapsed', 'ws-wide');
  document.documentElement.classList.add('touring');
  if (clean) document.documentElement.classList.add('tour-clean');
  T.at = Math.max(0, T.order.indexOf(chapter));
  play();
}

export async function exit(silent = false) {
  if (!T) return;
  const t = T; T = null; t.token += 1;
  stopNet();
  if (t.recording) sendRecording(t.b.id);
  document.documentElement.classList.remove('touring', 'tour-clean');
  $('#tour')?.remove();
  $('#app').style.transform = '';
  restorePrefs(t);
  if (!silent) ctx.toast?.('Tour closed. Everything is back as you left it.');
}

function snapshotPrefs() {
  const app = $('#app');
  const saved = {};
  for (const k of PREF_KEYS) { try { saved[k] = localStorage.getItem(k); } catch (_) {} }
  return { pid: ctx.state.projectId, theme: document.documentElement.dataset.theme, cls: app.className, saved };
}
function restorePrefs(t) {
  const { state } = ctx;
  if (t.mode === 'scripted') {
    delete state.data[DEMO];
    state.projects = state.projects.filter((p) => p.id !== DEMO);
    try { localStorage.removeItem(`${STORE}.${DEMO}`); } catch (_) {}
  }
  // Live work is real: stay in the project it made. Scripted leaves no trace.
  if (t.mode === 'scripted') state.projectId = t.prev.pid && state.projects.some((p) => p.id === t.prev.pid) ? t.prev.pid : null;
  try { localStorage.setItem(`${STORE}.current`, state.projectId || ''); } catch (_) {}
  if (t.prev.theme) document.documentElement.dataset.theme = t.prev.theme; else delete document.documentElement.dataset.theme;
  $('#app').className = t.prev.cls;
  // The tour clicks the real theme and layout controls, which persist themselves; put those back too.
  for (const [k, v] of Object.entries(t.prev.saved || {})) { try { if (v == null) localStorage.removeItem(k); else localStorage.setItem(k, v); } catch (_) {} }
  ctx.emit();
}

async function loadManifest(b) {
  try {
    const r = await fetch(`/scripted/fixtures/${b.id}/manifest.json`, { cache: 'no-cache' });
    if (!r.ok) return null;
    return await r.json();
  } catch (_) { return null; }
}
async function chapterData(i) {
  if (T.cache[i]) return T.cache[i];
  const name = T.files.chapters?.[i];
  if (!name) return null;
  try {
    const r = await fetch(`/scripted/fixtures/${T.b.id}/${name}`, { cache: 'no-cache' });
    return (T.cache[i] = r.ok ? await r.json() : null);
  } catch (_) { return null; }
}

// ---------- The play loop ----------
async function play() {
  while (T && T.at < T.order.length) {
    const token = T.token;
    const ok = await runChapter(T.order[T.at], token);
    if (!T || token !== T.token) return;           // seeked or exited meanwhile; the seek restarted the loop
    if (ok) progress.watched(T.b.id, CHAPTERS[T.order[T.at]].id);
    T.continuous = ok && T.order[T.at + 1] === T.order[T.at] + 1;
    if (T.recording) sendRecording(T.b.id);
    T.at += 1;
    progress.set({ last: { branch: T.b.id, chapter: T.order[Math.min(T.at, T.order.length - 1)] } });
    renderBar();
  }
  if (T) finale();
}

export function seek(orderIndex) {
  if (!T) return;
  T.token += 1;
  T.at = Math.max(0, Math.min(orderIndex, T.order.length - 1));
  T.playing = true;
  T.continuous = false;
  hideBeat(); hideQuiz();
  renderBar();
  play();
}

async function runChapter(ci, token) {
  const ch = CHAPTERS[ci];
  T.ci = ci;
  renderBar();
  if (T.mode === 'scripted') {
    const data = await chapterData(ci);
    if (!alive(token)) return false;
    if (!data) { await chapterCard(ch, token, 'Not recorded yet for this hunch. Skipping ahead.'); T.continuous = false; return false; }
    // Playing straight through, the project is already where the recording was (and a stream from the last
    // chapter may still be writing into it). Only a jump loads the chapter's snapshot.
    if (T.continuous) setChapter(ci);
    else if (ch.jumpFrom) {
      // This chapter watches something the previous one started (the trial stream): start it again, quietly.
      await enterChapterState(ci, data);
      ch.jumpFrom.prepare?.(api().d);
      ctx.emit();
      setChapter(ch.jumpFrom.chapter);
      await perform(ch.jumpFrom.do, token);
      await until(ch.jumpFrom.until ? () => ch.jumpFrom.until(api()) : () => true, 15000, token);
      setChapter(ci);
    } else await enterChapterState(ci, data);
  } else {
    // Live always begins from the home screen, with a fresh project made by the viewer's own hunch.
    if (ci === 0 && ctx.state.projectId) { ctx.actions.home?.(); await wait(900); }
    if (T.recording) cut(ch.id, normSnapshot());
  }
  if (ch.card !== false) await chapterCard(ch, token);
  for (const step of ch.steps) {
    if (!alive(token)) return false;
    if (step.when && !step.when(api())) continue;
    await runStep(step, token);
  }
  if (alive(token) && ch.quiz && QUIZ[ch.quiz] && !T.autoplay) await quiz(QUIZ[ch.quiz], token);
  return alive(token);
}

const alive = (token) => T && token === T.token;

// A recorded chapter starts from the project exactly as it was when the recording reached it.
async function enterChapterState(ci, data) {
  const { state } = ctx;
  net.pid = DEMO;
  if (!state.projects.some((p) => p.id === DEMO)) state.projects.unshift({ id: DEMO, title: T.b.title, updated: new Date().toISOString() });
  const snap = data.snapshot ? JSON.parse(JSON.stringify(data.snapshot).split('{pid}').join(DEMO)) : null;
  if (snap) state.data[DEMO] = { ...snap, activeThinker: null };
  else delete state.data[DEMO];
  if (net.mode !== 'replay') replay(await Promise.all(CHAPTERS.map((_, i) => chapterData(i))), ci);
  setChapter(ci);
  const target = data.snapshot ? DEMO : null;
  if (state.projectId !== target) await ctx.scene(target ? 'enter' : 'leave', () => { state.projectId = target; ctx.emit(); });
  else ctx.emit();
}

function normSnapshot() {
  const { state } = ctx;
  const pid = state.projectId;
  if (!pid || !state.data[pid]) return null;
  net.pid = pid;
  return JSON.parse(JSON.stringify(state.data[pid]).split(pid).join('{pid}'));
}

// ---------- Steps ----------
// { caption, sub, target, do, beat, until, hold, live, hotspots, layout, scene, timeout }
async function runStep(s, token) {
  const a = api();
  if (s.caption) caption(fill(s.caption), s.sub && fill(s.sub));
  if (s.target) frame(s.target);
  if (s.hotspots) hotspots(s.hotspots);
  // Live autopilot (for recording) acts like Scripted, except at approval gates, which wait for a human.
  const acts = T.mode === 'scripted' || (T.autopilot && !s.gate);
  if (s.beat && !T.autoplay && !(T.autopilot && !s.gate)) {
    await beat(s, token);
  } else if (s.do) {
    if (acts) await perform(s.do, token);
    else await coach(s, token);
  }
  if (!alive(token)) return;
  if (s.until) {
    const limit = s.timeout ?? (T.mode === 'scripted' ? 90000 : Infinity);
    if (T.mode === 'live' && !s.do && s.live) liveHint(fill(s.live));
    await until(() => s.until(a), limit, token);
    liveHint('');
  }
  await hold(s.hold ?? 2200, token);
  hotspots(null);
}

// Live: show where, say what to do, wait for the viewer (never act for them).
async function coach(s, token) {
  liveHint(fill(s.live || s.caption || 'Your move.'));
  if (!s.until) await until(() => false, s.hold ?? 6000, token);
}

async function perform(action, token) {
  const list = Array.isArray(action[0]) ? action : [action];
  for (const [kind, ...args] of list) {
    if (!alive(token)) return;
    await gate(token);
    if (kind === 'type') await typeInto(args[0], fill(args[1]), token);
    else if (kind === 'send') { const f = $(args[0] || '#composer'); f?.requestSubmit(); }
    else if (kind === 'click') await clickOn(args[0], token);
    else if (kind === 'act') ctx.actions[args[0]]?.(args[1]);
    else if (kind === 'say') ctx.say(fill(args[0]));
    else if (kind === 'call') await args[0](api());
    else if (kind === 'wait') await hold(args[0], token);
    else if (kind === 'dialog') await dialog(args[0] != null ? fill(args[0]) : null, args[1] || 'confirm', token);
  }
}

async function typeInto(sel, text, token) {
  const el = await find(sel, token);
  if (!el) return;
  frame(el);
  el.focus({ preventScroll: true });
  el.value = '';
  for (const ch of text) {
    if (!alive(token)) return;
    await gate(token);
    el.value += ch;
    el.dispatchEvent(new Event('input', { bubbles: true }));
    await wait(reduced() ? 0 : Math.min(35 + Math.random() * 55, 4000 / text.length) / T.speed);
  }
}

async function clickOn(sel, token) {
  const el = await find(sel, token);
  if (!el) return;
  el.scrollIntoView({ block: 'nearest', behavior: reduced() ? 'auto' : 'smooth' });
  frame(el);
  await hold(500, token);
  // The app re-renders by innerHTML; a node found half a second ago may be detached by now.
  const now = (typeof sel === 'string' && document.querySelector(sel)) || el;
  ripple(now);
  now.click();
}

async function dialog(text, which, token) {
  const box = await find(() => document.querySelector('.scrim .dialog, dialog.th-dialog[open] form'), token);
  if (!box) return;
  if (box.closest('dialog')) { await hold(1400, token); box.querySelector(which === 'cancel' ? 'button[value="cancel"]' : 'button[value="ok"]')?.click(); return; }
  const field = box.querySelector('textarea');
  if (field && text != null) await typeInto('.scrim .dialog textarea', text, token);
  await hold(700, token);
  box.querySelector(which === 'cancel' ? '[data-cancel], .chip:not(.primary)' : '.chip.primary, [type="submit"]')?.click();
}

async function find(sel, token, ms = 15000) {
  const t0 = Date.now();
  while (alive(token) && Date.now() - t0 < ms) {
    const el = typeof sel === 'function' ? sel(api()) : $(sel);
    if (el && el.getClientRects().length) return el;
    await wait(150);
  }
  return null;
}

async function until(fn, ms, token) {
  const t0 = Date.now();
  while (alive(token)) {
    try { if (fn()) return true; } catch (_) { /* state not there yet */ }
    if (Date.now() - t0 > ms) return false;
    await wait(200);
  }
  return false;
}

// Pausable hold: time only runs while playing; → skips it.
async function hold(ms, token) {
  let left = ms / (T?.speed || 1);
  while (alive(token) && left > 0) {
    if (T.skip) { T.skip = false; return; }
    await wait(100);
    if (T?.playing) left -= 100;
  }
}
async function gate(token) { while (alive(token) && !T.playing) await wait(120); }

// ---------- "Your turn" beats ----------
async function beat(s, token) {
  const a = api();
  const target = s.beat.target || s.target;
  frame(target);
  showBeat(fill(s.beat.ask), T.mode === 'scripted');
  const done = await new Promise((resolve) => {
    let settled = false;
    const finish = (v) => { if (!settled) { settled = true; resolve(v); } };
    T.beatShowMe = async () => { hideBeat(); if (T.mode === 'scripted' && s.do) await perform(s.do, token); finish(true); };
    T.beatSkip = async () => { hideBeat(); if (T.mode === 'scripted' && s.do && s.beat.skipDoes !== false) await perform(s.do, token); finish(true); };
    (async () => { await until(() => s.beat.done(a), Infinity, token); finish(true); })();
    if (T.mode === 'scripted') setTimeout(() => { if (!settled && alive(token) && T.playing && s.beat.auto !== false) $('#tourBeat')?.classList.add('nudge'); }, 8000);
  });
  hideBeat();
  if (done) caption('Nicely done.', null);
}

// ---------- Surfaces ----------
function mount() {
  const root = document.createElement('div');
  root.id = 'tour';
  root.innerHTML = `
    <svg class="t-spot" id="tourSpot" aria-hidden="true"><defs><mask id="tourMask"><rect width="100%" height="100%" fill="#fff"/><rect id="tourHole" rx="14" fill="#000"/></mask></defs>
      <rect width="100%" height="100%" mask="url(#tourMask)" class="t-dim"/><rect id="tourRim" rx="14" class="t-rim"/></svg>
    <div class="t-badge" id="tourBadge"></div>
    <div class="t-caption" id="tourCaption" aria-live="polite"><p class="t-cap"></p><p class="t-sub"></p></div>
    <div class="t-live" id="tourLive" hidden></div>
    <div class="t-beat" id="tourBeat" hidden><span class="t-beat-dot"></span><p></p><div><button data-t="showme">Show me</button><button data-t="skipbeat" class="ghost">Skip</button></div></div>
    <div class="t-hot" id="tourHot"></div>
    <div class="t-bar" id="tourBar"></div>
    <div class="t-card" id="tourCard" hidden></div>
    <div class="t-sheet" id="tourSheet" hidden></div>`;
  document.body.appendChild(root);
  root.addEventListener('click', onClick);
  document.addEventListener('keydown', onKey, true);
  let idle;
  const wake = () => { root.classList.add('awake'); clearTimeout(idle); idle = setTimeout(() => root.classList.remove('awake'), 2200); };
  document.addEventListener('pointermove', wake, { passive: true });
  wake();
  renderBadge();
  renderBar();
}

function renderBadge() {
  const el = $('#tourBadge');
  if (!el || !T) return;
  el.innerHTML = T.mode === 'scripted'
    ? `<b>Scripted demo</b> · replaying a real run recorded ${esc((T.files?.recorded_at || '').slice(0, 10))}`
    : `<b>Live</b> · your real backend${T.recording ? ' · <i>recording</i>' : ''} · nothing costly runs without your click`;
  el.className = `t-badge ${T.mode}`;
}

function renderBar() {
  const el = $('#tourBar');
  if (!el || !T) return;
  const cur = T.order[T.at];
  const w = progress.watchedSet(T.b.id);
  el.innerHTML = `
    <button data-t="toggle" aria-label="${T.playing ? 'Pause' : 'Play'}" title="${T.playing ? 'Pause' : 'Play'} (Space)">${T.playing ? ICON.pause : ICON.play}</button>
    <button data-t="prev" aria-label="Previous chapter" title="Previous chapter (←)">${ICON.prev}</button>
    <button data-t="next" aria-label="Skip ahead" title="Skip ahead (→)">${ICON.next}</button>
    <div class="t-dots" role="tablist" aria-label="Chapters">${T.order.map((ci, i) => `<button data-t="seek" data-i="${i}" role="tab" aria-selected="${ci === cur}" class="${w.has(CHAPTERS[ci].id) ? 'seen' : ''}" title="${esc(CHAPTERS[ci].numeral)} · ${esc(CHAPTERS[ci].title)}">${moon(i, T.order.length, ci === cur || w.has(CHAPTERS[ci].id))}</button>`).join('')}</div>
    <span class="t-now">${CHAPTERS[cur] ? `${esc(CHAPTERS[cur].numeral)} · ${esc(fill(CHAPTERS[cur].title))}` : 'The end'}</span>
    <button data-t="speed" title="Speed">${T.speed}×</button>
    <button data-t="cc" aria-pressed="${T.cc}" title="Captions">CC</button>
    <button data-t="mode" class="t-mode ${T.mode}" title="Scripted plays a recorded run · Live uses your real backend">${T.mode === 'scripted' ? 'Scripted' : 'Live'}</button>
    <button data-t="menu" title="Chapters, reels and glossary">${ICON.menu}</button>
    <button data-t="exit" aria-label="Exit the tour" title="Exit (Esc)">${ICON.close}</button>`;
  $('#tour').classList.toggle('paused', !T.playing);
}

function caption(text, sub) {
  const el = $('#tourCaption');
  if (!el || !T) return;
  el.hidden = !T.cc;
  const cap = el.querySelector('.t-cap');
  cap.innerHTML = String(text || '').split(' ').map((w, i) => `<span style="--w:${i}">${esc(w)}</span>`).join(' ');
  el.querySelector('.t-sub').textContent = sub || '';
  el.classList.remove('in'); void el.offsetWidth; el.classList.add('in');
}

function liveHint(text) {
  const el = $('#tourLive');
  if (!el) return;
  el.hidden = !text;
  el.innerHTML = text ? `<span class="t-beat-dot"></span>${esc(text)}` : '';
}

function showBeat(text, canShow) {
  const el = $('#tourBeat');
  el.hidden = false; el.classList.remove('nudge');
  el.querySelector('p').innerHTML = `<b>Your turn.</b> ${esc(text)}`;
  el.querySelector('[data-t="showme"]').hidden = !canShow;
}
function hideBeat() { const el = $('#tourBeat'); if (el) el.hidden = true; if (T) { T.beatShowMe = null; T.beatSkip = null; } }

// Camera: frame a target with the spotlight; on wide screens, push in a little.
let framed = null;
function frame(target) {
  const el = typeof target === 'string' ? $(target) : typeof target === 'function' ? target(api()) : target;
  framed = el || null;
  place();
}
function place() {
  const hole = $('#tourHole'), rim = $('#tourRim'), app = $('#app');
  if (!hole) return;
  const r = framed?.getClientRects().length ? framed.getBoundingClientRect() : null;
  $('#tour').classList.toggle('spot', !!r);
  if (!r) { app.style.transform = ''; return; }
  const pad = 10;
  for (const n of [hole, rim]) {
    n.setAttribute('x', r.left - pad); n.setAttribute('y', r.top - pad);
    n.setAttribute('width', r.width + pad * 2); n.setAttribute('height', r.height + pad * 2);
  }
}
addEventListener('resize', () => T && place());
setInterval(() => { if (T && framed) place(); }, 250);

function ripple(el) {
  if (reduced()) return;
  const r = el.getBoundingClientRect();
  const dot = document.createElement('i');
  dot.className = 't-click';
  dot.style.left = `${r.left + r.width / 2}px`; dot.style.top = `${r.top + r.height / 2}px`;
  $('#tour')?.appendChild(dot);
  setTimeout(() => dot.remove(), 700);
}

function hotspots(list) {
  const el = $('#tourHot');
  if (!el) return;
  el.innerHTML = '';
  if (!list) return;
  for (const h of list) {
    const t = $(h.sel);
    if (!t || !t.getClientRects().length) continue;
    const r = t.getBoundingClientRect();
    el.insertAdjacentHTML('beforeend', `<button class="t-spotinfo" style="left:${Math.min(innerWidth - 30, r.right - 8)}px;top:${Math.max(8, r.top - 8)}px" aria-label="${esc(h.text)}"><span>i</span><em>${esc(h.text)}</em></button>`);
  }
}

// Chapter title cards: letterbox, gold numeral, one line of promise.
async function chapterCard(ch, token, note = '') {
  const el = $('#tourCard');
  frame(null);
  el.hidden = false;
  el.innerHTML = `<i class="lb"></i><i class="lb"></i><div><span class="t-num">${esc(ch.numeral)}</span><h2>${esc(fill(ch.title))}</h2><p>${esc(fill(note || ch.promise))}</p></div>`;
  el.classList.remove('out'); void el.offsetWidth; el.classList.add('in');
  await hold(note ? 2600 : 2400, token);
  el.classList.add('out');
  await wait(reduced() ? 0 : 600);
  el.hidden = true;
}

// ---------- Sheets: pick a hunch, the library, glossary, quiz, finale ----------
function sheet(html) {
  const el = $('#tourSheet');
  el.hidden = false; el.innerHTML = `<div class="t-sheet-in">${html}</div>`;
  return el;
}
function closeSheet() { const el = $('#tourSheet'); if (el) { el.hidden = true; el.innerHTML = ''; } }

async function pickHunch(opts, notice = '') {
  if (!$('#tour')) {
    // A bare overlay just for the picker, before a tour exists.
    const root = document.createElement('div'); root.id = 'tour'; root.className = 'picker';
    root.innerHTML = '<div class="t-sheet" id="tourSheet"></div>';
    document.body.appendChild(root);
    root.addEventListener('click', onPickerClick);
    document.addEventListener('keydown', onPickerKey, true);
  }
  const recorded = await Promise.all(branches.map((b) => loadManifest(b).then(Boolean)));
  const last = progress.get().last;
  sheet(`<p class="t-kicker">The guided tour · about 3 minutes</p>
    <h2>Pick a hunch. Watch Thoth weigh it.</h2>
    <p class="muted">Each one is a real run, recorded end to end, and each ends differently. Thoth isn't a yes-machine.</p>
    ${notice ? `<p class="t-notice">${esc(notice)}</p>` : ''}
    <div class="t-hunches">${branches.map((b, i) => `<button class="t-hunch" data-pick="${b.id}" data-recorded="${recorded[i] ? 1 : 0}" aria-disabled="${!recorded[i] && opts.mode !== 'live'}">
      <span class="t-hunch-icon" style="--c:${b.color}">${b.icon}</span><b>${esc(b.hunch)}</b><span class="faint">${esc(b.field)}</span>
      <span class="t-outcome">${recorded[i] ? esc(b.outcome) : 'Coming soon'}</span></button>`).join('')}</div>
    <div class="t-row">
      <label class="t-switch"><input type="checkbox" id="tourLiveToggle" ${opts.mode === 'live' ? 'checked' : ''}> Live: drive your real backend yourself</label>
      ${last ? `<button class="t-link" data-resume="${esc(last.branch)}:${last.chapter}">Resume: ${esc(CHAPTERS[last.chapter]?.numeral || '')} · ${esc(CHAPTERS[last.chapter]?.title || '')}</button>` : ''}
      <button class="t-link" data-closepicker>Not now</button>
    </div>`);
  pickerOpts = opts;
}
let pickerOpts = {};
function closePicker() {
  document.removeEventListener('keydown', onPickerKey, true);
  if (!T) $('#tour')?.remove(); else closeSheet();
}
function onPickerKey(e) { if (e.key === 'Escape' && !T) { e.preventDefault(); closePicker(); } }
function onPickerClick(e) {
  const pick = e.target.closest('[data-pick]');
  const resume = e.target.closest('[data-resume]');
  const live = $('#tourLiveToggle')?.checked;
  if (e.target.closest('[data-closepicker]')) return closePicker();
  if (e.target.id === 'tourLiveToggle') { document.querySelectorAll('.t-hunch').forEach((h) => h.setAttribute('aria-disabled', String(!live && h.dataset.recorded !== '1'))); return; }
  if (pick && pick.getAttribute('aria-disabled') === 'true') return;
  if (pick || resume) {
    const [branch, chapter] = resume ? resume.dataset.resume.split(':') : [pick.dataset.pick, pickerOpts.chapter || 0];
    closePicker();
    $('#tour')?.remove();
    start({ ...pickerOpts, branch, chapter: +chapter, mode: live ? 'live' : 'scripted' });
  }
}

function library() {
  T.playing = false; renderBar();
  const w = progress.watchedSet(T.b.id);
  sheet(`<p class="t-kicker">${esc(T.b.hunch)}</p><h2>Chapters</h2>
    <div class="t-lib">${CHAPTERS.map((c, i) => `<button class="t-tile${w.has(c.id) ? ' seen' : ''}" data-chapter="${i}">${moon(i, CHAPTERS.length, w.has(c.id))}<span class="t-num">${esc(c.numeral)}</span><b>${esc(fill(c.title))}</b><span class="faint">${esc(c.length)}${w.has(c.id) ? ' · watched' : ''}</span></button>`).join('')}</div>
    <h3>Short reels</h3>
    <div class="t-reels">${REELS.map((r) => `<button class="t-reel" data-reel="${r.id}"><b>${esc(r.title)}</b><span class="faint">${esc(r.length)}</span></button>`).join('')}</div>
    <h3>Glossary</h3>
    <dl class="t-gloss">${GLOSSARY.map(([k, v]) => `<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`).join('')}</dl>
    <div class="t-row"><button class="t-link" data-t="other">Pick another hunch</button><button class="t-link" data-t="resume">Back to the film</button></div>`);
}

async function quiz(q, token) {
  T.playing = true;
  const el = sheet(`<p class="t-kicker">Quick check · optional</p><h2>${esc(q.q)}</h2>
    <div class="t-quiz">${q.options.map((o, i) => `<button data-quiz="${i}">${esc(o)}</button>`).join('')}</div><p class="t-why" hidden></p>
    <div class="t-row"><button class="t-link" data-t="quizskip">Skip</button></div>`);
  await new Promise((resolve) => {
    T.quizDone = resolve;
    el.onclick = (e) => {
      const b = e.target.closest('[data-quiz]');
      if (!b) return;
      el.querySelectorAll('[data-quiz]').forEach((x, i) => { x.disabled = true; x.classList.toggle('right', i === q.answer); });
      if (+b.dataset.quiz !== q.answer) b.classList.add('wrong');
      const why = el.querySelector('.t-why'); why.hidden = false; why.textContent = q.why;
      el.querySelector('[data-t="quizskip"]').textContent = 'Continue';
    };
  });
  if (alive(token)) closeSheet();
}
function hideQuiz() { if (T?.quizDone) { T.quizDone(); T.quizDone = null; } closeSheet(); }

function finale() {
  T.playing = false; renderBar(); frame(null); caption('', '');
  const w = progress.watchedSet(T.b.id);
  sheet(`<div class="t-finale"><img src="/assets/thoth_scales.jpg" alt="">
    <div><p class="t-kicker">The end of the tour</p><h2>Weigh your own question.</h2>
    <div class="t-moons">${CHAPTERS.map((c, i) => moon(i, CHAPTERS.length, w.has(c.id))).join('')}</div>
    <p class="muted">${w.size} of ${CHAPTERS.length} chapters watched. Everything you saw was recorded from a real run, honestly labelled, and nothing costly ran without a click.</p>
    <div class="t-row"><button class="t-cta" data-t="own">Start your own project with this question</button><button class="t-link" data-t="menu">Chapters & reels</button><button class="t-link" data-t="exit">Close</button></div></div></div>`);
}

// ---------- Input ----------
function onClick(e) {
  const b = e.target.closest('[data-t], [data-chapter], [data-reel]');
  if (!b || !T) return;
  if (b.dataset.chapter != null) { closeSheet(); const i = T.order.indexOf(+b.dataset.chapter); if (i >= 0) seek(i); else { T.order = CHAPTERS.map((_, k) => k); seek(+b.dataset.chapter); } return; }
  if (b.dataset.reel) { const r = REELS.find((x) => x.id === b.dataset.reel); closeSheet(); T.order = r.chapters; seek(0); return; }
  switch (b.dataset.t) {
    case 'toggle': T.playing = !T.playing; renderBar(); break;
    case 'prev': seek(T.at - (T.ci === T.order[T.at] ? 1 : 0)); break;
    case 'next': T.skip = true; break;
    case 'seek': seek(+b.dataset.i); break;
    case 'speed': T.speed = { 1: 1.5, 1.5: 2, 2: 1 }[T.speed]; net.speed = T.speed; progress.set({ speed: T.speed }); renderBar(); break;
    case 'cc': T.cc = !T.cc; progress.set({ cc: T.cc }); $('#tourCaption').hidden = !T.cc; renderBar(); break;
    case 'mode': switchMode(); break;
    case 'menu': library(); break;
    case 'resume': closeSheet(); T.playing = true; renderBar(); break;
    case 'other': { const m = T.mode; exit(true).then(() => pickHunch({ mode: m })); break; }
    case 'exit': exit(); break;
    case 'showme': T.beatShowMe?.(); break;
    case 'skipbeat': T.beatSkip?.(); break;
    case 'quizskip': T.quizDone?.(); T.quizDone = null; break;
    case 'own': { const q = T.b.hunch; exit(true).then(() => ctx.startOwn(q)); break; }
    default: break;
  }
}
function onKey(e) {
  if (!T) { document.removeEventListener('keydown', onKey, true); return; }
  const typing = e.target.closest?.('input, textarea, [contenteditable]');
  if (e.key === 'Escape') { e.preventDefault(); if (!$('#tourSheet').hidden) closeSheet(); else exit(); return; }
  if (typing) return;
  if (e.key === ' ') { e.preventDefault(); T.playing = !T.playing; renderBar(); }
  else if (e.key === 'ArrowRight') { e.preventDefault(); T.skip = true; }
  else if (e.key === 'ArrowLeft') { e.preventDefault(); seek(T.at - 1); }
}

// Scripted ⇄ Live at a chapter boundary. Live starts a fresh real project with the same hunch.
function switchMode() {
  const next = T.mode === 'scripted' ? 'live' : 'scripted';
  const b = T.b.id, ci = T.order[T.at];
  exit(true).then(() => start({ branch: b, chapter: next === 'live' ? 0 : ci, mode: next }));
}

// ---------- Recording hand-off ----------
// After every chapter (and on exit) the tape so far goes to ?sink=URL if given, and to window.__thothRecording.
function sendRecording(branchId) {
  const files = chapterFiles();
  if (!files.length) return;
  const manifest = { branch: branchId, recorded_at: new Date().toISOString(), chapters: files.map((f) => f.name) };
  window.__thothRecording = { manifest, files };
  const sink = new URLSearchParams(location.search).get('sink');
  if (sink) fetch(sink, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ manifest, files }) }).catch(() => {});
}

// Scripted only: the hunch typed on the home screen opens the demo project, the way a real one would.
async function begin(text) {
  const { state } = ctx;
  net.pid = DEMO;
  if (!state.projects.some((p) => p.id === DEMO)) state.projects.unshift({ id: DEMO, title: T.b.title, updated: new Date().toISOString() });
  delete state.data[DEMO];
  await ctx.scene('enter', () => { state.projectId = DEMO; ctx.emit(); });
  ctx.say(text);
}

export function resumeLabel() {
  const last = progress.get().last;
  const b = last && branches.find((x) => x.id === last.branch);
  return b && CHAPTERS[last.chapter] && last.chapter > 0 ? `${CHAPTERS[last.chapter].numeral} · ${CHAPTERS[last.chapter].title} · ${b.title}` : '';
}

// ---------- Helpers ----------
function api() {
  const { state } = ctx;
  return { state, get d() { return state.projectId ? state.data[state.projectId] : null; }, $, branch: T?.b, mode: T?.mode, actions: ctx.actions, begin };
}
function fill(s) {
  if (typeof s === 'function') s = s(api());
  return String(s ?? '').replace(/\{(\w+)\}/g, (_, k) => T?.b?.[k] ?? '');
}
function esc(s) { return String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])); }
function moon(i, n, lit) {
  const f = n <= 1 ? 1 : i / (n - 1), r = 7, rx = Math.abs(1 - 2 * f) * r;
  const path = f === 0 ? '' : `<path d="M9 2 A7 7 0 0 1 9 16 A${rx.toFixed(2)} 7 0 0 ${f < .5 ? 0 : 1} 9 2Z" fill="${lit ? 'var(--gold)' : 'var(--night-line)'}"/>`;
  return `<svg viewBox="0 0 18 18" aria-hidden="true"><circle cx="9" cy="9" r="${r}" fill="none" stroke="${lit ? 'var(--gold)' : 'var(--night-ink-3)'}" stroke-width="1.2"/>${path}</svg>`;
}
const ICON = {
  play: '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z"/></svg>',
  pause: '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M7 5h4v14H7zM13 5h4v14h-4z"/></svg>',
  prev: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M15 6l-6 6 6 6"/></svg>',
  next: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M9 6l6 6-6 6"/></svg>',
  menu: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M4 7h16M4 12h16M4 17h10"/></svg>',
  close: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M6 6l12 12M18 6L6 18"/></svg>',
};
