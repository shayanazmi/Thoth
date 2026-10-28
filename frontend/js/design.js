// Study design (docs/features/07): resources → 2-3 candidate designs built on the trial's lessons →
// choose one (with your notes) → it becomes the Design section; thinkers can critique it.
import { getJSON, postJSON } from './api.js';
import { state, project, emit, addMessage, currentHypothesis } from './store.js';
import { register, openPanel } from './chat.js';
import { PANELS } from './workspace.js';
import { esc } from './util.js';
import { askText } from './ui.js';

const RESOURCES = [
  ['time', 'Time available', 'e.g. 3 months, part-time'],
  ['population_access', 'Who you can reach', 'e.g. nurses at one hospital, ~60 on nights'],
  ['budget', 'Budget', 'e.g. none / £500'],
  ['skills', 'Skills', 'e.g. basic stats in SPSS, no qualitative training'],
  ['ethics_route', 'Ethics route', 'e.g. university student ethics committee'],
  ['tools', 'Tools and instruments', 'e.g. survey software, no actigraphs'],
];
const FEAS = { feasible: 'Feasible', feasible_with_changes: 'Feasible with changes', not_feasible: 'Not feasible' };
const VALIDITY = { statistical: 'Statistical conclusion', internal: 'Internal', construct: 'Construct', external: 'External' };

// The copy saved in localStorage is only a cache: fetch the server's once per page load (it changes from the
// proposal panel too, e.g. "Revise the design").
const fetchedThisPage = new Set();
let loadingDesign = false;
async function ensureLoaded(d, force = false) {
  if (!state.projectId || loadingDesign || (!force && d.design && fetchedThisPage.has(state.projectId))) return;
  fetchedThisPage.add(state.projectId);
  loadingDesign = true;
  try { d.design = { ...(d.design || {}), ...(await getJSON(`/api/design?project_id=${encodeURIComponent(state.projectId)}`)) }; emit(); }
  catch (_) { d.design = d.design || { resources: null, candidates: null, chosen: null }; }
  finally { loadingDesign = false; }
}

const unsourcedList = (u) => (u?.length ? `<div class="guard">Unsourced: ${u.map((x) => `“${esc(x)}”`).join(' · ')} <span class="faint">(cite a trial witness or mark it as an assumption)</span></div>` : '');

function resourcesForm(r) {
  return `<form class="design-resources" data-form="resources">
    <p class="muted">Tell Thoth what you actually have. Designs are checked against this; it is remembered for this project.</p>
    ${RESOURCES.map(([k, label, ph]) => `<label><span>${label}</span><input name="${k}" value="${esc(r?.[k] || '')}" placeholder="${esc(ph)}"></label>`).join('')}
    <div class="chips"><button class="chip primary" type="submit">Propose designs</button><span class="faint">one model call · about 1-2 minutes</span></div>
  </form>`;
}

function designCard(dz, i, rec, chosenName) {
  const isChosen = chosenName === dz.name;
  const threats = Object.keys(VALIDITY).map((v) => [v, (dz.threats || []).filter((t) => t.validity === v)]).filter(([, ts]) => ts.length);
  return `<details class="design-card${dz.name === rec ? ' recommended' : ''}"${dz.name === rec ? ' open' : ''}>
    <summary><b>${esc(dz.name)}</b>${dz.name === rec ? '<span class="verdict v-supported_within_limits">recommended</span>' : ''}<span class="verdict v-${dz.feasibility === 'feasible' ? 'supported_within_limits' : dz.feasibility === 'not_feasible' ? 'contradicted' : 'contested'}">${esc(FEAS[dz.feasibility] || dz.feasibility)}</span></summary>
    ${dz.revision_of ? `<div class="rev-box"><b>Revision of “${esc(dz.revision_of)}”</b> answering the peer Reviewer${dz.addresses?.length ? ` (${esc(dz.addresses.join(', '))})` : ''}
      ${(dz.changes || []).length ? `<ul class="list">${dz.changes.map((c) => `<li><span class="rk">${esc(c.finding_id)}</span>${esc(c.change)}</li>`).join('')}</ul>` : ''}
      ${(dz.unresolved || []).length ? `<div class="guard">Still open: ${dz.unresolved.map((u) => `${esc(u.finding_id)}: ${esc(u.why)}`).join(' · ')}</div>` : ''}</div>` : ''}
    <p>${esc(dz.summary)}</p>
    ${unsourcedList(dz.unsourced)}
    <div class="cases"><div><b>Can conclude</b><p>${esc(dz.can_conclude)}</p></div><div><b>Cannot conclude</b><p>${esc(dz.cannot_conclude)}</p></div></div>
    ${dz.tests_subclaims?.length ? `<div class="faint">Tests sub-claims ${esc(dz.tests_subclaims.join(', '))}</div>` : ''}
    <h4>Measures</h4><ul class="list">${(dz.measures || []).map((m) => `<li><b>${esc(m.construct)}</b>: ${esc(m.instrument)} <span class="prov">${m.source_witness_id === 'new' ? 'new · needs validation' : `${m.source_match === 'related' ? 'related to' : 'used by'} ${esc(m.source_witness_id)} · ${esc((m.source_title || '').slice(0, 60))}`}</span>${m.note && m.source_witness_id !== 'new' ? ` <span class="faint">${esc(m.note)}</span>` : ''}</li>`).join('')}</ul>
    <h4>Sampling</h4><p>${esc(dz.sampling)}</p><p class="faint">Sample size: ${esc(dz.sample_size)}</p>
    ${threats.length ? `<h4>Threats to validity</h4>${threats.map(([v, ts]) => `<div class="threat"><span class="rk">${VALIDITY[v]}</span><ul>${ts.map((t) => `<li>${esc(t.threat)} <span class="faint">→ ${esc(t.mitigation)}</span></li>`).join('')}</ul></div>`).join('')}` : ''}
    ${dz.blockers?.length ? `<h4>Against your resources</h4><ul class="list">${dz.blockers.map((b) => `<li>${esc(b)}</li>`).join('')}</ul>` : ''}
    ${dz.changes_to_make_feasible?.length ? `<div class="faint">Would become feasible if: ${esc(dz.changes_to_make_feasible.join('; '))}</div>` : ''}
    <div class="chips">${isChosen ? '<span class="faint">This is your design.</span>' : `<button class="chip primary" data-act="chooseDesign" data-arg="${i}">Choose this design</button>`}</div>
  </details>`;
}

function chosenBlock(c) {
  if (!c) return '';
  return `<div class="status-banner full"><b>Your design (v${c.version}): ${esc(c.name)}</b><br>
    <span class="faint">${c.author === 'user' ? 'Chosen with your notes' : 'Chosen as proposed'} · ${esc(c.can_conclude)}</span>
    ${c.researcher_notes ? `<p>${esc(c.researcher_notes)}</p>` : ''}
    ${unsourcedList(c.unsourced)}
    <div class="chips"><button class="chip" data-act="critiqueDesign">Ask thinkers to critique it</button><button class="chip" data-act="startProposal">Write the proposal</button></div></div>`;
}

function designPanel(d) {
  ensureLoaded(d);
  const hyp = currentHypothesis(d)?.text;
  if (!hyp) return `<h2>Study design</h2><p class="muted">Pin a hypothesis first. A design is chosen to test a specific claim.</p>`;
  const z = d.design || {};
  const c = z.candidates;
  return `<h2>Study design</h2>
    <p class="muted">${esc(hyp)}</p>
    ${chosenBlock(z.chosen)}
    ${z.proposing ? '<div class="status-banner"><b>Designing…</b><br><span class="faint">Reading your trial and resources.</span></div>' : ''}
    ${c?.designs?.length ? `${c.lessons_used ? '<p class="faint">Built on your latest trial: its witnesses, measures, boundary conditions and gaps.</p>' : '<p class="guard">No completed trial yet, so these designs are not grounded in the literature. Run a trial first for better designs.</p>'}
      ${(c.guardrail_notes || []).map((n) => `<div class="guard">${esc(n)}</div>`).join('')}
      ${c.designs.map((dz, i) => designCard(dz, i, c.recommended, z.chosen?.name)).join('')}
      ${c.why ? `<p><b>Why ${esc(c.recommended)}:</b> ${esc(c.why)}</p>` : ''}${c.what_others_add ? `<p class="faint">${esc(c.what_others_add)}</p>` : ''}
      <details><summary class="faint">Change resources and propose again</summary>${resourcesForm(z.resources)}</details>`
    : resourcesForm(z.resources)}`;
}
PANELS.design = designPanel;

document.addEventListener('submit', async (e) => {
  const form = e.target.closest('form[data-form="resources"]');
  if (!form) return;
  e.preventDefault();
  const d = project();
  const resources = Object.fromEntries(RESOURCES.map(([k]) => [k, form[k].value.trim()]));
  if (!Object.values(resources).some(Boolean)) return addMessage({ role: 'note', text: 'Fill in at least one resource (time, access, budget or skills).' });
  d.design = { ...(d.design || {}), resources, proposing: true };
  emit();
  state.busy += 1; emit();
  try {
    await postJSON('/api/design/resources', { project_id: state.projectId, resources });
    const out = await postJSON('/api/design/propose', { project_id: state.projectId, hypothesis: currentHypothesis(d).text, resources });
    d.design.candidates = out.designs?.length ? out : d.design.candidates;
    if (!out.designs?.length) addMessage({ role: 'note', text: "The Designer couldn't be reached; no designs were made up in its place." });
    else addMessage({ role: 'thoth', text: `**${out.designs.length} candidate designs are ready.** I'd start with *${out.recommended}*: ${out.why || ''}`, chips: [{ label: 'Compare them', act: 'panel', arg: 'design', primary: true }] });
  } catch (err) {
    addMessage({ role: 'note', text: `Couldn't propose designs: ${err.message}` });
  } finally { d.design.proposing = false; state.busy -= 1; emit(); }
});

register('chooseDesign', async (i) => {
  const d = project();
  const dz = d.design?.candidates?.designs?.[+i];
  if (!dz) return;
  const notes = await askText({ title: `Choose “${dz.name}”`, body: 'It becomes the Design section of your research file. Add your own changes or notes if you like.', label: 'Changes or notes (optional)', confirm: 'Use this design', cancel: 'Not yet', placeholder: 'e.g. Restrict to two hospitals; add a sleep diary at every wave.' });
  if (notes === null) return;
  try {
    d.design.chosen = await postJSON('/api/design/choose', { project_id: state.projectId, index: +i, notes });
    addMessage({ role: 'thoth', text: `Design chosen: **${dz.name}** (v${d.design.chosen.version}). It's now the Design section of your research file.`, chips: [{ label: 'Ask thinkers to critique it', act: 'critiqueDesign', primary: true }, { label: 'Write the proposal', act: 'startProposal' }] });
  } catch (err) { addMessage({ role: 'note', text: `Couldn't save the choice: ${err.message}` }); }
  emit();
});

register('critiqueDesign', async () => {
  const d = project();
  const c = d.design?.chosen;
  if (!c) return;
  const text = `Hypothesis: ${currentHypothesis(d)?.text}\n\nDesign: ${c.name} (${c.design_type}). ${c.summary}\nCan conclude: ${c.can_conclude}\nCannot conclude: ${c.cannot_conclude}\n`
    + `Measures: ${(c.measures || []).map((m) => `${m.construct}: ${m.instrument}`).join('; ')}\nSampling: ${c.sampling}. Sample size: ${c.sample_size}\n`
    + `Threats: ${(c.threats || []).map((t) => `${t.validity}: ${t.threat} (mitigation: ${t.mitigation})`).join('; ')}${c.researcher_notes ? `\nResearcher's notes: ${c.researcher_notes}` : ''}`;
  addMessage({ role: 'note', text: 'Three thinkers are critiquing your design, each on their own…' });
  state.busy += 1; emit();
  try {
    const res = await postJSON('/api/thinkers/review', { project_id: state.projectId, artifact: 'study design', text });
    const key = `rv_${Date.now()}`;
    d.reviews = d.reviews || {};
    d.reviews[key] = res.reviews || [];
    addMessage({ role: 'thoth', kind: 'reviews', reviews: key });
  } catch (err) { addMessage({ role: 'note', text: `Couldn't gather critiques: ${err.message}` }); }
  finally { state.busy -= 1; emit(); }
});

register('openDesign', () => openPanel('design', { fromUser: true }));

// A design-level FATAL from the proposal's peer Reviewer: ask the Designer for a revision that answers it.
register('reviseDesign', async () => {
  const d = project();
  openPanel('design', { fromUser: true });
  addMessage({ role: 'note', text: "Asking the Designer to revise your design to answer the peer Reviewer's design-level problem…" });
  state.busy += 1; emit();
  try {
    const out = await postJSON('/api/design/revise', { project_id: state.projectId });
    if (out.degraded) { addMessage({ role: 'note', text: out.message }); return; }
    await ensureLoaded(d, true);
    const rev = out.designs[0];
    addMessage({ role: 'thoth', text: `**A revised design is ready: ${rev.name}.** ${(rev.changes || []).map((c) => `${c.finding_id}: ${c.change}`).join(' ')}${rev.unresolved?.length ? ` Still open: ${rev.unresolved.map((u) => u.why).join(' ')}` : ''} Nothing changes until you choose it.`,
      chips: [{ label: 'Compare it', act: 'panel', arg: 'design', primary: true }] });
  } catch (err) { addMessage({ role: 'note', text: `Couldn't revise the design: ${err.message}` }); }
  finally { state.busy -= 1; emit(); }
});
