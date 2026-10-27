// Small in-page UI primitives: a modal text dialog (replaces window.prompt) and a toast.
const FOCUSABLE = 'button, [href], input, textarea, select, [tabindex]:not([tabindex="-1"])';

// askText({ title, body, label, value, confirm, cancel, multiline, required }) → Promise<string | null>
export function askText({ title, body = '', label = '', value = '', confirm = 'Save', cancel = 'Cancel', placeholder = '', required = false } = {}) {
  return new Promise((resolve) => {
    const returnTo = document.activeElement;
    const id = `dlg${Date.now().toString(36)}`;
    const scrim = document.createElement('div');
    scrim.className = 'scrim';
    scrim.innerHTML = `<form class="dialog" role="dialog" aria-modal="true" aria-labelledby="${id}t">
      <h3 id="${id}t"></h3>${body ? `<p class="dialog-body"></p>` : ''}
      ${label ? `<label class="dialog-label" for="${id}f"></label>` : ''}
      <textarea id="${id}f" class="dialog-field" rows="5"></textarea>
      <div class="dialog-row"><button type="button" class="chip" data-cancel></button><button type="submit" class="chip primary"></button></div></form>`;
    const form = scrim.querySelector('form');
    scrim.querySelector('h3').textContent = title || '';
    if (body) scrim.querySelector('.dialog-body').textContent = body;
    if (label) scrim.querySelector('.dialog-label').textContent = label;
    const field = scrim.querySelector('textarea');
    field.value = value; field.placeholder = placeholder;
    scrim.querySelector('[data-cancel]').textContent = cancel;
    scrim.querySelector('[type="submit"]').textContent = confirm;
    const done = (result) => {
      document.removeEventListener('keydown', onKey, true);
      scrim.classList.add('leaving');
      setTimeout(() => scrim.remove(), 160);
      try { returnTo?.focus?.({ preventScroll: true }); } catch (_) {}
      resolve(result);
    };
    const onKey = (e) => {
      if (e.key === 'Escape') { e.preventDefault(); done(null); }
      else if (e.key === 'Tab') {
        const items = [...form.querySelectorAll(FOCUSABLE)].filter((x) => !x.disabled);
        if (!items.length) return;
        const first = items[0], last = items[items.length - 1];
        if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
        else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
      } else if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) { form.requestSubmit(); }
    };
    form.addEventListener('submit', (e) => { e.preventDefault(); const v = field.value; if (required && !v.trim()) { field.focus(); return; } done(v); });
    scrim.querySelector('[data-cancel]').addEventListener('click', () => done(null));
    scrim.addEventListener('mousedown', (e) => { if (e.target === scrim) done(null); });
    document.addEventListener('keydown', onKey, true);
    document.body.appendChild(scrim);
    field.focus(); field.setSelectionRange(field.value.length, field.value.length);
  });
}

let toastTimer;
export function toast(text) {
  let el = document.getElementById('toast');
  if (!el) { el = document.createElement('div'); el.id = 'toast'; el.className = 'toast'; el.setAttribute('role', 'status'); document.body.appendChild(el); }
  el.textContent = text; el.classList.add('on');
  clearTimeout(toastTimer); toastTimer = setTimeout(() => el.classList.remove('on'), 3200);
}
