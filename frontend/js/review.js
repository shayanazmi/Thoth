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
  screening_ft: 'Full-text screening', synthesis: 'Reading and weighing included studies', complete: 'Complete' };

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
    <div class="effort">${esc(e.scope || '')} · ${esc(e.duration || '')} · ${esc(e.model_calls || '')} model calls (free tier)</div>
    <div class="chips">${open ? `<button class="chip primary" data-act="runReview" data-arg="${esc(p.review_id)}">Approve and run</button><button class="chip" data-act="dropReview" data-arg="${esc(p.review_id)}">Not yet</button>` : `<span class="faint">${p.status === 'dropped' ? 'Not run.' : 'Approved and started.'}</span>`}</div>
  </div>`;
};
register('dropReview', (id) => { const p = (project().reviewPlans || {})[id]; if (p) p.status = 'dropped'; emit(); });

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
    case 'review_start': Object.assign(r, { mode: p.mode, protocol: p.protocol, status: 'running', stage: 'identifying' }); break;
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
  if (!Object.values(eligibility).some(Boolean)) return addMessage({ role: 'note', text: 'Fill in at least the population and outcome criteria first.' });
  p.status = 'approved'; p.mode = mode;
  d.sysReview = { review_id: id, mode, status: 'running', stage: 'identifying', counts: null, queue_ta: [], queue_ft: [], records: [], hypothesis: p.hypothesis };
  openPanel('review', { fromUser: true });
  emit();
  await stream(d, `/api/review/${encodeURIComponent(id)}/run`, { approve: true, mode, protocol: { eligibility, search } });
});

register('continueReview', async () => {
  const d = project();
  if (!d.sysReview) return;
  d.sysReview.status = 'running'; emit();
  await stream(d, `/api/review/${encodeURIComponent(d.sysReview.review_id)}/continue`, {});
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
  return `<div class="prisma">
    <div class="pf-row">${box('records identified', c.identified)}<div class="pf-side">${Object.entries(c.by_source || {}).map(([k, v]) => `${esc(k)} ${v}`).join(' · ')}<br>${c.duplicates_removed} duplicates removed</div></div>
    <div class="pf-row">${box('records screened', c.screened)}<div class="pf-side">${box('excluded at title/abstract', c.excluded_title_abstract, 'out')}${reasons(c.excluded_title_abstract_reasons)}${c.unscreened ? `<div class="guard">${c.unscreened} not yet screened</div>` : ''}</div></div>
    <div class="pf-row">${box('sought for retrieval', c.sought_for_retrieval)}<div class="pf-side">${box('not retrieved (no legal open full text)', c.not_retrieved, 'out')}${c.awaiting_retrieval ? `<div class="faint">${c.awaiting_retrieval} awaiting retrieval</div>` : ''}</div></div>
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
    ${q.slice(0, 12).map((x) => screenItem(x, stage)).join('')}
    <div class="chips"><button class="chip" data-act="acceptAll" data-arg="${stage}">Accept the Screener's remaining ${q.length} decision${q.length === 1 ? '' : 's'}</button></div>`;
}

let loading = false;
async function ensureLoaded(d) {
  if (d.sysReview || loading || !state.projectId) return;
  loading = true;
  try { const st = await getJSON(`/api/review/latest?project_id=${encodeURIComponent(state.projectId)}`); if (st.review_id) { d.sysReview = st; emit(); } }
  catch (_) { /* none yet */ } finally { loading = false; }
}

function reviewPanel(d) {
  ensureLoaded(d);
  const r = d.sysReview;
  if (!r) return null;
  const v = r.verdict;
  return `<h2>Systematic review</h2>
    <p class="muted">${esc(r.hypothesis || '')}</p>
    <div class="status-banner${r.status === 'complete' ? ' full' : ''}"><b>${esc(STAGE_LABEL[r.stage] || r.stage)}</b> · ${r.mode === 'auto' ? 'Auto' : 'Human-in-the-loop'}${r.status === 'awaiting_researcher' ? ' · waiting for you' : ''}${r.status === 'blocked' ? ` · blocked: ${esc(r.note || '')} <button class="link-btn strong" data-act="continueReview">Try again</button>` : ''}${r.progress && r.status === 'running' ? ` · ${r.progress.done}/${r.progress.total} screened` : ''}</div>
    ${queueBlock(r)}
    <h3>PRISMA 2020 flow</h3>
    ${prismaFlow(r.counts)}
    <p class="faint">Every number is counted from recorded decisions, yours and the Screener's.</p>
    ${r.status === 'complete' && (r.counts?.included || 0) > 0 ? `<div class="chips"><button class="chip primary" data-act="openReviewTrial">Open the included studies in the trial</button></div>${v ? `<p>Verdict on the included studies: <b>${esc((v.overall?.verdict || '').replace(/_/g, ' '))}</b>. ${esc(v.overall?.reason || '')}</p>` : ''}` : ''}
    ${r.status === 'complete' && !(r.counts?.included) && r.note ? `<div class="guard">${esc(r.note)}</div><div class="chips"><button class="chip" data-act="review">Plan a broader review</button></div>` : ''}`;
}

const basicReview = PANELS.review;
PANELS.review = (d) => reviewPanel(d) ?? basicReview(d);
