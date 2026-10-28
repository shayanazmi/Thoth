// The research proposal (docs/features/08): outline (edit, reorder) → approve with an estimate → sections are
// written one at a time and checked by the Verifier → peer Reviewer (FATAL → bounded revisions) → thinker
// reviews whose critical concerns you answer → "reviewed", otherwise "provisional" with what is still open.
import { getJSON, streamSSE } from './api.js';
import { state, project, emit, addMessage, currentHypothesis } from './store.js';
import { register, openPanel, cardRenderers, actions } from './chat.js';
import { PANELS } from './workspace.js';
import { esc, md } from './util.js';

const legacyDraft = PANELS.draft;
const FIX_IN = { design: 'fix in the study design', evidence: 'needs more evidence' };
const SEV = { FATAL: 'contradicted', MAJOR: 'contested', MINOR: 'insufficient_evidence' };
const PROBLEM = { causal_leap: 'causal leap', overgeneralization: 'overgeneralization', direction_inversion: 'direction inverted',
  predicate_drift: 'different outcome or measure', number_mismatch: 'number not in the source', none: '' };

// JSON calls that keep the server's reason (403 approval, 409 "has your edits").
async function call(method, path, body) {
  const res = await fetch((window.THOTH_API_BASE || '') + path, {
    method, headers: { 'Content-Type': 'application/json', Accept: 'application/json' }, body: body ? JSON.stringify(body) : undefined,
  });
  let data = {};
  try { data = await res.json(); } catch (_) {}
  if (!res.ok) { const e = new Error(data.detail || `${path} → ${res.status}`); e.status = res.status; throw e; }
  return data;
}

// Transient UI state lives here, not on the project object: that is saved to localStorage, and a reload in the
// middle of a run must not leave the panel stuck "writing" or "loading", or showing a stale copy.
const UI = new Map();
const fetched = new Set();
const loading = new Set();
const ui = () => { const id = state.projectId; if (!UI.has(id)) UI.set(id, { live: {}, stage: '', running: false, editingOutline: false }); return UI.get(id); };

async function load(d, force = false) {
  const id = state.projectId;
  if (!id || loading.has(id) || (!force && fetched.has(id))) return;
  loading.add(id);
  try { d.proposal = await getJSON(`/api/proposal?project_id=${encodeURIComponent(id)}`); fetched.add(id); emit(); }
  catch (_) { /* keep what we have; the server is the source of truth when reachable */ }
  finally { loading.delete(id); }
}

// ---------- In-page dialog (the workspace re-renders on every update, so edits live outside it) ----------
function dialog({ title, body, confirm = 'OK', cancel = 'Cancel', danger = false, onConfirm }) {
  const el = document.createElement('dialog');
  el.className = 'th-dialog';
  el.innerHTML = `<form method="dialog"><h3>${esc(title)}</h3><div class="dlg-body">${body}</div>
    <div class="chips"><button class="chip${danger ? ' danger' : ' primary'}" value="ok">${esc(confirm)}</button>${cancel ? `<button class="chip" value="cancel">${esc(cancel)}</button>` : ''}</div>
    <p class="dlg-error guard" hidden></p></form>`;
  document.body.appendChild(el);
  el.addEventListener('close', () => el.remove());
  el.querySelector('form').addEventListener('submit', async (e) => {
    if (e.submitter?.value !== 'ok') return;
    e.preventDefault();
    const btn = e.submitter;
    btn.disabled = true;
    try { await onConfirm?.(el); el.close(); }
    catch (err) { const p = el.querySelector('.dlg-error'); p.hidden = false; p.textContent = err.message; btn.disabled = false; }
  });
  el.showModal();
  el.querySelector('textarea, input')?.focus();
  return el;
}

// ---------- Start: the outline ----------
async function startProposal() {
  const d = project();
  await load(d);
  // The server's research file is the truth: a hypothesis pinned in another browser still counts.
  if (!currentHypothesis(d)?.text && !d.proposal?.research_file?.hypothesis) return addMessage({ role: 'thoth', text: 'Pin a hypothesis first: a proposal argues for testing a specific claim.' });
  openPanel('draft', { fromUser: true });
  ui(d).stage = 'Drafting an outline…';
  state.busy += 1; emit();
  try {
    d.proposal = await call('POST', '/api/proposal/outline', { project_id: state.projectId });
    ui(d).editingOutline = true;
    addMessage({ role: 'thoth', kind: 'proposalPlan' });
  } catch (err) { addMessage({ role: 'note', text: `Couldn't draft the outline: ${err.message}` }); }
  finally { ui(d).stage = ''; state.busy -= 1; emit(); }
}
register('startProposal', startProposal);

cardRenderers.proposalPlan = (m, d) => {
  const p = d.proposal;
  if (!p) return '';
  const e = p.estimate || {};
  const approved = !!p.approved;
  return `<div class="card proposal heavy">
    <div class="card-kicker">Proposal outline · nothing is written until you approve</div>
    <div class="card-title">${esc(p.research_file?.hypothesis || '')}</div>
    <ol class="list outline-mini">${p.outline.map((s) => `<li>${esc(s.title)}${s.missing ? ` <span class="faint">· needs ${esc(s.missing)}</span>` : ''}</li>`).join('')}</ol>
    <div class="effort">${esc(e.sections)} sections · ${esc(e.minutes)} min · ${esc(e.model_calls)} model calls · ${esc(e.cost)}</div>
    <div class="chips">${approved ? '<span class="faint">Approved and started.</span>'
      : '<button class="chip primary" data-act="proposalApprove">Approve and write</button><button class="chip" data-act="panel" data-arg="draft">Edit the outline first</button>'}</div></div>`;
};

cardRenderers.proposalProgress = (m, d) => {
  const p = d.proposal, u = ui(d);
  if (!p) return '';
  const st = p.status || {};
  return `<div class="card trial-progress${u.running ? ' live' : ''}"><div class="card-kicker">The proposal · ${esc(u.running ? u.stage : st.status || '')}</div>
    <div class="progress-grid"><span><b>${st.sections_written ?? 0}</b>/${st.sections_total ?? 0} sections</span><span><b>${st.verifier?.checked ?? 0}</b> claims checked</span><span><b>${st.verifier?.removed ?? 0}</b> removed</span>${p.review?.counts ? `<span><b>${p.review.counts.FATAL}</b> FATAL</span>` : ''}</div>
    <div class="chips"><button class="chip" data-act="panel" data-arg="draft">Watch it in the Draft tab</button></div></div>`;
};

// ---------- Outline editor ----------
function outlineEditor(d) {
  const p = d.proposal, e = p.estimate || {};
  return `<div class="outline-editor">
    <p class="muted">Reorder, rename or re-purpose sections; drop the ones you don't need. References are built from cited witnesses and always come last.</p>
    <ol class="outline-list">${p.outline.map((s, i) => s.key === 'references'
      ? `<li class="ol-row fixed"><span class="ol-n">${i + 1}</span><div><b>${esc(s.title)}</b><div class="faint">${esc(s.purpose)}</div></div></li>`
      : `<li class="ol-row"><span class="ol-n">${i + 1}</span><div class="ol-fields">
          <input data-ol="${i}" data-f="title" value="${esc(s.title)}" aria-label="Section ${i + 1} title">
          <textarea data-ol="${i}" data-f="purpose" rows="2" aria-label="Section ${i + 1} purpose">${esc(s.purpose)}</textarea>
          ${s.missing ? `<div class="guard">The research file has no ${esc(s.missing)}; this section will carry a [GAP].</div>` : ''}</div>
        <div class="ol-btns"><button class="icon-btn" data-act="olMove" data-arg="${i}:-1" title="Move up" aria-label="Move up" ${i === 0 ? 'disabled' : ''}>↑</button>
          <button class="icon-btn" data-act="olMove" data-arg="${i}:1" title="Move down" aria-label="Move down" ${i >= p.outline.length - 2 ? 'disabled' : ''}>↓</button>
          <button class="icon-btn" data-act="olDrop" data-arg="${i}" title="Remove section" aria-label="Remove section">✕</button></div></li>`).join('')}</ol>
    <div class="chips"><button class="chip" data-act="olAdd">Add a section</button></div>
    <div class="effort">Writing: ${esc(e.sections)} sections · ${esc(e.minutes)} min · ${esc(e.model_calls)} model calls · ${esc(e.revision_rounds)} revision rounds · ${esc(e.cost)}</div>
    <div class="chips"><button class="chip primary" data-act="proposalApprove">${p.mode === 'autopilot' ? 'Approve and write all sections' : 'Approve and write the first section'}</button>${p.approved ? '<button class="chip" data-act="olDone">Back to the proposal</button>' : ''}</div>
    <p class="faint">${p.mode === 'autopilot' ? 'Autopilot: every section is written and checked, then the peer Reviewer reads the whole proposal.' : 'Co-pilot: one section at a time; you approve each next one. The peer Reviewer reads it once every section is written.'}</p></div>`;
}

document.addEventListener('input', (e) => {
  const t = e.target.closest('[data-ol]');
  if (!t) return;
  const s = project()?.proposal?.outline?.[+t.dataset.ol];
  if (s) s[t.dataset.f] = t.value;  // kept in memory; no re-render while typing
});

register('olMove', (arg) => {
  const d = project(), o = d.proposal.outline;
  const [i, dir] = arg.split(':').map(Number);
  const j = i + dir;
  if (j < 0 || j >= o.length - 1) return;
  [o[i], o[j]] = [o[j], o[i]];
  emit();
});
register('olDrop', (i) => { const o = project().proposal.outline; if (o.length > 2) o.splice(+i, 1); emit(); });
register('olAdd', () => {
  dialog({ title: 'Add a section', confirm: 'Add',
    body: '<label>Title<input name="t" placeholder="e.g. Patient and public involvement"></label><label>What it should cover<textarea name="p" rows="3"></textarea></label>',
    onConfirm: (el) => {
      const title = el.querySelector('[name=t]').value.trim();
      if (!title) throw new Error('Give the section a title.');
      const o = project().proposal.outline;
      o.splice(o.length - 1, 0, { key: title.toLowerCase().replace(/[^a-z0-9]+/g, '_').slice(0, 40), title, purpose: el.querySelector('[name=p]').value.trim() });
      emit();
    } });
});
register('olEdit', () => { ui(project()).editingOutline = true; emit(); });
register('olDone', async () => {
  const d = project();
  try { d.proposal = await call('PUT', '/api/proposal/outline', { project_id: state.projectId, outline: d.proposal.outline }); } catch (err) { addMessage({ role: 'note', text: err.message }); }
  ui(d).editingOutline = false; emit();
});

// Live counts while sections arrive (the server's full status comes at the end).
function tally(p) {
  const secs = Object.values(p.sections), st = (p.status = p.status || {});
  st.sections_written = secs.filter((s) => s.draft).length;
  st.verifier = {};
  for (const s of secs) for (const [k, v] of Object.entries(s.verification?.summary || {})) st.verifier[k] = (st.verifier[k] || 0) + v;
}

// ---------- Approve and write (live) ----------
register('proposalApprove', async () => {
  const d = project(), u = ui(d);
  if (u.running || !d.proposal) return;
  u.running = true; u.editingOutline = false; u.live = {}; u.stage = 'Starting';
  d.proposal.approved = { at: Date.now() / 1000 };
  addMessage({ role: 'thoth', kind: 'proposalProgress' });
  openPanel('draft', { fromUser: true });
  state.busy += 1; emit();
  u.next = null;
  try {
    await streamSSE('/api/proposal/write', { project_id: state.projectId, approve: true, outline: d.proposal.outline }, live(d));
  } catch (err) { addMessage({ role: 'note', text: `Writing stopped: ${err.message}` }); }
  finally {
    u.running = false; u.stage = ''; state.busy -= 1;
    await load(d, true);
    const st = d.proposal?.status;
    if (u.next) {
      // Co-pilot: one section per approval.
      const written = Object.values(d.proposal.sections).filter((x) => x.draft).length;
      addMessage({ role: 'thoth', text: `**Section ${written} of ${st?.sections_total ?? '?'} is written.** Read it, change it if you like, then approve the next one: “${u.next.title}”.`,
        chips: [{ label: `Write “${u.next.title}”`, act: 'proposalApprove', primary: true }, { label: 'Read it', act: 'panel', arg: 'draft' }] });
    } else if (st) {
      addMessage({ role: 'thoth', text: `**The proposal is drafted: ${st.status}.** ${st.verifier?.checked || 0} claims checked, ${st.verifier?.removed || 0} removed, ${st.verifier?.softened || 0} softened.${d.proposal.review?.counts ? ` The Reviewer found ${d.proposal.review.counts.FATAL} FATAL, ${d.proposal.review.counts.MAJOR} MAJOR and ${d.proposal.review.counts.MINOR} MINOR problems.` : ''}`,
        chips: [{ label: 'Read it', act: 'panel', arg: 'draft', primary: true }, { label: 'Ask thinkers to review it', act: 'proposalThinkers' }] });
    }
    emit();
  }
});

// One handler for the write and review streams: live section status, revisions, the review.
function live(d) {
  const u = ui(d);
  const titles = Object.fromEntries(d.proposal.outline.map((s) => [s.key, s.title]));
  return (type, pl) => {
      const p = d.proposal;
      switch (type) {
        case 'section_writing': u.live[pl.key] = 'writing'; u.stage = `Writing “${pl.title}”`; break;
        case 'section_done': p.sections[pl.key] = pl.section; u.live[pl.key] = pl.revised ? 'revised' : 'done'; tally(p); break;
        case 'section_failed': u.live[pl.key] = 'failed'; addMessage({ role: 'note', text: `${titles[pl.key] || pl.key}: ${pl.message}` }); break;
        case 'section_kept': u.live[pl.key] = 'kept'; break;
        case 'review_start': u.stage = pl.round ? `Reviewer, round ${pl.round + 1}` : 'Peer Reviewer reading the whole proposal'; break;
        case 'review_done': p.review = pl.review; break;
        case 'review_failed': addMessage({ role: 'note', text: pl.message }); break;
        case 'section_revising': u.live[pl.key] = 'revising'; u.stage = `Revising “${titles[pl.key] || pl.key}” for a FATAL problem (round ${pl.round} of 2)`; break;
        case 'status': p.status = pl; break;
        case 'awaiting_next': u.next = pl; break;
        case 'error': addMessage({ role: 'note', text: pl.error }); break;
        default: break;
      }
      emit();
  };
}

// ---------- Sections ----------
const citeHtml = (ids, w) => `<span class="cite" title="${esc(ids.map((i) => `${i}: ${w[i]?.title || 'not a witness'} (${(w[i]?.access || '').replace('_', ' ')})`).join('\n'))}">(${esc(ids.map((i) => w[i]?.cite || i).join('; '))})</span>`;
// [W3] → (Lee et al., 2021); a witness id in the running text → Lee et al. (2021).
const renderCites = (text, w) => esc(text.replace(/\s*\{\{\s*file\s*:[^}]*\}\}/g, '')).replace(/\[(W\d+(?:\s*[;,]\s*W\d+)*)\]|\bW\d+\b/g, (all, g) => (g ? citeHtml(g.split(/\s*[;,]\s*/), w)
  : w[all] ? `<span class="cite" title="${esc(`${all}: ${w[all].title}`)}">${esc(w[all].narrative)}</span>` : all));

function sectionHtml(sec, w) {
  const v = sec.verification;
  if (!v) return md(sec.draft.replace(/\{\{\s*w\s*:\s*(W\d+)\s*\}\}/g, '[$1]').replace(/\s*\{\{[^}]*\}\}/g, '')).replace(/\[(W\d+(?:\s*[;,]\s*W\d+)*)\]/g, (_, g) => citeHtml(g.split(/\s*[;,]\s*/), w));
  const src = v.segments.map((s) => {
    if (s.t === 'text') return s.text;
    const r = s.r || {};
    if (r.action === 'remove') return '';
    const cls = r.kind === 'gap' ? 'v-gap' : r.kind === 'uncited' || r.kind === 'unchecked' ? 'v-flag' : r.action === 'soften' ? 'v-soft' : r.kind === 'claim' ? 'v-ok' : '';
    const tip = r.action === 'soften' ? `Softened (${PROBLEM[r.problem] || r.problem}). Was: “${r.original.replace(/\{\{[^}]+\}\}/g, '').trim()}” ${r.why}` : r.why || (r.kind === 'claim' ? 'Checked against the cited witness.' : '');
    const by = r.checked_by && !/ultra/i.test(r.checked_by) ? ` (checked by the fallback model ${r.checked_by})` : '';
    return cls ? `<span class="vm ${cls}" title="${esc(tip + by)}">${renderCites(s.text, w)}</span>` : renderCites(s.text, w);
  }).join('');
  return md(src);
}

function liveLabel(d, key, sec) {
  const l = ui(d).live[key];
  if (l === 'writing') return '<span class="badge live">writing…</span>';
  if (l === 'revising') return '<span class="badge live">revising…</span>';
  if (l === 'failed') return '<span class="badge bad">not written</span>';
  if (!sec) return '<span class="badge">not written</span>';
  if (sec.user_edited && !sec.verification) return '<span class="badge acc-abstract_only">your edits · not verified</span>';
  if (!sec.verification) return '<span class="badge acc-abstract_only">not verified</span>';
  const fallback = sec.written_by && !/ultra/i.test(sec.written_by) ? ` <span class="badge" title="Ultra was rate-limited; this section was written by ${esc(sec.written_by)}">fallback model</span>` : '';
  const staleDesign = sec.design_stale ? ` <span class="badge bad" title="Regenerate it to follow the current design">${esc(sec.design_stale)}</span>` : '';
  return `<span class="badge acc-full_text">${sec.user_edited ? 'your edits · ' : ''}verified${sec.revisions ? ` · revised ×${sec.revisions}` : ''}</span>${fallback}${staleDesign}`;
}

function sectionCard(d, s, i) {
  const p = d.proposal, sec = p.sections[s.key], w = p.witnesses || {};
  if (s.key === 'references') return `<section class="pz-sec"><div class="prose">${md(p.references?.markdown || '')}</div><p class="faint">Built from the witnesses still cited after the Verifier, not written by a model.</p></section>`;
  const v = sec?.verification, sm = v?.summary;
  const fatals = (p.review?.weaknesses || []).filter((x) => x.section === s.key);
  return `<section class="pz-sec" id="pz-${esc(s.key)}">
    <div class="pz-head"><span class="ol-n">${i + 1}</span><b>${esc(s.title)}</b>${liveLabel(d, s.key, sec)}
      ${fatals.length ? `<span class="badge bad">${fatals.length} reviewer finding${fatals.length > 1 ? 's' : ''}</span>` : ''}</div>
    ${sec && sec.draft ? `<div class="prose pz-body">${sectionHtml(sec, w)}</div>` : `<p class="faint">${esc(s.purpose)}</p>`}
    ${sm ? `<div class="pz-ver faint">Verifier: ${sm.checked} claim${sm.checked === 1 ? '' : 's'} checked · ${sm.kept} kept · ${sm.softened} softened · ${sm.removed} removed${sm.flagged ? ` · <span class="v-flag">${sm.flagged} flagged</span>` : ''}${sm.gaps ? ` · <span class="v-gap">${sm.gaps} gap${sm.gaps > 1 ? 's' : ''}</span>` : ''}</div>` : ''}
    ${v?.removed?.length ? `<details class="removed"><summary>Removed unsupported claims (${v.removed.length})</summary><ul class="list">${v.removed.map((r) => `<li><s>${esc(r.sentence)}</s><br><span class="faint">${r.witnesses?.length ? esc(r.witnesses.join(', ')) + ' · ' : ''}${esc(PROBLEM[r.problem] || '')}${PROBLEM[r.problem] ? ' · ' : ''}${esc(r.why)}</span></li>`).join('')}</ul></details>` : ''}
    ${p.approved && !ui(d).running ? `<div class="chips">${sec?.draft ? `<button class="chip" data-act="pzEdit" data-arg="${esc(s.key)}">Edit</button>` : ''}
      <button class="chip" data-act="pzRegen" data-arg="${esc(s.key)}">${sec?.draft ? 'Regenerate' : 'Write this section'}</button>
      ${sec?.draft && !v ? `<button class="chip primary" data-act="pzVerify" data-arg="${esc(s.key)}">Verify</button>` : ''}</div>` : ''}
  </section>`;
}

async function sectionCall(key, path, body, label) {
  const d = project(), u = ui(d);
  u.live[key] = label; state.busy += 1; emit();
  try {
    const out = await call('POST', `/api/proposal/sections/${encodeURIComponent(key)}/${path}`, { project_id: state.projectId, ...body });
    if (out.degraded) addMessage({ role: 'note', text: out.message });
    u.live[key] = out.degraded ? 'failed' : 'done';
    await load(d, true);
  } catch (err) { u.live[key] = ''; throw err; }
  finally { state.busy -= 1; emit(); }
}

register('pzRegen', (key) => {
  const d = project(), sec = d.proposal.sections[key];
  const title = d.proposal.outline.find((s) => s.key === key)?.title || key;
  const run = (overwrite, instruction) => sectionCall(key, 'regenerate', { overwrite, instruction }, 'writing').catch((err) => addMessage({ role: 'note', text: err.message }));
  dialog({
    title: sec?.user_edited ? `Replace your edits to “${title}”?` : `${sec?.draft ? 'Regenerate' : 'Write'} “${title}”`,
    danger: !!sec?.user_edited, confirm: sec?.user_edited ? 'Replace my edits' : 'Write it',
    body: `${sec?.user_edited ? '<p class="guard">This section has your own edits. Regenerating replaces them with a new draft from the research file (earlier versions stay in the notebook history).</p>' : ''}
      <label>Anything the Writer should do differently? (optional)<textarea name="i" rows="3" placeholder="e.g. shorter; lead with the strongest divergent witness"></textarea></label>
      <p class="faint">About 1 model call plus one Verifier check per factual sentence.</p>`,
    onConfirm: (el) => { run(!!sec?.user_edited, el.querySelector('[name=i]').value.trim()); },
  });
});

register('pzEdit', (key) => {
  const d = project(), sec = d.proposal.sections[key];
  const text = sec.user_edited || !sec.verification ? sec.draft : sec.verification.final_markdown;
  dialog({ title: `Edit “${d.proposal.outline.find((s) => s.key === key)?.title || key}”`, confirm: 'Save my edits',
    body: `<textarea name="m" rows="18" class="pz-edit">${esc(text)}</textarea>
      <p class="faint">[W3] marks a citation to witness W3, and {{file:verdict}} a sentence resting on your research file. Keep them so the Verifier can check your wording. Your edits are never overwritten without asking.</p>`,
    onConfirm: async (el) => {
      await call('PUT', `/api/proposal/sections/${encodeURIComponent(key)}`, { project_id: state.projectId, markdown: el.querySelector('[name=m]').value });
      await load(d, true);
      addMessage({ role: 'thoth', text: 'Saved your edits. Until the Verifier checks them, the proposal stays provisional.', chips: [{ label: 'Verify now', act: 'pzVerify', arg: key, primary: true }] });
    } });
});

register('pzVerify', (key) => sectionCall(key, 'verify', {}, 'writing').catch((err) => addMessage({ role: 'note', text: err.message })));

// ---------- Reviewer ----------
function reviewerBlock(p) {
  const r = p.review;
  const again = '<div class="chips"><button class="chip primary" data-act="pzReview">Run the peer Reviewer</button></div>';
  if (!r) return Object.keys(p.sections).length ? `<div class="pz-review"><b>Peer Reviewer</b><p class="faint">Not run yet.</p>${again}</div>` : '';
  if (r.degraded) return `<div class="pz-review"><b>Peer Reviewer</b><div class="guard">The Reviewer couldn't be reached (the free tier was rate-limiting); no review was made up in its place.</div>${again}</div>`;
  const title = (k) => p.outline.find((s) => s.key === k)?.title || '';
  return `<details class="pz-review" ${r.counts?.FATAL ? 'open' : ''}><summary><b>Peer Reviewer</b> <span class="faint">${r.counts.FATAL} FATAL · ${r.counts.MAJOR} MAJOR · ${r.counts.MINOR} MINOR · ${r.loops} revision round${r.loops === 1 ? '' : 's'}${p.status?.reviewer?.state === 'stale' ? ' · out of date' : ''}</span></summary>
    <p>${esc(r.summary)}</p>
    ${(r.weaknesses || []).map((x) => `<div class="finding sev-${x.severity}"><span class="verdict v-${SEV[x.severity]}">${x.severity}</span> <span class="faint">${esc(title(x.section) || 'unplaced')}</span>
      ${x.passage ? `<blockquote>${esc(x.passage)}</blockquote>${x.quoted ? '' : '<span class="faint">(passage not found verbatim in the proposal)</span>'}` : ''}
      <p>${esc(x.problem)}</p>${x.fix ? `<p class="faint">Fix: ${esc(x.fix)}</p>` : ''}
      ${FIX_IN[x.fix_in] ? `<div><span class="badge">${FIX_IN[x.fix_in]}</span>${x.severity === 'FATAL' && x.fix_in === 'design' ? ' <span class="faint">Rewording the proposal can\'t fix this, so it wasn\'t sent to the Writer.</span>' : ''}</div>` : ''}</div>`).join('')}
    ${r.held?.length ? `<p class="faint">Not revised automatically: ${r.held.map((h) => `${esc(h.id)} (${esc(h.why)})`).join('; ')}.</p>` : ''}
    ${r.held?.some((h) => h.fix_in === 'design') ? '<div class="chips"><button class="chip primary" data-act="reviseDesign">Revise the design for this</button></div>' : ''}
    ${r.resolved_held?.length ? `<h4>Resolved</h4><ul class="list">${r.resolved_held.map((h) => `<li><span class="rk">${esc(h.id)}</span>${esc(h.problem)} <span class="faint">· resolved by design v${esc(h.resolved_by_design_version)} (raised against v${esc(h.design_version ?? '?')})</span></li>`).join('')}</ul>` : ''}
    ${r.questions?.length ? `<h4>Questions</h4><ul class="list">${r.questions.map((q) => `<li>${esc(q)}</li>`).join('')}</ul>` : ''}
    <div class="chips"><button class="chip" data-act="pzReview">Run the Reviewer again</button></div></details>`;
}

register('pzReview', async () => {
  const d = project(), u = ui(d);
  u.running = true; u.stage = 'Peer Reviewer reading the whole proposal'; state.busy += 1; emit();
  try { await streamSSE('/api/proposal/review/stream', { project_id: state.projectId }, live(d)); }
  catch (err) { addMessage({ role: 'note', text: err.message }); }
  finally {
    u.running = false; u.stage = ''; state.busy -= 1;
    await load(d, true);
    const c = d.proposal?.review?.counts;
    if (c) addMessage({ role: 'thoth', text: `**Peer review: ${c.FATAL} FATAL, ${c.MAJOR} MAJOR, ${c.MINOR} MINOR** after ${d.proposal.review.loops} revision round${d.proposal.review.loops === 1 ? '' : 's'}. The proposal is ${d.proposal.status.status}.`, chips: [{ label: 'See the findings', act: 'panel', arg: 'draft', primary: true }] });
    emit();
  }
});

// ---------- After the design changes (docs/features/07 ↔ 08): regenerate what restates it, then review again ----------
function staleSections(p) {
  return Object.entries(p?.sections || {}).filter(([, s]) => s.design_stale).map(([k, s]) => ({ key: k, title: s.title || k, edited: !!s.user_edited }));
}

register('pzFollowDesign', () => {
  const d = project();
  const stale = staleSections(d.proposal);
  const auto = stale.filter((s) => !s.edited), manual = stale.filter((s) => s.edited);
  if (!stale.length) return;
  // Cost first (the non-negotiable): every regenerated section is written and verified, then the Reviewer reads it all.
  dialog({
    title: 'Bring the proposal up to the new design',
    body: `<p>Regenerate ${auto.length} section${auto.length === 1 ? '' : 's'} (${esc(auto.map((s) => s.title).join(', ') || 'none')}) from the current design, then run the peer Reviewer again: about ${auto.length * 2 + 2} model calls.</p>
      ${manual.length ? `<p class="guard">Your edited section${manual.length > 1 ? 's' : ''} (${esc(manual.map((s) => s.title).join(', '))}) won't be touched; update ${manual.length > 1 ? 'them' : 'it'} yourself.</p>` : ''}`,
    confirm: auto.length ? 'Regenerate and review' : 'Run the Reviewer again',
    onConfirm: async () => {
      const u = ui(d);
      u.running = true; state.busy += 1; emit();
      try {
        for (const [i, s] of auto.entries()) {
          u.stage = `Rewriting ${s.title} for the new design (${i + 1} of ${auto.length})`; emit();
          await call('POST', `/api/proposal/sections/${encodeURIComponent(s.key)}/regenerate`, { project_id: state.projectId, overwrite: false });
        }
      } finally { u.running = false; u.stage = ''; state.busy -= 1; await load(d, true); }
      setTimeout(() => (actions.pzReview || (() => {}))(), 0);
    },
  });
});

// A design chosen in the Design tab makes proposal sections stale: refetch so the panel says so at once.
register('proposalStale', () => { fetched.delete(state.projectId); const d = project(); if (d) load(d, true); });

// ---------- Thinkers ----------
function thinkersBlock(p) {
  const th = p.thinkers;
  const btn = `<button class="chip${th ? '' : ' primary'}" data-act="proposalThinkers">${th ? 'Ask for fresh thinker reviews' : 'Ask thinkers to review it'}</button>`;
  if (!th) return `<div class="pz-thinkers"><b>Thinker reviews</b><p class="faint">Independent reviews by three thinkers. Critical concerns must be answered before the proposal can be called reviewed.</p><div class="chips">${btn}</div></div>`;
  return `<div class="pz-thinkers"><b>Thinker reviews</b>
    ${th.reviews.map((r) => `<details class="design-card"><summary><b>${esc(r.thinker_name)}</b>${r.degraded ? '<span class="faint">couldn\'t be reached</span>' : r.verdict ? `<span class="badge">${esc(r.verdict)}</span>` : ''}</summary><div class="prose">${md(r.review)}</div></details>`).join('')}
    ${th.concerns.length ? `<ul class="list concerns">${th.concerns.map((c) => {
      const must = c.severity === 'critical' || c.severity === 'unknown';
      return `<li class="concern${must && !c.answer ? ' open' : ''}"><span class="badge${c.severity === 'critical' ? ' bad' : ''}">${esc(c.severity === 'unknown' ? 'unsorted' : c.severity)}</span> <b>${esc(c.thinker_name)}:</b> ${esc(c.claim)}${c.why ? ` <span class="faint">${esc(c.why)}</span>` : ''}
        ${c.answer ? `<div class="answer"><span class="rk">Your reply</span>${esc(c.answer)}</div>` : must ? `<div class="chips"><button class="chip primary" data-act="pzAnswer" data-arg="${esc(c.id)}">Answer</button></div>` : ''}</li>`;
    }).join('')}</ul>` : ''}
    <div class="chips">${btn}</div></div>`;
}

register('proposalThinkers', async () => {
  const d = project();
  await load(d);
  if (!Object.keys(d.proposal?.sections || {}).length) return addMessage({ role: 'note', text: 'Write the proposal first.' });
  openPanel('draft', { fromUser: true });
  addMessage({ role: 'note', text: 'Three thinkers are reading the whole proposal, each on their own…' });
  ui(d).stage = 'Thinkers reviewing'; state.busy += 1; emit();
  try {
    await call('POST', '/api/proposal/thinkers', { project_id: state.projectId });
    await load(d, true);
    const open = d.proposal.status.thinkers.open;
    addMessage({ role: 'thoth', text: open ? `**${open} critical concern${open > 1 ? 's' : ''} need${open > 1 ? '' : 's'} your answer** before the proposal can be called reviewed.` : 'The thinkers raised no critical concerns.', chips: [{ label: 'See their reviews', act: 'panel', arg: 'draft', primary: true }] });
  } catch (err) { addMessage({ role: 'note', text: `Couldn't gather thinker reviews: ${err.message}` }); }
  finally { ui(d).stage = ''; state.busy -= 1; emit(); }
});

register('pzAnswer', (cid) => {
  const d = project(), c = d.proposal.thinkers.concerns.find((x) => x.id === cid);
  dialog({ title: `Answer ${c.thinker_name}`, confirm: 'Record my answer',
    body: `<blockquote>${esc(c.claim)}</blockquote><label>Your answer (it goes on record; you can also change the proposal itself)<textarea name="r" rows="6"></textarea></label>`,
    onConfirm: async (el) => {
      const reply = el.querySelector('[name=r]').value.trim();
      if (!reply) throw new Error('Write an answer first.');
      await call('POST', `/api/proposal/concerns/${encodeURIComponent(cid)}/answer`, { project_id: state.projectId, reply });
      await load(d, true);
    } });
});

// ---------- Export ----------
register('pzExport', () => {
  const d = project(), st = d.proposal.status;
  const prov = st.status === 'provisional';
  dialog({ title: 'Export the proposal as Markdown?', confirm: prov ? 'Export with PROVISIONAL watermark' : 'Export',
    body: (prov ? `<p class="guard">This proposal is provisional. The file will be marked PROVISIONAL and list the ${st.gaps.length} open item${st.gaps.length > 1 ? 's' : ''}.</p>` : '<p>The proposal passed the Verifier, the Reviewer and the thinkers.</p>')
      + '<p class="faint">PDF and Word export come later; nothing is exported without your approval.</p>',
    onConfirm: async () => {
      const out = await call('POST', '/api/proposal/export', { project_id: state.projectId, approve: true, format: 'markdown' });
      const url = URL.createObjectURL(new Blob([out.content], { type: 'text/markdown' }));
      const a = Object.assign(document.createElement('a'), { href: url, download: out.filename });
      document.body.appendChild(a); a.click(); a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 2000);
    } });
});

// ---------- Panel ----------
function statusHeader(p) {
  const st = p.status, v = st.verifier || {}, r = st.reviewer || {}, t = st.thinkers || {};
  const reviewed = st.status === 'reviewed';
  return `<div class="status-banner${reviewed ? ' full' : ''} pz-status"><b>${reviewed ? 'Reviewed' : 'Provisional'}</b> · ${st.sections_written}/${st.sections_total} sections
    <div class="pz-meters"><span>Verifier <b>${v.checked || 0}</b> checked · <b>${v.removed || 0}</b> removed · <b>${v.flagged || 0}</b> flagged</span>
      <span>Reviewer ${r.state === 'none' ? 'not run' : `<b>${r.open.FATAL}</b> FATAL · <b>${r.open.MAJOR}</b> MAJOR · <b>${r.open.MINOR}</b> MINOR open${r.state === 'stale' ? ' (out of date)' : ''}`}</span>
      <span>Thinkers ${t.reviewed ? `<b>${t.need_answer - t.open}</b> answered · <b>${t.open}</b> open` : 'not asked'}</span></div>
    ${(st.advisories || []).map((x) => `<div class="faint">Advice: ${esc(x)} <button class="link-btn" data-act="review">Plan a systematic review</button></div>`).join('')}
    ${st.gaps.length ? `<details><summary class="faint">${st.gaps.length} open item${st.gaps.length > 1 ? 's' : ''}</summary><ul class="list">${st.gaps.map((g) => `<li>${esc(g)}</li>`).join('')}</ul></details>` : ''}
    ${staleSections(p).length && !ui(p).running ? `<div class="guard">${staleSections(p).length} section${staleSections(p).length > 1 ? 's were' : ' was'} written for an older design. <button class="chip primary" data-act="pzFollowDesign">Bring the proposal up to the new design</button></div>` : ''}
    <div class="chips">${st.sections_written < st.sections_total && !ui(p).running ? `<button class="chip primary" data-act="proposalApprove">${p.mode === 'autopilot' ? 'Write the remaining sections' : 'Write the next section'}</button>` : ''}<button class="chip" data-act="pzExport">Export…</button><button class="chip" data-act="olEdit">Edit the outline</button></div></div>`;
}

function proposalPanel(d) {
  load(d);
  const p = fetched.has(state.projectId) ? d.proposal : null, u = ui(d);
  const legacy = d.report ? `<details class="pz-legacy"><summary class="faint">The earlier check's synthesis</summary>${legacyDraft(d)}</details>` : '';
  if (!p) return `<h2>Research proposal</h2><p class="faint">Loading…</p>${legacy}`;
  const rf = p.research_file || {};
  if (!p.has_outline) {
    return `<h2>Research proposal</h2>
      <div class="empty"><b>No proposal yet.</b><br>Thoth drafts an outline from your research file, you edit and approve it, then each section is written from your trial, design and your own words, and checked.
      <ul class="list pz-file"><li>${rf.hypothesis ? '✓ Hypothesis' : '· No hypothesis pinned'}</li><li>${rf.trial ? `✓ Trial with ${rf.witnesses} witnesses` : '· No completed trial (literature sections will carry gaps)'}</li><li>${rf.design ? '✓ Chosen study design' : '· No chosen design (methods will carry a gap)'}</li></ul>
      <div class="chips"><button class="chip primary" data-act="startProposal" ${rf.hypothesis ? '' : 'disabled'}>Draft an outline</button></div></div>${u.stage ? `<p class="faint">${esc(u.stage)}</p>` : ''}${legacy}`;
  }
  if (!p.approved || u.editingOutline) return `<h2>Research proposal · outline</h2>${outlineEditor(d)}${legacy}`;
  return `<h2>Research proposal</h2>
    ${statusHeader(p)}
    ${u.running || u.stage ? `<div class="status-banner"><b>${esc(u.stage || 'Working…')}</b></div>` : ''}
    ${p.outline.map((s, i) => sectionCard(d, s, i)).join('')}
    ${reviewerBlock(p)}
    ${thinkersBlock(p)}${legacy}`;
}
PANELS.draft = proposalPanel;
