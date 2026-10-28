// One state object, saved per project in this browser. Views subscribe and re-render.
import { uid } from './util.js';

const KEY = 'thoth.ui.v2';
const listeners = new Set();

export const STAGES = [
  { id: 'explore', label: 'Explore', panel: 'ideas' },
  { id: 'thinkers', label: 'Thinkers', panel: 'thinkers' },
  { id: 'hypothesis', label: 'Hypothesis', panel: 'hypothesis' },
  { id: 'check', label: 'Check', panel: 'check' },
  { id: 'review', label: 'Review', panel: 'review' },
  { id: 'design', label: 'Design', panel: 'design' },
  { id: 'draft', label: 'Draft', panel: 'draft' },
];

function blankProject(id) {
  return {
    sessionId: `sess_${id}`,
    messages: [],
    hypothesis: { versions: [], view: -1 },
    question: '',
    rivals: [],
    proposals: {},
    reviews: {},
    papers: {},
    ideas: [],
    firstObservation: '',
    brief: null,
    pendingBrief: null,
    runs: [],
    scan: null,
    prisma: null,
    report: null,
    status: null,
    originality: null,
    thinkerReview: null,
    followUps: [],
    recommendFormal: null,
    council: null,
    debatePicks: [],
    thinkerSpoke: false,
    escalation: null,
    activeThinker: null,
    panel: 'ideas',
    pinned: false,
    lastStage: 'explore',
  };
}

export const state = {
  projects: [],
  projectId: null,
  thinkers: [],
  data: {},
  busy: 0,
};

export function project() {
  if (!state.projectId) return null;
  if (!state.data[state.projectId]) state.data[state.projectId] = load(state.projectId) || blankProject(state.projectId);
  return state.data[state.projectId];
}

function load(id) {
  try {
    const raw = localStorage.getItem(`${KEY}.${id}`);
    return raw ? { ...blankProject(id), ...JSON.parse(raw) } : null;
  } catch (_) { return null; }
}

export function save() {
  const d = project();
  if (!d) return;
  try { localStorage.setItem(`${KEY}.${state.projectId}`, JSON.stringify({ ...d, activeThinker: null })); } catch (_) { /* storage full or blocked */ }
}

export function peek(id) {
  return state.data[id] || load(id);
}

export function rememberProject(id) {
  try { localStorage.setItem(`${KEY}.current`, id || ''); } catch (_) {}
}

export function lastProject() {
  try { return localStorage.getItem(`${KEY}.current`) || null; } catch (_) { return null; }
}

export function subscribe(fn) { listeners.add(fn); return () => listeners.delete(fn); }

export function emit() {
  save();
  for (const fn of listeners) fn();
}

export function addMessage(msg) {
  const d = project();
  const m = { id: uid('m'), at: Date.now(), ...msg };
  d.messages.push(m);
  emit();
  return m;
}

export function updateMessage(id, patch) {
  const d = project();
  const m = d.messages.find((x) => x.id === id);
  if (m) Object.assign(m, patch);
  emit();
}

// ---------- Hypothesis versions ----------
export function currentHypothesis(d = project()) {
  const v = d?.hypothesis?.versions || [];
  return v.length ? v[v.length - 1] : null;
}

// `saved`: the server already has this version (an accepted Thoth proposal is written when it's accepted).
// Why a version changed is kept on the server with the version (vision §3.2, §8.1): a reason, what triggered it,
// and any evidence (a trial verdict, a thinker's reply). The server adds what was known at the time.
const SOURCE_TRIGGER = { you: 'user_edit', thoth: 'thoth_proposal', idea: 'idea', thinker: 'thinker_critique' };

export function setHypothesis(text, reason, source = 'you', { saved = false, trigger, evidence } = {}) {
  const d = project();
  const clean = String(text || '').trim();
  if (!clean) return;
  const cur = currentHypothesis(d);
  if (cur && cur.text === clean) return;
  d.hypothesis.versions.push({ text: clean, reason, source, at: Date.now(), evidence: evidence || [] });
  d.hypothesis.view = d.hypothesis.versions.length - 1;
  if (!saved) persistSection('hypothesis', clean, { reason, source, trigger: trigger || SOURCE_TRIGGER[source] || 'user_edit', evidence: evidence || [] });
  emit();
}

// ---------- The project on the server (docs/features/02) ----------
// The server holds the question, every hypothesis version, the rivals and the conversation, so another
// browser can rebuild the project. localStorage only caches the view (panels, cards).
const isLocal = (id) => !id || String(id).startsWith('local_');

export async function persistSection(section, value, rationale) {
  if (isLocal(state.projectId)) return;
  try {
    const res = await fetch(`${window.THOTH_API_BASE || ''}/api/projects/${encodeURIComponent(state.projectId)}/notebook`, {
      method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ section, value, ...(rationale ? { rationale } : {}) }),
    });
    const out = await res.json();
    const p = state.projects.find((x) => x.id === state.projectId);
    if (p && out.kind) { p.kind = out.kind; emit(); }
  } catch (_) { /* offline: the local copy still has it; the next hydrate re-sends it */ }
}

const SOURCE_REASON = { you: 'Written by you', thoth: 'Proposed by Thoth, accepted by you' };

export async function hydrate(id) {
  if (isLocal(id)) return;
  let s;
  try { s = await (await fetch(`${window.THOTH_API_BASE || ''}/api/projects/${encodeURIComponent(id)}/state`)).json(); } catch (_) { return; }
  const d = state.data[id] || project();
  if (!d || !s || s.project_id !== id) return;
  const local = d.hypothesis.versions;
  if (s.hypothesis.length) {
    // The server's history wins, reasons included (older versions without one keep a local reason, if any).
    d.hypothesis.versions = s.hypothesis.map((v) => ({ text: v.text, source: v.source, at: v.at, version: v.version,
      trigger: v.trigger, evidence: v.evidence || [], context: v.context || [],
      reason: v.reason || local.find((x) => x.text === v.text)?.reason || SOURCE_REASON[v.source] || '' }));
    d.hypothesis.view = d.hypothesis.versions.length - 1;
  } else if (local.length) {
    persistSection('hypothesis', local[local.length - 1].text); // a project from before this change: send it up once
  }
  if (s.question) d.question = s.question;
  else if (d.question) persistSection('question', d.question);
  if (s.rivals?.length || !(d.rivals || []).length) d.rivals = s.rivals || [];
  else d.rivals.forEach((r) => persistSection('rival_hypothesis', r)); // rivals from before this change: send them up once
  if (!d.messages.length && s.messages.length) d.messages = s.messages.map((m, i) => ({ id: `srv_${i}`, ...m }));
  const p = state.projects.find((x) => x.id === id);
  if (p) p.kind = s.kind;
  emit();
}

export function forgetProject(id) {
  delete state.data[id];
  try { localStorage.removeItem(`${KEY}.${id}`); } catch (_) {}
}

// ---------- Journey stages ----------
export function stageState(d = project()) {
  const done = new Set();
  const available = new Set();
  if (!d) return { done, available, current: 'explore', running: false };
  const hasUser = d.messages.some((m) => m.role === 'user');
  const hyp = currentHypothesis(d);
  const trialRunning = d.trial?.status === 'running';
  const running = d.runs.some((r) => !r.done) || trialRunning;
  if (hasUser) done.add('explore');
  if (d.thinkerSpoke) done.add('thinkers');
  if (hyp) done.add('hypothesis');
  if (d.status || d.trial?.verdict) done.add('check');
  if (d.prisma) done.add('review');
  if (d.design?.chosen) done.add('design');

  if (hasUser && !d.thinkerSpoke) available.add('thinkers');
  if (!hyp && (d.ideas.length || d.escalation)) available.add('hypothesis');
  if (hyp && !d.status && !d.trial?.verdict) available.add('check');
  if ((d.recommendFormal || d.status || d.trial?.verdict) && !d.prisma) available.add('review');
  if (d.trial?.verdict && !d.design?.chosen) available.add('design');
  if (d.report || d.design?.chosen || d.proposal?.has_outline) available.add('draft');
  if (d.proposal?.status?.status === 'reviewed') done.add('draft');

  let current = 'explore';
  for (const s of STAGES) if (done.has(s.id)) current = s.id;
  const active = d.runs.find((r) => !r.done);
  if (active) current = active.mode === 'formal' ? 'review' : 'check';
  if (trialRunning) current = 'check';
  return { done, available, current, running };
}
