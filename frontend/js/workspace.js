// Stage-aware workspace. Follows the journey by default; any tab can be opened by hand and pinned.
import { state, project, emit, currentHypothesis, stageState, STAGES } from './store.js';
import { register, verdictLine } from './chat.js';
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
const label = (l) => `<span class="label ${esc(l)}">${esc(String(l).replace(/_/g, ' '))}</span>`;

function planSection(d, mode) {
  const b = d.pendingBrief;
  if (!b || (mode && (b.review_mode || 'scan') !== mode)) return '';
  const c = b.cost || {};
  return `<div class="ws-section card heavy">
    <div class="card-kicker">Plan v${b.version} · from the retired scan pipeline; it can no longer run</div>
    <div class="card-title">${esc(b.research_question)}</div>
    ${b.objectives?.length ? `<ul class="list">${b.objectives.map((o) => `<li>${esc(o)}</li>`).join('')}</ul>` : ''}
    <dl class="kv"><dt>Mode</dt><dd>${b.review_mode === 'formal' ? 'Formal PRISMA-aligned review' : 'Lightweight scan'}</dd>
      ${c.papers_considered ? `<dt>Papers</dt><dd>${esc(c.papers_considered)}</dd><dt>Full texts</dt><dd>${esc(c.full_text_attempts)}</dd><dt>Time</dt><dd>${esc(c.typical_duration)}</dd>` : ''}</dl>
    <div class="chips"><button class="chip primary" data-act="check">Put the hypothesis on trial instead</button></div>
  </div>`;
}

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
      <p>${esc(takes[t.id] || t.brings || '')}</p>
      <div class="acts"><button class="link-btn strong" data-act="join" data-arg="${t.id}">Talk</button><button class="link-btn" data-act="room" data-arg="${t.id}">Alone</button><button class="link-btn" data-act="pick" data-arg="${t.id}">${d.debatePicks.includes(t.id) ? 'Picked' : 'Debate'}</button></div>
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
    <div class="ws-section"><h3>Versions</h3><ol class="list">${v.map((x, i) => `<li><span class="badge">v${i + 1}</span> ${esc(x.text)}<br><span class="faint">${esc(x.reason || '')} · ${esc(x.source || '')} · ${clock(x.at)}</span></li>`).reverse().join('')}</ol></div>`;
}

function checkPanel(d) {
  const running = d.runs.some((r) => !r.done && r.mode !== 'formal');
  const head = planSection(d, 'scan');
  if (!d.status) {
    if (running) return `<h2>Check</h2>${head}${empty('Checking…', 'Thoth is searching, reading abstracts and checking claims. Follow the steps in the conversation or the timeline below.')}`;
    return `<h2>Check</h2>${head}${head ? '' : empty('Not checked yet.', 'A lightweight check reads up to 20 abstracts and tells you what the evidence says about your hypothesis, and how original it looks.', currentHypothesis(d) ? '<button class="chip primary" data-act="check">Check my hypothesis</button>' : '<button class="chip" data-act="prefill" data-arg="/hypothesis ">Write a hypothesis first</button>')}`;
  }
  const claims = d.status.claims || [];
  const forC = claims.filter((c) => c.label === 'supported');
  const against = claims.filter((c) => c.label === 'contradicted');
  const unclear = claims.filter((c) => c.label !== 'supported' && c.label !== 'contradicted');
  const o = d.originality || {};
  const papers = d.scan?.papers || [];
  const claimList = (list) => list.length ? `<ul class="list">${list.map((c) => `<li>${label(c.label)} ${esc(c.claim)}${c.reason ? `<br><span class="faint">${esc(c.reason)}</span>` : ''}</li>`).join('')}</ul>` : '<span class="faint">None</span>';
  return `<h2>Check</h2>${head}
    <div class="ws-section"><h3>Verdict</h3><p class="verdict">${esc(verdictLine(d))}</p>
      <span class="faint">${d.scan ? 'Based on a lightweight scan: titles and abstracts only.' : 'Based on the formal review.'}</span></div>
    <div class="ws-section"><h3>What the evidence leaves open</h3>
      <ul class="list">${(d.status.gaps || []).map((g) => `<li>${esc(g)}</li>`).join('')}${(d.followUps || []).slice(0, 3).map((q) => `<li>${esc(q)}</li>`).join('')}</ul>
      <div class="chips">${d.prisma ? '' : '<button class="chip primary" data-act="review">Plan a formal review</button>'}<button class="chip" data-act="council">Refine with the council</button><button class="chip" data-act="hypEdit">Revise the hypothesis</button></div></div>
    <div class="ws-section"><h3>Evidence for and against</h3><div class="cols">
      <div class="col for"><h4>Supports (${forC.length})</h4>${claimList(forC)}</div>
      <div class="col against"><h4>Challenges (${against.length})</h4>${claimList(against)}</div>
      <div class="col unclear"><h4>Unclear (${unclear.length})</h4>${claimList(unclear)}</div></div></div>
    <div class="ws-section"><h3>Originality</h3>${o.verdict ? `<p><span class="badge">${esc(o.verdict.replace(/_/g, ' '))}</span> ${esc(o.explanation || '')}</p>
      ${o.adjacent_queries?.length ? `<p class="faint">Adjacent-field searches: ${o.adjacent_queries.map(esc).join(' · ')} → ${o.adjacent_results ?? 0} results</p>` : ''}
      ${o.closest_prior_work?.length ? `<ul class="list">${o.closest_prior_work.map((p) => `<li>${p.url ? `<a href="${esc(p.url)}" target="_blank" rel="noopener">${esc(p.title)}</a>` : esc(p.title)} <span class="badge">overlap ${p.overlap}</span></li>`).join('')}</ul>` : ''}
      <p class="faint">${esc(o.limits || '')}</p>` : '<span class="faint">Not assessed.</span>'}</div>
    ${papers.length ? `<div class="ws-section"><h3>Papers read (${papers.length})</h3><ul class="list">${papers.map((p) => `<li>${p.url ? `<a href="${esc(p.url)}" target="_blank" rel="noopener">${esc(p.title)}</a>` : esc(p.title)} <span class="badge">${esc((p.reading_depth || '').replace('_', ' '))}</span> <span class="faint">${esc(p.year || '')} · ${esc(p.source_api || '')}</span></li>`).join('')}</ul></div>` : ''}`;
}

function reviewPanel(d) {
  const head = planSection(d, 'formal');
  const running = d.runs.some((r) => !r.done && r.mode === 'formal');
  if (!d.prisma) {
    const e = d.recommendFormal?.effort || {};
    return `<h2>Formal review</h2>${head}${running ? empty('Running…', 'Searching, following citations, retrieving full texts and recording every screening decision. Counts appear as they are recorded.') : head ? '' : empty('No formal review yet.', `A PRISMA-aligned review records every search, screening decision and exclusion. It costs more than a scan${e.typical_duration ? ` (about ${esc(e.typical_duration)})` : ''} and always asks for approval first.`, '<button class="chip primary" data-act="review">Plan a formal review</button>')}`;
  }
  const f = d.prisma.flow_counts || {};
  const box = (name, n) => `<div class="box"><span>${name}</span><b>${n ?? '–'}</b></div>`;
  return `<h2>Formal review</h2>${head}
    <div class="ws-section"><h3>PRISMA flow</h3><div class="flow">
      ${box('Records identified', f.total_identified)}<div class="arrow">↓</div>
      ${box('Records screened', f.records_screened)}${box('Excluded at title/abstract', f.records_excluded_title_abstract)}<div class="arrow">↓</div>
      ${box('Reports sought', f.reports_sought_for_retrieval)}${box('Not retrieved', f.reports_not_retrieved)}<div class="arrow">↓</div>
      ${box('Full texts assessed', f.reports_assessed_for_eligibility)}${box('Excluded at full text', f.reports_excluded_full_text)}<div class="arrow">↓</div>
      ${box('Included reports', f.included_reports)}</div>
      <p class="faint">Counts come only from recorded screening decisions.</p></div>`;
}

function draftPanel(d) {
  if (!d.report) return `<h2>Draft</h2>${empty('No draft yet.', 'After a check or a formal review, the synthesis appears here with its honest status. Editing with tracked changes comes in a later build.')}`;
  const s = d.status || {};
  const full = s.report_status === 'fully_reviewed';
  return `<h2>Draft</h2>
    <div class="status-banner${full ? ' full' : ''}"><b>${full ? 'Fully reviewed' : 'Provisional'}</b>${s.gaps?.length ? ` · ${s.gaps.length} open gap${s.gaps.length > 1 ? 's' : ''}` : ''}<br><span class="faint">${esc(s.pdf_export || 'No PDF is created unless you ask.')}</span></div>
    <article class="prose">${md(d.report)}</article>`;
}

export const PANELS = { ideas: ideasPanel, thinkers: thinkersPanel, hypothesis: hypothesisPanel, check: checkPanel, review: reviewPanel, design: () => '<h2>Study design</h2>', draft: draftPanel };

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
