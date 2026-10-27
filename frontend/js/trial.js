// The trial (docs/features/05, 06): the hypothesis on trial, papers as witnesses, a neutral verdict.
// Plan (editable sub-claims + estimate) → approve → the library and matrix fill in live → verdict.
import { getJSON, postJSON, streamSSE } from './api.js';
import { state, project, emit, addMessage, currentHypothesis } from './store.js';
import { register, openPanel, actions, cardRenderers } from './chat.js';
import { PANELS } from './workspace.js';
import { esc, md, brandMark } from './util.js';
import { fresh, letterbox } from './motion.js';
import { askText } from './ui.js';

const VERDICT = {
  already_established: 'Already established',
  supported_within_limits: 'Supported within limits',
  contested: 'Contested',
  contradicted: 'Contradicted',
  insufficient_evidence: 'Insufficient evidence',
};
const ORIGINALITY = {
  likely_novel: 'Likely novel',
  partial_overlap: 'Partial overlap with prior work',
  substantially_covered: 'Substantially covered by prior work',
  insufficiently_assessed: 'Originality not reliably assessed',
};
const ACCESS = { full_text: 'full text', abstract_only: 'abstract only', metadata_only: 'title only', pending: 'fetching…' };
const DIR = { convergent: ['▲', 'convergent'], divergent: ['▼', 'divergent'], null: ['○', 'null'], not_addressed: ['·', 'not addressed'] };
const PROV = { from_full_text: 'full text', from_abstract: 'abstract', not_reported: 'not reported', not_accessible: 'not accessible' };

// ---------- Plan ----------
async function startTrial() {
  const d = project();
  const hyp = currentHypothesis(d)?.text;
  if (!hyp) return addMessage({ role: 'thoth', text: 'Pin a hypothesis first; then it can be put on trial.', chips: [{ label: 'Write one', act: 'prefill', arg: '/hypothesis ' }] });
  addMessage({ role: 'user', text: `Put this on trial: ${hyp}` });
  addMessage({ role: 'note', text: 'Splitting the hypothesis into the claims it is made of. Nothing runs until you approve.' });
  state.busy += 1; emit();
  try {
    const plan = await postJSON('/api/trial/plan', { project_id: state.projectId, hypothesis: hyp });
    d.trialPlans = d.trialPlans || {};
    d.trialPlans[plan.trial_id] = { ...plan, status: 'planned' };
    addMessage({ role: 'thoth', kind: 'trialPlan', trial: plan.trial_id });
  } catch (err) {
    addMessage({ role: 'thoth', text: `Couldn't plan the trial: ${err.message}` });
  } finally { state.busy -= 1; emit(); }
}
actions.startTrial = startTrial;
register('startTrial', startTrial);

cardRenderers.trialPlan = (m, d) => {
  const p = (d.trialPlans || {})[m.trial];
  if (!p) return '';
  const open = p.status === 'planned';
  const e = p.estimate || {};
  return `<div class="card proposal heavy trial-plan" data-trial="${esc(p.trial_id)}">
    <div class="card-kicker">Trial plan · nothing runs until you approve</div>
    <div class="card-title">${esc(p.hypothesis)}</div>
    <div class="muted">The hypothesis is split into the claims it is made of. Each paper will be read against each one. ${open ? 'Edit them if they misstate what you mean.' : ''}</div>
    <ol class="subclaims">${p.subclaims.map((s, i) => `<li>${open ? `<textarea rows="2" data-sub="${i}" aria-label="Sub-claim ${i + 1}">${esc(s.claim)}</textarea>` : esc(s.claim)}</li>`).join('')}</ol>
    ${p.ambiguities?.length ? `<details class="ambig"><summary>${p.ambiguities.length} thing${p.ambiguities.length > 1 ? 's' : ''} your hypothesis leaves open</summary><ul class="list">${p.ambiguities.map((a) => `<li>${esc(a)}</li>`).join('')}</ul></details>` : ''}
    <div class="effort">${esc(e.scope || '')} · ${esc(e.duration || '')} · ${esc(e.model_calls || '')} model calls (free tier)</div>
    <div class="chips">${open ? `<button class="chip primary" data-act="runTrial" data-arg="${esc(p.trial_id)}">Approve and run</button><button class="chip" data-act="dropTrial" data-arg="${esc(p.trial_id)}">Not yet</button>` : `<span class="faint">${p.status === 'dropped' ? 'Not run.' : 'Approved and started.'}</span>`}</div>
  </div>`;
};

register('dropTrial', (id) => { const p = (project().trialPlans || {})[id]; if (p) p.status = 'dropped'; emit(); });

// ---------- Run (live) ----------
register('runTrial', async (id, el) => {
  const d = project();
  const p = (d.trialPlans || {})[id];
  if (!p || p.status !== 'planned') return;
  const card = el.closest('.trial-plan');
  const subclaims = [...card.querySelectorAll('textarea[data-sub]')].map((t) => t.value.trim()).filter(Boolean);
  p.status = 'approved';
  d.trial = { trial_id: id, hypothesis: p.hypothesis, subclaims: p.subclaims, papers: {}, order: [], verdict: null, status: 'running', stage: 'Searching', started: Date.now(), strategy: null };
  addMessage({ role: 'thoth', kind: 'trialProgress', trial: id });
  openPanel('check', { fromUser: true });
  emit();
  state.busy += 1; emit();
  liveTrial = id;
  try {
    await streamSSE(`/api/trial/${encodeURIComponent(id)}/run`, { approve: true, subclaims }, (type, pl) => onEvent(d, type, pl));
  } catch (err) {
    d.trial.status = 'failed';
    addMessage({ role: 'note', text: `The trial stopped: ${err.message}` });
  } finally { liveTrial = null; state.busy -= 1; emit(); }
});

function onEvent(d, type, pl) {
  const t = d.trial;
  if (!t) return;
  const paper = (id) => (t.papers[id] = t.papers[id] || { paper_id: id, status: 'found', access: 'pending' });
  switch (type) {
    case 'trial_start': t.subclaims = pl.subclaims; break;
    case 'strategy': t.strategy = pl; t.stage = 'Searching OpenAlex and Europe PMC'; break;
    case 'paper_found': Object.assign(paper(pl.paper_id), { meta: pl.meta }); t.order.push(pl.paper_id); t.stage = 'Fetching full texts and reading'; break;
    case 'paper_access': Object.assign(paper(pl.paper_id), { access: pl.access, text_source: pl.text_source, status: 'reading' }); break;
    case 'paper_read': Object.assign(paper(pl.paper_id), { record: pl.record, status: 'analysing' }); break;
    case 'matrix_row': Object.assign(paper(pl.paper_id), { row: pl.row, weight: pl.weight, status: 'done' }); break;
    case 'paper_failed': case 'paper_skipped': Object.assign(paper(pl.paper_id), { status: type === 'paper_failed' ? 'failed' : 'unreadable', reason: pl.reason }); break;
    case 'search_filtered': t.filtered = pl; break;
    case 'rereading': t.stage = `Re-reading ${pl.papers.length} paper${pl.papers.length > 1 ? 's' : ''} the fallback model read`; break;
    case 'paper_reread':
      if (pl.recovered) Object.assign(paper(pl.paper_id), { record: pl.record });
      else Object.assign(paper(pl.paper_id), { rereadFailed: true });
      break;
    case 'subclaims_updated': t.subclaims = pl.subclaims; t.stage = 'Redoing every row for your sub-claims'; break;
    case 'row_failed': Object.assign(paper(pl.paper_id), { row: pl.row }); break;
    case 'adjacent': t.adjacent = pl; break;
    case 'judging': t.stage = `Weighing ${pl.witnesses} witnesses`; break;
    case 'verdict': t.verdict = pl; break;
    case 'trial_complete':
      t.status = 'complete'; t.stage = 'Done';
      addMessage({ role: 'thoth', text: `**The trial is in.** ${verdictSentence(t)}`, chips: [{ label: 'Open the trial', act: 'panel', arg: 'check', primary: true }, { label: 'Design a study', act: 'openDesign' }, { label: 'Get reviews', act: 'reviewHyp' }] });
      break;
    case 'error': addMessage({ role: 'note', text: pl.error }); t.status = t.status === 'running' ? 'failed' : t.status; break;
    default: break;
  }
  emit();
}

function verdictSentence(t) {
  const v = t.verdict;
  if (!v) return 'No verdict could be reached.';
  const done = Object.values(t.papers).filter((p) => p.status === 'done').length;
  return `${VERDICT[v.overall.verdict] || v.overall.verdict}. ${v.overall.reason || ''} (${done} witnesses, ${v.full_text_witnesses ?? '?'} read in full; ${ORIGINALITY[v.originality?.label] || ''}.)`;
}

cardRenderers.trialProgress = (m, d) => {
  const t = d.trial && d.trial.trial_id === m.trial ? d.trial : null;
  if (!t) return '<div class="card"><div class="muted">An earlier trial.</div></div>';
  const ps = Object.values(t.papers);
  const n = (s) => ps.filter((p) => p.status === s).length;
  const full = ps.filter((p) => p.access === 'full_text').length;
  const secs = Math.round(((t.status === 'running' ? Date.now() : (t.ended || Date.now())) - t.started) / 1000);
  return `<div class="card trial-progress${t.status === 'running' ? ' live' : ''}">
    <div class="card-kicker">The trial · ${esc(t.stage || '')}</div>
    <div class="progress-grid"><span><b>${ps.length}</b> found</span><span><b>${full}</b> full text</span><span><b>${n('done')}</b> analysed</span>${n('failed') + n('unreadable') ? `<span><b>${n('failed') + n('unreadable')}</b> couldn't be read</span>` : ''}<span class="faint">${secs}s</span></div>
    <div class="chips"><button class="chip" data-act="panel" data-arg="check">Watch the matrix fill in</button></div></div>`;
};

// ---------- The trial panel (workspace "Check") ----------
// The trial streaming in this tab, if any. A saved trial that says "running" without a live stream is
// stale (the page was reloaded or the server restarted), so it is refreshed from the server.
let liveTrial = null;

async function ensureLoaded(d) {
  const stale = d.trial && d.trial.status === 'running' && liveTrial !== d.trial.trial_id;
  if ((d.trial && !stale) || d.trialLoading || !state.projectId) return;
  d.trialLoading = true;
  try {
    const t = stale ? await getJSON(`/api/trial/${encodeURIComponent(d.trial.trial_id)}`)
      : await getJSON(`/api/trial/latest?project_id=${encodeURIComponent(state.projectId)}`);
    if (t.trial_id) {
      d.trial = { trial_id: t.trial_id, hypothesis: t.hypothesis, subclaims: t.subclaims, verdict: Object.keys(t.verdict || {}).length ? t.verdict : null,
        filtered: t.strategy?.europepmc_dropped_off_topic?.count ? { dropped: t.strategy.europepmc_dropped_off_topic.count, titles: t.strategy.europepmc_dropped_off_topic.titles } : null,
        status: t.status, stage: { complete: 'Done', stopped: 'Stopped before finishing' }[t.status] || t.status, started: Date.now(), papers: {}, order: [] };
      for (const p of t.papers) { d.trial.papers[p.paper_id] = p; d.trial.order.push(p.paper_id); }
      emit();
    }
  } catch (_) { /* no trial yet */ } finally { d.trialLoading = false; }
}

function witnessIds(t) {
  // The Judge numbers witnesses W1.. in the order they were found, counting only analysed papers.
  const ids = {};
  let i = 0;
  for (const id of t.order) if (t.papers[id]?.status === 'done') ids[id] = `W${(i += 1)}`;
  return ids;
}

const SCALE = ['contradicted', 'contested', 'insufficient_evidence', 'supported_within_limits', 'already_established'];
// "Insufficient evidence" → last word italic in rubric, like the design prototype.
function verdictHeading(label) {
  const w = String(label).split(' ');
  return w.length > 1 ? `${esc(w.slice(0, -1).join(' '))} <em>${esc(w[w.length - 1])}</em>` : `<em>${esc(label)}</em>`;
}

function ruling(t, v) {
  const key = v.overall.verdict;
  const label = VERDICT[key] || key;
  const full = v.full_text_witnesses ?? 0;
  const orig = v.originality?.label;
  const origNote = ORIGINALITY[orig] || 'Originality not assessed';
  const notAssessed = !orig || orig === 'insufficiently_assessed';
  const done = Object.values(t.papers || {}).filter((p) => p.status === 'done');
  const speaking = done.filter((p) => (p.row?.per_subclaim || []).some((x) => x.direction && x.direction !== 'not_addressed')).length;
  // The single most important sentence in a session gets a ceremony, once.
  const fx = fresh(`ruling:${t.trial_id}:${key}`, 3000);
  if (fx.first) letterbox(1300);
  return `<section class="ruling v-${esc(key)}${fx.cls}"${fx.attr} aria-label="Verdict">
    <div class="seal" aria-hidden="true"><svg class="ring" viewBox="0 0 160 160"><defs><path id="sealPath" d="M80 80 m-62 0 a62 62 0 1 1 124 0 a62 62 0 1 1 -124 0"/></defs><circle cx="80" cy="80" r="76" fill="none" stroke="currentColor" stroke-width="1.2"/><text font-family="IBM Plex Sans, sans-serif" font-size="10.5" font-weight="600" letter-spacing="3.6" fill="currentColor"><textPath href="#sealPath">THE RULING · NEUTRAL COURT · THE RULING · NEUTRAL COURT ·</textPath></text></svg><span class="moon">${brandMark()}</span></div>
    <div><div class="r-kicker">Verdict on your hypothesis · ${v.witnesses} witnesses</div>
      <h3 class="r-verdict">${verdictHeading(label)}</h3>
      <p class="r-why">${esc(v.overall.reason || '')}</p></div>
    <div class="scale" role="img" aria-label="Verdict scale: ${esc(label)} selected">${SCALE.map((k) => `<div${k === key ? ' class="here"' : ''}>${esc(VERDICT[k])}</div>`).join('')}</div>
    ${(v.guardrail_notes || []).map((n) => `<div class="guard" style="grid-column:1/-1">${esc(n)}</div>`).join('')}
    <div class="facts">
      <div class="fact"><b>${v.witnesses}</b>witnesses read</div>
      <div class="fact"><b>${full} <small>/ ${v.witnesses}</small></b>read in full text<div class="depth" aria-hidden="true"><i class="f" style="flex:${full}"></i><i class="a" style="flex:${Math.max(0, v.witnesses - full)}"></i></div></div>
      <div class="fact"><b>${speaking}</b>speak to your claims</div>
      <div class="fact${notAssessed ? ' warn' : ''}"><b>${esc(notAssessed ? 'Not assessed' : origNote)}</b>originality${v.originality?.reason ? `: ${esc(v.originality.reason).slice(0, 110)}` : ''}</div>
    </div></section>
    `;
}

function verdictBlock(t) {
  const v = t.verdict;
  if (!v) return t.status === 'running' ? `<div class="status-banner"><b>${esc(t.stage)}</b><br><span class="faint">The verdict comes after every paper has been read and weighed.</span></div>` : '';
  return `${ruling(t, v)}
    ${(v.per_subclaim || []).map((s) => `<details class="subverdict"${v.per_subclaim.length <= 2 ? ' open' : ''}><summary><span class="sv-n">${s.id}</span><span>${esc(s.claim)}</span><span class="verdict v-${esc(s.verdict)}">${esc(VERDICT[s.verdict] || s.verdict)}</span></summary>
      ${s.certainty ? `<div class="faint">Certainty: ${esc(s.certainty)}${(s.rated_down_for || []).length ? ` · rated down for ${esc(s.rated_down_for.join('; '))}` : ''}</div>` : ''}
      <div class="cases"><div><b>Case for</b>${md(s.case_for || '—')}${s.witness_ids_for?.length ? `<div class="faint">${esc(s.witness_ids_for.join(', '))}</div>` : ''}</div>
      <div><b>Case against</b>${md(s.case_against || '—')}${s.witness_ids_against?.length ? `<div class="faint">${esc(s.witness_ids_against.join(', '))}</div>` : ''}</div></div>
      ${s.conflicts ? `<div class="faint">Conflicts: ${esc(s.conflicts)}</div>` : ''}</details>`).join('')}
    ${v.gaps?.length ? `<h3>Not covered by these ${v.witnesses} papers</h3><ul class="list">${v.gaps.map((g) => `<li>${esc(g.gap)} <span class="faint">(${esc((g.revealed_by || []).join(', '))})</span></li>`).join('')}</ul><p class="faint">A trial reads a sample of the literature. These are gaps in the sample, which may point to gaps in the literature; a systematic review would tell.</p>` : ''}
    ${v.hypothesis_weaknesses?.length ? `<h3>What would strengthen the hypothesis</h3><ul class="list">${v.hypothesis_weaknesses.map((w) => `<li>${esc(w)}</li>`).join('')}</ul>` : ''}
    <div class="chips"><button class="chip" data-act="rejudgeTrial" title="The Judge only; the rows stay as they are">Weigh again</button>
      <button class="chip" data-act="editSubclaims" title="Redo every row against edited sub-claims, then weigh again">Edit sub-claims</button>
      <button class="chip" data-act="verdictThinkers">Ask thinkers about this verdict</button></div>`;
}

function recordBlock(p) {
  const r = p.record || {};
  const f = (k, label) => r[k] ? `<div><span class="rk">${label}</span>${esc(r[k].value ?? '—')} <span class="prov">${esc(PROV[r[k].provenance] || '')}</span></div>` : '';
  return `<div class="record">
    ${f('aim', 'Aim')}${f('design', 'Design')}${f('setting', 'Setting')}${f('population', 'Population')}${f('sample_size', 'Sample')}
    ${(r.measures || []).length ? `<div><span class="rk">Measures</span><ul>${r.measures.map((m) => `<li>${esc(m.construct)}: ${esc(m.instrument || m.how_measured || '')} <span class="prov">${esc(PROV[m.provenance] || '')}</span></li>`).join('')}</ul></div>` : ''}
    ${(r.results || []).length ? `<div><span class="rk">Results</span><ul>${r.results.map((x) => `<li>${esc(x.finding)} ${x.numbers ? `(${esc(x.numbers)})` : ''} <span class="prov">${esc(x.locator)}</span></li>`).join('')}</ul></div>` : ''}
    ${(r.limitations_stated || []).length ? `<div><span class="rk">Authors' limits</span>${esc(r.limitations_stated.join('; '))}</div>` : ''}
    ${(r.limitations_noticed_by_reader || []).length ? `<div><span class="rk">Reader noticed</span>${esc(r.limitations_noticed_by_reader.join('; '))}</div>` : ''}
    ${p.row?.boundary_conditions?.length ? `<div><span class="rk">Boundary</span>${esc(p.row.boundary_conditions.join('; '))}</div>` : ''}
    ${p.row?.appraisal?.risks_of_bias?.length ? `<div><span class="rk">Risks of bias</span>${esc(p.row.appraisal.risks_of_bias.join('; '))}</div>` : ''}
    ${p.row?.blind_spots?.length ? `<div><span class="rk">Blind spots</span>${esc(p.row.blind_spots.join('; '))}</div>` : ''}
    <div class="faint">Text: ${esc(p.text_source || ACCESS[p.access] || '')}</div>
    ${readByNote(p)}
    ${p.access !== 'full_text' && p.status !== 'found' ? `<label class="chip upload">Upload PDF to complete<input type="file" accept="application/pdf" data-upload="${esc(p.paper_id)}" hidden></label>` : ''}
  </div>`;
}

// A paper that was read but says nothing about any sub-claim is folded away: the pattern is the finding.
const isSilent = (p) => p.status === 'done' && !(p.row?.per_subclaim || []).some((x) => x.direction && x.direction !== 'not_addressed');
function silentGroup(list, row) {
  return `<details class="silent-group"><summary>${list.length} paper${list.length > 1 ? 's say' : ' says'} nothing about any of your claims. <b>Show ${list.length > 1 ? 'them' : 'it'}</b></summary><div class="matrix-body">${list.map(row).join('')}</div></details>`;
}

function matrix(t) {
  const ids = witnessIds(t);
  const subs = t.subclaims || [];
  const rows = t.order.map((id) => t.papers[id]).filter(Boolean);
  if (!rows.length) return '';
  const row = (p) => {
  const m = p.meta || {};
  const done = p.status === 'done';
  const rec = p.record || {};
  const isay = p.i_say_user || p.row?.i_say_draft || '';
  return `<details class="mrow ${esc(p.status)}"><summary>
      <span class="wid">${esc(ids[p.paper_id] || '')}</span>
      <span class="mtitle">${esc(m.title || '…')}<span class="faint"> · ${esc(m.year ?? '')}${rec.design?.value ? ` · ${esc(String(rec.design.value).replace(/_/g, ' '))}` : ''}${rec.sample_size?.value ? ` · n ${esc(String(rec.sample_size.value).slice(0, 40))}` : ''}</span></span>
      <span class="badge acc-${esc(p.access)}">${esc(ACCESS[p.access] || p.access)}</span>
      <span class="dirs">${done ? subs.map((s) => { const x = (p.row.per_subclaim || []).find((y) => y.id === s.id) || {}; const [g, l] = DIR[x.direction] || DIR.not_addressed; return `<span class="dir d-${esc(x.direction || 'not_addressed')}" title="${s.id}. ${esc(l)}${x.locator ? ` · ${esc(x.locator)}` : ''}">${g}</span>`; }).join('') : `<span class="faint">${esc({ found: 'queued', reading: 'reading…', analysing: 'analysing…', failed: "couldn't read", unreadable: 'title only' }[p.status] || p.status)}</span>`}</span>
      ${done ? `<span class="weight" title="Witness weight">${p.weight}</span>` : ''}
    </summary>
    ${m.url ? `<a href="${esc(m.url)}" target="_blank" rel="noopener" class="faint">${esc(m.venue || 'Source')} ↗</a>` : ''}
    ${done ? `<div class="isay"><span class="rk">${p.i_say_user ? 'You say' : "Thoth's draft “I say”"}</span> ${esc(isay)} <span class="faint">· ${esc(p.row.stance)}</span> <button class="link-btn" data-act="editISay" data-arg="${esc(p.paper_id)}">${p.i_say_user ? 'Edit' : 'Write your own'}</button></div>
      ${(p.row.per_subclaim || []).filter((x) => x.direction !== 'not_addressed').map((x) => `<div class="faint">${x.id}. ${esc(DIR[x.direction][1])} · ${esc(x.locator)}${x.note ? ` · ${esc(x.note)}` : ''}</div>`).join('')}` : ''}
    ${p.record ? recordBlock(p) : (p.reason ? `<div class="faint">${esc(p.reason)}</div>` : '')}
  </details>`;
  };
  const loud = rows.filter((p) => !isSilent(p)), silent = rows.filter(isSilent);
  const off = t.filtered;
  return `<h3>The matrix</h3>
    ${off?.dropped ? `<details class="faint"><summary>${off.dropped} off-topic Europe PMC result${off.dropped > 1 ? 's' : ''} left out (title and abstract shared too few words with the search)</summary><ul class="list">${(off.titles || []).map((x) => `<li>${esc(x)}</li>`).join('')}</ul></details>` : ''}
    <p class="faint">Rows are witnesses, columns your sub-claims. ▲ convergent · ▼ divergent · ○ null · · not addressed. Weight = design strength × how much of the paper was read.</p>
    <div class="matrix">${loud.map(row).join('')}${silent.length ? silentGroup(silent, row) : ''}</div>
    <form class="add-doi" data-act-form="addDoi"><input name="doi" placeholder="Add a paper by DOI (e.g. 10.1186/…)" aria-label="DOI"><button class="chip">Add</button></form>`;
}

function trialPanel(d) {
  ensureLoaded(d);
  const t = d.trial;
  if (!t) return null;
  return `<h2>The trial</h2>
    <p class="muted">${esc(t.hypothesis)}</p>
    ${verdictBlock(t)}
    ${matrix(t)}`;
}

const basicCheck = PANELS.check;
PANELS.check = (d) => trialPanel(d) ?? basicCheck(d);

// ---------- Editing, uploads, additions ----------
register('editISay', async (pid) => {
  const t = project().trial;
  const p = t?.papers[pid];
  if (!p) return;
  const value = await askText({ title: 'Your own reading', body: p.meta?.title || '', label: 'How do you read this paper against your hypothesis? (“I say”)', value: p.i_say_user || p.row?.i_say_draft || '', confirm: 'Save my reading' });
  if (value === null) return;
  try { Object.assign(p, await (await fetch(`${window.THOTH_API_BASE || ''}/api/trial/papers/${encodeURIComponent(pid)}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ i_say: value }) })).json()); }
  catch (err) { addMessage({ role: 'note', text: `Couldn't save: ${err.message}` }); }
  emit();
});

register('rejudgeTrial', async () => {
  const d = project();
  const t = d.trial;
  if (!t) return;
  t.stage = 'Weighing again…'; emit();
  state.busy += 1; emit();
  try { t.verdict = await postJSON(`/api/trial/${encodeURIComponent(t.trial_id)}/rejudge`, {}); t.stage = 'Done'; }
  catch (err) { addMessage({ role: 'note', text: `Couldn't weigh again: ${err.message}` }); }
  finally { state.busy -= 1; emit(); }
});

function applyEvents(d, events) { for (const e of events || []) onEvent(d, e.event, e.payload); }

document.addEventListener('change', async (e) => {
  const input = e.target.closest('input[data-upload]');
  if (!input || !input.files?.[0]) return;
  const d = project();
  const pid = input.dataset.upload;
  const file = input.files[0];
  if (file.size > 15 * 1024 * 1024) return addMessage({ role: 'note', text: 'That PDF is larger than 15 MB.' });
  const b64 = await new Promise((res) => { const r = new FileReader(); r.onload = () => res(String(r.result).split(',')[1]); r.readAsDataURL(file); });
  d.trial.papers[pid].status = 'reading'; emit();
  state.busy += 1; emit();
  try { applyEvents(d, (await postJSON(`/api/trial/papers/${encodeURIComponent(pid)}/pdf`, { pdf_base64: b64 })).events); }
  catch (err) { addMessage({ role: 'note', text: `Upload failed: ${err.message}` }); }
  finally { state.busy -= 1; emit(); }
});

document.addEventListener('submit', async (e) => {
  const form = e.target.closest('form[data-act-form="addDoi"]');
  if (!form) return;
  e.preventDefault();
  const d = project();
  const doi = form.doi.value.trim();
  if (!doi || !d.trial) return;
  form.doi.value = '';
  state.busy += 1; emit();
  try { applyEvents(d, (await postJSON(`/api/trial/${encodeURIComponent(d.trial.trial_id)}/papers`, { doi })).events); }
  catch (err) { addMessage({ role: 'note', text: `Couldn't add that paper: ${err.message}` }); }
  finally { state.busy -= 1; emit(); }
});

// Which model read a paper: the fallback may have answered when the primary was rate-limited.
const PRIMARY = 'nemotron-3-ultra';
export function readByNote(p) {
  const by = p.record?.read_by || '';
  if (!by || by.includes(PRIMARY)) return '';
  return `<div class="guard">Read by the fallback model (${esc(by)}) because the primary was busy${p.rereadFailed ? '; a re-read with the primary failed too' : ''}; treat with extra care.</div>`;
}

// ---------- Edit sub-claims (redo rows) and thinker reviews of the verdict ----------
register('editSubclaims', async () => {
  const d = project();
  const t = d.trial;
  if (!t || t.status === 'running') return;
  const n = Object.values(t.papers).filter((p) => p.status === 'done').length;
  const value = await askText({ title: 'Edit the sub-claims', confirm: `Redo ${n} rows and weigh again`, required: true,
    body: `One claim per line (at most 6). Each paper's matrix row is redone against them (${n} model calls plus the Judge, a few minutes on the free tier). The papers are not read again: their records stay as they are.`,
    value: (t.subclaims || []).map((s) => s.claim).join('\n') });
  if (value === null) return;
  const subclaims = value.split('\n').map((x) => x.trim()).filter(Boolean).slice(0, 6);
  t.status = 'running'; t.stage = 'Saving your sub-claims'; t.verdict = null; t.started = Date.now();
  liveTrial = t.trial_id;
  state.busy += 1; emit();
  try { await streamSSE(`/api/trial/${encodeURIComponent(t.trial_id)}/subclaims`, { approve: true, subclaims }, (type, pl) => onEvent(d, type, pl)); }
  catch (err) { addMessage({ role: 'note', text: `Couldn't redo the rows: ${err.message}` }); }
  finally { liveTrial = null; t.status = 'complete'; t.stage = 'Done'; state.busy -= 1; emit(); }
});

register('verdictThinkers', async () => {
  const d = project();
  const v = d.trial?.verdict;
  if (!v) return;
  const text = `Hypothesis: ${d.trial.hypothesis}\n\nOverall verdict: ${VERDICT[v.overall.verdict] || v.overall.verdict}. ${v.overall.reason || ''}\n`
    + `${v.witnesses} witnesses, ${v.full_text_witnesses} read in full. Originality: ${ORIGINALITY[v.originality?.label] || ''}. ${v.originality?.reason || ''}\n\n`
    + (v.per_subclaim || []).map((s) => `Sub-claim ${s.id}: ${s.claim}\nVerdict: ${VERDICT[s.verdict] || s.verdict}${s.certainty ? ` (certainty ${s.certainty})` : ''}\nCase for: ${s.case_for || '-'}\nCase against: ${s.case_against || '-'}${s.conflicts ? `\nConflicts: ${s.conflicts}` : ''}`).join('\n\n')
    + (v.gaps?.length ? `\n\nGaps in these witnesses:\n${v.gaps.map((g) => `- ${g.gap}`).join('\n')}` : '');
  addMessage({ role: 'note', text: 'Three thinkers are reading the verdict, each on their own…' });
  state.busy += 1; emit();
  try {
    const res = await postJSON('/api/thinkers/review', { project_id: state.projectId, artifact: 'trial verdict', text });
    const key = `rv_${Date.now()}`;
    d.reviews = d.reviews || {};
    d.reviews[key] = res.reviews || [];
    addMessage({ role: 'thoth', kind: 'reviews', reviews: key });
  } catch (err) { addMessage({ role: 'note', text: `Couldn't gather reviews: ${err.message}` }); }
  finally { state.busy -= 1; emit(); }
});
