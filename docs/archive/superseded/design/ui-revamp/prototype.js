// Thoth UI revamp prototype: static, no build. Everything here is demo data for the night-shift-nurses project.
const $ = (s, r = document) => r.querySelector(s), $$ = (s, r = document) => [...r.querySelectorAll(s)];
const shell = $('#shell');
const STAGES = [['explore', 'Explore'], ['thinkers', 'Thinkers'], ['hypothesis', 'Hypothesis'], ['check', 'Check'], ['review', 'Review'], ['design', 'Design'], ['draft', 'Draft']];
const TITLES = { explore: 'Ideas', thinkers: 'Thinkers', hypothesis: 'Hypothesis', check: 'The trial', review: 'Review', design: 'Design', draft: 'Proposal' };
const OFFER = { check: true };
const store = { get: k => { try { return localStorage.getItem(k); } catch (_) { return null; } }, set: (k, v) => { try { localStorage.setItem(k, v); } catch (_) {} } };

// Moon phase for stage i of n (new moon to full moon), same idea as the shipping app.
function moon(i, n) {
  const f = i / (n - 1), cx = 10, cy = 10, r = 8.2;
  let lit = '';
  if (f > 0) {
    const k = Math.cos(f * Math.PI), rx = Math.abs(k) * r, sweep = k > 0 ? 0 : 1;
    lit = f >= 1 ? `<circle cx="${cx}" cy="${cy}" r="${r}" fill="currentColor"/>` : `<path d="M${cx} ${cy - r}A${r} ${r} 0 0 1 ${cx} ${cy + r}A${rx.toFixed(2)} ${r} 0 0 ${sweep} ${cx} ${cy - r}Z" fill="currentColor"/>`;
  }
  return `<svg viewBox="0 0 20 20" aria-hidden="true"><circle cx="${cx}" cy="${cy}" r="${r}" fill="none" stroke="currentColor" stroke-width="1.3"/>${lit}</svg>`;
}

let stage = 'check';
function go(id, opts = {}) {
  stage = id; shell.dataset.stage = id;
  if (shell.dataset.mode === 'chat' && !opts.keepMode) setMode('split');
  $('#journey').innerHTML = STAGES.map(([sid, label], i) => {
    const cur = sid === id, done = i < STAGES.findIndex(s => s[0] === id);
    return `<li class="${cur ? 'current' : done ? 'done' : ''}"><button class="step" data-stage="${sid}" ${cur ? 'aria-current="step"' : ''}>${moon(i, STAGES.length)}<span class="lbl">${label}</span>${OFFER[sid] && !cur ? '<i class="offer" title="Thoth has a suggestion here"></i>' : ''}</button></li>`;
  }).join('');
  $$('.panel').forEach(p => p.classList.toggle('on', p.dataset.panel === id));
  $('#folioTitle').textContent = TITLES[id];
  $('#folioScroll').scrollTop = 0; closeDrawer();
  if (id === 'check') animateMatrix();
}

function setMode(m) {
  shell.dataset.mode = m; store.set('proto.mode', m);
  $$('.seg button').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.mode === m)));
  $$('.tabbar button').forEach(b => b.setAttribute('aria-current', String(b.dataset.mode === m || (m === 'folio' && b.dataset.mode === 'split'))));
}

// ---------- Matrix ----------
const W = [
  ['W3', 'The role of burnout on nurses’ intention to leave the profession: the role of work shifts', '2025 · cross-sectional · n 229', 'abstract', [0, 0, 1, 0], .25],
  ['W15', 'Effects of shift work on sleep quality and mental health of nurses', '2025 · narrative review', 'full', [0, 0, 1, 0], .3],
  ['W10', 'Psychological flexibility and night shifts on mental health in nurses', '2024 · cross-sectional · n 422', 'abstract', [0, 0, 0, 0], .25, 'nul'],
  ['W9', 'Circadian type determines working ability (evening-types, mediated by insufficient sleep)', '2022 · cross-sectional · n 13,114', 'abstract', [0, 0, 0, 0], .25],
  ['W1', 'Circadian misalignment increases mood vulnerability in simulated shift work', '2020', 'full', [0, 0, 0, 0], .3],
  ['W2', 'Health challenges and fatigue among female night-shift nurses', '2026 · cross-sectional', 'full', [0, 0, 0, 0], .3],
  ['W4', 'Sleep, circadian rhythm and body weight: parallel developments', '2016 · narrative review', 'full', [0, 0, 0, 0], .3],
  ['W5', 'Assessment of night-shift effects on nurses’ health and work', '2025', 'full', [0, 0, 0, 0], .3],
  ['W6', 'Sleep intervention for NHS shift workers: noise-masking earbuds', '2026 · pilot', 'abstract', [0, 0, 0, 0], .17],
  ['W7', 'Shift work and circadian dysregulation of reproduction', '2013 · narrative review', 'full', [0, 0, 0, 0], .3],
  ['W8', 'Scale to measure emotional load in nurses during night shifts', '2025', 'full', [0, 0, 0, 0], .3],
  ['W11', 'Endogenous metabolomic responses in circadian-disrupted night-shift workers', '2026 · scoping review', 'full', [0, 0, 0, 0], .3],
  ['W12', 'Shift work: health, performance and safety, and countermeasures', '2012 · narrative review', 'abstract', [0, 0, 0, 0], .17],
  ['W13', 'The rhythm of decline: circadian disruption in neurodegeneration', '2025 · narrative review', 'abstract', [0, 0, 0, 0], .17],
  ['W14', 'Health-related quality of life for nurses at day and night shift', '2022', 'full', [0, 0, 0, 0], .3],
];
const CLAIMS = ['Shift → misalignment', 'Misalignment → exhaustion', 'Night nurses more exhausted', 'Misalignment mediates'];
const GLYPH = { 1: ['conv', '<svg viewBox="0 0 16 16"><path d="M3 12l5-8 5 8z"/></svg>', 'convergent'], '-1': ['div', '<svg viewBox="0 0 16 16"><path d="M3 4l5 8 5-8z"/></svg>', 'divergent'], nul: ['nul', '<svg viewBox="0 0 16 16"><circle cx="8" cy="8" r="4"/></svg>', 'null result'] };
function cell(w, i) {
  const v = w[4][i], isNull = w[6] === 'nul' && i === 2;
  const g = isNull ? GLYPH.nul : GLYPH[v];
  return g ? `<span class="cell ${g[0]}" title="${g[2]}">${g[1]}<span class="sr">${g[2]}</span></span>` : `<span class="cell none" aria-label="not addressed">·</span>`;
}
function renderMatrix() {
  const signal = w => w[4].some(Boolean) || w[6];
  const loud = W.filter(signal), silent = W.filter(w => !signal(w));
  const row = (w, cls = '') => `<tr class="${cls}" tabindex="0" data-w="${w[0]}"><th scope="row"><div class="wt"><span class="id">${w[0]}</span><span class="t">${w[1]}</span><span class="m">${w[2]} · <span class="tag ${w[3] === 'full' ? 'ok' : 'na'}" style="padding:1px 8px">${w[3] === 'full' ? 'full text' : 'abstract only'}</span></span></div></th>${[0, 1, 2, 3].map(i => `<td class="td">${cell(w, i)}</td>`).join('')}<td class="td"><div class="w-bar"><i style="width:${w[5] * 300}%"></i></div><span class="num">${w[5].toFixed(2)}</span></td></tr>`;
  $('#matrix').innerHTML = `<thead><tr><th scope="col">Witness</th>${CLAIMS.map((c, i) => `<th scope="col">${i + 1}<span class="sc-name">${c}</span></th>`).join('')}<th scope="col">Weight</th></tr></thead><tbody>
    ${loud.map(w => row(w)).join('')}
    <tr class="group"><td colspan="6"><span id="silentLabel">${silent.length} papers say nothing about any of your claims.</span> <button type="button" id="toggleSilent">Show them</button></td></tr>
    ${silent.map(w => row(w, 'silent hide')).join('')}</tbody>`;
  $('#toggleSilent').onclick = e => { const show = e.target.textContent === 'Show them'; $$('tr.silent').forEach(r => r.classList.toggle('hide', !show)); e.target.textContent = show ? 'Hide them' : 'Show them'; };
}
function animateMatrix() {
  if (matchMedia('(prefers-reduced-motion: reduce)').matches) return;
  $$('#matrix .cell, #matrix .w-bar').forEach((c, i) => c.animate([{ opacity: 0, transform: 'scale(.6)' }, { opacity: 1, transform: 'none' }], { duration: 420, delay: 250 + (i % 5) * 60 + Math.floor(i / 5) * 18, easing: 'cubic-bezier(.2,.7,.2,1)', fill: 'backwards' }));
}
$('#onlySignal').addEventListener('change', e => { $$('tr.silent').forEach(r => r.classList.toggle('hide', e.target.checked)); const b = $('#toggleSilent'); if (b) b.textContent = e.target.checked ? 'Show them' : 'Hide them'; });

// ---------- Witness drawer (replaces window.prompt) ----------
function openDrawer(id) {
  const w = W.find(x => x[0] === id); if (!w) return;
  $('#drawerIn').innerHTML = `<div style="display:flex;justify-content:space-between;align-items:center"><span class="eyebrow">Witness ${w[0]}</span><button class="ibtn" id="closeDrawer" aria-label="Close witness detail"><svg class="icon"><use href="#i-x"/></svg></button></div>
    <h3>${w[1]}</h3><span class="tag ${w[3] === 'full' ? 'ok' : 'na'}">${w[3] === 'full' ? 'Read in full text' : 'Abstract only: silence is not evidence'}</span>
    <dl><dt>Design</dt><dd>${w[2]}</dd><dt>Weight</dt><dd class="num">${w[5].toFixed(2)} <span style="color:var(--ink-3)">(design strength × amount read)</span></dd>
    <dt>Against claim 3</dt><dd>${w[4][2] ? 'Convergent. Nurses on nights score higher on the exhaustion subscale.' : 'Does not address it.'}</dd><dt>Locator</dt><dd>${w[3] === 'full' ? 'p. 6, Results, ¶2' : 'Not available (abstract only)'}</dd></dl>
    <label class="lbl" for="isay">Your own reading <span style="font-weight:400;color:var(--ink-3)">(“I say”)</span></label>
    <textarea class="field" id="isay" placeholder="How do you read this paper against your hypothesis?"></textarea>
    <div style="display:flex;gap:8px;margin-top:14px"><button class="btn primary" id="saveSay">Save my reading</button><button class="btn ghost">Open source</button></div>`;
  $('#drawer').dataset.open = 'true';
  $('#closeDrawer').onclick = closeDrawer; $('#saveSay').onclick = () => { toast('Saved. Your reading will travel with this witness.'); closeDrawer(); };
  $('#isay').focus({ preventScroll: true });
}
function closeDrawer() { const d = $('#drawer'); if (d) d.dataset.open = 'false'; }
document.addEventListener('click', e => { const tr = e.target.closest('#matrix tbody tr[data-w]'); if (tr) openDrawer(tr.dataset.w); });
document.addEventListener('keydown', e => { if ((e.key === 'Enter' || e.key === ' ') && e.target.matches('#matrix tr[data-w]')) { e.preventDefault(); openDrawer(e.target.dataset.w); } if (e.key === 'Escape') { closeDrawer(); $$('.scrim').forEach(s => s.classList.remove('on')); } });

// ---------- Roster ----------
const THINKERS = [['Aristotle', 'A', 'What is the thing?'], ['Ibn al-Haytham', 'I', 'Doubt, then test'], ['David Hume', 'H', 'What did you observe?', 'hume'], ['Charles Darwin', 'D', 'Patient accumulation'], ['Florence Nightingale', 'N', 'Compare like with like', 'night'], ['Max Weber', 'W', 'Meaning and many causes'], ['Karl Popper', 'P', 'What would show you wrong?', 'popper'], ['Thomas Kuhn', 'K', 'Which paradigm?'], ['Herbert Simon', 'S', 'Real people, limited information'], ['Elinor Ostrom', 'O', 'Field evidence first']];
$('#roster').innerHTML = THINKERS.map(t => `<button class="th" aria-pressed="${['popper', 'hume', 'night'].includes(t[3])}"><span class="who ${t[3] ? 't-' + t[3] : ''}">${t[1]}</span><b>${t[0]}</b><small>${t[2]}</small></button>`).join('');
$('#roster').addEventListener('click', e => { const b = e.target.closest('.th'); if (b) b.setAttribute('aria-pressed', String(b.getAttribute('aria-pressed') !== 'true')); });

// ---------- Choose design sheet (replaces window.prompt) ----------
let chosen = '';
document.addEventListener('click', e => { const c = e.target.closest('[data-choose]'); if (c) { chosen = c.dataset.choose; $('#chooseT').textContent = `Choose “${chosen}”`; $('#chooseSub').textContent = 'It becomes the Design section of your research file and the basis for the proposal. You can change your mind later; earlier choices are kept.'; $('#choose').classList.add('on'); $('#chooseNotes').focus(); } });
$('#chooseGo').onclick = () => { $('#choose').classList.remove('on'); toast(`“${chosen}” is now your design. The proposal draft has started.`); };
$$('[data-close]').forEach(b => b.onclick = () => $('#choose').classList.remove('on'));
$$('.scrim').forEach(s => s.addEventListener('mousedown', e => { if (e.target === s) s.classList.remove('on'); }));

// ---------- Palette ----------
const CMDS = [...STAGES.map(([id, l]) => [`Go to ${l}`, 'Stage', () => go(id)]), ['Put the hypothesis on trial', 'Action', () => go('check')], ['Ask Karl Popper to critique', 'Thinker', () => go('thinkers')], ['Switch light / dark', 'View', () => toggleTheme()], ['Give the file the whole screen', 'View', () => setMode('folio')]];
function openPalette() { $('#palette').classList.add('on'); $('#pIn').value = ''; renderPalette(''); $('#pIn').focus(); }
function renderPalette(q) { const items = CMDS.filter(c => c[0].toLowerCase().includes(q.toLowerCase())); $('#pList').innerHTML = items.map((c, i) => `<li><button class="${i === 0 ? 'sel' : ''}" data-i="${CMDS.indexOf(c)}"><span>${c[0]}</span><span class="kbd">${c[1]}</span></button></li>`).join('') || '<li style="padding:14px;color:var(--ink-3)">Nothing matches.</li>'; }
$('#pIn').addEventListener('input', e => renderPalette(e.target.value));
$('#pIn').addEventListener('keydown', e => { if (e.key === 'Enter') { const b = $('#pList .sel') || $('#pList button'); b && b.click(); } });
$('#pList').addEventListener('click', e => { const b = e.target.closest('button'); if (b) { $('#palette').classList.remove('on'); CMDS[b.dataset.i][2](); } });
$('#cmdkBtn').onclick = openPalette;
document.addEventListener('keydown', e => { if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); openPalette(); } });

// ---------- Misc ----------
function toast(t) { const el = $('#toast'); el.textContent = t; el.classList.add('on'); clearTimeout(toast.t); toast.t = setTimeout(() => el.classList.remove('on'), 3200); }
function toggleTheme(force) { const dark = force ? force === 'dark' : document.documentElement.dataset.theme !== 'dark'; document.documentElement.dataset.theme = dark ? 'dark' : 'light'; store.set('proto.theme', dark ? 'dark' : 'light'); }
$('#theme').onclick = () => toggleTheme();
$$('.seg button, .tabbar button').forEach(b => b.addEventListener('click', () => setMode(b.dataset.mode)));
document.addEventListener('click', e => {
  const s = e.target.closest('[data-stage]'); if (s) go(s.dataset.stage);
  const a = e.target.closest('[data-act]'); if (a) toast({ adjacent: 'Estimate: about 6 minutes, free tier. Nothing runs until you approve.', falsifier: 'Popper is drafting a falsifier with you…', weigh: 'Weighing again with your readings included.', reply: 'Reply goes to this thinker only.' }[a.dataset.act] || 'Done.');
  if (e.target.closest('#chat') && shell.dataset.mode === 'folio') setMode('split');
});
$('#pin').addEventListener('click', e => { if (!e.target.closest('button')) { const p = $('#pin'); p.dataset.open = p.dataset.open !== 'true'; } });
$('#share').onclick = () => toast('Export asks first: a PDF is only made with your approval.');
$('#input').addEventListener('input', e => { e.target.style.height = 'auto'; e.target.style.height = e.target.scrollHeight + 'px'; });
$('#composer').addEventListener('submit', e => { e.preventDefault(); const v = $('#input').value.trim(); if (!v) return; const m = document.createElement('div'); m.className = 'msg user'; m.innerHTML = `<div class="prose"></div>`; m.firstChild.textContent = v; $('#msgs').appendChild(m); $('#input').value = ''; $('#msgs').scrollTop = 1e6; });

// boot: ?mode=folio&stage=design&theme=dark for deep links / screenshots
const q = new URLSearchParams(location.search);
renderMatrix();
const savedTheme = q.get('theme') || store.get('proto.theme') || (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
toggleTheme(savedTheme);
setMode(q.get('mode') || (innerWidth < 761 ? 'chat' : 'split'));
go(q.get('stage') || 'check', { keepMode: true });
if (q.get('drawer')) openDrawer(q.get('drawer'));
