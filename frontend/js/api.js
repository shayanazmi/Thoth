// Thin client for the Thoth backend. One chat stream (/api/chat/stream) plus a few JSON routes.

const BASE = window.THOTH_API_BASE || '';

export async function getJSON(path) {
  const res = await fetch(BASE + path, { headers: { Accept: 'application/json' } });
  if (!res.ok) throw new Error(`${path} → ${res.status}`);
  return res.json();
}

export async function postJSON(path, body) {
  const res = await fetch(BASE + path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
    body: JSON.stringify(body || {}),
  });
  if (!res.ok) throw new Error(`${path} → ${res.status}`);
  return res.json();
}

// Streams typed cards from the unified chat endpoint. sse-starlette frames lines
// with CRLF, so normalise before splitting on blank lines.
export function streamChat(body, onEvent) {
  return streamSSE('/api/chat/stream', body, onEvent);
}

export async function streamSSE(path, body, onEvent) {
  const res = await fetch(BASE + path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
    body: JSON.stringify(body),
  });
  if (!res.ok || !res.body) throw new Error(`Thoth could not be reached (${res.status}).`);
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, '\n');
    let idx;
    while ((idx = buffer.indexOf('\n\n')) >= 0) {
      const frame = buffer.slice(0, idx);
      buffer = buffer.slice(idx + 2);
      const data = frame.split('\n').filter((l) => l.startsWith('data: ')).map((l) => l.slice(6)).join('\n');
      if (!data) continue;
      try {
        const evt = JSON.parse(data);
        onEvent(evt.event, evt.payload || {});
      } catch (_) { /* ignore keep-alives and malformed frames */ }
    }
  }
}
