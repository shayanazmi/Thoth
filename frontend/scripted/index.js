// The guided tour. Everything about it lives in this folder; main.js imports this file once and ignores a
// failure, so deleting frontend/scripted/ removes the tour completely.
// For people: the "Try the demo" button on the landing page. The URL params below are developer tools.
//   ?demo                     open the hunch picker          ?demo&branch=nurses&chapter=5   jump straight in
//   ?demo&autoplay&clean      a clean film for screen recording (no controls, beats resolve themselves)
//   ?demo&live                Live mode: your real backend; the tour explains and waits for you
//   ?demo&live&record[&autopilot][&sink=URL]   record a real run into fixtures (see README.md)
import * as director from './director.js';

export async function install(core) {
  // A tour closed by closing the tab leaves its demo project behind; tidy it.
  try { Object.keys(localStorage).filter((k) => k.startsWith('thoth.ui.v2.demo_')).forEach((k) => localStorage.removeItem(k)); } catch (_) {}
  if (core.state.projectId === 'demo_thoth_tour') { core.state.projectId = null; core.emit(); }

  const css = document.createElement('link');
  css.rel = 'stylesheet'; css.href = '/scripted/tour.css?v=2';
  document.head.appendChild(css);

  const branches = await fetch('/scripted/branches.json').then((r) => r.json()).catch(() => []);
  director.init({
    ...core,
    startOwn: (q) => { core.actions.home?.(); setTimeout(() => { const i = document.getElementById('homeInput'); if (i) { i.value = q; i.focus(); } }, 900); },
  }, branches);

  const open = (opts = {}) => director.start(opts);

  // The demo is optional: it starts only from this button on the landing page. The intro is never touched.
  const decorate = () => {
    const copy = document.querySelector('.home-copy');
    if (copy && !copy.querySelector('.tour-invite')) {
      const resume = director.resumeLabel();
      (copy.querySelector('.home-promises') || copy.lastElementChild).insertAdjacentHTML('beforebegin', `<button class="tour-invite" type="button"><span class="tour-play"><svg viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z"/></svg></span><span><b>${resume ? 'Resume the demo' : 'Try the demo'}</b><small>${resume || 'Watch Thoth go from a stray thought to a drafted proposal · 3 min'}</small></span></button>`);
      copy.querySelector('.tour-invite').addEventListener('click', () => open());
    }
  };
  core.subscribe(decorate);
  decorate();

  // Developer deep links (recording, screen capture) still work, but only after the intro has played.
  const q = new URLSearchParams(location.search);
  if (q.has('demo')) {
    const intro = document.getElementById('intro');
    while (intro && !intro.hidden) await new Promise((r) => setTimeout(r, 300));
    open({
      branch: q.get('branch'), chapter: +(q.get('chapter') || 0), reel: q.get('reel'),
      mode: q.has('live') || q.has('record') ? 'live' : 'scripted',
      autoplay: q.has('autoplay'), clean: q.has('clean'), recording: q.has('record'), autopilot: q.has('autopilot'),
    });
  }
}
