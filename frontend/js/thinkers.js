// Thinkers as co-authors (docs/features/03): join the chat, one-on-one room, independent reviews,
// the council's first reactions, moderated debates, and a profile behind every bust.
// Every thinker message is a perspective; none can veto (vision §6.4).
import { getJSON, postJSON, streamSSE } from './api.js';
import { state, project, emit, addMessage, currentHypothesis } from './store.js';
import { register, openPanel, actions } from './chat.js';
import { $, esc, md, uid, bustSVG } from './util.js';

// Exact id, or a whole word of the name ("hume", "nightingale", "haytham"); never a fragment like "a".
function thinker(id) {
  const key = String(id || '').toLowerCase().replace(/^\//, '').trim();
  if (!key) return undefined;
  return state.thinkers.find((t) => t.id === key)
    || (key.length >= 3 ? state.thinkers.find((t) => t.name.toLowerCase().split(/[\s-]+/).includes(key)) : undefined);
}

function subject() {
  const d = project();
  const lastUser = [...d.messages].reverse().find((m) => m.role === 'user');
  return currentHypothesis(d)?.text || d.question || lastUser?.text || d.firstObservation || '';
}

async function busy(fn) {
  state.busy += 1; emit();
  try { return await fn(); } finally { state.busy -= 1; emit(); }
}

function ask(tid, message, mode) {
  return busy(() => postJSON(`/api/thinkers/${encodeURIComponent(tid)}/reply`, { project_id: state.projectId, message, mode }));
}

function postThinker(t, out) {
  const d = project();
  d.thinkerSpoke = true;
  if (out?.degraded || !out?.reply) return addMessage({ role: 'note', text: out?.message || `${t.name} couldn't respond.` });
  addMessage({ role: 'thinker', thinker: { id: t.id, name: t.name }, text: out.reply });
}

// ---------- Join the chat ----------
async function join(id, text) {
  const t = thinker(id);
  if (!t) return addMessage({ role: 'note', text: `I don't know a thinker called “${id}”.` });
  const d = project();
  d.activeThinker = { id: t.id, name: t.name };
  addMessage({ role: 'note', text: `${t.name} joins the conversation.` });
  if (text) addMessage({ role: 'user', text });
  const msg = (text || '').trim() || `Here is what I'm working on: ${subject() || 'I am still finding my question.'} What strikes you?`;
  try { postThinker(t, await ask(t.id, msg, 'join')); }
  catch (err) { addMessage({ role: 'note', text: `${t.name} couldn't respond: ${err.message}` }); }
}
// Clicks pass (arg, element); slash commands pass (id, text).
register('join', (id, extra) => join(id, typeof extra === 'string' ? extra : ''));

register('thinkerReply', async (text) => {
  const t = thinker(project().activeThinker?.id);
  if (!t) return;
  try { postThinker(t, await ask(t.id, text, 'join')); }
  catch (err) { addMessage({ role: 'note', text: `${t.name} couldn't respond: ${err.message}` }); }
});

register('leaveThinker', () => {
  const d = project();
  const name = d.activeThinker?.name;
  d.activeThinker = null;
  addMessage({ role: 'note', text: `${name || 'The thinker'} steps back. You're talking with Thoth again.` });
});

// ---------- Council: every thinker's first reaction, written independently ----------
async function council(idea) {
  const d = project();
  const text = (idea || '').trim() || subject();
  if (!text) return addMessage({ role: 'thoth', text: 'Tell me the idea first, then the council can weigh in.' });
  addMessage({ role: 'note', text: `Asking all ${state.thinkers.length} thinkers for a first reaction, each on their own (about 20 seconds)…` });
  try {
    d.council = await busy(() => postJSON('/api/thinkers/council', { project_id: state.projectId, idea: text }));
    d.debatePicks = [];
    d.thinkerSpoke = true;
    addMessage({ role: 'thoth', kind: 'council', chips: [{ label: 'Set up a debate', act: 'panel', arg: 'thinkers' }] });
    openPanel('thinkers');
  } catch (err) {
    addMessage({ role: 'thoth', text: `The council couldn't be gathered: ${err.message}` });
  }
}
register('council', (arg) => council(typeof arg === 'string' ? arg : ''));
actions.council = council;

// ---------- Reviews: chosen thinkers assess the hypothesis without seeing each other ----------
async function reviewHypothesis(ids) {
  const d = project();
  const hyp = currentHypothesis(d)?.text;
  if (!hyp) return addMessage({ role: 'thoth', text: 'Pin a hypothesis first, then thinkers can review it.' });
  const chosen = ids && ids.length ? ids : null;
  addMessage({ role: 'note', text: `${chosen ? chosen.map((i) => thinker(i)?.name).join(', ') : 'Three thinkers'} are reviewing your hypothesis, each on their own…` });
  try {
    const res = await busy(() => postJSON('/api/thinkers/review', { project_id: state.projectId, artifact: 'hypothesis', text: hyp, thinker_ids: chosen }));
    const key = uid('rv');
    d.reviews = d.reviews || {};
    d.reviews[key] = res.reviews || [];
    d.thinkerSpoke = true;
    addMessage({ role: 'thoth', kind: 'reviews', reviews: key });
  } catch (err) {
    addMessage({ role: 'thoth', text: `The reviews couldn't be gathered: ${err.message}` });
  }
}
register('reviewHyp', (arg) => reviewHypothesis(String(arg || '').split(',').filter(Boolean)));

// ---------- Debate: 2-3 thinkers, sequential rounds, then Thoth's distillation ----------
register('pick', (id) => {
  const d = project();
  const picks = d.debatePicks;
  const i = picks.indexOf(id);
  if (i >= 0) picks.splice(i, 1); else { picks.push(id); if (picks.length > 3) picks.shift(); }
  emit();
});

async function debate(ids, topicArg) {
  const picked = (ids && ids.length >= 2 ? ids : ['popper', 'kuhn']).map(thinker).filter(Boolean).slice(0, 3);
  if (picked.length < 2) return addMessage({ role: 'note', text: 'Pick two or three thinkers, e.g. /debate popper kuhn.' });
  const question = (topicArg || '').trim() || subject();
  if (!question) return addMessage({ role: 'thoth', text: 'What should they debate? Share the idea first.' });
  const d = project();
  d.thinkerSpoke = true;
  d.debatePicks = [];
  addMessage({ role: 'thoth', text: `**Debate: ${picked.map((t) => t.name).join(' · ')}.** Three rounds; each answers what was actually said, and I'll sum up at the end.\n\n*Question:* “${question}”` });
  await busy(() => streamSSE('/api/thinkers/debate', {
    project_id: state.projectId, thinker_ids: picked.map((t) => t.id), question, rounds: 3, hypothesis: currentHypothesis(d)?.text || '',
  }, (type, p) => {
    if (type === 'debate_turn') addMessage({ role: 'thinker', thinker: { id: p.thinker_id, name: p.thinker_name }, text: p.text, round: p.round });
    else if (type === 'debate_stopped') addMessage({ role: 'note', text: p.reason });
    else if (type === 'debate_summary') {
      addMessage(p.summary
        ? { role: 'thoth', text: `**Where the debate landed.** ${p.summary}`, chips: picked.map((t) => ({ label: `Talk with ${t.name.split(' ').pop()}`, act: 'join', arg: t.id })) }
        : { role: 'note', text: "The debate is above; I couldn't write a summary of it right now." });
    } else if (type === 'notebook_proposal') {
      d.proposals[p.proposal_id] = { ...p, type, status: 'open' };
      addMessage({ role: 'thoth', kind: 'proposal', proposal: p.proposal_id });
    } else if (type === 'error') addMessage({ role: 'note', text: p.error });
    emit();
  })).catch((err) => addMessage({ role: 'note', text: `The debate couldn't continue: ${err.message}` }));
}
register('debate', (arg) => debate(String(arg || '').split(',').filter(Boolean)));
// "/debate popper kuhn <question>": thinker names come first; everything after them is the question.
actions.debateCmd = (a) => {
  const parts = String(a || '').trim().split(/\s+/).filter(Boolean);
  const named = [];
  while (parts.length && named.length < 3 && thinker(parts[0])) named.push(thinker(parts.shift()).id);
  debate(named.length >= 2 ? named : null, parts.join(' '));
};

// ---------- Profile behind every bust ----------
const PROFILE_SECTIONS = [['life', 'Life and problems'], ['cared_about', 'What they cared about'], ['how_they_thought', 'How their thinking moved'], ['temperament', 'Temperament'], ['blind_spots', 'Blind spots'], ['territory', 'Territory'], ['sources', 'Sources']];

async function openProfile(id) {
  const t = thinker(id);
  if (!t) return;
  let el = document.getElementById('profile');
  if (!el) {
    el = document.createElement('div');
    el.id = 'profile';
    el.className = 'profile-overlay';
    el.addEventListener('click', (e) => { if (e.target === el || e.target.closest('[data-act="join"], [data-act="room"]')) el.hidden = true; });
    document.body.appendChild(el);
  }
  el.hidden = false;
  el.innerHTML = `<div class="profile-card" role="dialog" aria-label="${esc(t.name)}">
    <div class="profile-head">${bustSVG(t.name)}<div><h2>${esc(t.name)}</h2><div class="faint">${esc(t.years || '')}</div></div><button class="btn-ghost" data-act="closeProfile" style="margin-left:auto">Close</button></div>
    <p class="muted">${esc(t.brings || '')}</p>
    <p class="faint">This is the brief ${esc(t.name.split(' ').pop())} is given, which is why it says “you”. Disputed claims are marked; sources are at the end.</p>
    <div class="profile-body faint">Loading…</div></div>`;
  const body = el.querySelector('.profile-body');
  try {
    const p = await getJSON(`/api/thinkers/${encodeURIComponent(t.id)}/profile`);
    body.className = 'profile-body';
    body.innerHTML = PROFILE_SECTIONS.filter(([k]) => p[k]).map(([k, label]) => `<details${k === 'how_they_thought' ? ' open' : ''}><summary>${label}</summary><div class="prose">${md(p[k])}</div></details>`).join('')
      + `<div class="chips"><button class="chip primary" data-act="join" data-arg="${t.id}">Bring ${esc(t.name.split(' ').pop())} into the chat</button><button class="chip" data-act="room" data-arg="${t.id}">Talk one-on-one</button></div>`;
  } catch (err) { body.textContent = `Couldn't load the profile: ${err.message}`; }
}
register('profile', (id) => openProfile(id));
register('closeProfile', () => { const el = document.getElementById('profile'); if (el) el.hidden = true; });

// ---------- One-on-one room ----------
let room = null;
function renderRoom() {
  const el = $('#room');
  if (!room) { el.hidden = true; el.innerHTML = ''; return; }
  el.hidden = false;
  const draft = $('#roomInput')?.value || ''; // a reply landing re-renders the room; keep what's being typed
  el.innerHTML = `<div class="room-head"><button class="bust-btn" data-act="profile" data-arg="${room.t.id}" aria-label="About ${esc(room.t.name)}">${bustSVG(room.t.name)}</button><div><h2>${esc(room.t.name)}</h2><div class="faint">${esc(room.t.years || '')} · one-on-one · remembers this project</div></div>
      <button class="btn-ghost" data-act="leaveRoom" style="margin-left:auto">Return to Thoth</button></div>
    <div class="messages" id="roomMessages">${room.msgs.map((m) => m.role === 'user'
      ? `<div class="msg user"><div class="body">${esc(m.text)}</div></div>`
      : m.role === 'note' ? `<div class="msg note"><div class="body">${esc(m.text)}</div></div>`
      : `<div class="msg thinker"><div class="who">${bustSVG(room.t.name)}</div><div class="body"><div class="name">${esc(room.t.name)}</div><div class="prose">${md(m.text)}</div></div></div>`).join('')}
      ${room.waiting ? '<div class="msg note"><div class="body">…</div></div>' : ''}</div>
    <form class="composer" id="roomForm"><textarea id="roomInput" rows="1" placeholder="Talk with ${esc(room.t.name)}…" aria-label="Message ${esc(room.t.name)}"></textarea><button class="send-btn" aria-label="Send">↑</button></form>`;
  const box = $('#roomMessages'); box.scrollTop = box.scrollHeight;
  const form = $('#roomForm'); const input = $('#roomInput');
  input.value = draft;
  input.focus();
  input.addEventListener('keydown', (e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); form.requestSubmit(); } });
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const text = input.value.trim();
    if (!text || !room) return;
    room.msgs.push({ role: 'user', text }); room.waiting = true; renderRoom();
    await roomSay(text);
  });
}

async function roomSay(text) {
  const current = room;
  try {
    const out = await ask(current.t.id, text, 'room');
    current.msgs.push(out?.reply ? { role: 'thinker', text: out.reply } : { role: 'note', text: out?.message || 'No reply.' });
  } catch (err) { current.msgs.push({ role: 'note', text: `No reply: ${err.message}` }); }
  current.waiting = false;
  if (room === current) renderRoom();
}

async function openRoom(id) {
  const t = thinker(id);
  if (!t) return addMessage({ role: 'note', text: 'Which thinker? e.g. /room popper' });
  room = { t, msgs: [], waiting: true };
  renderRoom();
  await roomSay(`Here is what I'm working on: ${subject() || 'I am still finding my question.'} What strikes you?`);
}
register('room', (id) => openRoom(id));
actions.room = openRoom;

register('leaveRoom', () => {
  if (!room) return;
  const d = project();
  const turns = room.msgs.filter((m) => m.role === 'user').length;
  d.thinkerSpoke = d.thinkerSpoke || turns > 0;
  const last = [...room.msgs].reverse().find((m) => m.role === 'thinker');
  addMessage({ role: 'thoth', text: `You spent ${turns} turn${turns === 1 ? '' : 's'} with **${room.t.name}**, who will remember it.${last ? ` Their last point: “${last.text.slice(0, 220)}${last.text.length > 220 ? '…' : ''}”` : ''}` });
  room = null;
  renderRoom();
});
