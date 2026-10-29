// Autopilot / Co-pilot (docs/features/02): one switch per project, with per-step overrides. Either way, heavy
// runs still ask once, up front, with an estimate. The mode lives on the server (a versioned notebook entry).
import { getJSON } from './api.js';
import { state, subscribe } from './store.js';
import { register } from './chat.js';
import { esc } from './util.js';
import { toast } from './ui.js';

export const MODE = new Map(); // project id → {mode, step_overrides, effective}; module memory, not localStorage
const loading = new Set();
const STEPS = [
  ['subclaims', 'Sub-claims', 'Co-pilot: proposed for you to edit and approve. Autopilot: set by Thoth and shown; edit them later.'],
  ['screening', 'Screening', 'Co-pilot: you confirm each include / exclude. Autopilot: the Screener decides; uncertain ones are queued for you.'],
  ['proposal', 'Proposal sections', 'Co-pilot: one section at a time, each on your approval. Autopilot: all sections, then the review.'],
];
const LABEL = { copilot: 'Co-pilot', autopilot: 'Autopilot' };
const live = (id) => id && !String(id).startsWith('local_');

export function modeOf(step) {
  return MODE.get(state.projectId)?.effective?.[step] || 'copilot';
}

async function load(id) {
  if (!live(id) || loading.has(id) || MODE.has(id)) return;
  loading.add(id);
  try { MODE.set(id, await getJSON(`/api/projects/${encodeURIComponent(id)}/mode`)); paint(); } catch (_) {}
  finally { loading.delete(id); }
}

function paint() {
  let btn = document.getElementById('modeBtn');
  if (!btn) {
    const anchor = document.getElementById('themeToggle');
    if (!anchor) return;
    btn = document.createElement('button');
    btn.id = 'modeBtn';
    btn.className = 'mode-btn';
    btn.dataset.act = 'openMode';
    anchor.before(btn);
  }
  const m = MODE.get(state.projectId);
  btn.hidden = !live(state.projectId);
  const mixed = m && Object.keys(m.step_overrides || {}).length;
  btn.textContent = m ? `${LABEL[m.mode]}${mixed ? ' · mixed' : ''}` : '…';
  btn.title = 'How Thoth works on this project: Co-pilot asks at each step, Autopilot carries on. Heavy runs always ask first.';
  btn.setAttribute('aria-label', `Mode: ${btn.textContent}. Change`);
}

subscribe(() => { load(state.projectId); paint(); });

register('openMode', () => {
  const m = MODE.get(state.projectId);
  if (!m) return;
  const scrim = document.createElement('div');
  scrim.className = 'scrim';
  const radio = (name, value, checked) => `<input type="radio" name="${name}" value="${value}" ${checked ? 'checked' : ''}>`;
  scrim.innerHTML = `<form class="dialog mode-dialog" role="dialog" aria-modal="true" aria-labelledby="modeTitle">
    <h3 id="modeTitle">How should Thoth work on this project?</h3>
    <div class="mode-main">
      <label>${radio('mode', 'copilot', m.mode === 'copilot')} <b>Co-pilot</b><span class="faint"> Thoth proposes; you approve each step.</span></label>
      <label>${radio('mode', 'autopilot', m.mode === 'autopilot')} <b>Autopilot</b><span class="faint"> Thoth carries on and shows its work; you can change anything after.</span></label>
    </div>
    <p class="faint">Either way, a trial, a systematic review or a proposal is never started without your approval and an estimate.</p>
    <details ${Object.keys(m.step_overrides).length ? 'open' : ''}><summary>Per step</summary>
      ${STEPS.map(([k, label, what]) => `<div class="mode-step"><span><b>${label}</b><br><span class="faint">${esc(what)}</span></span>
        <select name="${k}" aria-label="${label}: Co-pilot, Autopilot or the project's mode"><option value="">Same as the project</option>${['copilot', 'autopilot'].map((v) => `<option value="${v}" ${m.step_overrides[k] === v ? 'selected' : ''}>${LABEL[v]}</option>`).join('')}</select></div>`).join('')}
    </details>
    <div class="dialog-row"><button type="button" class="chip" data-cancel>Cancel</button><button type="submit" class="chip primary">Save</button></div></form>`;
  const close = () => scrim.remove();
  scrim.querySelector('[data-cancel]').addEventListener('click', close);
  scrim.addEventListener('mousedown', (e) => { if (e.target === scrim) close(); });
  scrim.addEventListener('keydown', (e) => { if (e.key === 'Escape') close(); });
  scrim.querySelector('form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const f = e.target;
    const overrides = Object.fromEntries(STEPS.map(([k]) => [k, f[k].value]).filter(([, v]) => v));
    try {
      const res = await fetch(`${window.THOTH_API_BASE || ''}/api/projects/${encodeURIComponent(state.projectId)}/mode`, {
        method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ mode: f.mode.value, step_overrides: overrides }),
      });
      if (!res.ok) throw new Error((await res.json()).detail || res.status);
      MODE.set(state.projectId, await res.json());
      paint();
      toast(`Mode: ${LABEL[f.mode.value]}${Object.keys(overrides).length ? ', with per-step changes' : ''}.`);
      close();
    } catch (err) { toast(`Couldn't save the mode: ${err.message}`); }
  });
  document.body.appendChild(scrim);
  scrim.querySelector('input[name="mode"]:checked')?.focus();
});
