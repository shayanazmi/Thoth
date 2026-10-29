// Systematic review (docs/features/05 tier 3): protocol → approve (Auto or Human-in-the-loop) → identification →
// title/abstract screening → full-text retrieval and screening → included studies weighed in a linked trial.
// PRISMA counts come from the server, computed only from recorded decisions.
import { getJSON, postJSON, streamSSE } from './api.js';
import { state, project, emit, addMessage, currentHypothesis } from './store.js';
import { register, openPanel, actions, cardRenderers } from './chat.js';
import { PANELS } from './workspace.js';
import { esc } from './util.js';

const CRITERIA = [['population', 'Population'], ['exposure', 'Exposure'], ['comparison', 'Comparison'], ['outcomes', 'Outcomes'],
  ['designs', 'Study designs'], ['dates', 'Dates'], ['languages', 'Languages']];
const STAGE_LABEL = { planned: 'Planned', identifying: 'Searching', screening_ta: 'Title/abstract screening', retrieving: 'Retrieving full texts',
  citation_chasing: 'Following citations', screening_ft: 'Full-text screening', synthesis: 'Reading and weighing included studies', complete: 'Complete' };
// The review's budget (backend/research/review.py DEFAULT_BUDGET): identification is free, screening is cheap, full texts
// are the expensive step. The researcher sets it before approving; the estimate follows it.
const BUDGET = [['keyword_records', 'Database records', 'records to fetch from OpenAlex, Europe PMC and Semantic Scholar'],
  ['citation_records', 'Citation records', 'records to add by following citations'],
  ['citation_rounds', 'Citation rounds', 'rounds of following references and citing papers (0 = off)'],
  ['stop_after_irrelevant', 'Stop after … irrelevant', 'stop screening database results after this many irrelevant records in a row (0 = never)'],
  ['full_text', 'Full texts', 'full texts read, appraised and weighed']];
const RULE_LABEL = { source_exhausted: 'Database exhausted', budget_reached: 'Budget reached', consecutive_irrelevant: 'Screening stopped early',
  citation_saturation: 'Citations saturated', citation_rounds_max: 'Citation rounds used', citation_budget_reached: 'Citation budget used',
  citation_off: 'Citation searching off', ft_budget: 'Full-text budget', source_error: 'Database error', user_stop: 'Stopped by you' };

// ---------- Protocol ----------
async function startSystematicReview(topic) {
  const d = project();
  const hyp = String(topic || '').trim() || currentHypothesis(d)?.text;
  if (!hyp) return addMessage({ role: 'thoth', text: 'Pin a hypothesis first; a systematic review needs a question to screen against.' });
  addMessage({ role: 'user', text: `Plan a systematic review: ${hyp}` });
  addMessage({ role: 'note', text: 'Drafting a protocol. Nothing is searched or screened until you approve it.' });
  state.busy += 1; emit();
  try {
    const p = await postJSON('/api/review/protocol', { project_id: state.projectId, hypothesis: hyp, question: d.question || '' });
    d.reviewPlans = d.reviewPlans || {};
    d.reviewPlans[p.review_id] = { ...p, status: 'planned', mode: 'copilot' };
    addMessage({ role: 'thoth', kind: 'reviewProtocol', review: p.review_id });
  } catch (err) {
    addMessage({ role: 'thoth', text: `Couldn't draft the protocol: ${err.message}` });
  } finally { state.busy -= 1; emit(); }
}
actions.startSystematicReview = startSystematicReview;

cardRenderers.reviewProtocol = (m, d) => {
  const p = (d.reviewPlans || {})[m.review];
  if (!p) return '';
  const open = p.status === 'planned';
  const e = p.estimate || {};
  const el = p.protocol.eligibility || {};
  return `<div class="card proposal heavy review-protocol" data-review="${esc(p.review_id)}">
    <div class="card-kicker">Systematic review protocol · nothing runs until you approve</div>
    <div class="card-title">${esc(p.hypothesis)}</div>
    <div class="muted">Each record is screened against these criteria. Screen on what was studied, never on what was found.${p.degraded ? ' <span class="guard">The Librarian couldn\'t be reached: the criteria are empty; fill them in.</span>' : ''}</div>
    <div class="criteria">${CRITERIA.map(([k, label]) => `<label><span>${label}</span>${open ? `<textarea rows="2" data-crit="${k}">${esc(el[k] || '')}</textarea>` : `<p>${esc(el[k] || '—')}</p>`}</label>`).join('')}</div>
    <details><summary class="faint">Search strings</summary>
      <label><span>OpenAlex</span>${open ? `<input data-search="openalex" value="${esc(p.protocol.search.openalex)}">` : `<code>${esc(p.protocol.search.openalex)}</code>`}</label>
      <label><span>Europe PMC</span>${open ? `<input data-search="europepmc" value="${esc(p.protocol.search.europepmc)}">` : `<code>${esc(p.protocol.search.europepmc)}</code>`}</label>
    </details>
    ${open ? `<div class="mode-switch" role="radiogroup" aria-label="Screening mode">
      <label><input type="radio" name="mode-${esc(p.review_id)}" value="copilot" ${p.mode !== 'auto' ? 'checked' : ''}> <b>Human-in-the-loop</b><span class="faint">: you confirm every include/exclude (keyboard-fast)</span></label>
      <label><input type="radio" name="mode-${esc(p.review_id)}" value="auto" ${p.mode === 'auto' ? 'checked' : ''}> <b>Auto</b><span class="faint">: the Screener decides; uncertain ones are queued for you to audit</span></label>
    </div>` : `<div class="faint">Mode: ${p.mode === 'auto' ? 'Auto' : 'Human-in-the-loop'}</div>`}
    ${open ? `<details class="budget"><summary class="faint">Budget and stopping rules</summary>
      <div class="budget-grid">${BUDGET.map(([k, label, help]) => { const [lo, hi] = (p.budget_bounds || {})[k] || [0, 1000]; return `<label title="${esc(help)}">${esc(label)}<input type="number" data-budget="${k}" min="${lo}" max="${hi}" value="${esc((p.budget || {})[k] ?? '')}"></label>`; }).join('')}</div>
      <p class="faint">A search stops when a database runs out, the budget is reached, or a stopping rule fires, and the review says which. None of these proves nothing else exists.</p></details>` : ''}
    <div class="effort" data-estimate="${esc(p.review_id)}">${esc(e.scope || '')} · ${esc(e.duration || '')} · ${esc(e.model_calls || '')} model calls (free tier)</div>
    <div class="chips">${open ? `<button class="chip primary" data-act="runReview" data-arg="${esc(p.review_id)}">Approve and run</button><button class="chip" data-act="dropReview" data-arg="${esc(p.review_id)}">Not yet</button>` : `<span class="faint">${p.status === 'dropped' ? 'Not run.' : 'Approved and started.'}</span>`}</div>
  </div>`;
};
register('dropReview', (id) => { const p = (project().reviewPlans || {})[id]; if (p) p.status = 'dropped'; emit(); });

function readBudget(card) {
  return Object.fromEntries([...card.querySelectorAll('input[data-budget]')].map((i) => [i.dataset.budget, Number(i.value)]));
}

// Re-estimate as the researcher edits the budget (debounced; the server clamps it to the allowed bounds).
let budgetTimer = null;
document.addEventListener('input', (e) => {
  const input = e.target.closest?.('input[data-budget]');
  if (!input) return;
  const card = input.closest('.review-protocol');
  clearTimeout(budgetTimer);
  budgetTimer = setTimeout(async () => {
    try {
      const out = await postJSON('/api/review/estimate', { budget: readBudget(card) });
      const p = (project().reviewPlans || {})[card.dataset.review];
      if (p) { p.budget = out.budget; p.estimate = out.estimate; }
      const el = card.querySelector('[data-estimate]');
      if (el) el.textContent = `${out.estimate.scope} · ${out.estimate.duration} · ${out.estimate.model_calls} model calls (free tier)`;
    } catch (_) { /* keep the last estimate */ }
  }, 400);
});

// ---------- Run / continue (streamed) ----------
async function refresh(d) {
  if (!d.sysReview?.review_id) return;
  try { Object.assign(d.sysReview, await getJSON(`/api/review/${encodeURIComponent(d.sysReview.review_id)}`)); } catch (_) { /* keep last */ }
  emit();
}

function onEvent(d, type, p) {
  const r = d.sysReview;
  if (!r) return;
  switch (type) {
    case 'review_start': Object.assign(r, { mode: p.mode, protocol: p.protocol, budget: p.budget, status: 'running', stage: 'identifying', stopping: [], searchLog: null }); break;
    case 'search_page': r.stage = 'identifying'; r.lastPage = p; break;
    case 'stop_rule': r.stopping = [...(r.stopping || []), p]; break;
    case 'citation_round': r.stage = 'citation_chasing'; r.lastRound = p; break;
    case 'stopped':
      r.status = 'stopped'; r.stopping_now = false;
      addMessage({ role: 'thoth', text: `**Review stopped.** ${p.message}`, chips: [{ label: 'Continue the review', act: 'continueReview', primary: true }, { label: 'See where it stopped', act: 'panel', arg: 'review' }] });
      break;
    case 'counts': r.counts = p; break;
    case 'screening_progress': r.stage = p.stage === 'ta' ? 'screening_ta' : 'screening_ft'; r.progress = p; break;
    case 'retrieved': r.stage = 'retrieving'; break;
    case 'included': r.stage = 'synthesis'; break;
    case 'paused':
      r.status = 'awaiting_researcher'; r.stage = p.stage === 'ta' ? 'screening_ta' : 'screening_ft';
      r[p.stage === 'ta' ? 'queue_ta' : 'queue_ft'] = p.queue;
      addMessage({ role: 'thoth', text: `**Your turn.** ${p.queue.length} ${p.stage === 'ta' ? 'title/abstract' : 'full-text'} decision${p.queue.length === 1 ? '' : 's'} to confirm. The Screener's suggestion is on each; press I, E or M.`, chips: [{ label: 'Screen now', act: 'panel', arg: 'review', primary: true }] });
      break;
    case 'blocked': r.status = 'blocked'; r.note = p.reason; addMessage({ role: 'note', text: p.reason }); break;
    case 'verdict': r.verdict = p; break;
    case 'review_complete':
      r.status = 'complete'; r.stage = 'complete'; r.trial_id = p.trial_id; r.note = p.note || '';
      if (!p.included) {
        addMessage({ role: 'thoth', text: `**Systematic review complete: no study was included.** ${p.note || ''}`, chips: [{ label: 'See the PRISMA flow', act: 'panel', arg: 'review', primary: true }, { label: 'Plan a broader review', act: 'review' }] });
      } else {
        addMessage({ role: 'thoth', text: `**Systematic review complete.** ${p.included} of ${r.counts?.identified ?? 0} records met every criterion; they were read in full and weighed in the trial.`, chips: [{ label: 'See the PRISMA flow', act: 'panel', arg: 'review', primary: true }, { label: 'Open the included studies', act: 'openReviewTrial' }] });
      }
      break;
    case 'error': addMessage({ role: 'note', text: p.error }); break;
    default: break;
  }
  emit();
}

async function stream(d, path, body) {
  state.busy += 1; emit();
  try { await streamSSE(path, body, (t, p) => onEvent(d, t, p)); }
  catch (err) { addMessage({ role: 'note', text: `The review stopped: ${err.message}` }); }
  finally { state.busy -= 1; await refresh(d); }
}

register('runReview', async (id, el) => {
  const d = project();
  const p = (d.reviewPlans || {})[id];
  if (!p || p.status !== 'planned') return;
  const card = el.closest('.review-protocol');
  const eligibility = Object.fromEntries([...card.querySelectorAll('textarea[data-crit]')].map((t) => [t.dataset.crit, t.value.trim()]));
  const search = Object.fromEntries([...card.querySelectorAll('input[data-search]')].map((i) => [i.dataset.search, i.value.trim()]));
  const mode = card.querySelector(`input[name="mode-${id}"]:checked`)?.value || 'copilot';
  const budget = readBudget(card);
  if (!Object.values(eligibility).some(Boolean)) return addMessage({ role: 'note', text: 'Fill in at least the population and outcome criteria first.' });
  p.status = 'approved'; p.mode = mode;
  d.sysReview = { review_id: id, mode, status: 'running', stage: 'identifying', counts: null, queue_ta: [], queue_ft: [], records: [], hypothesis: p.hypothesis };
  openPanel('review', { fromUser: true });
  emit();
  await stream(d, `/api/review/${encodeURIComponent(id)}/run`, { approve: true, mode, protocol: { eligibility, search }, budget });
});

register('continueReview', async () => {
  const d = project();
  if (!d.sysReview) return;
  d.sysReview.status = 'running'; emit();
  await stream(d, `/api/review/${encodeURIComponent(d.sysReview.review_id)}/continue`, {});
});

register('stopReview', async () => {
  const r = project().sysReview;
  if (!r || r.status !== 'running') return;
  r.stopping_now = true; emit();
  try { await postJSON(`/api/review/${encodeURIComponent(r.review_id)}/stop`, {}); }
  catch (err) { r.stopping_now = false; addMessage({ role: 'note', text: `Couldn't stop it: ${err.message}` }); emit(); }
});

register('raiseFullText', async () => {
  const d = project();
  const r = d.sysReview;
  if (!r) return;
  // Ten more at a time: each full text costs about four model calls (Screener, Reader, Appraiser, Analyst).
  const now = r.budget?.full_text || 30;
  const want = Math.min(80, now + Math.min(10, r.counts?.not_retrieved_budget || 10));
  try {
    const out = await postJSON(`/api/review/${encodeURIComponent(r.review_id)}/budget`, { full_text: want });
    r.budget = out.budget;
    addMessage({ role: 'note', text: `Full-text budget raised to ${out.budget.full_text}. ${out.estimate.model_calls} model calls in all for this review.` });
    d.sysReview.status = 'running'; emit();
    await stream(d, `/api/review/${encodeURIComponent(r.review_id)}/continue`, {});
  } catch (err) { addMessage({ role: 'note', text: `Couldn't change the budget: ${err.message}` }); }
});

// Opening a long section fetches it (once per opening); its open state survives re-renders.
document.addEventListener('toggle', (e) => {
  const el = e.target;
  if (!(el instanceof HTMLDetailsElement) || !el.dataset.load) return;
  const r = project()?.sysReview;
  if (!r) return;
  const key = el.dataset.load === 'loadSearchLog' ? 'searchLogOpen' : 'recordsOpen';
  if (r[key] === el.open) return;
  r[key] = el.open;
  if (el.open) actions[el.dataset.load](el.dataset.load === 'loadRecords' ? 'all|0' : undefined);
}, true);

register('reviewMore', () => { const r = project().sysReview; if (r) { r.queueShown = (r.queueShown || 12) + 24; emit(); } });

// The search record and the full record list are fetched when opened (they can be long).
register('loadSearchLog', async () => {
  const r = project().sysReview;
  if (!r) return;
  try { r.searchLog = (await getJSON(`/api/review/${encodeURIComponent(r.review_id)}/searches`)).searches; emit(); }
  catch (err) { addMessage({ role: 'note', text: `Couldn't load the search record: ${err.message}` }); }
});

register('loadRecords', async (arg) => {
  const r = project().sysReview;
  if (!r) return;
  const [filter, offset] = String(arg || 'all|0').split('|');
  try { r.recordPage = await getJSON(`/api/review/${encodeURIComponent(r.review_id)}/records?filter=${encodeURIComponent(filter)}&offset=${Number(offset) || 0}&limit=50`); emit(); }
  catch (err) { addMessage({ role: 'note', text: `Couldn't load the records: ${err.message}` }); }
});

register('openReviewTrial', () => { const d = project(); d.trial = null; openPanel('check', { fromUser: true }); });

// ---------- Screening decisions ----------
async function decideRecord(recordId, stage, decision, reason) {
  const d = project();
  try {
    const out = await postJSON(`/api/review/${encodeURIComponent(d.sysReview.review_id)}/decisions/${encodeURIComponent(recordId)}`, { stage, decision, reason });
    d.sysReview.counts = out.counts;
    const key = stage === 'ta' ? 'queue_ta' : 'queue_ft';
    d.sysReview[key] = (d.sysReview[key] || []).filter((q) => q.record_id !== recordId);
    emit();
  } catch (err) { addMessage({ role: 'note', text: `Couldn't record that: ${err.message}` }); }
}

register('screen', (arg, el) => {
  const [recordId, stage, decision] = String(arg).split('|');
  if (decision === 'exclude') {
    const reason = el.closest('.screen-item')?.querySelector('select[data-reason]')?.value;
    if (!reason) { el.closest('.screen-item')?.querySelector('select[data-reason]')?.focus(); return addMessage({ role: 'note', text: 'Choose which protocol criterion the record fails.' }); }
    return decideRecord(recordId, stage, 'exclude', reason);
  }
  decideRecord(recordId, stage, decision, '');
});

register('acceptAll', async (stage) => {
  const d = project();
  try { const out = await postJSON(`/api/review/${encodeURIComponent(d.sysReview.review_id)}/accept-all`, { stage }); d.sysReview.counts = out.counts; d.sysReview[stage === 'ta' ? 'queue_ta' : 'queue_ft'] = []; emit(); }
  catch (err) { addMessage({ role: 'note', text: `Couldn't accept: ${err.message}` }); }
});

// Keyboard: I include, E exclude (needs a reason chosen), M maybe, on the first item in the queue.
document.addEventListener('keydown', (e) => {
  if (e.target.closest('input, textarea, [contenteditable="true"]') || e.metaKey || e.ctrlKey || e.altKey) return;
  const first = document.querySelector('#workspace .screen-item');
  if (!first) return;
  const key = { i: 'include', e: 'exclude', m: 'maybe' }[e.key.toLowerCase()];
  if (!key) return;
  const btn = first.querySelector(`[data-act="screen"][data-arg$="|${key}"]`);
  if (btn) { e.preventDefault(); btn.click(); }
});

// ---------- Panel ----------
function box(label, n, cls = '') { return `<div class="pf-box ${cls}"><div class="pf-n">${n ?? '—'}</div><div class="pf-l">${label}</div></div>`; }

function reasons(obj) {
  const entries = Object.entries(obj || {});
  return entries.length ? `<ul class="pf-reasons">${entries.map(([k, v]) => `<li>${esc(k)}: ${v}</li>`).join('')}</ul>` : '';
}

function prismaFlow(c) {
  if (!c) return '<div class="faint">Counts appear as records are found and screened.</div>';
  const rb = c.removed_before_screening || {};
  const sources = Object.entries(c.by_source || {}).filter(([k]) => !k.startsWith('Citation search'));
  return `<div class="prisma">
    <div class="pf-row id-col">
      <div>${box('identified from databases', c.identified_databases ?? c.identified)}<div class="pf-side">${sources.map(([k, v]) => `${esc(k)} ${v}`).join(' · ')}</div></div>
      <div>${box('identified by citation searching', c.identified_citations ?? 0)}<div class="pf-side">${c.citation?.rounds ? `${c.citation.rounds} round${c.citation.rounds === 1 ? '' : 's'} from ${c.citation.seeds} screened records` : 'not run'}</div></div>
    </div>
    <div class="pf-row"><div class="pf-side">Removed before screening: ${rb.duplicates ?? c.duplicates_removed} duplicates${rb.automated_offtopic ? ` · ${rb.automated_offtopic} by the off-topic filter` : ''}${rb.no_title ? ` · ${rb.no_title} without a title` : ''}</div></div>
    <div class="pf-row">${box('records screened', c.screened_by_screener ?? c.screened)}<div class="pf-side">${box('excluded at title/abstract', c.excluded_title_abstract, 'out')}${reasons(c.excluded_title_abstract_reasons)}${c.not_screened_stopped ? box('not screened (stopping rule)', c.not_screened_stopped, 'out') : ''}${c.unscreened ? `<div class="guard">${c.unscreened} not yet screened</div>` : ''}</div></div>
    <div class="pf-row">${box('sought for retrieval', c.sought_for_retrieval)}<div class="pf-side">${box('not retrieved (no legal open full text)', c.not_retrieved, 'out')}${c.not_retrieved_budget ? `${box('not retrieved (full-text budget)', c.not_retrieved_budget, 'out')}<button class="link-btn strong" data-act="raiseFullText">Read ${Math.min(10, c.not_retrieved_budget)} more (about ${Math.min(10, c.not_retrieved_budget) * 4} model calls)</button>` : ''}${c.awaiting_retrieval ? `<div class="faint">${c.awaiting_retrieval} awaiting retrieval</div>` : ''}</div></div>
    <div class="pf-row">${box('assessed in full', c.assessed_full_text)}<div class="pf-side">${box('excluded at full text', c.excluded_full_text, 'out')}${reasons(c.excluded_full_text_reasons)}${c.full_text_unscreened ? `<div class="guard">${c.full_text_unscreened} not yet screened</div>` : ''}</div></div>
    <div class="pf-row">${box('studies included', c.included, 'in')}</div>
  </div>`;
}

function screenItem(q, stage) {
  const d = q.decision || {};
  const evidence = (d.criteria || []).map((c) => `<li class="crit-${esc(c.met)}"><b>${esc(c.criterion)}</b> ${esc(c.met)}${c.evidence ? `: “${esc(String(c.evidence).slice(0, 160))}”` : ''}</li>`).join('');
  return `<div class="screen-item">
    <div class="si-title">${q.meta.url ? `<a href="${esc(q.meta.url)}" target="_blank" rel="noopener">${esc(q.meta.title)}</a>` : esc(q.meta.title)} <span class="faint">${esc(q.meta.year ?? '')}</span></div>
    ${q.meta.abstract ? `<p class="si-abs">${esc(String(q.meta.abstract).slice(0, 420))}${String(q.meta.abstract).length > 420 ? '…' : ''}</p>` : ''}
    <div class="si-sugg">Screener suggests <b>${esc(d.decision)}</b>${d.reason ? ` (${esc(d.reason)})` : ''} · confidence ${Math.round((d.confidence || 0) * 100)}%${d.note ? ` · <span class="guard">${esc(d.note)}</span>` : ''}</div>
    ${evidence ? `<ul class="si-crit">${evidence}</ul>` : ''}
    <div class="chips">
      <button class="chip${d.decision === 'include' ? ' primary' : ''}" data-act="screen" data-arg="${esc(q.record_id)}|${stage}|include">Include <kbd>I</kbd></button>
      <select data-reason aria-label="Exclusion reason"><option value="">reason…</option>${CRITERIA.map(([k, l]) => `<option value="${k}"${d.reason === k ? ' selected' : ''}>${l}</option>`).join('')}</select>
      <button class="chip${d.decision === 'exclude' ? ' primary' : ''}" data-act="screen" data-arg="${esc(q.record_id)}|${stage}|exclude">Exclude <kbd>E</kbd></button>
      ${stage === 'ta' ? `<button class="chip${d.decision === 'maybe' ? ' primary' : ''}" data-act="screen" data-arg="${esc(q.record_id)}|${stage}|maybe">Maybe <kbd>M</kbd></button>` : ''}
    </div></div>`;
}

function queueBlock(r) {
  const stage = r.stage === 'screening_ft' ? 'ft' : 'ta';
  const q = (stage === 'ta' ? r.queue_ta : r.queue_ft) || [];
  const auditOnly = r.mode === 'auto';
  if (!q.length) {
    if (r.status === 'awaiting_researcher') return '<div class="chips"><button class="chip primary" data-act="continueReview">All confirmed: continue the review</button></div>';
    return '';
  }
  return `<h3>${auditOnly ? 'Audit: low-confidence decisions' : `Your screening: ${stage === 'ta' ? 'title/abstract' : 'full text'}`} <span class="faint">(${q.length} left)</span></h3>
    <p class="faint">${auditOnly ? 'The review went ahead with these; changing one updates the PRISMA counts.' : 'Confirm or override each decision. Keyboard: I include · E exclude (pick a reason) · M maybe.'}</p>
    ${q.slice(0, r.queueShown || 12).map((x) => screenItem(x, stage)).join('')}
    ${q.length > (r.queueShown || 12) ? `<button class="link-btn" data-act="reviewMore">Show ${Math.min(24, q.length - (r.queueShown || 12))} more</button>` : ''}
    <div class="chips"><button class="chip" data-act="acceptAll" data-arg="${stage}">Accept the Screener's remaining ${q.length} decision${q.length === 1 ? '' : 's'}</button></div>`;
}

let loading = false;
async function ensureLoaded(d) {
  if (d.sysReview || loading || !state.projectId) return;
  loading = true;
  try { const st = await getJSON(`/api/review/latest?project_id=${encodeURIComponent(state.projectId)}`); if (st.review_id) { d.sysReview = st; emit(); } }
  catch (_) { /* none yet */ } finally { loading = false; }
}

function stoppingBlock(r) {
  const stops = r.stopping || [];
  const lim = r.limitations || [];
  if (!stops.length && !lim.length) return '';
  return `<details class="originality"${r.status === 'complete' ? ' open' : ''}><summary><b>Why the search stopped, and what it may have missed</b></summary>
    <ul class="list">${stops.map((s) => `<li${s.superseded ? ' class="faint"' : ''}><span class="badge">${esc(RULE_LABEL[s.rule] || s.rule)}</span> ${esc(s.detail)}${s.superseded ? ' <i>(no longer applies)</i>' : ''}</li>`).join('')}</ul>
    ${lim.length ? `<h4>Limitations</h4><ul class="list">${lim.map((x) => `<li>${esc(x)}</li>`).join('')}</ul>` : ''}</details>`;
}

const fmtDate = (t) => { try { return new Date(t * 1000).toLocaleString(); } catch (_) { return ''; } };

function searchLogBlock(r) {
  const log = r.searchLog;
  return `<details class="originality" data-load="loadSearchLog"${r.searchLogOpen ? ' open' : ''}><summary><b>Search record</b> <span class="faint">every request, as made</span></summary>
    ${!log ? '<p class="faint">Loading…</p>' : !log.length ? '<p class="faint">Nothing searched yet.</p>'
      : `<div style="overflow-x:auto"><table class="search-log"><thead><tr><th>When</th><th>Database</th><th>Kind</th><th>Query</th><th>Page</th><th>Returned</th><th>New</th><th>Total</th><th>Notes</th></tr></thead>
      <tbody>${log.filter((s) => s.requested !== 0).map((s) => `<tr><td>${esc(fmtDate(s.searched_at))}</td><td>${esc(s.source)}</td><td>${esc(s.kind)}${s.round ? ` (round ${s.round})` : ''}</td><td><code>${esc(s.query || '')}</code></td><td>${s.page ?? ''}</td><td>${s.returned ?? ''}</td><td>${s.new_unique ?? ''}</td><td>${s.total_available ?? '?'}</td><td>${s.removed_offtopic ? `${s.removed_offtopic} off-topic removed ` : ''}${s.error ? `<span class="guard">${esc(s.error)}</span>` : ''}</td></tr>`).join('')}</tbody></table></div>`}
  </details>`;
}

const FILTERS = [['all', 'All'], ['included', 'Included'], ['excluded_ta', 'Excluded (title/abstract)'], ['excluded_ft', 'Excluded (full text)'],
  ['not_screened', 'Not screened'], ['citation', 'From citations'], ['duplicates', 'Duplicates']];

function recordsBlock(r) {
  const pg = r.recordPage;
  const flt = pg?.filter || 'all';
  const decision = (x) => { const ft = x.screening?.ft; const ta = x.screening?.ta; return x.dup_of ? 'duplicate' : ft ? `full text: ${ft.decision}${ft.reason ? ` (${ft.reason})` : ''}` : ta ? `title/abstract: ${ta.decision}${ta.reason ? ` (${ta.reason})` : ''}` : 'not screened yet'; };
  return `<details class="originality" data-load="loadRecords"${r.recordsOpen ? ' open' : ''}><summary><b>All records</b> <span class="faint">${r.counts?.identified ?? 0}</span></summary>
    <div class="chips">${FILTERS.map(([k, l]) => `<button class="chip${k === flt ? ' primary' : ''}" data-act="loadRecords" data-arg="${k}|0">${esc(l)}</button>`).join('')}</div>
    ${!pg ? '<p class="faint">Loading…</p>' : `<ul class="list">${pg.records.map((x) => `<li>${x.meta.url ? `<a href="${esc(x.meta.url)}" target="_blank" rel="noopener">${esc(x.meta.title)}</a>` : esc(x.meta.title)} <span class="faint">· ${esc(x.meta.year ?? '')} · ${esc(x.source)} · ${esc(decision(x))}</span></li>`).join('')}</ul>
      <div class="chips">${pg.offset > 0 ? `<button class="chip" data-act="loadRecords" data-arg="${flt}|${Math.max(0, pg.offset - pg.limit)}">Previous</button>` : ''}<span class="faint">${pg.total ? `${pg.offset + 1}–${Math.min(pg.total, pg.offset + pg.limit)} of ${pg.total}` : 'none'}</span>${pg.offset + pg.limit < pg.total ? `<button class="chip" data-act="loadRecords" data-arg="${flt}|${pg.offset + pg.limit}">Next</button>` : ''}</div>`}
  </details>`;
}

function reviewPanel(d) {
  ensureLoaded(d);
  const r = d.sysReview;
  if (!r) return null;
  const v = r.verdict;
  return `<h2>Systematic review</h2>
    <p class="muted">${esc(r.hypothesis || '')}</p>
    <div class="status-banner${r.status === 'complete' ? ' full' : ''}"><b>${esc(STAGE_LABEL[r.stage] || r.stage)}</b> · ${r.mode === 'auto' ? 'Auto' : 'Human-in-the-loop'}${r.status === 'awaiting_researcher' ? ' · waiting for you' : ''}${r.status === 'blocked' ? ` · blocked: ${esc(r.note || '')} <button class="link-btn strong" data-act="continueReview">Try again</button>` : ''}${r.progress && r.status === 'running' ? ` · ${r.progress.done}/${r.progress.total} screened` : ''}${r.status === 'running' && r.lastPage && r.stage === 'identifying' ? ` · ${esc(r.lastPage.source)} page ${r.lastPage.page}` : ''}${r.status === 'running' ? ` <button class="chip" data-act="stopReview" ${r.stopping_now ? 'disabled' : ''}>${r.stopping_now ? 'Stopping…' : 'Stop'}</button>` : ''}${r.status === 'stopped' ? ' · stopped <button class="link-btn strong" data-act="continueReview">Continue</button>' : ''}</div>
    ${queueBlock(r)}
    <h3>PRISMA 2020 flow</h3>
    ${prismaFlow(r.counts)}
    <p class="faint">Every number is counted from recorded decisions, yours and the Screener's.</p>
    ${stoppingBlock(r)}
    ${searchLogBlock(r)}
    ${recordsBlock(r)}
    ${r.status === 'complete' && (r.counts?.included || 0) > 0 ? `<div class="chips"><button class="chip primary" data-act="openReviewTrial">Open the included studies in the trial</button></div>${v ? `<p>Verdict on the included studies: <b>${esc((v.overall?.verdict || '').replace(/_/g, ' '))}</b>. ${esc(v.overall?.reason || '')}</p>` : ''}` : ''}
    ${r.status === 'complete' && !(r.counts?.included) && r.note ? `<div class="guard">${esc(r.note)}</div><div class="chips"><button class="chip" data-act="review">Plan a broader review</button></div>` : ''}`;
}

const basicReview = PANELS.review;
PANELS.review = (d) => reviewPanel(d) ?? basicReview(d);
