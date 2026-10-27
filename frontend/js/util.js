// Shared helpers: escaping, sanitised markdown, and the small SVG vocabulary
// (mark, moon phases, thinker busts, ink stroke).

export const $ = (sel, root = document) => root.querySelector(sel);

export function esc(text) {
  return String(text ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

// LLM output is untrusted: render markdown, then sanitise.
// <unchecked>…</unchecked> marks general-knowledge claims (docs/features/01): rendered with a
// dotted underline and a "check" link that looks the claim up.
export function md(text) {
  const claims = [];
  const src = String(text ?? '')
    .replace(/<unchecked>([\s\S]*?)<\/unchecked>/g, (_, c) => `\u2063U${claims.push(c.trim()) - 1}\u2063${c}\u2063/U\u2063`)
    .replace(/\[\[([^\]]+)\]\]/g, '`source: $1`')
    .replace(/\[!(CAUTION|WARNING|NOTE|IMPORTANT|TIP)\]\s*/g, '');
  let html = window.marked && window.DOMPurify
    ? window.DOMPurify.sanitize(window.marked.parse(src, { breaks: true }))
    : esc(src).replace(/\n/g, '<br>');
  html = html.replace(/\u2063U(\d+)\u2063([\s\S]*?)\u2063\/U\u2063/g, (_, i, inner) =>
    `<span class="unchecked" title="From general knowledge, not yet checked against sources">${inner}</span>`
    + `<button type="button" class="check-link" data-act="checkClaim" data-arg="${esc(claims[+i])}">check</button>`);
  return html;
}

export function uid(prefix = 'id') {
  return `${prefix}_${Date.now().toString(36)}${Math.random().toString(36).slice(2, 7)}`;
}

export function clock(ts) {
  return new Date(ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

// The mark ("Ink moon"): a crescent with one drop of ink falling from it. Uses currentColor so it
// follows the theme; each instance gets its own mask id.
let markSeq = 0;
export function markSVG(cls = '') {
  const id = `thothMark${markSeq += 1}`;
  return `<svg class="${cls}" viewBox="0 0 64 64" aria-hidden="true">
    <defs><mask id="${id}"><rect width="64" height="64" fill="#fff"/><circle cx="39" cy="24" r="19" fill="#000"/></mask></defs>
    <circle cx="30" cy="30" r="22" fill="currentColor" mask="url(#${id})"/>
    <path class="mark-drop" d="M45 47 C45 47 40.5 53 40.5 56 a4.5 4.5 0 0 0 9 0 C49.5 53 45 47 45 47Z" fill="currentColor"/>
  </svg>`;
}

// Moon phase for journey stage i of n (new moon → full moon). Lit part on the right (waxing).
export function moonSVG(index, total, filled = true) {
  const f = total <= 1 ? 1 : index / (total - 1);
  const r = 7, cx = 9, cy = 9;
  const rx = Math.abs(1 - 2 * f) * r;
  const sweep = f < 0.5 ? 0 : 1;
  const lit = f === 0 ? '' : `<path d="M${cx} ${cy - r} A${r} ${r} 0 0 1 ${cx} ${cy + r} A${rx.toFixed(2)} ${r} 0 0 ${sweep} ${cx} ${cy - r} Z" fill="${filled ? 'var(--moon-fill)' : 'var(--line)'}"/>`;
  return `<svg viewBox="0 0 18 18" aria-hidden="true"><circle cx="${cx}" cy="${cy}" r="${r}" fill="none" stroke="var(--moon)" stroke-width="1.2"/>${lit}</svg>`;
}

// Placeholder bust: a small classical bust on a plinth with the thinker's initial (3D busts come later).
export function bustSVG(name = '?') {
  // Last word of the name, after any particle ("al-Haytham" → H).
  const initial = esc(((name.trim().split(/\s+/).pop() || '?').split('-').pop() || '?')[0].toUpperCase());
  return `<svg class="bust" viewBox="0 0 40 40" aria-hidden="true">
    <circle cx="20" cy="20" r="19.5" fill="var(--surface-2)"/>
    <ellipse cx="20" cy="12.6" rx="5.2" ry="6.2" fill="var(--ink-3)"/>
    <path d="M17.6 17.8h4.8v3.2h-4.8z" fill="var(--ink-3)"/>
    <path d="M10.5 29c.8-5 4.6-8.2 9.5-8.2s8.7 3.2 9.5 8.2z" fill="var(--ink-3)"/>
    <rect x="12" y="29" width="16" height="4.2" rx="1" fill="var(--ink-2)"/>
    <text x="20" y="32.4" text-anchor="middle" font-family="Newsreader, Georgia, serif" font-size="4" font-weight="600" fill="var(--surface)">${initial}</text>
  </svg>`;
}

// The brand mark used across the app (sidebar, home, Thoth's avatar, intro).
export function brandMark(cls = '') {
  return markSVG(cls);
}

// Progress is a reed stroke being drawn, not a spinner.
export function strokeSVG() {
  return '<svg class="stroke" viewBox="0 0 34 8" fill="none" aria-hidden="true"><path d="M1 4 C 8 1, 14 7, 21 4 S 30 2, 33 4" stroke-width="1.6" stroke-linecap="round"/></svg>';
}
