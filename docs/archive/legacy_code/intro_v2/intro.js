// Intro: "your question becomes the moon".
// Darkness and a cursor ask "What's been on your mind?". The user types a real question (or a sample
// types itself when idle). On Enter the letters dissolve into live ink (a real-time GPU fluid
// simulation that also follows the pointer), the currents coil into a crescent, the ink turns to
// moonlight, the scribe underlines the question in red, and the app opens with it already asked.
// Once per browser session; ?intro forces it; reduced motion skips it; no WebGL → text-only version.

import { markSVG } from './util.js';

const SEEN = 'thoth.intro.seen';
const SAMPLES = [
  'Why do cities feel faster at night?',
  'Why do some memories fade while others stay sharp?',
  'Why do people trust a confident wrong answer?',
];

let running = false;

export function maybePlayIntro(onDone) {
  const forced = new URLSearchParams(location.search).has('intro');
  let seen = false;
  try { seen = sessionStorage.getItem(SEEN) === '1'; } catch (_) {}
  if (!forced && (seen || matchMedia('(prefers-reduced-motion: reduce)').matches)) return;
  playIntro(onDone);
}

export function playIntro(onDone = () => {}) {
  if (running) return;
  running = true;
  const el = document.getElementById('intro');
  el.hidden = false;
  el.classList.remove('leaving', 'no-fluid');
  el.innerHTML = `
    <canvas class="intro-fluid" aria-hidden="true"></canvas>
    <div class="intro-ask" id="introAsk">
      <p class="intro-prompt">What's been on your mind?</p>
      <div class="intro-field"><span class="intro-typed" id="introTyped"></span><span class="intro-caret"></span></div>
      <p class="intro-hint" id="introHint">Type a question and press Enter</p>
    </div>
    <div class="intro-record" id="introRecord" hidden>
      <p class="intro-q" id="introQ"></p>
      <svg class="intro-underline" viewBox="0 0 600 14" preserveAspectRatio="none" aria-hidden="true"><path d="M4 9 C 120 3, 260 12, 380 6 S 540 4, 596 8"/></svg>
      <span class="intro-mark">${markSVG()}</span>
      <p class="intro-brand">THOTH</p>
      <p class="intro-tag">Find the questions worth asking.</p>
    </div>
    <button class="intro-skip" id="introSkip">Skip</button>
    <input class="intro-input" id="introInput" aria-label="Your question" autocomplete="off" maxlength="120">`;

  const canvas = el.querySelector('canvas');
  const input = el.querySelector('#introInput');
  const typed = el.querySelector('#introTyped');
  const hint = el.querySelector('#introHint');
  const timers = [];
  const at = (ms, fn) => timers.push(setTimeout(() => running && fn(), ms));

  let fluid = null;
  try { fluid = createFluid(canvas); } catch (_) { fluid = null; }
  if (!fluid) el.classList.add('no-fluid');

  let phase = 'ask';
  let question = '';
  let sample = false;
  let idleTimer = null;

  const finish = (q = null, isSample = false) => {
    if (!running) return;
    running = false;
    timers.forEach(clearTimeout);
    clearTimeout(idleTimer);
    try { sessionStorage.setItem(SEEN, '1'); } catch (_) {}
    document.removeEventListener('keydown', onKey, true);
    el.classList.add('leaving');
    setTimeout(() => { fluid?.dispose(); el.hidden = true; el.innerHTML = ''; }, 1000);
    onDone(q, isSample);
  };

  const onKey = (e) => {
    if (e.key === 'Escape') { e.preventDefault(); finish(); }
  };
  document.addEventListener('keydown', onKey, true);
  el.querySelector('#introSkip').addEventListener('click', () => finish());

  // ---------- Ask phase ----------
  const sync = () => { typed.textContent = input.value; hint.style.opacity = input.value ? '0' : ''; };
  const armIdle = () => {
    clearTimeout(idleTimer);
    idleTimer = setTimeout(() => { if (phase === 'ask' && !input.value) autoType(); }, 4500);
  };
  input.addEventListener('input', () => { sync(); armIdle(); });
  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && input.value.trim() && phase === 'ask') { e.preventDefault(); begin(input.value.trim(), false); }
  });
  el.addEventListener('pointerdown', (e) => { if (!e.target.closest('.intro-skip')) setTimeout(() => input.focus(), 0); });
  setTimeout(() => input.focus(), 60);
  armIdle();

  function autoType() {
    const text = SAMPLES[Math.floor(Math.random() * SAMPLES.length)];
    hint.textContent = 'For example…';
    hint.style.opacity = '';
    let i = 0;
    const tick = () => {
      if (!running || phase !== 'ask' || (input.value && input.value !== text.slice(0, i))) return;
      i += 1;
      input.value = text.slice(0, i);
      typed.textContent = input.value;
      if (i < text.length) timers.push(setTimeout(tick, 45 + Math.random() * 55));
      else at(650, () => begin(text, true));
    };
    tick();
  }

  // ---------- Dissolve → crescent → record ----------
  function begin(q, isSample) {
    phase = 'dissolve';
    question = q;
    sample = isSample;
    clearTimeout(idleTimer);
    input.blur();
    const ask = el.querySelector('#introAsk');
    if (fluid) fluid.dissolveText(typed.getBoundingClientRect(), q, getComputedStyle(typed).font);
    ask.classList.add('dissolving');
    const showRecord = () => {
      const rec = el.querySelector('#introRecord');
      el.querySelector('#introQ').textContent = q;
      rec.hidden = false;
      requestAnimationFrame(() => rec.classList.add('on'));
    };
    if (!fluid) {
      at(1600, showRecord);
      at(4600, () => finish(question, sample));
      return;
    }
    // Phases run on simulation time, so a slow machine plays the same choreography, just slower.
    const cues = [
      [1.5, () => { phase = 'crescent'; fluid.formCrescent(); }],
      [3.9, () => fluid.toMoonlight()],
      [4.7, showRecord],
      [8.4, () => finish(question, sample)],
    ];
    const t0 = fluid.simTime();
    const poll = () => {
      if (!running) return;
      const t = fluid.simTime() - t0;
      while (cues.length && t >= cues[0][0]) cues.shift()[1]();
      if (cues.length) timers.push(setTimeout(poll, 50));
    };
    poll();
  }
}

// =====================================================================================
// GPU fluid (stable fluids: advection, vorticity, pressure projection). WebGL1 + half floats.
// =====================================================================================
function createFluid(canvas) {
  const gl = canvas.getContext('webgl', { alpha: false, depth: false, stencil: false, antialias: false, preserveDrawingBuffer: false });
  if (!gl) return null;
  const halfFloat = gl.getExtension('OES_texture_half_float');
  const linear = gl.getExtension('OES_texture_half_float_linear');
  if (!halfFloat) return null;
  const HALF = halfFloat.HALF_FLOAT_OES;
  const FILTER = linear ? gl.LINEAR : gl.NEAREST;

  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  const resize = () => {
    canvas.width = Math.floor(canvas.clientWidth * dpr);
    canvas.height = Math.floor(canvas.clientHeight * dpr);
  };
  resize();

  const compile = (type, src) => {
    const s = gl.createShader(type);
    gl.shaderSource(s, src);
    gl.compileShader(s);
    if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(s));
    return s;
  };
  const VERT = compile(gl.VERTEX_SHADER, `
    precision highp float;
    attribute vec2 aPosition;
    varying vec2 vUv, vL, vR, vT, vB;
    uniform vec2 texelSize;
    void main () {
      vUv = aPosition * 0.5 + 0.5;
      vL = vUv - vec2(texelSize.x, 0.0); vR = vUv + vec2(texelSize.x, 0.0);
      vT = vUv + vec2(0.0, texelSize.y); vB = vUv - vec2(0.0, texelSize.y);
      gl_Position = vec4(aPosition, 0.0, 1.0);
    }`);
  const program = (frag) => {
    const p = gl.createProgram();
    gl.attachShader(p, VERT);
    gl.attachShader(p, compile(gl.FRAGMENT_SHADER, 'precision highp float; precision highp sampler2D;\n' + frag));
    gl.bindAttribLocation(p, 0, 'aPosition');
    gl.linkProgram(p);
    if (!gl.getProgramParameter(p, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(p));
    const u = {};
    const n = gl.getProgramParameter(p, gl.ACTIVE_UNIFORMS);
    for (let i = 0; i < n; i += 1) { const name = gl.getActiveUniform(p, i).name; u[name] = gl.getUniformLocation(p, name); }
    return { p, u };
  };

  const P = {
    clear: program(`varying vec2 vUv; uniform sampler2D uTexture; uniform float value;
      void main () { gl_FragColor = value * texture2D(uTexture, vUv); }`),
    splat: program(`varying vec2 vUv; uniform sampler2D uTarget; uniform float aspectRatio; uniform vec3 color; uniform vec2 point; uniform float radius;
      void main () { vec2 p = vUv - point; p.x *= aspectRatio; vec3 s = exp(-dot(p, p) / radius) * color;
        gl_FragColor = vec4(texture2D(uTarget, vUv).xyz + s, 1.0); }`),
    advect: program(`varying vec2 vUv; uniform sampler2D uVelocity, uSource; uniform vec2 texelSize, center; uniform float dt, dissipation, pull, spin, radius, aspectRatio;
      void main () {
        vec2 v = texture2D(uVelocity, vUv).xy;
        // Extra (non-physical) gathering flow for the ink only: draw it onto a ring and turn it.
        vec2 d = vUv - center; d.x *= aspectRatio; float r = length(d) + 1e-4;
        vec2 extra = (-d / r) * (r - radius) * pull + vec2(-d.y, d.x) / r * spin * exp(-pow((r - radius) / radius, 2.0));
        extra.x /= aspectRatio;
        vec2 coord = vUv - dt * (v + extra) * texelSize;
        gl_FragColor = texture2D(uSource, coord) / (1.0 + dissipation * dt); }`),
    divergence: program(`varying vec2 vUv, vL, vR, vT, vB; uniform sampler2D uVelocity;
      void main () { float L = texture2D(uVelocity, vL).x, R = texture2D(uVelocity, vR).x, T = texture2D(uVelocity, vT).y, B = texture2D(uVelocity, vB).y;
        vec2 C = texture2D(uVelocity, vUv).xy;
        if (vL.x < 0.0) L = -C.x; if (vR.x > 1.0) R = -C.x; if (vT.y > 1.0) T = -C.y; if (vB.y < 0.0) B = -C.y;
        gl_FragColor = vec4(0.5 * (R - L + T - B), 0.0, 0.0, 1.0); }`),
    curl: program(`varying vec2 vUv, vL, vR, vT, vB; uniform sampler2D uVelocity;
      void main () { float L = texture2D(uVelocity, vL).y, R = texture2D(uVelocity, vR).y, T = texture2D(uVelocity, vT).x, B = texture2D(uVelocity, vB).x;
        gl_FragColor = vec4(0.5 * (R - L - T + B), 0.0, 0.0, 1.0); }`),
    vorticity: program(`varying vec2 vUv, vL, vR, vT, vB; uniform sampler2D uVelocity, uCurl; uniform float curl, dt;
      void main () { float L = texture2D(uCurl, vL).x, R = texture2D(uCurl, vR).x, T = texture2D(uCurl, vT).x, B = texture2D(uCurl, vB).x, C = texture2D(uCurl, vUv).x;
        vec2 force = 0.5 * vec2(abs(T) - abs(B), abs(R) - abs(L)); force /= length(force) + 0.0001; force *= curl * C; force.y *= -1.0;
        vec2 v = texture2D(uVelocity, vUv).xy + force * dt; gl_FragColor = vec4(clamp(v, -1000.0, 1000.0), 0.0, 1.0); }`),
    pressure: program(`varying vec2 vUv, vL, vR, vT, vB; uniform sampler2D uPressure, uDivergence;
      void main () { float L = texture2D(uPressure, vL).x, R = texture2D(uPressure, vR).x, T = texture2D(uPressure, vT).x, B = texture2D(uPressure, vB).x;
        float d = texture2D(uDivergence, vUv).x; gl_FragColor = vec4((L + R + B + T - d) * 0.25, 0.0, 0.0, 1.0); }`),
    gradient: program(`varying vec2 vUv, vL, vR, vT, vB; uniform sampler2D uPressure, uVelocity;
      void main () { float L = texture2D(uPressure, vL).x, R = texture2D(uPressure, vR).x, T = texture2D(uPressure, vT).x, B = texture2D(uPressure, vB).x;
        vec2 v = texture2D(uVelocity, vUv).xy - vec2(R - L, T - B); gl_FragColor = vec4(v, 0.0, 1.0); }`),
    coil: program(`varying vec2 vUv; uniform sampler2D uVelocity; uniform vec2 center; uniform float aspectRatio, radius, swirl, pull, dt;
      void main () {
        vec2 d = vUv - center; d.x *= aspectRatio; float r = length(d) + 1e-4;
        vec2 tangent = vec2(-d.y, d.x) / r; vec2 inward = -d / r;
        float band = exp(-pow((r - radius) / (radius * 0.9), 2.0));
        vec2 f = tangent * swirl * band + inward * (r - radius) * pull;
        f.x /= aspectRatio;
        gl_FragColor = vec4(texture2D(uVelocity, vUv).xy + f * dt, 0.0, 1.0); }`),
    display: program(`varying vec2 vUv; uniform sampler2D uTexture; uniform vec3 ink, glow; uniform float moon, time, aspectRatio, radius; uniform vec2 center;
      void main () {
        vec3 d = texture2D(uTexture, vUv).rgb; float a = clamp(max(d.r, max(d.g, d.b)), 0.0, 1.6);
        // Light the coiled ink like a sphere lit from behind-right: a crescent emerges.
        vec2 q = (vUv - center); q.x *= aspectRatio; q /= radius * 1.1;
        float rr = dot(q, q);
        vec3 nrm = vec3(q, sqrt(max(0.0, 1.0 - min(rr, 1.0))));
        float lit = dot(normalize(nrm), normalize(vec3(1.0, 0.32, -0.5)));
        float disc = 1.0 - smoothstep(0.82, 1.0, rr);
        float shade = (0.06 + 2.4 * smoothstep(0.0, 0.42, lit)) * disc;
        a *= mix(1.0, shade, moon);
        vec2 c = vUv - 0.5; float vign = 1.0 - dot(c, c) * 0.9;
        vec3 bg = mix(vec3(0.012, 0.014, 0.03), vec3(0.03, 0.035, 0.075), vUv.y) * vign;
        float n = fract(sin(dot(vUv * 800.0 + time, vec2(12.9898, 78.233))) * 43758.5453) * 0.02;
        vec3 inkCol = mix(ink, glow, moon);
        vec3 col = bg + inkCol * (1.0 - exp(-a * 1.15)) + glow * moon * pow(min(a, 1.4), 3.0) * 0.18;
        gl_FragColor = vec4(col + n, 1.0); }`),
  };

  // Full-screen quad
  gl.bindBuffer(gl.ARRAY_BUFFER, gl.createBuffer());
  gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, -1, 1, 1, 1, 1, -1]), gl.STATIC_DRAW);
  gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, gl.createBuffer());
  gl.bufferData(gl.ELEMENT_ARRAY_BUFFER, new Uint16Array([0, 1, 2, 0, 2, 3]), gl.STATIC_DRAW);
  gl.vertexAttribPointer(0, 2, gl.FLOAT, false, 0, 0);
  gl.enableVertexAttribArray(0);
  const blit = (target) => {
    if (target) { gl.viewport(0, 0, target.w, target.h); gl.bindFramebuffer(gl.FRAMEBUFFER, target.fbo); }
    else { gl.viewport(0, 0, gl.drawingBufferWidth, gl.drawingBufferHeight); gl.bindFramebuffer(gl.FRAMEBUFFER, null); }
    gl.drawElements(gl.TRIANGLES, 6, gl.UNSIGNED_SHORT, 0);
  };

  const fbo = (w, h) => {
    gl.activeTexture(gl.TEXTURE0);
    const tex = gl.createTexture();
    gl.bindTexture(gl.TEXTURE_2D, tex);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, FILTER);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, FILTER);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, w, h, 0, gl.RGBA, HALF, null);
    const f = gl.createFramebuffer();
    gl.bindFramebuffer(gl.FRAMEBUFFER, f);
    gl.framebufferTexture2D(gl.FRAMEBUFFER, gl.COLOR_ATTACHMENT0, gl.TEXTURE_2D, tex, 0);
    if (gl.checkFramebufferStatus(gl.FRAMEBUFFER) !== gl.FRAMEBUFFER_COMPLETE) throw new Error('fbo');
    gl.viewport(0, 0, w, h);
    gl.clearColor(0, 0, 0, 1);
    gl.clear(gl.COLOR_BUFFER_BIT);
    return { tex, fbo: f, w, h, texel: [1 / w, 1 / h], attach(id) { gl.activeTexture(gl.TEXTURE0 + id); gl.bindTexture(gl.TEXTURE_2D, tex); return id; } };
  };
  const double = (w, h) => {
    let a = fbo(w, h), b = fbo(w, h);
    return { get read() { return a; }, get write() { return b; }, swap() { [a, b] = [b, a]; }, w, h, texel: [1 / w, 1 / h] };
  };
  const res = (n) => {
    const aspect = canvas.width / canvas.height;
    return aspect >= 1 ? [Math.round(n * aspect), n] : [n, Math.round(n / aspect)];
  };
  const [sw, sh] = res(160);
  const [dw, dh] = res(Math.min(1024, Math.max(512, Math.round(canvas.height / 1.4))));
  const velocity = double(sw, sh);
  const pressure = double(sw, sh);
  const divergence = fbo(sw, sh);
  const curlF = fbo(sw, sh);
  const dye = double(dw, dh);

  const S = { curl: 22, velDiss: 0.35, dyeDiss: 0.25, pressureIters: 20, moon: 0, moonTarget: 0, coil: 0 };
  const C = { x: 0.5, y: 0.5, r: 0.2 };
  const INK = [0.36, 0.42, 0.78];
  const GLOW = [0.92, 0.94, 1.0];
  const aspect = () => canvas.width / canvas.height;

  function splat(x, y, dx, dy, color, radius = 0.0009) {
    gl.useProgram(P.splat.p);
    gl.uniform1i(P.splat.u.uTarget, velocity.read.attach(0));
    gl.uniform1f(P.splat.u.aspectRatio, aspect());
    gl.uniform2f(P.splat.u.point, x, y);
    gl.uniform3f(P.splat.u.color, dx, dy, 0);
    gl.uniform1f(P.splat.u.radius, radius);
    blit(velocity.write); velocity.swap();
    gl.uniform1i(P.splat.u.uTarget, dye.read.attach(0));
    gl.uniform3f(P.splat.u.color, color[0], color[1], color[2]);
    blit(dye.write); dye.swap();
  }

  function step(dt) {
    gl.disable(gl.BLEND);
    if (S.coil > 0.001) {
      gl.useProgram(P.coil.p);
      gl.uniform1i(P.coil.u.uVelocity, velocity.read.attach(0));
      gl.uniform2f(P.coil.u.center, C.x, C.y);
      gl.uniform1f(P.coil.u.aspectRatio, aspect());
      gl.uniform1f(P.coil.u.radius, C.r);
      gl.uniform1f(P.coil.u.swirl, 260 * S.coil);
      gl.uniform1f(P.coil.u.pull, 0.0);
      gl.uniform1f(P.coil.u.dt, dt);
      blit(velocity.write); velocity.swap();
    }
    gl.useProgram(P.curl.p);
    gl.uniform2fv(P.curl.u.texelSize, velocity.texel);
    gl.uniform1i(P.curl.u.uVelocity, velocity.read.attach(0));
    blit(curlF);
    gl.useProgram(P.vorticity.p);
    gl.uniform2fv(P.vorticity.u.texelSize, velocity.texel);
    gl.uniform1i(P.vorticity.u.uVelocity, velocity.read.attach(0));
    gl.uniform1i(P.vorticity.u.uCurl, curlF.attach(1));
    gl.uniform1f(P.vorticity.u.curl, S.curl);
    gl.uniform1f(P.vorticity.u.dt, dt);
    blit(velocity.write); velocity.swap();
    gl.useProgram(P.divergence.p);
    gl.uniform2fv(P.divergence.u.texelSize, velocity.texel);
    gl.uniform1i(P.divergence.u.uVelocity, velocity.read.attach(0));
    blit(divergence);
    gl.useProgram(P.clear.p);
    gl.uniform1i(P.clear.u.uTexture, pressure.read.attach(0));
    gl.uniform1f(P.clear.u.value, 0.8);
    blit(pressure.write); pressure.swap();
    gl.useProgram(P.pressure.p);
    gl.uniform2fv(P.pressure.u.texelSize, velocity.texel);
    gl.uniform1i(P.pressure.u.uDivergence, divergence.attach(0));
    for (let i = 0; i < S.pressureIters; i += 1) {
      gl.uniform1i(P.pressure.u.uPressure, pressure.read.attach(1));
      blit(pressure.write); pressure.swap();
    }
    gl.useProgram(P.gradient.p);
    gl.uniform2fv(P.gradient.u.texelSize, velocity.texel);
    gl.uniform1i(P.gradient.u.uPressure, pressure.read.attach(0));
    gl.uniform1i(P.gradient.u.uVelocity, velocity.read.attach(1));
    blit(velocity.write); velocity.swap();
    gl.useProgram(P.advect.p);
    gl.uniform2fv(P.advect.u.texelSize, velocity.texel);
    gl.uniform1i(P.advect.u.uVelocity, velocity.read.attach(0));
    gl.uniform1i(P.advect.u.uSource, velocity.read.attach(0));
    gl.uniform1f(P.advect.u.dt, dt);
    gl.uniform1f(P.advect.u.dissipation, S.velDiss);
    gl.uniform2f(P.advect.u.center, C.x, C.y);
    gl.uniform1f(P.advect.u.radius, C.r);
    gl.uniform1f(P.advect.u.aspectRatio, aspect());
    gl.uniform1f(P.advect.u.pull, 0);
    gl.uniform1f(P.advect.u.spin, 0);
    blit(velocity.write); velocity.swap();
    gl.uniform1i(P.advect.u.uVelocity, velocity.read.attach(0));
    gl.uniform1i(P.advect.u.uSource, dye.read.attach(1));
    gl.uniform1f(P.advect.u.dissipation, S.dyeDiss);
    gl.uniform1f(P.advect.u.pull, 380 * S.coil);
    gl.uniform1f(P.advect.u.spin, 46 * S.coil);
    blit(dye.write); dye.swap();
  }

  let time = 0;
  function render() {
    gl.useProgram(P.display.p);
    gl.uniform1i(P.display.u.uTexture, dye.read.attach(0));
    gl.uniform3fv(P.display.u.ink, INK);
    gl.uniform3fv(P.display.u.glow, GLOW);
    gl.uniform1f(P.display.u.moon, S.moon);
    gl.uniform1f(P.display.u.time, time);
    gl.uniform1f(P.display.u.aspectRatio, aspect());
    gl.uniform2f(P.display.u.center, C.x, C.y);
    gl.uniform1f(P.display.u.radius, C.r);
    blit(null);
  }

  // Pointer stirs the ink.
  let last = null;
  const onMove = (e) => {
    const r = canvas.getBoundingClientRect();
    const x = (e.clientX - r.left) / r.width, y = 1 - (e.clientY - r.top) / r.height;
    if (last) {
      const dx = (x - last.x) * 3200, dy = (y - last.y) * 3200;
      if (Math.abs(dx) + Math.abs(dy) > 0.5) splat(x, y, dx, dy, INK.map((c) => c * 0.08), 0.0011);
    }
    last = { x, y };
  };
  window.addEventListener('pointermove', onMove);

  // Emitters run each frame (ambient current, text dissolve, crescent).
  const emitters = [];
  let lastT = performance.now();
  const born = lastT;
  let frames = 0;
  let raf = 0;
  // Test aid: ?introSpeed=N runs N simulation steps per frame (for throttled preview panes).
  const SUBSTEPS = Math.max(1, Math.min(40, Number(new URLSearchParams(location.search).get('introSpeed')) || 1));
  const frame = (now) => {
    const dt = Math.min((now - lastT) / 1000, 1 / 20);
    lastT = now;
    for (let sub = 0; sub < SUBSTEPS; sub += 1) {
      time += dt;
      for (let i = emitters.length - 1; i >= 0; i -= 1) if (emitters[i](now) === false) emitters.splice(i, 1);
      if (sub < SUBSTEPS - 1) step(dt);
    }
    S.moon = S.moonStart !== undefined ? Math.min(1, (time - S.moonStart) / 0.8) : 0;
    frames += 1;
    step(dt);
    render();
    raf = requestAnimationFrame(frame);
  };
  emitters.push((now) => {
    const t = now / 1000;
    if (Math.random() < 0.06) splat(0.5 + Math.cos(t * 0.3) * 0.35, 0.12 + Math.random() * 0.1, Math.sin(t) * 30, 60, INK.map((c) => c * 0.02), 0.004);
  });
  raf = requestAnimationFrame(frame);

  const onResize = () => resize();
  window.addEventListener('resize', onResize);

  return {
    // Turn the typed letters into ink: sample the rendered text and release it left to right.
    dissolveText(rect, text, font) {
      const r = canvas.getBoundingClientRect();
      const off = document.createElement('canvas');
      off.width = Math.max(1, Math.ceil(rect.width)); off.height = Math.max(1, Math.ceil(rect.height));
      const g = off.getContext('2d');
      g.font = font; g.fillStyle = '#fff'; g.textBaseline = 'middle';
      g.fillText(text, 0, off.height / 2);
      const data = g.getImageData(0, 0, off.width, off.height).data;
      const pts = [];
      const stride = Math.max(3, Math.round(off.width / 160));
      for (let y = 0; y < off.height; y += stride) for (let x = 0; x < off.width; x += stride) {
        if (data[(y * off.width + x) * 4 + 3] > 120) pts.push([(rect.left + x - r.left) / r.width, 1 - (rect.top + y - r.top) / r.height]);
      }
      pts.sort((a, b) => a[0] - b[0]);
      C.x = (rect.left + rect.width / 2 - r.left) / r.width;
      C.y = 1 - (rect.top + rect.height / 2 - r.top) / r.height + 0.08;
      C.r = Math.min(0.2, Math.max(0.12, (rect.width / r.height) * 0.28));
      const start = time;
      const span = 0.9;
      let idx = 0;
      emitters.push((now) => {
        const until = Math.floor(((time - start) / span) * pts.length);
        for (; idx < Math.min(until, pts.length); idx += 1) {
          const [x, y] = pts[idx];
          splat(x, y, (Math.random() - 0.5) * 120, 40 + Math.random() * 90, INK.map((c) => c * 0.34), 0.00018);
        }
        return idx < pts.length;
      });
    },
    // Coil the question's own ink into a ring around its centre; moonlight then lights one side.
    formCrescent() {
      S.curl = 12;
      S.dyeDiss = 0.12;
      const start = time;
      emitters.push(() => {
        const k = Math.min(1, (time - start) / 1.6);
        S.coil = k < 1 ? 0.35 + 0.65 * k : 1;
        if (Math.random() < 0.5) {
          const a = Math.random() * Math.PI * 2;
          const x = C.x + (Math.cos(a) * C.r) / aspect(), y = C.y + Math.sin(a) * C.r;
          splat(x, y, -Math.sin(a) * 40, Math.cos(a) * 40, INK.map((c) => c * 0.045), 0.0005);
        }
        if (time - start > 3.4) { S.coil = 0.5; return false; }
      });
    },
    toMoonlight() {
      // Hold the moon: almost no fading, gentle motion, and a light top-up so it stays full to the end.
      S.moonStart = time; S.curl = 4; S.dyeDiss = 0.012; S.velDiss = 1.2;
      emitters.push(() => {
        if (Math.random() < 0.35) {
          const a = Math.random() * Math.PI * 2, rr = C.r * Math.sqrt(Math.random()) * 0.9;
          splat(C.x + (Math.cos(a) * rr) / aspect(), C.y + Math.sin(a) * rr, 0, 0, INK.map((c) => c * 0.02), 0.0008);
        }
      });
    },
    simTime() { return time; },
    fps() { return frames / ((performance.now() - born) / 1000); },
    dispose() {
      cancelAnimationFrame(raf);
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('resize', onResize);
      gl.getExtension('WEBGL_lose_context')?.loseContext();
    },
  };
}
