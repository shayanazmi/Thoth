/**
 * Thoth Authentication & Settings Modal Component
 */

(function (window) {
  const modalHtml = `
  <div id="thothAuthModal" class="thoth-modal-backdrop" style="display:none;">
    <div class="thoth-modal-card">
      <div class="thoth-modal-header">
        <div style="display:flex;align-items:center;gap:10px;">
          <i data-lucide="shield-check" style="color:#e7c77b;width:20px;height:20px;"></i>
          <h3 style="margin:0;font-size:18px;color:#f0f2fa;">Researcher Access & Settings</h3>
        </div>
        <button id="closeAuthModalBtn" class="thoth-icon-btn">&times;</button>
      </div>

      <div class="thoth-modal-tabs">
        <button class="thoth-tab-btn active" id="tabAuthAction">Authentication</button>
        <button class="thoth-tab-btn" id="tabEnvAction">Endpoint Settings</button>
      </div>

      <div class="thoth-modal-body" id="authBodyPanel">
        <div id="authStatusBanner" class="auth-status-banner">
          <span class="status-indicator"></span>
          <span id="authStatusText">Signed in as Guest</span>
        </div>

        <form id="thothAuthForm" style="display:flex;flex-direction:column;gap:12px;margin-top:14px;">
          <div>
            <label style="font-size:12px;color:#a0a4b8;">Email Address</label>
            <input type="email" id="authEmailInput" class="thoth-input" placeholder="researcher@thoth.studio" required />
          </div>
          <div>
            <label style="font-size:12px;color:#a0a4b8;">Password</label>
            <input type="password" id="authPasswordInput" class="thoth-input" placeholder="••••••••••••" required />
          </div>

          <div style="display:flex;gap:10px;margin-top:8px;">
            <button type="submit" id="signInSubmitBtn" class="thoth-primary-btn" style="flex:1;">Sign In</button>
            <button type="button" id="signUpSubmitBtn" class="thoth-secondary-btn" style="flex:1;">Create Account</button>
          </div>
        </form>

        <div id="signOutContainer" style="display:none;margin-top:16px;">
          <button id="signOutBtn" class="thoth-danger-btn" style="width:100%;">Disconnect Session</button>
        </div>

        <div id="authFeedbackMsg" style="font-size:12px;margin-top:10px;display:none;"></div>
      </div>

      <div class="thoth-modal-body" id="envBodyPanel" style="display:none;">
        <p style="font-size:12px;color:#8e92a8;margin-top:0;">
          Override service connection endpoints for custom cloud deployments (saved locally in browser):
        </p>
        <div style="display:flex;flex-direction:column;gap:10px;">
          <div>
            <label style="font-size:11px;color:#a0a4b8;">FastAPI Backend Gateway URL (API_BASE_URL)</label>
            <input type="text" id="settingApiUrl" class="thoth-input" placeholder="e.g. https://api-thoth.up.railway.app" />
          </div>
          <div>
            <label style="font-size:11px;color:#a0a4b8;">Supabase Project URL</label>
            <input type="text" id="settingSupabaseUrl" class="thoth-input" placeholder="e.g. https://xyz.supabase.co" />
          </div>
          <div>
            <label style="font-size:11px;color:#a0a4b8;">Supabase Public Anon Key</label>
            <input type="password" id="settingSupabaseAnonKey" class="thoth-input" placeholder="eyJhbGciOi..." />
          </div>
          <button id="saveSettingsBtn" class="thoth-primary-btn" style="margin-top:8px;">Save Settings</button>
        </div>
      </div>
    </div>
  </div>
  `;

  class AuthModalComponent {
    init() {
      if (document.getElementById('thothAuthModal')) return;

      const container = document.createElement('div');
      container.innerHTML = modalHtml;
      document.body.appendChild(container.firstElementChild);

      this.modal = document.getElementById('thothAuthModal');
      this.bindEvents();
      this.updateState();

      if (window.lucide && typeof window.lucide.createIcons === 'function') {
        window.lucide.createIcons();
      }
    }

    bindEvents() {
      const closeBtn = document.getElementById('closeAuthModalBtn');
      const form = document.getElementById('thothAuthForm');
      const signUpBtn = document.getElementById('signUpSubmitBtn');
      const signOutBtn = document.getElementById('signOutBtn');
      const saveSettingsBtn = document.getElementById('saveSettingsBtn');
      const tabAuth = document.getElementById('tabAuthAction');
      const tabEnv = document.getElementById('tabEnvAction');

      closeBtn.onclick = () => this.hide();
      this.modal.onclick = (e) => {
        if (e.target === this.modal) this.hide();
      };

      tabAuth.onclick = () => {
        tabAuth.classList.add('active');
        tabEnv.classList.remove('active');
        document.getElementById('authBodyPanel').style.display = 'block';
        document.getElementById('envBodyPanel').style.display = 'none';
      };

      tabEnv.onclick = () => {
        tabEnv.classList.add('active');
        tabAuth.classList.remove('active');
        document.getElementById('authBodyPanel').style.display = 'none';
        document.getElementById('envBodyPanel').style.display = 'block';
      };

      form.onsubmit = async (e) => {
        e.preventDefault();
        const email = document.getElementById('authEmailInput').value;
        const pass = document.getElementById('authPasswordInput').value;
        this.showMessage('Authenticating...', 'info');
        try {
          await window.ThothAuth.signInWithPassword(email, pass);
          this.showMessage('Signed in successfully.', 'success');
          setTimeout(() => this.hide(), 800);
        } catch (err) {
          this.showMessage(err.message, 'error');
        }
      };

      signUpBtn.onclick = async () => {
        const email = document.getElementById('authEmailInput').value;
        const pass = document.getElementById('authPasswordInput').value;
        if (!email || !pass) {
          this.showMessage('Please provide both email and password.', 'error');
          return;
        }
        this.showMessage('Creating account...', 'info');
        try {
          await window.ThothAuth.signUp(email, pass);
          this.showMessage('Account created! Please check your email for confirmation.', 'success');
        } catch (err) {
          this.showMessage(err.message, 'error');
        }
      };

      signOutBtn.onclick = async () => {
        await window.ThothAuth.signOut();
        this.showMessage('Signed out.', 'info');
        this.updateState();
      };

      saveSettingsBtn.onclick = () => {
        const apiUrl = document.getElementById('settingApiUrl').value.trim();
        const supaUrl = document.getElementById('settingSupabaseUrl').value.trim();
        const supaKey = document.getElementById('settingSupabaseAnonKey').value.trim();

        window.THOTH_CONFIG.setOverride('API_BASE_URL', apiUrl);
        window.THOTH_CONFIG.setOverride('SUPABASE_URL', supaUrl);
        window.THOTH_CONFIG.setOverride('SUPABASE_ANON_KEY', supaKey);

        alert('Settings saved. Reloading page to apply new endpoints.');
        window.location.reload();
      };

      window.addEventListener('thoth:auth:state', () => this.updateState());
    }

    updateState() {
      const user = window.ThothAuth?.currentUser;
      const statusText = document.getElementById('authStatusText');
      const signOutContainer = document.getElementById('signOutContainer');
      const form = document.getElementById('thothAuthForm');

      if (user && user.email) {
        statusText.textContent = `Connected: ${user.email}`;
        signOutContainer.style.display = 'block';
        form.style.display = 'none';
      } else {
        statusText.textContent = 'Guest Researcher Mode';
        signOutContainer.style.display = 'none';
        form.style.display = 'flex';
      }

      // Prepopulate settings inputs
      const config = window.THOTH_CONFIG || {};
      if (document.getElementById('settingApiUrl')) {
        document.getElementById('settingApiUrl').value = config.API_BASE_URL || '';
        document.getElementById('settingSupabaseUrl').value = config.SUPABASE_URL || '';
        document.getElementById('settingSupabaseAnonKey').value = config.SUPABASE_ANON_KEY || '';
      }
    }

    showMessage(text, type) {
      const msg = document.getElementById('authFeedbackMsg');
      msg.textContent = text;
      msg.style.display = 'block';
      msg.style.color = type === 'error' ? '#ef4444' : (type === 'success' ? '#10b981' : '#e7c77b');
    }

    show() {
      this.init();
      this.updateState();
      this.modal.style.display = 'flex';
    }

    hide() {
      if (this.modal) this.modal.style.display = 'none';
    }
  }

  window.ThothAuthModal = new AuthModalComponent();
})(window);
