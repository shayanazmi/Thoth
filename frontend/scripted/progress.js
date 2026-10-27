// What the viewer has watched, where they stopped, speed and captions. Per browser, best effort:
// storage can be blocked, and the tour works the same without it.
const KEY = 'thoth.tour.v1';
let mem = {};

export function get() {
  try { return JSON.parse(localStorage.getItem(KEY) || '{}'); } catch (_) { return mem; }
}
export function set(patch) {
  const next = { ...get(), ...patch };
  mem = next;
  try { localStorage.setItem(KEY, JSON.stringify(next)); } catch (_) {}
}
export function watched(branch, chapterId) {
  const w = get().watched || {};
  w[branch] = [...new Set([...(w[branch] || []), chapterId])];
  set({ watched: w });
}
export const watchedSet = (branch) => new Set((get().watched || {})[branch] || []);
