// Conversation: sends turns to /api/chat/stream, turns stream events into compact cards,
// offers next steps (chips, cards), and handles slash commands. Typing is never blocked.
import { streamChat, postJSON } from './api.js';
import { state, project, emit, addMessage, updateMessage, currentHypothesis, setHypothesis, stageState, STAGES } from './store.js';
import { $, esc, md, uid, brandMark, bustSVG, strokeSVG } from './util.js';
import { askText } from './ui.js';
import { fresh, seen } from './motion.js';

// ---------- Action registry (buttons carry data-act / data-arg) ----------
export const actions = {};
// Other modules (e.g. trial.js) render their own message kinds here.
export const cardRenderers = {};
// Extra lines under the pinned hypothesis (e.g. strength markers, hypothesis.js): fn(d, version, isCurrent) → html.
export const hypCardExtras = [];
export function register(name, fn) { actions[name] = fn; }

document.addEventListener('click', (e) => {
  const el = e.target.closest('[data-act]');
  if (!el || el.disabled) return;
  const fn = actions[el.dataset.act];
  if (!fn) return;
  e.preventDefault();
  fn(el.dataset.arg, el);
});

// ---------- Panels (the workspace module renders them) ----------
export function openPanel(name, { fromUser = false } = {}) {
  const d = project();
  if (!d) return;
  if (d.pinned && !fromUser) return;
  d.panel = name;
  if (fromUser) {
    const app = document.getElementById('app');
    app.classList.add('ws-open');
    if (app.classList.contains('ws-collapsed')) { app.classList.remove('ws-collapsed'); try { localStorage.setItem('thoth.ws', 'open'); } catch (_) {} }
  }
  emit();
}
register('panel', (name) => openPanel(name, { fromUser: true }));

// ---------- Conversation turns ----------
function chatTurns(d) {
  const turns = [];
  let pending = null;
  for (const m of d.messages) {
    if (m.role === 'user') { if (pending) turns.push(pending); pending = { user: m.text, assistant: '' }; }
    else if (pending && (m.role === 'thoth' || m.role === 'thinker') && m.text) pending.assistant += (pending.assistant ? '\n' : '') + m.text;
  }
  if (pending) turns.push(pending);
  return turns.slice(-8);
}

export async function sendTurn(body, ctx = {}) {
  const d = project();
  const payload = {
    session_id: d.sessionId, chat_turns: chatTurns(d), project_id: state.projectId,
    research_file: { question: d.question || '', hypothesis: currentHypothesis()?.text || '' },
    active_thinker: d.activeThinker?.id || null,
    ...body,
  };
  state.busy += 1; emit();
  try {
    await streamChat(payload, (type, p) => handleEvent(type, p));
  } catch (err) {
    addMessage({ role: 'thoth', text: `I couldn't reach the server: ${err.message}` });
  } finally {
    state.busy -= 1;
    emit();
  }
}

const HUMAN_ORIGINALITY = {
  likely_novel: 'no close prior work found in the searches run',
  partial_overlap: 'partly covered by prior work',
  substantially_covered: 'largely covered by prior work',
  insufficiently_assessed: 'originality could not be assessed reliably',
};

export function verdictLine(d) {
  const c = d.status?.claim_counts || {};
  const S = c.supported || 0, C = c.contradicted || 0, U = (c.uncertain || 0) + (c.insufficiently_assessed || 0);
  let v;
  if (!S && !C && !U) v = 'Too little was audited to judge the evidence';
  else if (S && !C && !U) v = 'Supported by the sources read';
  else if (C > S) v = 'Mostly challenged by the sources read';
  else if (S) v = 'Partly supported, partly challenged or unclear';
  else v = 'Unclear: the evidence read is mixed or insufficient';
  const parts = [v];
  if (d.originality?.verdict) parts.push(HUMAN_ORIGINALITY[d.originality.verdict] || d.originality.verdict);
  parts.push(d.status?.report_status === 'fully_reviewed' ? 'fully reviewed' : 'provisional');
  return parts.join(' · ');
}

// /api/chat/stream sends conductor cards, idea promotions, errors and complete. (The retired plan-and-pipeline
// events are gone; results older projects saved from it still render from their stored state.)
function handleEvent(type, p) {
  const d = project();
  switch (type) {
    case 'turn_start':
    case 'complete':
      break;
    case 'direct_answer':
      addMessage({ role: 'thoth', text: p.answer || '', degraded: !!p.degraded });
      break;
    case 'quick_look_result': {
      const key = uid('pl');
      d.papers[key] = { query: p.query, papers: p.papers || [] };
      addMessage({ role: 'thoth', kind: 'papers', papers: key });
      break;
    }
    case 'notebook_proposal':
    case 'thinker_suggestion':
    case 'step_offer':
      d.proposals[p.proposal_id] = { ...p, type, status: 'open' };
      addMessage({ role: 'thoth', kind: 'proposal', proposal: p.proposal_id });
      break;
    case 'idea_promoted': {
      const idea = d.ideas.find((i) => i.title === p.idea?.title) || d.ideas[d.ideas.length - 1];
      if (idea) idea.status = 'promoted';
      addMessage({ role: 'note', text: `Added “${p.idea?.title || 'idea'}” to your idea network.` });
      break;
    }
    case 'error':
      addMessage({ role: 'thoth', text: `Something went wrong: ${p.error || 'unknown error'}` });
      break;
    default:
      break;
  }
  emit();
}

// ---------- User-facing actions ----------
export function say(text, ctx = {}) {
  const clean = String(text || '').trim();
  if (!clean) return;
  const d = project();
  if (!d.firstObservation) d.firstObservation = clean;
  addMessage({ role: 'user', text: clean });
  if (d.activeThinker && actions.thinkerReply) return actions.thinkerReply(clean);
  sendTurn({ message: clean }, { id: uid('ctx'), ...ctx });
}
register('say', (t) => say(t));

// Plan cards saved by the retired pipeline still show an Approve button in older projects.
register('approve', () => addMessage({ role: 'note', text: 'That older plan can no longer run. Use Check to put the hypothesis on trial, or plan a systematic review; each asks for approval first.' }));

register('promote', (key) => {
  const idea = project().ideas.find((i) => i.key === key);
  if (!idea || idea.status === 'promoted') return;
  idea.status = 'promoting';
  sendTurn({ message: '', idea_promotion: { title: idea.title, hypothesis: idea.hypothesis, rationale: idea.rationale } }, { id: uid('ctx') });
});

register('dismissIdea', (key) => {
  const idea = project().ideas.find((i) => i.key === key);
  if (idea) idea.status = 'dismissed';
  emit();
});

register('useAsHypothesis', (arg) => {
  const d = project();
  const idea = d.ideas.find((i) => i.key === arg);
  if (idea) setHypothesis(idea.hypothesis || idea.title, 'From an idea Thoth noticed in the conversation', 'idea');
  else setHypothesis(arg, 'Proposed in a thinker conversation', d.escalation?.source || 'thinker');
  addMessage({ role: 'thoth', text: 'Pinned as your working hypothesis. You can edit it, refine it with a thinker, or check it against the literature.', chips: [{ label: 'Check the evidence', act: 'check', primary: true }, { label: 'Hear the council', act: 'council' }] });
  openPanel('hypothesis');
});

// "Check" puts the hypothesis on trial (trial.js); a formal review is the systematic review (review.js).
export function startCheck() { return actions.startTrial?.(); }
register('check', startCheck);

export function startReview(topic) { return actions.startSystematicReview?.(topic); }
register('review', () => startReview());

// ---------- Conductor cards: unchecked claims, proposals, suggestions, offers ----------
register('checkClaim', (claim) => {
  if (!claim) return;
  addMessage({ role: 'user', text: `Check: ${claim}` });
  sendTurn({ message: '', check_claim: claim }, { id: uid('ctx') });
});

async function resolveProposal(pid, action, value) {
  const d = project();
  const prop = d.proposals[pid];
  if (!prop || prop.status !== 'open') return null;
  prop.status = 'saving'; emit();
  try {
    const res = await postJSON(`/api/chat/proposals/${encodeURIComponent(pid)}`, { action, value });
    prop.status = res.status;
    return res;
  } catch (err) {
    prop.status = 'open';
    addMessage({ role: 'note', text: `Couldn't save that: ${err.message}` });
    return null;
  } finally { emit(); }
}

function applyNotebook(section, value, how) {
  const d = project();
  if (section === 'question') d.question = value;
  else if (section === 'hypothesis') { setHypothesis(value, how, 'thoth', { saved: true }); openPanel('hypothesis'); }
  else if (section === 'rival_hypothesis') d.rivals.push(value);
  emit();
}

register('acceptProposal', async (pid) => {
  const res = await resolveProposal(pid, 'accept');
  if (res?.section) applyNotebook(res.section, res.value, 'Proposed by Thoth, accepted by you');
});
register('editProposal', async (pid) => {
  const prop = project().proposals[pid];
  if (!prop) return;
  const value = await askText({ title: `Edit the ${prop.section.replace('_', ' ')}`, value: prop.value, confirm: 'Save my version', required: true });
  if (value === null || !value.trim()) return;
  const res = await resolveProposal(pid, 'edit', value.trim());
  if (res?.section) applyNotebook(res.section, res.value, 'Proposed by Thoth, edited by you');
});
register('dismissProposal', (pid) => resolveProposal(pid, 'dismiss'));
register('inviteThinker', async (pid) => {
  const prop = project().proposals[pid];
  const res = await resolveProposal(pid, 'accept');
  if (res && prop) actions.join?.(prop.thinker_id);
});
register('acceptOffer', (pid) => {
  const d = project();
  const prop = d.proposals[pid];
  if (!prop || prop.status !== 'open') return;
  if (prop.step === 'systematic_review' && actions.startSystematicReview) {
    prop.status = 'accepted';
    postJSON(`/api/chat/proposals/${encodeURIComponent(pid)}`, { action: 'accept' }).catch(() => {});
    return actions.startSystematicReview();
  }
  if (prop.step === 'trial') {
    prop.status = 'accepted';
    postJSON(`/api/chat/proposals/${encodeURIComponent(pid)}`, { action: 'accept' }).catch(() => {});
    return actions.startTrial?.();
  }
  // An older "scan" offer: the trial is the lightweight check now.
  prop.status = 'accepted';
  postJSON(`/api/chat/proposals/${encodeURIComponent(pid)}`, { action: 'accept' }).catch(() => {});
  return actions.startTrial?.();
});

const SECTION_LABEL = { question: 'Research question', hypothesis: 'Hypothesis', rival_hypothesis: 'Rival hypothesis', thinker_note: 'Thinker note' };

function proposalCard(prop) {
  const open = prop.status === 'open';
  const closed = { accepted: 'Accepted', edited: 'Accepted with your edit', dismissed: 'Dismissed', saving: 'Saving…' }[prop.status] || '';
  if (prop.type === 'notebook_proposal') {
    return `<div class="card proposal">
      <div class="card-kicker">Add to your research file? · ${esc(SECTION_LABEL[prop.section] || prop.section)}</div>
      <div class="card-title">${esc(prop.value)}</div>
      ${prop.why ? `<div class="muted">${esc(prop.why)}</div>` : ''}
      <div class="chips">${open ? `<button class="chip primary" data-act="acceptProposal" data-arg="${esc(prop.proposal_id)}">Accept</button>
        <button class="chip" data-act="editProposal" data-arg="${esc(prop.proposal_id)}">Edit</button>
        <button class="chip" data-act="dismissProposal" data-arg="${esc(prop.proposal_id)}">Not now</button>` : `<span class="faint">${closed}</span>`}</div></div>`;
  }
  if (prop.type === 'thinker_suggestion') {
    return `<div class="card proposal thinker-suggest">
      <div class="card-kicker">A thinker might help</div>
      <div class="suggest-row">${bustSVG(prop.name)}<div><div class="card-title">${esc(prop.name)}</div><div class="muted">${esc(prop.why)}</div></div></div>
      <div class="chips">${open ? `<button class="chip primary" data-act="inviteThinker" data-arg="${esc(prop.proposal_id)}">Bring ${esc(prop.name.split(' ').pop())} in</button>
        <button class="chip" data-act="dismissProposal" data-arg="${esc(prop.proposal_id)}">Not now</button>` : `<span class="faint">${closed === 'Accepted' ? 'Invited' : closed}</span>`}</div></div>`;
  }
  const e = prop.estimate || {};
  return `<div class="card proposal heavy">
    <div class="card-kicker">Next step, if you want it · nothing starts until you say so</div>
    <div class="card-title">${esc(e.label || prop.step)}</div>
    ${prop.why ? `<div class="muted">${esc(prop.why)}</div>` : ''}
    <div class="effort">${esc(e.scope || '')} · ${esc(e.duration || '')} · ${esc(e.model_calls || '')} model calls (free tier)</div>
    <div class="chips">${open ? `<button class="chip primary" data-act="acceptOffer" data-arg="${esc(prop.proposal_id)}">Plan it</button>
      <button class="chip" data-act="dismissProposal" data-arg="${esc(prop.proposal_id)}">Not yet</button>` : `<span class="faint">${closed === 'Accepted' ? 'Planned below' : closed}</span>`}</div></div>`;
}

const VERDICT = { supportive: 'supportive', mixed: 'mixed', objecting: 'objecting' };
function reviewsCard(reviews) {
  if (!reviews.length) return '<div class="card"><div class="muted">No reviews came back.</div></div>';
  return `<div class="card reviews"><div class="card-kicker">Independent reviews of your ${esc(reviews[0]?.artifact || 'hypothesis')} · written without seeing each other</div>
    ${reviews.map((r) => {
      const env = r.envelope || {};
      const critical = (env.concerns || []).filter((c) => c.severity === 'critical').length;
      return `<details class="review"${reviews.length === 1 ? ' open' : ''}><summary><button class="bust-btn" data-act="profile" data-arg="${esc(r.thinker_id)}" aria-label="About ${esc(r.thinker_name)}">${bustSVG(r.thinker_name)}</button>
        <b>${esc(r.thinker_name)}</b>${r.degraded ? '<span class="faint">couldn\'t be reached</span>' : `<span class="verdict v-${esc(env.verdict || 'unread')}">${esc(VERDICT[env.verdict] || 'read the review')}</span>${critical ? `<span class="verdict v-objecting">${critical} critical</span>` : ''}`}</summary>
        ${r.degraded ? '' : `<div class="prose">${md(r.review)}</div>${env.would_change_mind_if ? `<div class="faint">Would change their mind: ${esc(env.would_change_mind_if)}</div>` : ''}
        <div class="acts"><button class="link-btn strong" data-act="join" data-arg="${esc(r.thinker_id)}">Answer ${esc(r.thinker_name.split(' ').pop())}</button></div>`}</details>`;
    }).join('')}</div>`;
}

function papersCard(pl) {
  if (!pl) return '';
  if (!pl.papers.length) return `<div class="card papers"><div class="card-kicker">Quick look · ${esc(pl.query)}</div><div class="muted">No papers found for this query.</div></div>`;
  return `<details class="card papers"><summary><span class="card-kicker">Quick look · ${pl.papers.length} papers · abstracts only</span><span class="faint">${esc(pl.query)}</span></summary>
    <ol class="paper-list">${pl.papers.map((p) => `<li><a href="${esc(p.url)}" target="_blank" rel="noopener">${esc(p.title)}</a>
      <div class="faint">${esc((p.authors || []).join(', '))}${p.year ? ` · ${esc(p.year)}` : ''} · ${p.access === 'abstract_only' ? 'abstract' : 'no abstract'}</div></li>`).join('')}</ol></details>`;
}

export function prefill(text) {
  const input = $('#input');
  input.value = text;
  input.focus();
  input.dispatchEvent(new Event('input'));
}
register('prefill', prefill);

// ---------- Slash commands ----------
export const COMMANDS = [
  { cmd: '/brainstorm', desc: 'Think out loud about something puzzling', run: () => { prefill(''); $('#input').placeholder = 'What has been puzzling you?'; } },
  { cmd: '/council', desc: 'Every thinker gives a one-line take', run: (a) => actions.council?.(a) },
  { cmd: '/debate', desc: 'Two thinkers debate your idea (e.g. /debate popper kuhn)', run: (a) => actions.debateCmd?.(a) },
  { cmd: '/room', desc: 'One-on-one with a thinker (e.g. /room hume)', run: (a) => actions.room?.(a.trim().split(/\s+/)[0]) },
  { cmd: '/hypothesis', desc: 'Write or replace the working hypothesis', run: (a) => (a.trim() ? (setHypothesis(a, 'Written by you', 'you'), openPanel('hypothesis')) : openPanel('hypothesis', { fromUser: true })) },
  { cmd: '/check', desc: 'Check the hypothesis against the literature', run: () => startCheck() },
  { cmd: '/review', desc: 'Formal PRISMA review (plan first, needs approval)', run: (a) => startReview(a) },
  { cmd: '/draft', desc: 'Open the research draft', run: () => openPanel('draft', { fromUser: true }) },
];

export function thinkerCommands() {
  return state.thinkers.map((t) => ({ cmd: `/${t.id}`, desc: `${t.name} joins the conversation`, run: (a) => actions.join?.(t.id, a) }));
}

function allCommands() { return [...COMMANDS, ...thinkerCommands()]; }

function runCommand(text) {
  const [head, ...rest] = text.trim().split(/\s+/);
  const arg = rest.join(' ');
  const c = allCommands().find((x) => x.cmd === head.toLowerCase());
  if (!c) { addMessage({ role: 'note', text: `Unknown command ${head}. Type / to see what's available.` }); return; }
  c.run(arg);
}

// ---------- Rendering ----------
function chipHTML(c) {
  return `<button type="button" class="chip${c.primary ? ' primary' : ''}" data-act="${esc(c.act)}" data-arg="${esc(c.arg ?? '')}">${esc(c.label)}</button>`;
}

function renderBody(m, d) {
  switch (m.kind) {
    case 'idea': {
      const i = d.ideas.find((x) => x.key === m.idea) || {};
      const closed = i.status !== 'suggested';
      return `<div class="card">
        <div class="card-kicker">Idea worth capturing? · ${esc(i.trigger_label || i.trigger || 'noticed')}</div>
        <div class="card-title">${esc(i.title || '')}</div>
        <div class="muted">${esc(i.rationale || '')}</div>
        <div class="chips">
          <button class="chip primary" data-act="useAsHypothesis" data-arg="${esc(i.key)}">Make it the hypothesis</button>
          <button class="chip" data-act="promote" data-arg="${esc(i.key)}" ${i.status === 'promoted' || i.status === 'promoting' ? 'disabled' : ''}>${i.status === 'promoted' ? 'Saved to ideas' : 'Save to ideas'}</button>
          <button class="chip" data-act="dismissIdea" data-arg="${esc(i.key)}" ${closed ? 'disabled' : ''}>Not now</button>
        </div></div>`;
    }
    case 'plan': {
      const b = d.brief && d.brief.brief_id === m.brief ? d.brief : null;
      const pending = d.pendingBrief && d.pendingBrief.brief_id === m.brief && d.pendingBrief.version === m.version;
      const cost = pending ? d.pendingBrief.cost : null;
      const formal = (b?.review_mode || cost?.review_mode) === 'formal';
      return `<div class="card${formal ? ' heavy' : ''}">
        <div class="card-kicker">${formal ? 'Formal PRISMA review' : 'Lightweight literature check'} · plan v${m.version}</div>
        <div class="card-title">${esc(b?.research_question || 'Research plan')}</div>
        ${cost ? `<div class="effort">${esc(cost.papers_considered)} · full texts: ${esc(cost.full_text_attempts)} · ${esc(cost.typical_duration)}</div>` : ''}
        <div class="chips">
          <span class="faint">An older plan; this path was retired.</span><button class="chip" data-act="check">Check instead</button>
          <button class="chip" data-act="panel" data-arg="${formal ? 'review' : 'check'}">See the plan</button>
        </div></div>`;
    }
    case 'formal': {
      const r = d.recommendFormal || {};
      const e = r.effort || {};
      return `<div class="card heavy">
        <div class="card-kicker">Next step suggested</div>
        <div class="card-title">This could be worth a formal review</div>
        <ul class="list">${(r.reasons || []).map((x) => `<li>${esc(x)}</li>`).join('')}</ul>
        <div class="effort">Extra effort: ${esc(e.papers_considered || '')} · ${esc(e.full_text_attempts || '')} · ${esc(e.typical_duration || '')}</div>
        <div class="chips">${d.prisma ? '<span class="faint">Formal review done.</span>' : '<button class="chip primary" data-act="review">Yes, plan a formal review</button><button class="chip" data-act="noop">Not yet</button>'}</div>
      </div>`;
    }
    case 'proposal': return d.proposals[m.proposal] ? proposalCard(d.proposals[m.proposal]) : '';
    case 'reviews': return reviewsCard((d.reviews || {})[m.reviews] || []);
    case 'papers': return papersCard(d.papers[m.papers]);
    case 'steps': {
      const r = d.runs.find((x) => x.id === m.run);
      if (!r) return '';
      const last = r.steps[r.steps.length - 1];
      const summary = r.done ? r.steps.filter((s) => /Searched|scan|PRISMA|Status|Originality/.test(s.text)).map((s) => s.text.split(' · ').slice(-1)[0]).join(' · ') || 'Done' : (last?.text || 'Starting…');
      return `<details class="steps${r.done ? ' done' : ''}">
        <summary>${strokeSVG()}<span>${esc(summary)}</span><span class="faint mono" style="margin-left:auto">${r.steps.length} steps</span></summary>
        <ol>${r.steps.map((s) => `<li>${esc(s.text)}</li>`).join('')}</ol>
      </details>`;
    }
    case 'council': {
      const c = d.council;
      if (!c) return '';
      return `<div class="card"><div class="card-kicker">The council · ${esc(c.idea ? c.idea.slice(0, 80) : '')}</div>
        <div class="council-grid">${c.council.filter((t) => t.take).slice(0, 3).map((t) => `<div class="council-item${d.debatePicks.includes(t.id) ? ' picked' : ''}">
          <header><button class="bust-btn" data-act="profile" data-arg="${t.id}" aria-label="About ${esc(t.name)}">${bustSVG(t.name)}</button><span>${esc(t.name)}</span></header>
          <p>${esc(t.take)}</p>
          <div class="acts"><button class="link-btn strong" data-act="join" data-arg="${t.id}">Talk</button><button class="link-btn" data-act="room" data-arg="${t.id}">Alone</button><button class="link-btn" data-act="pick" data-arg="${t.id}">${d.debatePicks.includes(t.id) ? 'Picked' : 'Debate'}</button></div>
        </div>`).join('')}</div>
        <div><button class="link-btn strong" data-act="panel" data-arg="thinkers">All ${c.council.length} takes in the workspace →</button></div>
        ${c.council.some((t) => !t.take) ? `<div class="faint">${c.council.filter((t) => !t.take).length} thinker(s) couldn't be reached; nothing was written for them.</div>` : ''}
      </div>`;
    }
    default:
      if (cardRenderers[m.kind]) return cardRenderers[m.kind](m, d);
      return `<div class="prose">${md(m.text)}</div>`;
  }
}

function renderMessage(m, d) {
  const fx = fresh(`msg:${m.id}`);
  if (m.role === 'user') return `<div class="msg user${fx.cls}"${fx.attr}><div class="body">${esc(m.text)}</div></div>`;
  if (m.role === 'note') return `<div class="msg note${fx.cls}"${fx.attr}><div class="body">${esc(m.text)}</div></div>`;
  const isThinker = m.role === 'thinker';
  const who = isThinker ? `<button class="bust-btn" data-act="profile" data-arg="${esc(m.thinker?.id)}" aria-label="About ${esc(m.thinker?.name)}">${bustSVG(m.thinker?.name)}</button>` : brandMark();
  const name = isThinker ? `${esc(m.thinker?.name)}${m.round ? ` · debate, round ${m.round}` : ' · perspective'}` : 'Thoth';
  const chips = (m.chips || []).length ? `<div class="chips">${m.chips.map(chipHTML).join('')}</div>` : '';
  return `<div class="msg ${m.role}${fx.cls}"${fx.attr} data-id="${m.id}"><div class="who">${who}</div><div class="body"><div class="name">${name}</div>${renderBody(m, d)}${chips}</div></div>`;
}

let lastCount = 0;
let lastPid = null;
export function renderConversation() {
  const d = project();
  const box = $('#messages');
  if (!d) { box.innerHTML = ''; lastPid = null; return; }
  // Opening a project: its history is already there; only what arrives from now on enters.
  if (lastPid !== state.projectId) { seen(d.messages.slice(0, -1).map((m) => `msg:${m.id}`)); lastPid = state.projectId; }
  const open = new Set([...box.querySelectorAll('details[open]')].map((el) => el.closest('.msg')?.dataset.id));
  const nearBottom = box.scrollHeight - box.scrollTop - box.clientHeight < 120;
  box.innerHTML = d.messages.map((m) => renderMessage(m, d)).join('');
  for (const id of open) box.querySelector(`.msg[data-id="${id}"] details`)?.setAttribute('open', '');
  if (nearBottom || d.messages.length !== lastCount) { box.scrollTop = box.scrollHeight; requestAnimationFrame(() => { box.scrollTop = box.scrollHeight; }); }
  lastCount = d.messages.length;

  const banner = $('#thinkerBanner');
  if (d.activeThinker) {
    banner.hidden = false;
    banner.innerHTML = `<button class="bust-btn" data-act="profile" data-arg="${esc(d.activeThinker.id)}" aria-label="About ${esc(d.activeThinker.name)}">${bustSVG(d.activeThinker.name)}</button><span>Talking with <b>${esc(d.activeThinker.name)}</b>. Thoth is listening.</span><button class="link-btn" data-act="leaveThinker" style="margin-left:auto">Back to Thoth</button>`;
  } else banner.hidden = true;
  renderHypothesisCard(d);
}

function renderHypothesisCard(d) {
  const slot = $('#hypothesisCard');
  const versions = d.hypothesis.versions;
  const q = d.question ? `<div class="q-line"><span class="q-label">Question</span>${esc(d.question)}</div>` : '';
  if (!versions.length) { slot.innerHTML = q ? `<div class="hyp-card question-only">${q}</div>` : ''; return; }
  const view = Math.min(Math.max(d.hypothesis.view, 0), versions.length - 1);
  const v = versions[view];
  const isCurrent = view === versions.length - 1;
  const trail = versions.map((x, i) => ({ ...x, n: i + 1 })).filter((x) => x.source && !['you', 'idea'].includes(x.source)).map((x) => `${x.source} (v${x.n})`);
  slot.innerHTML = `<div class="hyp-card">${q}
    <div class="hyp-top">Hypothesis
      <span class="versions"><button data-act="hypPrev" ${view === 0 ? 'disabled' : ''} aria-label="Previous version">◀</button>v${view + 1}${isCurrent ? '' : ' (older)'}<button data-act="hypNext" ${isCurrent ? 'disabled' : ''} aria-label="Next version">▶</button></span></div>
    <div class="hyp-text" id="hypText" data-act="hypToggle" title="Tap to expand">${esc(v.text)}</div>
    <div class="hyp-trail">${esc(v.reason || '')}${trail.length ? ` · refined after ${esc(trail.join(', '))}` : ''}</div>
    ${hypCardExtras.map((f) => f(d, v, isCurrent)).join('')}
    <div class="hyp-actions">
      <button class="link-btn strong" data-act="check">Check this →</button>
      <button class="link-btn" data-act="hypEdit">Edit</button>
      <button class="link-btn" data-act="reviewHyp">Get reviews</button>
      <button class="link-btn" data-act="council">Ask the council</button>
      <button class="link-btn" data-act="panel" data-arg="hypothesis">History</button>
    </div></div>`;
}

register('hypPrev', () => { const d = project(); d.hypothesis.view = Math.max(0, d.hypothesis.view - 1); emit(); });
register('hypNext', () => { const d = project(); d.hypothesis.view = Math.min(d.hypothesis.versions.length - 1, d.hypothesis.view + 1); emit(); });
register('hypEdit', () => {
  const el = $('#hypText');
  if (!el) return;
  const d = project();
  d.hypothesis.view = d.hypothesis.versions.length - 1;
  el.textContent = currentHypothesis().text;
  el.contentEditable = 'true';
  el.focus();
  const finish = () => {
    el.contentEditable = 'false';
    setHypothesis(el.textContent, 'Edited by you', 'you');
    emit();
  };
  el.addEventListener('blur', finish, { once: true });
  el.addEventListener('keydown', (e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); el.blur(); } });
});
register('noop', () => {});
register('hypToggle', (_, el) => { if (el.contentEditable !== 'true') el.closest('.hyp-card')?.classList.toggle('expanded'); });

// ---------- Composer ----------
export function initComposer() {
  const form = $('#composer');
  const input = $('#input');
  const menu = $('#slashMenu');
  let sel = 0;
  let items = [];

  const resize = () => { input.style.height = 'auto'; input.style.height = Math.min(input.scrollHeight, 200) + 'px'; };
  const closeMenu = () => { menu.hidden = true; items = []; };
  const showMenu = () => {
    const v = input.value;
    if (!v.startsWith('/') || v.includes('\n')) return closeMenu();
    const head = v.split(/\s/)[0].toLowerCase();
    if (v.includes(' ')) return closeMenu();
    items = allCommands().filter((c) => c.cmd.startsWith(head)).slice(0, 12);
    if (!items.length) return closeMenu();
    sel = Math.min(sel, items.length - 1);
    menu.innerHTML = items.map((c, i) => `<button type="button" role="option" aria-selected="${i === sel}" data-i="${i}"><span class="cmd">${esc(c.cmd)}</span><span class="desc">${esc(c.desc)}</span></button>`).join('');
    menu.hidden = false;
  };
  const choose = (i) => { input.value = items[i].cmd + ' '; closeMenu(); input.focus(); resize(); };

  menu.addEventListener('mousedown', (e) => { const b = e.target.closest('button[data-i]'); if (b) { e.preventDefault(); choose(+b.dataset.i); } });
  input.addEventListener('input', () => { resize(); sel = 0; showMenu(); });
  input.addEventListener('keydown', (e) => {
    if (!menu.hidden && items.length) {
      if (e.key === 'ArrowDown') { e.preventDefault(); sel = (sel + 1) % items.length; showMenu(); return; }
      if (e.key === 'ArrowUp') { e.preventDefault(); sel = (sel - 1 + items.length) % items.length; showMenu(); return; }
      if (e.key === 'Tab') { e.preventDefault(); choose(sel); return; }
      if (e.key === 'Escape') { closeMenu(); return; }
    }
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); form.requestSubmit(); }
  });
  form.addEventListener('submit', (e) => {
    e.preventDefault();
    const text = input.value.trim();
    if (!text) return;
    if (!menu.hidden && items.length && text === items[sel].cmd.slice(0, text.length) && !text.includes(' ') && text !== items[sel].cmd) { choose(sel); return; }
    input.value = ''; resize(); closeMenu();
    input.placeholder = 'Think out loud… or type / for actions';
    if (text.startsWith('/')) runCommand(text);
    else say(text);
  });
}

export function currentStageLabel() {
  const s = stageState();
  return STAGES.find((x) => x.id === s.current)?.label || 'Explore';
}
