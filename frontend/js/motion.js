// Motion: one language for the whole app. Two tools:
//  · scene(kind, mutate): wraps a big state change (home ↔ project, layout, theme) in a View Transition;
//    html[data-scene] tells motion.css which choreography to play. No View Transitions → plain swap.
//  · fresh(key): the UI re-renders by innerHTML, so CSS entrance animations would replay on every emit.
//    fresh() remembers when a thing first appeared and returns a class + negative animation-delay, so an
//    entrance plays once and later renders land on its final frame.
const reduced = () => matchMedia('(prefers-reduced-motion: reduce)').matches;

export function scene(kind, mutate, { x, y } = {}) {
  const root = document.documentElement;
  if (reduced() || !document.startViewTransition) { mutate(); return Promise.resolve(); }
  root.dataset.scene = kind;
  if (x != null) { root.style.setProperty('--vt-x', `${x}px`); root.style.setProperty('--vt-y', `${y}px`); }
  let ran = false;
  const t = document.startViewTransition(() => { ran = true; mutate(); });
  // A hidden or throttled tab may never paint the "before" frame; never let a transition hold up the state change.
  setTimeout(() => { if (!ran) t.skipTransition(); }, 800);
  t.ready.catch(() => {});
  t.finished.catch(() => {}).finally(() => { if (root.dataset.scene === kind) delete root.dataset.scene; });
  // Resolves once the new state is in place (the animation keeps playing), so callers can await it.
  return t.updateCallbackDone.catch(() => {});
}

const born = new Map();
const LIFE = 2400; // longer than any entrance animation

// Returns ' fresh" style="animation-delay:-Nms' style fragments for template strings:
//   `<div class="msg${fx.cls}"${fx.attr}>`
export function fresh(key, life = LIFE) {
  const now = performance.now();
  if (!born.has(key)) born.set(key, now);
  const age = now - born.get(key);
  if (reduced() || age > life) return { cls: '', attr: '', first: false };
  return { cls: ' fresh', attr: ` style="--age:-${Math.round(age)}ms"`, first: age < 1 };
}

// Play an entrance again (a panel re-opened, a stage re-reached).
export function again(key) { born.delete(key); }

// Mark a whole batch as already seen (e.g. a project's old messages on open) so only new things enter.
export function seen(keys) { const t = performance.now() - LIFE - 1; for (const k of keys) if (!born.has(k)) born.set(k, t); }

// Cinema bars: a short letterbox dip for big moments (the ruling). Pure overlay, never blocks input.
export function letterbox(ms = 1100) {
  if (reduced()) return;
  const el = document.createElement('div');
  el.className = 'letterbox';
  el.style.setProperty('--lb-ms', `${ms}ms`);
  el.innerHTML = '<i></i><i></i>';
  document.body.appendChild(el);
  setTimeout(() => el.remove(), ms + 50);
}
