// Thoth · Developed by Shayan Azmi
// Stage-aware workspace. Follows the journey by default; any tab can be opened by hand and pinned.
import { state, project, emit, currentHypothesis, stageState, STAGES } from './store.js';
import { register } from './chat.js';
import { $, esc, md, clock, bustSVG } from './util.js';
import { fresh, again } from './motion.js';

let shownPanel = null;

const TABS = [
  ['ideas', 'Ideas'], ['thinkers', 'Thinkers'], ['hypothesis', 'Hypothesis'],
  ['check', 'Check'], ['review', 'Review'], ['design', 'Design'], ['draft', 'Draft'],
];

register('pin', () => { const d = project(); d.pinned = !d.pinned; emit(); });
register('closeWorkspace', () => {
  const app = document.getElementById('app');
  app.classList.remove('ws-open');
  if (window.matchMedia('(min-width: 1200px)').matches) {
    app.classList.add('ws-collapsed');
    try { localStorage.setItem('thoth.ws', 'collapsed'); } catch (_) {}
  }
});

const empty = (title, body, action = '') => `<div class="empty"><b>${title}</b><br>${body}${action ? `<div class="chips">${action}</div>` : ''}</div>`;

function ideasPanel(d) {
  const ideas = d.ideas.filter((i) => i.status !== 'dismissed');
  return `<h2>Ideas</h2>
    ${d.firstObservation ? `<div class="ws-section"><h3>Where this started</h3><p class="prose">${esc(d.firstObservation)}</p></div>` : ''}
    <div class="ws-section"><h3>Directions noticed</h3>${ideas.length ? `<ul class="list">${ideas.map((i) => `<li><b>${esc(i.title)}</b> <span class="badge">${esc(i.status)}</span><br><span class="muted">${esc(i.rationale || '')}</span><div class="chips"><button class="chip" data-act="useAsHypothesis" data-arg="${esc(i.key)}">Make it the hypothesis</button></div></li>`).join('')}</ul>` : empty('Nothing yet.', 'As you talk, Thoth points out directions that might be worth investigating. Nothing is saved unless you choose.')}</div>
    ${d.followUps?.length ? `<div class="ws-section"><h3>Open questions</h3><ul class="list">${d.followUps.map((q) => `<li>${esc(q)} <button class="link-btn" data-act="say" data-arg="${esc(q)}">Ask</button></li>`).join('')}</ul></div>` : ''}`;
}

function thinkersPanel(d) {
  const takes = Object.fromEntries((d.council?.council || []).map((t) => [t.id, t.take]));
  return `<h2>Thinkers</h2>
    <p class="muted">Ten co-authors, each with their own mind. They remember this project, can change their minds, and none has a veto. Tap a bust to see how they thought.</p>
    <div class="chips"><button class="chip primary" data-act="council">Hear first reactions</button>${d.hypothesis.versions.length ? '<button class="chip" data-act="reviewHyp">Get reviews of the hypothesis</button>' : ''}${d.debatePicks.length >= 2 ? `<button class="chip" data-act="debate" data-arg="${d.debatePicks.join(',')}">Debate the ${d.debatePicks.length} picked</button>` : '<span class="faint">Pick two or three below for a debate.</span>'}</div>
    <div class="council-grid">${state.thinkers.map((t) => `<div class="council-item${d.debatePicks.includes(t.id) ? ' picked' : ''}">
      <header><button class="bust-btn" data-act="profile" data-arg="${t.id}" aria-label="About ${esc(t.name)}">${bustSVG(t.name)}</button><span>${esc(t.name)}</span><span class="faint" style="margin-left:auto">${esc(t.years || '')}</span></header>
      <div class="prose">${md(takes[t.id] || t.brings || '')}</div>
      <div class="acts"><button class="link-btn strong" data-act="join" data-arg="${t.id}">Talk</button><button class="link-btn" data-act="room" data-arg="${t.id}" title="A one-to-one conversation with ${esc(t.name)}, away from the others">Alone</button><button class="link-btn" data-act="pick" data-arg="${t.id}">${d.debatePicks.includes(t.id) ? 'Picked' : 'Debate'}</button></div>
    </div>`).join('')}</div>`;
}

// The backend sometimes turns a thinker's questions into "criteria"; show only clean statements.
function cleanCriteria(list) {
  return (list || []).filter((x) => typeof x === 'string' && !x.includes('?') && x.length < 220).slice(0, 3);
}

function hypothesisPanel(d) {
  const v = d.hypothesis.versions;
  const cur = currentHypothesis(d);
  const b = d.brief || {};
  if (!cur) {
    return `<h2>Hypothesis</h2>${empty('No hypothesis yet.', 'Keep talking, use an idea Thoth noticed, accept one a thinker proposes, or write your own.', '<button class="chip primary" data-act="prefill" data-arg="/hypothesis ">Write one</button><button class="chip" data-act="council">Hear the council</button>')}`;
  }
  return `<h2>Hypothesis</h2>
    <div class="ws-section"><p class="hyp-text">${esc(cur.text)}</p>
      <div class="chips"><button class="chip primary" data-act="check">Check against the literature</button><button class="chip" data-act="hypEdit">Edit</button></div></div>
    ${d.firstObservation ? `<div class="ws-section"><h3>Original motivation (kept unchanged)</h3><p>${esc(d.firstObservation)}</p></div>` : ''}
    ${b.context_and_assumptions?.length ? `<div class="ws-section"><h3>Assumptions</h3><ul class="list">${b.context_and_assumptions.map((x) => `<li>${esc(x)}</li>`).join('')}</ul></div>` : ''}
    ${cleanCriteria(b.falsification_criteria).length ? `<div class="ws-section"><h3>What would prove it wrong</h3><ul class="list">${cleanCriteria(b.falsification_criteria).map((x) => `<li>${esc(x)}</li>`).join('')}</ul></div>` : ''}
    ${v.length && v[0].reason ? `<div class="ws-section"><h3>Where it started</h3><p>${esc(v[0].text)}</p><p class="faint">${esc(v[0].reason)}${(v[0].context || []).filter((c) => c.kind === 'question').map((c) => ` · asked: “${esc(c.label)}”`).join('')}</p></div>` : ''}
    <div class="ws-section"><h3>Versions, and why each changed</h3><ol class="list">${v.map((x, i) => `<li><span class="badge">v${i + 1}</span> ${esc(x.text)}
      <br><span class="faint">${esc(x.reason || '')} · ${esc(TRIGGER[x.trigger] || x.source || '')} · ${clock(x.at)}</span>
      ${(x.evidence || []).length ? `<div class="chips">${x.evidence.map((e) => `<span class="badge" title="${esc(e.kind.replace(/_/g, ' '))}">${esc(e.label || e.kind)}</span>`).join('')}</div>` : ''}
      ${(x.context || []).filter((c) => c.kind !== 'question').length ? `<div class="faint">What was known then: ${x.context.filter((c) => c.kind !== 'question').map((c) => esc(c.label)).join('; ')}</div>` : ''}</li>`).reverse().join('')}</ol></div>`;
}

const TRIGGER = { initial: 'first version', user_edit: 'your edit', thoth_proposal: 'proposed by Thoth, accepted by you', trial_verdict: 'after a trial',
  review_finding: 'after a review finding', thinker_critique: 'from a thinker conversation', rival_swap: 'a rival swapped in', idea: 'from an idea' };

function checkPanel(d) {
  return `<h2>Check</h2>${empty('Not checked yet.', 'Put your hypothesis on trial: Thoth splits it into claims, reads papers as witnesses and gives a ruling that can go against it. You see the plan and its cost first.', currentHypothesis(d) ? '<button class="chip primary" data-act="check">Check my hypothesis</button>' : '<button class="chip" data-act="prefill" data-arg="/hypothesis ">Write a hypothesis first</button>')}`;
}

function reviewPanel() {
  return `<h2>Systematic review</h2>${empty('No systematic review yet.', 'A PRISMA 2020 review records every search, screening decision and exclusion. It costs more than a trial and always asks for approval first.', '<button class="chip primary" data-act="review">Plan a systematic review</button>')}`;
}

export const PANELS = { ideas: ideasPanel, thinkers: thinkersPanel, hypothesis: hypothesisPanel, check: checkPanel, review: reviewPanel, design: () => '<h2>Study design</h2>', draft: () => '<h2>Research proposal</h2>' };

function timeline(d) {
  const run = d.runs[d.runs.length - 1];
  if (!run) return '';
  return `<details class="timeline" ${run.done ? '' : 'open'}><summary><span class="dot${run.done ? '' : ' live'}"></span>Activity · ${run.mode === 'formal' ? 'formal review' : 'check'} · ${run.done ? 'finished' : 'running'}</summary>
    <ol>${run.steps.map((s) => `<li><time>${clock(s.t)}</time><span>${esc(s.text)}</span></li>`).join('')}</ol></details>`;
}

let lastStage = null;
export function renderWorkspace() {
  const d = project();
  const ws = $('#workspace');
  if (!d) { ws.innerHTML = ''; return; }
  const st = stageState(d);
  if (st.current !== lastStage) {
    if (lastStage !== null && !d.pinned) d.panel = STAGES.find((s) => s.id === st.current)?.panel || d.panel;
    lastStage = st.current;
  }
  const panel = PANELS[d.panel] ? d.panel : 'ideas';
  const keepScroll = ws.querySelector('.ws-body')?.scrollTop || 0;
  const pageKey = `page:${state.projectId}:${panel}`;
  if (shownPanel !== pageKey) { again(pageKey); shownPanel = pageKey; }
  const page = fresh(pageKey, 1000);
  ws.innerHTML = `<div class="ws-tabs">
      <div class="ws-tablist" role="tablist">${TABS.map(([id, name]) => `<button class="ws-tab" role="tab" aria-selected="${id === panel}" data-act="panel" data-arg="${id}">${name}</button>`).join('')}</div>
      <button class="icon-btn" data-act="pin" aria-pressed="${d.pinned}" title="${d.pinned ? 'Pinned: click to follow the journey again' : 'Pin this panel'}" aria-label="Pin panel">
        <svg viewBox="0 0 24 24" fill="${d.pinned ? 'currentColor' : 'none'}" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"><path d="M9 4h6l-1 6 3 3H7l3-3z"/><path d="M12 13v7" stroke-linecap="round"/></svg>
      </button>
      <button class="icon-btn" data-act="closeWorkspace" aria-label="Hide workspace" title="Hide workspace">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"><path d="M9 6l6 6-6 6"/></svg>
      </button>
    </div>
    <div class="ws-body${page.cls}"${page.attr}>${PANELS[panel](d)}</div>${timeline(d)}`;
  ws.querySelector('.ws-body').scrollTop = keepScroll;
}

export function resetStageMemory() { lastStage = null; }
