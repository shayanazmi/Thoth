// Boot: projects sidebar (collapsible), home (open question + doors), moon-phase journey,
// theme, workspace toggle, phone bottom bar, first-visit intro.
import { getJSON, postJSON } from './api.js';
import { state, project, emit, subscribe, stageState, STAGES, peek, rememberProject, lastProject, setHypothesis, hydrate, forgetProject } from './store.js';
import { register, renderConversation, initComposer, say, prefill, openPanel, startCheck, startReview, actions, COMMANDS } from './chat.js';
import { toast, askText } from './ui.js';
import './thinkers.js';
import './trial.js';
import './design.js';
import './proposal.js';
import './hypothesis.js';
import './mode.js';
import './review.js';
import { renderWorkspace, resetStageMemory } from './workspace.js';
import { $, esc, brandMark, moonSVG } from './util.js';
import { maybePlayIntro, playIntro } from './intro-cinema.js';
import { scene, fresh, again } from './motion.js';

const app = $('#app');
const wide = () => window.matchMedia('(min-width: 1200px)').matches;
const store = {
  get: (k) => { try { return localStorage.getItem(k); } catch (_) { return null; } },
  set: (k, v) => { try { localStorage.setItem(k, v); } catch (_) {} },
};

// ---------- Theme ----------
function applyTheme(t) {
  if (t) document.documentElement.dataset.theme = t; else delete document.documentElement.dataset.theme;
}
// Obsidian is the brand default; papyrus only when chosen, or when the OS asks for light on a first visit.
applyTheme(store.get('thoth.theme') || (matchMedia('(prefers-color-scheme: light)').matches ? 'light' : null));
$('#themeToggle').addEventListener('click', (e) => {
  const next = document.documentElement.dataset.theme === 'light' ? 'dark' : 'light';
  scene('theme', () => applyTheme(next), { x: e.clientX, y: e.clientY });
  store.set('thoth.theme', next);
});

// ---------- Collapse: sidebar rail and workspace ----------
if (store.get('thoth.sb') === 'collapsed') app.classList.add('sb-collapsed');
if (store.get('thoth.ws') === 'collapsed') app.classList.add('ws-collapsed');

register('toggleSidebar', () => {
  app.classList.toggle('sb-collapsed');
  store.set('thoth.sb', app.classList.contains('sb-collapsed') ? 'collapsed' : 'open');
  renderSidebar();
});

$('#workspaceToggle').addEventListener('click', () => {
  if (wide()) {
    app.classList.toggle('ws-collapsed');
    store.set('thoth.ws', app.classList.contains('ws-collapsed') ? 'collapsed' : 'open');
  } else {
    app.classList.toggle('ws-open');
  }
  syncToggles();
});

// Layout modes: chat (file hidden) · split · file (file gets most of the width). Wide screens only.
function layoutMode() { return app.classList.contains('ws-collapsed') ? 'chat' : app.classList.contains('ws-wide') ? 'file' : 'split'; }
function setLayout(mode) {
  if (mode !== layoutMode()) scene('layout', () => applyLayout(mode));
  else applyLayout(mode);
}
function applyLayout(mode) {
  app.classList.toggle('ws-collapsed', mode === 'chat');
  app.classList.toggle('ws-wide', mode === 'file');
  store.set('thoth.ws', mode === 'chat' ? 'collapsed' : 'open');
  store.set('thoth.layout', mode);
  syncToggles();
}
if (store.get('thoth.layout') === 'file' && !app.classList.contains('ws-collapsed')) app.classList.add('ws-wide');
$('#layoutSeg').addEventListener('click', (e) => { const b = e.target.closest('button[data-layout]'); if (b) setLayout(b.dataset.layout); });

function syncToggles() {
  const mode = layoutMode();
  for (const b of $('#layoutSeg').querySelectorAll('button')) b.setAttribute('aria-pressed', String(b.dataset.layout === mode));
  const shown = wide() ? !app.classList.contains('ws-collapsed') : app.classList.contains('ws-open');
  $('#workspaceToggle').setAttribute('aria-pressed', String(shown));
}

$('#sidebarToggle').addEventListener('click', () => app.classList.toggle('sb-open'));
$('#bottombar').addEventListener('click', (e) => {
  const b = e.target.closest('button[data-mobile]');
  if (!b) return;
  const which = b.dataset.mobile;
  if (which === 'chat') app.classList.remove('ws-open');
  else { if (which === 'hypothesis') openPanel('hypothesis', { fromUser: true }); else app.classList.add('ws-open'); }
});
document.addEventListener('click', (e) => {
  if (app.classList.contains('sb-open') && !e.target.closest('#sidebar') && !e.target.closest('#sidebarToggle')) app.classList.remove('sb-open');
});

// ---------- Projects ----------
const cleanTitle = (t) => String(t || 'Untitled').replace(/^project:\s*/i, '').trim() || 'Untitled';

async function loadProjects() {
  try {
    const res = await getJSON('/api/projects');
    state.projects = (res.projects || []).map((p) => ({ id: p.project_id || p.id, title: cleanTitle(p.title), updated: p.updated_at || p.created_at || '', kind: p.kind || 'thread' }));
  } catch (_) {
    state.projects = [];
  }
}

async function createProject(title) {
  const clean = cleanTitle(title).slice(0, 70);
  let id;
  try {
    const res = await postJSON('/api/projects', { title: clean });
    id = res.project?.project_id || res.project?.id;
  } catch (_) { /* fall back to a local-only project */ }
  id = id || `local_${Date.now().toString(36)}`;
  state.projects.unshift({ id, title: clean, updated: new Date().toISOString(), kind: 'thread' });
  await selectProject(id);
  return id;
}

function selectProject(id) {
  const fromHome = !state.projectId;
  const go = () => {
    state.projectId = id;
    rememberProject(id);
    resetStageMemory();
    project();
    app.classList.remove('sb-open');
    emit();
    hydrate(id); // the server's copy: question, hypothesis versions, rivals, and the chat in a new browser
  };
  if (fromHome) return scene('enter', go);
  go();
  return Promise.resolve();
}

async function ensureProject(title) {
  if (state.projectId) return state.projectId;
  return createProject(title);
}

register('selectProject', (id) => selectProject(id));
register('home', () => { if (!state.projectId) return; scene('leave', () => { state.projectId = null; rememberProject(''); emit(); }); });
register('replayIntro', () => playIntro(onIntroDone));

const ICON = {
  collapse: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"><rect x="3.5" y="4.5" width="17" height="15" rx="2.5"/><path d="M9.5 4.5v15"/></svg>',
};

function renderSidebar() {
  const stageOf = (id) => {
    const d = peek(id);
    const cur = d ? stageState(d).current : 'explore';
    const i = STAGES.findIndex((s) => s.id === cur);
    return { i: Math.max(0, i), label: STAGES[Math.max(0, i)].label };
  };
  const collapsed = app.classList.contains('sb-collapsed');
  $('#sidebar').innerHTML = `
    <div class="side-head">
      <a class="brand" href="#" data-act="home" aria-label="Thoth home" title="Home"><span class="brand-mark">${brandMark()}</span><span class="brand-name">THOTH</span></a>
      <button class="icon-btn collapse-btn" data-act="toggleSidebar" aria-label="${collapsed ? 'Expand' : 'Collapse'} sidebar" title="${collapsed ? 'Expand' : 'Collapse'} sidebar">${ICON.collapse}</button>
    </div>
    <form class="new-project" id="newProject"><input id="newProjectName" placeholder="New project…" aria-label="New project name"><button aria-label="Create project">+</button></form>
    ${sideGroup('Projects', state.projects.filter((p) => p.kind === 'project'), 'A chat becomes a project when you accept a hypothesis.', stageOf)}
    ${sideGroup('Threads', state.projects.filter((p) => p.kind !== 'project'), 'No open threads.', stageOf)}
    <div class="side-foot">Papers, notes and drafts stay inside their project. <button class="link-btn" data-act="replayIntro">Replay intro</button></div>`;
  $('#newProject').addEventListener('submit', (e) => {
    e.preventDefault();
    const v = $('#newProjectName').value.trim();
    if (v) createProject(v);
  });
}

// A chat is a thread until a hypothesis is accepted; then it is a project (docs/features/02).
function sideGroup(label, items, emptyText, stageOf) {
  return `<div class="side-label">${label}</div>
    <ul class="project-list">${items.map((p) => {
      const s = stageOf(p.id);
      return `<li class="p-row"><button data-act="selectProject" data-arg="${esc(p.id)}" aria-current="${p.id === state.projectId}" title="${esc(p.title)} · ${esc(s.label)}">
        <span class="p-moon">${moonSVG(s.i, STAGES.length)}</span>
        <span class="p-text"><span class="p-title">${esc(p.title)}</span><span class="p-stage">${esc(s.label)}</span></span></button>
        <button class="icon-btn p-delete" data-act="deleteProject" data-arg="${esc(p.id)}" aria-label="Delete ${esc(p.title)}" title="Delete…">×</button></li>`;
    }).join('') || `<li class="faint" style="padding:8px 10px;font-size:.85rem">${emptyText}</li>`}</ul>`;
}

// Deleting removes everything the project holds, after one confirmation that lists it.
register('deleteProject', async (id) => {
  const p = state.projects.find((x) => x.id === id);
  if (!p) return;
  let summary = 'everything stored in this browser';
  if (!id.startsWith('local_')) {
    try { summary = (await getJSON(`/api/projects/${encodeURIComponent(id)}/footprint`)).summary; } catch (_) { return toast("Couldn't reach the server; nothing was deleted."); }
  }
  const typed = await askText({ title: `Delete “${p.title}”?`, confirm: 'Delete everything',
    body: `This removes ${summary} from this project, for good. Nothing is kept in a global library.`,
    label: 'Type “delete” to confirm' });
  if (typed === null) return;
  if (typed.trim().toLowerCase() !== 'delete') return toast('Not deleted: type “delete” to confirm.');
  if (!id.startsWith('local_')) {
    const res = await fetch(`${window.THOTH_API_BASE || ''}/api/projects/${encodeURIComponent(id)}?confirm=true`, { method: 'DELETE' }).catch(() => null);
    if (!res || (!res.ok && res.status !== 404)) return toast("Couldn't delete it; nothing was removed.");
  }
  forgetProject(id);
  state.projects = state.projects.filter((x) => x.id !== id);
  if (state.projectId === id) { state.projectId = null; rememberProject(''); }
  toast(`Deleted “${p.title}”.`);
  emit();
});

// ---------- Home ----------
const DOOR_ICONS = {
  brainstorm: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"><path d="M12 3a6 6 0 0 0-3.5 10.9V16h7v-2.1A6 6 0 0 0 12 3zM9.5 19h5M10.5 21.5h3"/></svg>',
  thinker: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><ellipse cx="12" cy="8" rx="3.6" ry="4.2"/><path d="M5.5 20c.6-3.6 3.2-5.8 6.5-5.8s5.9 2.2 6.5 5.8z" stroke-linejoin="round"/></svg>',
  check: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"><circle cx="11" cy="11" r="6.5"/><path d="M20 20l-4.3-4.3M8.5 11l1.8 1.8 3.4-3.6"/></svg>',
  review: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"><path d="M5 4h14M7 9h10M9 14h6M11 19h2"/></svg>',
  draft: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"><path d="M14.5 4.5l5 5L9 20H4v-5z"/><path d="M12.5 6.5l5 5"/></svg>',
};
const DOORS = [
  { id: 'brainstorm', label: 'Brainstorm', hint: 'What has been puzzling you lately?' },
  { id: 'thinker', label: 'Talk to a thinker' },
  { id: 'check', label: 'Check a hypothesis' },
  { id: 'review', label: 'Literature review' },
  { id: 'draft', label: 'Draft' },
];

register('door', async (id) => {
  const homeInput = $('#homeInput');
  if (id === 'brainstorm') { homeInput.placeholder = DOORS[0].hint; homeInput.focus(); return; }
  const seed = homeInput?.value.trim();
  await ensureProject(seed || { thinker: 'Thinking with philosophers', check: 'Hypothesis check', review: 'Literature review', draft: 'Research draft' }[id]);
  if (id === 'thinker') { openPanel('thinkers', { fromUser: true }); }
  if (id === 'check') { if (seed) { setHypothesis(seed, 'Written by you', 'you'); openPanel('hypothesis', { fromUser: true }); } else prefill('/hypothesis '); }
  if (id === 'review') { if (seed) startReview(seed); else prefill('/review '); }
  if (id === 'draft') openPanel('draft', { fromUser: true });
});

function renderHome() {
  const recent = state.projects.slice(0, 4);
  const orbit = Array.from({ length: 7 }, (_, i) => { const t = (i / 7) * Math.PI * 2 - Math.PI / 2; return `<span class="orbit-moon" style="left:${(50 + 46 * Math.cos(t)).toFixed(2)}%;top:${(50 + 46 * Math.sin(t)).toFixed(2)}%">${moonSVG(i, 7)}</span>`; }).join('');
  $('#home').innerHTML = `<div class="home-inner">
    <div class="home-copy">
      <p class="home-eyebrow">A research companion</p>
      <h1>Find the question <em>worth</em> asking.</h1>
      <p class="lede">Start with a hunch. Thoth thinks it through with you, reads what is already known, puts your hypothesis on trial, and tells you honestly what it could not verify.</p>
      <form class="home-input" id="homeForm"><textarea id="homeInput" rows="2" placeholder="I noticed something odd about…" aria-label="Your thought"></textarea>
        <button class="send-btn" aria-label="Start"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 19V5M6 11l6-6 6 6"/></svg></button></form>
      <div class="doors">${DOORS.map((d) => `<button class="door" data-act="door" data-arg="${d.id}">${DOOR_ICONS[d.id]}${esc(d.label)}</button>`).join('')}</div>
      <ul class="home-promises"><li>Nothing costly runs without your approval</li><li>An abstract is never passed off as the full paper</li></ul>
      ${recent.length ? `<div class="home-recent"><span>Recent</span>${recent.map((p) => `<button data-act="selectProject" data-arg="${esc(p.id)}">${esc(p.title.length > 42 ? p.title.slice(0, 40) + '…' : p.title)}</button>`).join('')}</div>` : ''}
    </div>
    <div class="home-arch" aria-hidden="true"><div class="arch-in" id="archIn"><img src="/assets/thoth_bust_1000.jpg" alt=""><div class="orbit">${orbit}</div></div><span class="plaque">Thoth · keeper of the record</span></div>
  </div>`;
  const form = $('#homeForm');
  const input = $('#homeInput');
  input.addEventListener('keydown', (e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); form.requestSubmit(); } });
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const text = input.value.trim();
    if (!text) return;
    await ensureProject(text);
    say(text);
  });
}

// ---------- Journey path ----------
register('stage', (id) => {
  const d = project();
  if (!d) return;
  if (id === 'explore') { $('#input').focus(); return; }
  // Opening the stage only shows the roster; the council (ten model calls) runs only when asked.
  if (id === 'thinkers') { openPanel('thinkers', { fromUser: true }); return; }
  if (id === 'hypothesis') { openPanel('hypothesis', { fromUser: true }); return; }
  if (id === 'check') { if (!d.status && !d.trial && !d.runs.some((r) => !r.done)) startCheck(); openPanel('check', { fromUser: true }); return; }
  if (id === 'review') { openPanel('review', { fromUser: true }); return; }
  if (id === 'design') { openPanel('design', { fromUser: true }); return; }
  if (id === 'draft') openPanel('draft', { fromUser: true });
});

// The moon you just reached fills with gold once per arrival.
let reachedKey = null;
function reached(stageId) {
  const key = `stage:${state.projectId}:${stageId}`;
  if (reachedKey !== key) { again(key); reachedKey = key; }
  return fresh(key, 1200);
}

function renderJourney() {
  const d = project();
  const st = stageState(d);
  const items = STAGES.map((s, i) => {
    const reach = st.current === s.id ? reached(s.id) : { cls: '', attr: '' };
    const cls = [st.done.has(s.id) ? 'done' : '', st.current === s.id ? 'current' : '', st.available.has(s.id) ? 'available' : ''].join(' ') + reach.cls;
    const lit = st.done.has(s.id) || st.current === s.id;
    return `<button class="stage ${cls}"${reach.attr} data-act="stage" data-arg="${s.id}" ${st.current === s.id ? 'aria-current="step"' : ''} title="${s.label}${st.available.has(s.id) ? ' · ready when you are' : ''}">${moonSVG(i, STAGES.length, lit)}<span>${s.label}</span></button>`;
  });
  const curIdx = STAGES.findIndex((s) => s.id === st.current);
  $('#journey').innerHTML = items.join('<span class="journey-sep" aria-hidden="true"></span>')
    + `<span class="journey-compact">${moonSVG(curIdx, STAGES.length)}${STAGES[curIdx].label} · ${curIdx + 1} of ${STAGES.length}${state.busy ? ' · working…' : ''}</span>`;
}

// The bust on the home screen is lit by a lantern that follows the pointer.
document.addEventListener('pointermove', (e) => {
  const a = document.getElementById('archIn');
  if (!a) return;
  const r = a.getBoundingClientRect();
  a.style.setProperty('--lx', `${((e.clientX - r.left) / r.width) * 100}%`);
  a.style.setProperty('--ly', `${((e.clientY - r.top) / r.height) * 100}%`);
}, { passive: true });

// ---------- Render loop ----------
function render() {
  const d = project();
  app.dataset.view = d ? 'work' : 'home';
  renderSidebar();
  if (!d) renderHome();
  renderJourney();
  renderConversation();
  renderWorkspace();
  syncBottomBar();
  syncToggles();
}
subscribe(render);

function syncBottomBar() {
  const open = app.classList.contains('ws-open');
  const panel = project()?.panel;
  for (const b of $('#bottombar').querySelectorAll('button')) {
    const which = b.dataset.mobile;
    b.classList.toggle('active', open ? (which === 'hypothesis' ? panel === 'hypothesis' : which === 'workspace' && panel !== 'hypothesis') : which === 'chat');
  }
}
new MutationObserver(() => { syncBottomBar(); syncToggles(); }).observe(app, { attributes: true, attributeFilter: ['class'] });

// The intro's question starts a real conversation; a sample question is left in the home box to send.
let bootReady;
const booted = new Promise((r) => { bootReady = r; });
async function onIntroDone(question, isSample) {
  if (!question) return;
  await booted;
  if (isSample) {
    state.projectId = null; rememberProject(''); emit();
    const input = $('#homeInput');
    if (input) { input.value = question; input.focus(); }
    return;
  }
  state.projectId = null;
  await createProject(question);
  say(question);
}

async function boot() {
  initComposer();
  maybePlayIntro(onIntroDone);
  try { state.thinkers = (await getJSON('/api/thinkers')).thinkers || []; } catch (_) { state.thinkers = []; }
  await loadProjects();
  const last = lastProject();
  if (last && state.projects.some((p) => p.id === last)) state.projectId = last;
  render();
  // A reload restores the project from this browser's cache; the server's copy (versions and why each changed,
  // rivals, the chat) is the source of truth, so fetch it too.
  if (state.projectId) hydrate(state.projectId);
  bootReady();
  // Optional guided tour: lives entirely in /scripted; if that folder is gone, this quietly does nothing.
  import('/scripted/index.js').then((m) => m.install({ state, emit, subscribe, actions, register, say, openPanel, scene, toast, rememberProject })).catch(() => {});
}
boot();
