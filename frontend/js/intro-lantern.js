// Intro "the lantern": Thoth is a stone bust in a dark hall and the pointer is the only light. The user types a
// question; its letters lift off the line, fly into the moon disc on the crown, the disc flares, and the screen
// irises open from the disc into the app with that question already asked.
// Kept as ?intro=lantern; the default intro is intro-cinema.js (the ink-fluid intro is archived in docs/archive/legacy_code/intro_v2/).
const SEEN = 'thoth.intro.seen';
const SAMPLES = [
  'Why do people trust a confident wrong answer?',
  'Why do some memories fade while others stay sharp?',
  'Why do cities feel faster at night?',
];
let running = false;

export function maybePlayIntro(onDone) {
  const params = new URLSearchParams(location.search);
  let seen = false;
  try { seen = sessionStorage.getItem(SEEN) === '1'; } catch (_) {}
  if (!params.has('intro') && (seen || matchMedia('(prefers-reduced-motion: reduce)').matches)) return;
  playIntro(onDone);
}

export function playIntro(onDone = () => {}) {
  if (running) return;
  running = true;
  const el = document.getElementById('intro');
  el.hidden = false;
  el.className = 'intro lantern';
  el.style.removeProperty('--ix'); el.style.removeProperty('--iy');
  el.innerHTML = `<div class="lt-stage" id="ltStage"><img src="/assets/thoth_bust_1000.jpg" alt="" aria-hidden="true"><div class="lt-light" id="ltLight"></div><div class="lt-disc" id="ltDisc"></div></div>
    <form class="lt-ask" id="ltForm"><p class="lt-prompt" id="ltPrompt">What's been on your mind?</p>
      <div class="lt-field"><input id="ltInput" autocomplete="off" maxlength="120" aria-label="Your question" placeholder="${SAMPLES[0]}"><button class="lt-go" aria-label="Begin"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12h14M13 6l6 6-6 6"/></svg></button></div>
      <p class="lt-hint">Move the light. Type a question and press Enter.</p></form>
    <button class="intro-skip" id="ltSkip">Skip</button>`;
  const stage = el.querySelector('#ltStage'), input = el.querySelector('#ltInput');
  const timers = [];
  const later = (ms, fn) => timers.push(setTimeout(fn, ms));
  let done = false;

  const onMove = (e) => {
    const r = stage.getBoundingClientRect();
    stage.style.setProperty('--lx', `${((e.clientX - r.left) / r.width) * 100}%`);
    stage.style.setProperty('--ly', `${((e.clientY - r.top) / r.height) * 100}%`);
  };
  const onKey = (e) => { if (e.key === 'Escape') { e.preventDefault(); close(null, false, 0); } };
  document.addEventListener('pointermove', onMove, { passive: true });
  document.addEventListener('keydown', onKey, true);

  const cleanup = () => {
    timers.forEach(clearTimeout);
    document.removeEventListener('pointermove', onMove);
    document.removeEventListener('keydown', onKey, true);
    document.querySelectorAll('.lt-mote').forEach((m) => m.remove());
    running = false;
    el.hidden = true; el.innerHTML = ''; el.className = 'intro';
  };
  function close(q, isSample, delay) {
    if (done) return; done = true;
    try { sessionStorage.setItem(SEEN, '1'); } catch (_) {}
    if (!delay) { el.classList.add('leaving'); later(500, () => { cleanup(); onDone(q, isSample); }); return; }
    later(delay, () => { cleanup(); onDone(q, isSample); });
  }

  const launch = (text, isSample) => {
    if (done) return;
    if (matchMedia('(prefers-reduced-motion: reduce)').matches) { close(text, isSample, 0); return; }
    done = true;
    input.blur(); el.classList.add('typing');
    const r = input.getBoundingClientRect();
    const disc = el.querySelector('#ltDisc').getBoundingClientRect();
    const tx = disc.left + disc.width / 2, ty = disc.top + disc.height / 2;
    const chars = [...text].slice(0, 70), span = Math.min(r.width, 560), x0 = r.left + r.width / 2 - span / 2;
    chars.forEach((ch, i) => {
      if (ch === ' ') return;
      const m = document.createElement('span'); m.className = 'lt-mote'; m.textContent = ch; document.body.appendChild(m);
      const sx = x0 + (i / chars.length) * span, sy = r.top + r.height / 2 - 14;
      const mx = sx + (Math.random() - .5) * 140, my = sy - 120 - Math.random() * 120;
      m.animate([{ transform: `translate(${sx}px,${sy}px) scale(1)`, opacity: 1 }, { transform: `translate(${mx}px,${my}px) scale(.9)`, opacity: .9, offset: .45 }, { transform: `translate(${tx}px,${ty}px) scale(.2)`, opacity: 0 }],
        { duration: 1500 + Math.random() * 500, delay: i * 22, easing: 'cubic-bezier(.5,0,.3,1)', fill: 'forwards' }).onfinish = () => m.remove();
    });
    const total = 2000 + chars.length * 22;
    el.querySelector('#ltForm').classList.add('away');
    later(total - 500, () => el.classList.add('flare'));
    later(total, () => {
      el.style.setProperty('--ix', `${((disc.left + disc.width / 2) / innerWidth) * 100}%`);
      el.style.setProperty('--iy', `${((disc.top + disc.height / 2) / innerHeight) * 100}%`);
      el.classList.add('open');
    });
    later(total + 1500, () => { cleanup(); onDone(text, isSample); });
    try { sessionStorage.setItem(SEEN, '1'); } catch (_) {}
  };

  el.querySelector('#ltForm').addEventListener('submit', (e) => {
    e.preventDefault();
    const v = input.value.trim();
    if (v) launch(v, false);
  });
  el.querySelector('#ltSkip').addEventListener('click', () => close(null, false, 0));
  later(2600, () => input.focus({ preventScroll: true }));
  // Nobody typed: a sample question writes itself and is left in the home box to send.
  later(9000, () => {
    if (input.value || done) return;
    const t = SAMPLES[Math.floor(Math.random() * SAMPLES.length)];
    let i = 0;
    const typer = setInterval(() => { if (done || input.value && i === 0) return clearInterval(typer); input.value = t.slice(0, ++i); if (i >= t.length) { clearInterval(typer); later(900, () => launch(t, true)); } }, 55);
    timers.push(typer);
  });
}
