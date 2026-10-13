/**
 * Thoth Web Client - Centralized Runtime Configuration
 *
 * Reads configuration from runtime window.__ENV__ (injected via Docker / Railway),
 * falls back to localStorage overrides, and provides sensible defaults.
 *
 * SECURITY: Never place secret keys (e.g. SUPABASE_SERVICE_ROLE_KEY) here.
 * Only public client keys (SUPABASE_ANON_KEY) are permitted.
 */

(function (window) {
  const env = window.__ENV__ || {};

  const CONFIG = {
    // API Gateway URL for research and chat streaming
    // Empty string defaults to same-origin relative endpoints (/api/...)
    API_BASE_URL: env.API_BASE_URL || localStorage.getItem('thoth_api_base_url') || '',

    // Supabase Public Client Credentials
    SUPABASE_URL: env.SUPABASE_URL || localStorage.getItem('thoth_supabase_url') || '',
    SUPABASE_ANON_KEY: env.SUPABASE_ANON_KEY || localStorage.getItem('thoth_supabase_anon_key') || '',

    // Application Metadata
    APP_NAME: 'Thoth Research Intelligence Studio',
    VERSION: '3.0.0',
    ENVIRONMENT: env.ENVIRONMENT || 'production',

    // Helper to persist runtime overrides for local testing
    setOverride(key, value) {
      if (value) {
        localStorage.setItem(`thoth_${key.toLowerCase()}`, value);
        CONFIG[key] = value;
      } else {
        localStorage.removeItem(`thoth_${key.toLowerCase()}`);
      }
    }
  };

  window.THOTH_CONFIG = CONFIG;
})(window);
