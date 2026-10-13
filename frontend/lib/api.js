/**
 * Thoth Authenticated API Client
 *
 * Wraps REST and Server-Sent Event (SSE) calls to the backend,
 * dynamically resolving API_BASE_URL and injecting Supabase Auth tokens.
 */

(function (window) {
  const config = window.THOTH_CONFIG || {};

  function resolveUrl(endpoint) {
    const base = config.API_BASE_URL ? config.API_BASE_URL.replace(/\/+$/, '') : '';
    const path = endpoint.startsWith('/') ? endpoint : `/${endpoint}`;
    return `${base}${path}`;
  }

  async function getAuthHeaders() {
    const headers = {
      'Content-Type': 'application/json',
      'Accept': 'application/json'
    };

    if (window.ThothAuth && typeof window.ThothAuth.getAccessToken === 'function') {
      const token = await window.ThothAuth.getAccessToken();
      if (token) {
        headers['Authorization'] = `Bearer ${token}`;
      }
    }

    return headers;
  }

  const ThothAPI = {
    resolveUrl,

    async get(endpoint, params = {}) {
      const url = new URL(resolveUrl(endpoint), window.location.origin);
      Object.keys(params).forEach(key => url.searchParams.append(key, params[key]));

      const headers = await getAuthHeaders();
      const response = await fetch(url.toString(), { method: 'GET', headers });

      if (!response.ok) {
        throw new Error(`API error ${response.status}: ${await response.text()}`);
      }
      return await response.json();
    },

    async post(endpoint, body = {}) {
      const url = resolveUrl(endpoint);
      const headers = await getAuthHeaders();

      const response = await fetch(url, {
        method: 'POST',
        headers,
        body: JSON.stringify(body)
      });

      if (!response.ok) {
        throw new Error(`API error ${response.status}: ${await response.text()}`);
      }
      return await response.json();
    },

    /**
     * Streams research or dialogue via SSE POST
     */
    async streamSSE(endpoint, body, { onMessage, onError, onDone, signal }) {
      const url = resolveUrl(endpoint);
      const headers = await getAuthHeaders();
      headers['Accept'] = 'text/event-stream';

      try {
        const response = await fetch(url, {
          method: 'POST',
          headers,
          body: JSON.stringify(body),
          signal
        });

        if (!response.ok) {
          const errText = await response.text();
          if (onError) onError(new Error(`Stream HTTP ${response.status}: ${errText}`));
          return;
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder('utf-8');
        let buffer = '';

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split('\n');
          buffer = lines.pop(); // Retain remainder

          for (const line of lines) {
            const trimmed = line.trim();
            if (trimmed.startsWith('data:')) {
              const dataStr = trimmed.slice(5).trim();
              if (dataStr === '[DONE]') {
                if (onDone) onDone();
                return;
              }
              try {
                const parsed = JSON.parse(dataStr);
                if (onMessage) onMessage(parsed);
              } catch (e) {
                // If raw string
                if (onMessage) onMessage({ type: 'text', content: dataStr });
              }
            }
          }
        }

        if (onDone) onDone();
      } catch (err) {
        if (err.name === 'AbortError') {
          console.log('[ThothAPI] Stream aborted by client.');
          return;
        }
        if (onError) onError(err);
      }
    },

    async checkHealth() {
      try {
        const url = resolveUrl('/health');
        const resp = await fetch(url);
        return resp.ok;
      } catch (e) {
        return false;
      }
    }
  };

  window.ThothAPI = ThothAPI;
})(window);
