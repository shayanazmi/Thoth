/**
 * Thoth Supabase Authentication Client
 *
 * Implements client-side session handling, token management, and auto-refresh
 * using only the public SUPABASE_ANON_KEY.
 */

(function (window) {
  const config = window.THOTH_CONFIG || {};

  class ThothAuthClient {
    constructor() {
      this.client = null;
      this.currentSession = null;
      this.currentUser = null;
      this.listeners = [];

      this.init();
    }

    init() {
      const url = config.SUPABASE_URL;
      const key = config.SUPABASE_ANON_KEY;

      if (url && key && window.supabase && typeof window.supabase.createClient === 'function') {
        try {
          this.client = window.supabase.createClient(url, key, {
            auth: {
              persistSession: true,
              autoRefreshToken: true,
              detectSessionInUrl: true
            }
          });

          // Subscribe to auth state transitions
          this.client.auth.onAuthStateChange((event, session) => {
            this.currentSession = session;
            this.currentUser = session?.user || null;
            this._notifyListeners(event, session);
          });

          // Fetch initial session
          this.client.auth.getSession().then(({ data: { session }, error }) => {
            if (!error && session) {
              this.currentSession = session;
              this.currentUser = session.user;
              this._notifyListeners('INITIAL_SESSION', session);
            }
          });
        } catch (err) {
          console.warn('[ThothAuth] Failed to initialize Supabase client:', err);
        }
      } else {
        // Fallback: Guest / Local offline mode
        this.currentSession = null;
        this.currentUser = {
          id: 'guest-researcher-001',
          email: 'guest@thoth.studio',
          user_metadata: { full_name: 'Guest Scribe' }
        };
      }
    }

    isConfigured() {
      return this.client !== null;
    }

    async getSession() {
      if (this.client) {
        const { data: { session } } = await this.client.auth.getSession();
        this.currentSession = session;
        return session;
      }
      return this.currentSession;
    }

    async getAccessToken() {
      const session = await this.getSession();
      return session?.access_token || null;
    }

    async signInWithPassword(email, password) {
      if (!this.client) {
        throw new Error('Supabase client is not configured. Please supply SUPABASE_URL and SUPABASE_ANON_KEY.');
      }
      const { data, error } = await this.client.auth.signInWithPassword({ email, password });
      if (error) throw error;
      this.currentSession = data.session;
      this.currentUser = data.user;
      return data;
    }

    async signUp(email, password, metadata = {}) {
      if (!this.client) {
        throw new Error('Supabase client is not configured.');
      }
      const { data, error } = await this.client.auth.signUp({
        email,
        password,
        options: { data: metadata }
      });
      if (error) throw error;
      return data;
    }

    async signInWithOAuth(provider) {
      if (!this.client) {
        throw new Error('Supabase client is not configured.');
      }
      const { data, error } = await this.client.auth.signInWithOAuth({
        provider,
        options: { redirectTo: window.location.origin }
      });
      if (error) throw error;
      return data;
    }

    async signOut() {
      if (this.client) {
        await this.client.auth.signOut();
      }
      this.currentSession = null;
      this.currentUser = null;
      this._notifyListeners('SIGNED_OUT', null);
    }

    onAuthStateChange(callback) {
      if (typeof callback === 'function') {
        this.listeners.push(callback);
      }
    }

    _notifyListeners(event, session) {
      for (const listener of this.listeners) {
        try {
          listener(event, session);
        } catch (e) {
          console.error('[ThothAuth] Listener error:', e);
        }
      }
      window.dispatchEvent(new CustomEvent('thoth:auth:state', { detail: { event, session } }));
    }
  }

  window.ThothAuth = new ThothAuthClient();
})(window);
