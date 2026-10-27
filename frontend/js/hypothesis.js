// The hypothesis (docs/features/04): strength markers on the pinned card, rivals parked on the server, swapping a
// rival in, and re-mapping the latest trial's library to it (only the matrix and the verdict are redone).
import { getJSON, postJSON } from './api.js';
import { state, project, emit, addMessage, currentHypothesis, hydrate, persistSection } from './store.js';
import { register, openPanel, hypCardExtras } from './chat.js';
import { PANELS } from './workspace.js';
import { esc } from './util.js';
import { askText, toast } from './ui.js';

const MARKERS = [
  ['direction_comparison', 'Direction and comparison', 'which way, and against what', 'no comparison'],
  ['population_scope', 'Population and scope', 'who, where, when', 'no scope'],
  ['falsifier', 'Falsifier', 'the result that would show it wrong', 'falsifier missing'],
];

// ---------- Strength markers (checked once per version on the server) ----------
// Kept in module memory, not on the project object: that is saved to localStorage, and a stale copy would
// outlive a server-side fix to the markers (seen in the walkthrough).
const MEMO = new Map();
const loading = new Set();
const memoKey = (text) => `${state.projectId}\u0000${text}`;

async function loadMarkers(text) {
  const key = memoKey(text);
  if (loading.has(key) || !state.projectId || state.projectId.startsWith('local_')) return;
  loading.add(key);
  try {
    const m = await getJSON(`/api/projects/${encodeURIComponent(state.projectId)}/markers`);
    MEMO.set(memoKey(m.text), m);
    emit();
  } catch (_) { MEMO.set(key, { checked: false, text }); emit(); }
  finally { loading.delete(key); }
}

function markersFor(d, text) {
  const m = MEMO.get(memoKey(text));
  if (m) return m;
  loadMarkers(text);
  return null;
}

hypCardExtras.push((d, v, isCurrent) => {
  if (!isCurrent) return '';
  const m = markersFor(d, v.text);
  if (!m) return '<div class="hyp-markers faint">Checking its strength markers…</div>';
  if (!m.checked) return '<div class="hyp-markers faint">Strength markers not checked (no model reachable). <button class="link-btn" data-act="recheckMarkers">Check</button></div>';
  const chip = (ok, label, tip) => `<span class="mk${ok ? '' : ' missing'}" title="${esc(tip)}">${ok ? '✓' : '·'} ${esc(label)}</span>`;
  return `<div class="hyp-markers">
    ${chip(m.can_go_on_trial, m.can_go_on_trial ? m.constructs.map((c) => c.name).join(', ') : `needs named constructs${m.constructs.length ? ` (only: ${m.constructs.map((c) => c.name).join(', ')})` : ''}`,
      m.can_go_on_trial ? `Named: ${m.constructs.map((c) => `“${c.quote}”`).join(', ')}` : 'A trial needs at least two things that vary, named (e.g. “night-shift work” and “emotional exhaustion”).')}
    ${MARKERS.map(([k, label, what, missing]) => chip(m[k]?.present, m[k]?.present ? label.split(' ')[0] : missing, m[k]?.present ? `${label}: “${m[k].quote}”` : `Not stated: ${what}. A weakness, not a blocker.`)).join('')}
  </div>`;
});

register('recheckMarkers', () => { const cur = currentHypothesis(); if (cur) MEMO.delete(memoKey(cur.text)); emit(); });

// ---------- Rivals ----------
const pid = () => encodeURIComponent(state.projectId);

function rivalsSection(d) {
  const rivals = d.rivals || [];
  return `<div class="ws-section"><h3>Rivals</h3>
    <p class="faint">One hypothesis is under trial; rivals wait here. Swapping one in keeps your library: the papers aren't searched or read again, only the matrix and the verdict are redone.</p>
    ${rivals.length ? `<ul class="list rivals">${rivals.map((r, i) => `<li><span>${esc(r)}</span>
      <span class="chips"><button class="chip" data-act="swapRival" data-arg="${i}">Swap in</button><button class="chip" data-act="retireRival" data-arg="${i}">Retire</button></span></li>`).join('')}</ul>`
      : '<p class="faint">No rivals parked.</p>'}
    <div class="chips"><button class="chip" data-act="parkRival">Park a rival</button></div></div>`;
}

function markersSection(d) {
  const cur = currentHypothesis(d);
  const m = cur && markersFor(d, cur.text);
  if (!m?.checked) return '';
  return `<div class="ws-section"><h3>Strength</h3><ul class="list">
    <li><b>Named constructs</b> (at least two needed for a trial): ${m.constructs.length ? m.constructs.map((c) => `${esc(c.name)} <span class="faint">“${esc(c.quote)}”</span>`).join('; ') : '<span class="guard">none named</span>'}</li>
    ${MARKERS.map(([k, label, what]) => `<li><b>${label}</b>: ${m[k]?.present ? `<span class="faint">“${esc(m[k].quote)}”</span>` : `<span class="guard">missing</span> <span class="faint">(${what}; a weakness the Judge will cite, not a blocker)</span>`}</li>`).join('')}
  </ul></div>`;
}

const basePanel = PANELS.hypothesis;
PANELS.hypothesis = (d) => {
  const html = basePanel(d);
  return currentHypothesis(d) ? html + markersSection(d) + rivalsSection(d) : html;
};

register('parkRival', async () => {
  const text = await askText({ title: 'Park a rival hypothesis', label: 'An alternative explanation you want to keep in view', confirm: 'Park it', required: true,
    placeholder: 'e.g. Night-shift nurses are more exhausted because of heavier workload, not the clock.' });
  if (!text?.trim()) return;
  await persistSection('rival_hypothesis', text.trim());
  await hydrate(state.projectId);
  toast('Rival parked.');
});

register('retireRival', async (i) => {
  const d = project();
  const text = d.rivals?.[+i];
  if (!text) return;
  try { d.rivals = (await postJSON(`/api/projects/${pid()}/rivals/retire`, { text })).rivals; emit(); }
  catch (err) { addMessage({ role: 'note', text: `Couldn't retire it: ${err.message}` }); }
});

register('swapRival', async (i) => {
  const d = project();
  const text = d.rivals?.[+i];
  if (!text) return;
  try {
    // Ask the server: the trial panel may not have been opened yet in this page.
    const latest = await getJSON(`/api/trial/latest?project_id=${pid()}`).catch(() => ({}));
    const hadTrial = latest?.status === 'complete' ? latest.trial_id : null;
    await postJSON(`/api/projects/${pid()}/rivals/swap`, { text });
    await hydrate(state.projectId);
    const n = d.hypothesis.versions.length;
    // The open trial is now about the previous version (the server says so on the next load, too).
    if (d.trial && d.trial.trial_id === hadTrial) Object.assign(d.trial, { stale: true, hypothesis_now: { version: n, text } });
    addMessage({ role: 'thoth', text: `**Swapped in as v${n}:** ${text}\n\nThe previous hypothesis is parked as a rival.${hadTrial ? ' The latest verdict was about the previous version; its papers can be re-mapped to this one without searching or reading again.' : ''}`,
      chips: hadTrial ? [{ label: 'Re-map the papers to v' + n, act: 'remapTrial', arg: hadTrial, primary: true }] : [{ label: 'Put it on trial', act: 'startTrial', primary: true }] });
  } catch (err) { addMessage({ role: 'note', text: `Couldn't swap it in: ${err.message}` }); }
});

// ---------- Re-map a trial's library to the current hypothesis ----------
register('remapTrial', async (trialId) => {
  const d = project();
  const id = trialId || d.trial?.trial_id;
  if (!id) return;
  addMessage({ role: 'note', text: 'Splitting the new hypothesis into sub-claims. The papers stay as they are; nothing runs until you approve.' });
  state.busy += 1; emit();
  try {
    const plan = await postJSON(`/api/trial/${encodeURIComponent(id)}/remap`, { project_id: state.projectId });
    d.trialPlans = d.trialPlans || {};
    d.trialPlans[plan.trial_id] = { ...plan, status: 'planned' };
    addMessage({ role: 'thoth', kind: 'trialPlan', trial: plan.trial_id });
  } catch (err) { addMessage({ role: 'note', text: `Couldn't plan the re-map: ${err.message}` }); }
  finally { state.busy -= 1; emit(); }
});

register('openHypothesis', () => openPanel('hypothesis', { fromUser: true }));
