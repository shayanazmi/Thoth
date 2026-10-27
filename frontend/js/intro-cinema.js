// Intro "The Weighing of the Question" (~14 s, skippable at any moment).
//   0.0 s  darkness; gold dust drifts in and converges        4.3 s  the dust gives way to the bust, lit by a
//   1.6 s  the dust locks into the Ink-moon mark                     raking gold light that follows the pointer
//   6.4 s  three title cards                                  11 s   the ask: "What's been on your mind?"
// On Enter the letters fly into the moon on the crown, the dust follows, the disc flares, and the screen irises
// open into the app with that question already asked. Once per browser session; ?intro forces it; reduced
// motion goes straight to a still ask card. ?intro=lantern plays the previous intro.
import { markSVG } from './util.js';

const SEEN = 'thoth.intro.seen';
const SAMPLES = [
  'Why do people trust a confident wrong answer?',
  'Why do some memories fade while others stay sharp?',
  'Why do cities feel faster at night?',
];
const CARDS = ['Begin with a hunch.', 'Weigh it against what is known.', 'Write only what holds.'];
const reduced = () => matchMedia('(prefers-reduced-motion: reduce)').matches;

let running = false;

export function maybePlayIntro(onDone) {
  const params = new URLSearchParams(location.search);
  if (params.get('intro') === 'lantern') { import('./intro-lantern.js').then((m) => m.playIntro(onDone)); return; }
  let seen = false;
  try { seen = sessionStorage.getItem(SEEN) === '1'; } catch (_) {}
  if (!params.has('intro') && seen) return;
  playIntro(onDone);
}

export function playIntro(onDone = () => {}) {
  if (running) return;
  running = true;
  const still = reduced();
  const el = document.getElementById('intro');
  el.hidden = false;
  el.className = `intro cinema${still ? ' still' : ''}`;
  el.innerHTML = `
    <canvas class="ic-dust" id="icDust" aria-hidden="true"></canvas>
    <div class="ic-stage" id="icStage" aria-hidden="true"><img src="/assets/thoth_bust_1000.jpg" alt=""><div class="ic-light"></div><div class="ic-disc" id="icDisc"></div></div>
    <div class="ic-bars" aria-hidden="true"><i></i><i></i></div>
    <div class="ic-cards" aria-live="polite">${CARDS.map((c, i) => `<p style="--i:${i}"><span>${c}</span><svg viewBox="0 0 300 12" preserveAspectRatio="none"><path d="M2 8 C 70 2, 150 11, 298 5"/></svg></p>`).join('')}</div>
    <form class="ic-ask" id="icForm">
      <p class="ic-prompt">What's been on your mind?</p>
      <div class="ic-field"><input id="icInput" autocomplete="off" maxlength="120" aria-label="Your question" placeholder="${SAMPLES[0]}">
        <button class="ic-go" aria-label="Begin"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12h14M13 6l6 6-6 6"/></svg></button></div>
      <div class="ic-beam" aria-hidden="true"><i></i></div>
      <div class="ic-actions" id="icActions"><button type="submit" class="ic-begin">Begin</button></div>
      <p class="ic-hint">Type any question and press Enter · Esc to skip</p>
    </form>
    <button class="intro-skip" id="icSkip" type="button">Skip</button>`;

  const stage = el.querySelector('#icStage');
  const input = el.querySelector('#icInput');
  const canvas = el.querySelector('#icDust');
  const timers = [];
  const later = (ms, fn) => timers.push(setTimeout(fn, ms));
  let done = false;
  let raf = 0;
  const dust = still ? null : makeDust(canvas);

  const phase = (p) => { el.dataset.phase = p; };
  const onMove = (e) => {
    const r = stage.getBoundingClientRect();
    stage.style.setProperty('--lx', `${((e.clientX - r.left) / r.width) * 100}%`);
    stage.style.setProperty('--ly', `${((e.clientY - r.top) / r.height) * 100}%`);
    dust?.pointer(e.clientX, e.clientY);
  };
  const onKey = (e) => {
    if (e.key === 'Escape') { e.preventDefault(); close(null, false); return; }
    // Any key during the opening jumps to the ask, so nobody waits for the film to type.
    if (el.dataset.phase !== 'ask' && !done && e.key.length === 1) { skipToAsk(); }
  };
  document.addEventListener('pointermove', onMove, { passive: true });
  document.addEventListener('keydown', onKey, true);

  const cleanup = () => {
    timers.forEach(clearTimeout); timers.length = 0;
    cancelAnimationFrame(raf);
    document.removeEventListener('pointermove', onMove);
    document.removeEventListener('keydown', onKey, true);
    document.querySelectorAll('.lt-mote').forEach((m) => m.remove());
    running = false;
    el.hidden = true; el.innerHTML = ''; el.className = 'intro'; delete el.dataset.phase;
  };
  const markSeen = () => { try { sessionStorage.setItem(SEEN, '1'); } catch (_) {} };
  function close(q, isSample) {
    if (done) return; done = true; markSeen();
    el.classList.add('leaving');
    setTimeout(() => { cleanup(); onDone(q, isSample); }, 600);
  }

  // ---------- The film ----------
  const loop = (t) => { dust.frame(t); raf = requestAnimationFrame(loop); };
  if (dust) {
    raf = requestAnimationFrame(loop);
    phase('dust');
    later(1600, () => { phase('mark'); dust.toMark(); });
    later(4300, () => { phase('bust'); dust.scatter(); });
    later(6400, () => phase('cards'));
    later(11000, () => skipToAsk());
  } else {
    phase('ask');
  }
  function skipToAsk() {
    if (el.dataset.phase === 'ask') return;
    timers.forEach(clearTimeout); timers.length = 0;
    phase('ask');
    dust?.scatter(true);
    setTimeout(() => input.focus({ preventScroll: true }), 300);
    idleSample();
  }
  if (still) { setTimeout(() => input.focus({ preventScroll: true }), 50); }

  // Nobody typed: a sample question writes itself and is left in the home box to send.
  function idleSample() {
    later(8000, () => {
      if (input.value || done) return;
      const t = SAMPLES[Math.floor(Math.random() * SAMPLES.length)];
      let i = 0;
      const typer = setInterval(() => {
        if (done || (input.value && i === 0)) return clearInterval(typer);
        input.value = t.slice(0, ++i);
        if (i >= t.length) { clearInterval(typer); later(900, () => weigh(t, true)); }
      }, 55);
      timers.push(typer);
    });
  }

  // ---------- The weighing ----------
  function weigh(text, isSample) {
    if (done) return;
    if (still) { close(text, isSample); return; }
    done = true; markSeen();
    input.blur();
    el.classList.add('weighing');
    const r = input.getBoundingClientRect();
    const disc = el.querySelector('#icDisc').getBoundingClientRect();
    const tx = disc.left + disc.width / 2, ty = disc.top + disc.height / 2;
    const chars = [...text].slice(0, 70), span = Math.min(r.width, 560), x0 = r.left + r.width / 2 - span / 2;
    chars.forEach((ch, i) => {
      if (ch === ' ') return;
      const m = document.createElement('span'); m.className = 'lt-mote'; m.textContent = ch; document.body.appendChild(m);
      const sx = x0 + (i / chars.length) * span, sy = r.top + r.height / 2 - 14;
      const mx = sx + (Math.random() - .5) * 160, my = sy - 120 - Math.random() * 140;
      m.animate([{ transform: `translate(${sx}px,${sy}px) scale(1)`, opacity: 1 }, { transform: `translate(${mx}px,${my}px) scale(.9)`, opacity: .95, offset: .45 }, { transform: `translate(${tx}px,${ty}px) scale(.2)`, opacity: 0 }],
        { duration: 1500 + Math.random() * 500, delay: i * 22, easing: 'cubic-bezier(.5,0,.3,1)', fill: 'forwards' }).onfinish = () => m.remove();
    });
    dust.gather(tx, ty);
    const total = 2000 + chars.length * 22;
    later(total - 500, () => el.classList.add('flare'));
    later(total, () => {
      el.style.setProperty('--ix', `${(tx / innerWidth) * 100}%`);
      el.style.setProperty('--iy', `${(ty / innerHeight) * 100}%`);
      el.classList.add('open');
    });
    later(total + 1500, () => { cleanup(); onDone(text, isSample); });
  }

  el.querySelector('#icForm').addEventListener('submit', (e) => {
    e.preventDefault();
    const v = input.value.trim();
    if (v) weigh(v, false); else input.focus();
  });
  el.querySelector('#icSkip').addEventListener('click', () => close(null, false));
}

// ---------- Gold dust: drift → mark → scatter over the bust → gather into the moon ----------
function makeDust(canvas) {
  const ctx = canvas.getContext('2d');
  const dpr = Math.min(devicePixelRatio || 1, 2);
  const lowEnd = (navigator.hardwareConcurrency || 8) <= 4 || matchMedia('(max-width: 760px)').matches;
  const N = lowEnd ? 360 : 720;
  let W = 0, H = 0;
  const resize = () => { W = innerWidth; H = innerHeight; canvas.width = W * dpr; canvas.height = H * dpr; ctx.setTransform(dpr, 0, 0, dpr, 0, 0); };
  resize();
  addEventListener('resize', resize);

  const P = Array.from({ length: N }, () => {
    const edge = Math.random() * 4 | 0;
    const x = edge === 0 ? -20 : edge === 1 ? W + 20 : Math.random() * W;
    const y = edge === 2 ? -20 : edge === 3 ? H + 20 : Math.random() * H;
    return { x, y, vx: 0, vy: 0, tx: W / 2 + (Math.random() - .5) * W * .7, ty: H / 2 + (Math.random() - .5) * H * .6, s: .6 + Math.random() * 1.6, a: 0, tw: Math.random() * 6.28, k: .012 + Math.random() * .02 };
  });
  let mode = 'drift';
  let px = W / 2, py = H / 2;

  // Points of the Ink-moon mark, sampled from the real SVG so the dust becomes the brand.
  let markPts = [];
  const img = new Image();
  img.onload = () => {
    const S = 220, off = document.createElement('canvas'); off.width = off.height = S;
    const o = off.getContext('2d'); o.drawImage(img, 0, 0, S, S);
    const data = o.getImageData(0, 0, S, S).data;
    for (let y = 0; y < S; y += 3) for (let x = 0; x < S; x += 3) if (data[(y * S + x) * 4 + 3] > 120) markPts.push([x / S, y / S]);
  };
  img.src = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(markSVG().replace(/currentColor/g, '#fff').replace('<svg ', '<svg xmlns="http://www.w3.org/2000/svg" width="220" height="220" '))}`;

  return {
    pointer(x, y) { px = x; py = y; },
    toMark() {
      if (!markPts.length) return;
      mode = 'mark';
      const size = Math.min(W, H) * .34, ox = W / 2 - size / 2, oy = H * .44 - size / 2;
      P.forEach((p, i) => { const m = markPts[(i * 7919) % markPts.length]; p.tx = ox + m[0] * size + (Math.random() - .5) * 2; p.ty = oy + m[1] * size + (Math.random() - .5) * 2; p.k = .05 + Math.random() * .04; });
    },
    scatter(soft) {
      mode = 'float';
      P.forEach((p) => { p.vx = (Math.random() - .5) * (soft ? 1 : 6); p.vy = -Math.random() * (soft ? 1 : 4); });
    },
    gather(x, y) { mode = 'gather'; P.forEach((p) => { p.tx = x; p.ty = y; p.k = .03 + Math.random() * .05; }); },
    frame(t) {
      ctx.clearRect(0, 0, W, H);
      ctx.globalCompositeOperation = 'lighter';
      for (const p of P) {
        if (mode === 'drift' || mode === 'mark' || mode === 'gather') {
          const pull = mode === 'drift' ? .06 : .32;
          p.vx += (p.tx - p.x) * p.k * pull; p.vy += (p.ty - p.y) * p.k * pull;
          p.vx *= .8; p.vy *= .8;
          p.a = Math.min(1, p.a + .02);
          if (mode === 'gather' && Math.hypot(p.tx - p.x, p.ty - p.y) < 8) p.a *= .8;
        } else {
          // Floating motes over the bust: rise slowly, sway, and lean away from the light.
          p.vy += -.004; p.vx += Math.sin(t / 900 + p.tw) * .004;
          const dx = p.x - px, dy = p.y - py, d2 = dx * dx + dy * dy;
          if (d2 < 14000) { p.vx += dx / 3000; p.vy += dy / 3000; }
          p.vx *= .985; p.vy *= .985;
          p.a = Math.max(.12, p.a * .996);
          if (p.y < -10) { p.y = H + 10; p.x = Math.random() * W; }
        }
        p.x += p.vx; p.y += p.vy;
        const tw = .65 + .35 * Math.sin(t / 380 + p.tw);
        ctx.fillStyle = `rgba(243, 213, 138, ${(p.a * tw * .85).toFixed(3)})`;
        ctx.beginPath(); ctx.arc(p.x, p.y, p.s, 0, 6.283); ctx.fill();
      }
      ctx.globalCompositeOperation = 'source-over';
    },
  };
}
