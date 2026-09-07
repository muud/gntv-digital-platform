import '../../shared/src/style.css';
import { store } from '../../shared/src/state.js';
import { VODS, CHANNELS } from '../../shared/src/utils/mockData.js';
import { initPartnerPortalDashboard } from './components/PartnerPortalDashboard.js';
import { initStudioDashboard } from './components/StudioDashboard.js';

const initApp = () => {
  const viewportContainer = document.querySelector('#viewport-container');
  const emergencyBanner = document.querySelector('#emergency-banner');
  const emergencyBannerText = document.querySelector('#emergency-banner-text');

  if (window.location.pathname.includes('partner-portal')) {
    store.setState('systemMode', 'partner-portal');
    const topNavContainer = document.querySelector('.top-nav-links');
    const authSection = document.querySelector('#header-auth-section');
    const headerActiveChannel = document.querySelector('#header-active-channel');
    if (topNavContainer) {
      topNavContainer.innerHTML = '<span class="top-nav-item active">Partner Self-Service Portal</span>';
    }
    if (authSection) {
      authSection.innerHTML = '<a href="/" style="color: var(--brand-primary); font-weight: 800; text-decoration: none; font-size: 12px;">Studio Login</a>';
    }
    if (headerActiveChannel) {
      headerActiveChannel.textContent = 'Partner Financial Reporting';
    }
    viewportContainer.innerHTML = '';
    initPartnerPortalDashboard(viewportContainer);
    return;
  }

  // Header telemetry nodes
  const headerViewerCount = document.querySelector('#header-viewer-count');
  const headerBitrate = document.querySelector('#header-bitrate');
  const headerFps = document.querySelector('#header-fps');
  const headerActiveChannel = document.querySelector('#header-active-channel');

  // Sync state between tabs/pages through localStorage if updated
  window.addEventListener('storage', (e) => {
    if (e.key === 'gntv_user' || e.key === 'gntv_system_mode') {
      window.location.reload();
    }
  });

  // Ensure default user is present
  if (!store.getState("user")) {
    const activeProf = store.getState("activeProfile") || store.getState("profilesList")[0];
    store.signIn(activeProf.isKids ? "kids@gntv.com" : "admin@gntv.com", activeProf.name);
  }

  // Set system mode to back (enterprise/control mode)
  store.setState('systemMode', 'back');

  // Check operator credentials token
  const hasStudioToken = sessionStorage.getItem('gntv_studio_token');
  const loginDialog = document.querySelector('#studio-operator-login-dialog');

  // Auth steps DOM
  const step1 = document.querySelector('#operator-auth-step-1');
  const step2 = document.querySelector('#operator-auth-step-2');
  const errorBox1 = document.querySelector('#operator-auth-error-step1');
  const errorBox2 = document.querySelector('#operator-auth-error-step2');
  const submitBtn1 = document.querySelector('#btn-submit-operator-step1');
  const submitBtn2 = document.querySelector('#btn-submit-operator-step2');
  const operatorUsername = document.querySelector('#operator-username');
  const operatorPassword = document.querySelector('#operator-password');
  const operatorTotp = document.querySelector('#operator-totp-token');

  function checkLockout() {
    const lockedUntil = localStorage.getItem('gntv_studio_lockout');
    if (lockedUntil && Date.now() < parseInt(lockedUntil)) {
      const minsLeft = Math.ceil((parseInt(lockedUntil) - Date.now()) / 60000);
      const lockMsg = `SECURITY BLOCKED: TOO MANY ATTEMPTS. TRY AGAIN IN ${minsLeft} MINS.`;
      if (errorBox1) {
        errorBox1.textContent = lockMsg;
        errorBox1.style.display = 'block';
      }
      submitBtn1.disabled = true;
      return true;
    }
    return false;
  }

  function recordFailedAttempt() {
    let attempts = parseInt(localStorage.getItem('gntv_studio_attempts') || '0');
    attempts++;
    if (attempts >= 3) {
      localStorage.setItem('gntv_studio_lockout', (Date.now() + 15 * 60000).toString());
      localStorage.setItem('gntv_studio_attempts', '0');
      checkLockout();
    } else {
      localStorage.setItem('gntv_studio_attempts', attempts.toString());
      if (errorBox1) {
        errorBox1.textContent = `INVALID CREDENTIALS. ATTEMPT ${attempts}/3`;
        errorBox1.style.display = 'block';
      }
    }
  }

  const showVerificationStep2 = () => {
    step1.style.display = 'none';
    step2.style.display = 'flex';
    if (operatorTotp) operatorTotp.focus();
  };

  const completeOperatorAuth = () => {
    sessionStorage.setItem('gntv_studio_token', 'secure_eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9');
    if (loginDialog) loginDialog.close();
    bootStudioApp();
  };

  const handleStep1Submit = () => {
    if (checkLockout()) return;
    const username = operatorUsername.value.trim();
    const password = operatorPassword.value.trim();

    // Verification Logic: Admin / Studio login credentials
    if (username === 'admin' && (password === 'gntv-secure-2026' || password === 'GNTV DIGITAL, ALL EVERYWHERE_Secure2026!')) {
      localStorage.setItem('gntv_studio_attempts', '0');
      if (errorBox1) errorBox1.style.display = 'none';
      showVerificationStep2();
    } else {
      recordFailedAttempt();
    }
  };

  const handleStep2Submit = () => {
    const code = operatorTotp.value.trim();
    if (code === '884422') {
      completeOperatorAuth();
    } else {
      if (errorBox2) {
        errorBox2.textContent = 'INVALID TOTP TOKEN SECURITY SIGNAL';
        errorBox2.style.display = 'block';
      }
      operatorTotp.value = '';
    }
  };

  if (submitBtn1) submitBtn1.addEventListener('click', handleStep1Submit);
  if (submitBtn2) submitBtn2.addEventListener('click', handleStep2Submit);

  if (operatorPassword) {
    operatorPassword.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') handleStep1Submit();
    });
  }
  if (operatorTotp) {
    operatorTotp.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') handleStep2Submit();
    });
  }

  // Bootstrapper for Back Office
  function bootStudioApp() {
    // Role permissions validation
    const user = store.getState('user');
    const userRole = user ? user.role : 'free';

    // Viewer: role === free
    const isViewer = userRole === 'free';
    if (isViewer) {
      // Permission Denied Interface
      viewportContainer.innerHTML = `
        <div style="flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 48px; text-align: center; font-family: var(--font-sans); min-height: calc(100vh - 120px);">
          <div style="font-size: 64px; margin-bottom: 24px;">🚫</div>
          <h2 style="font-size: 28px; font-weight: 850; letter-spacing: -1px; text-transform: uppercase; color: var(--brand-primary); margin-bottom: 12px;">Permission Denied</h2>
          <p style="color: rgba(255,255,255,0.6); max-width: 500px; line-height: 1.6; font-size: 14px; margin-bottom: 32px;">
            Your account status (${userRole.toUpperCase()}) does not possess clearance credentials to operate this studio console terminal. Please sign in as an Operator or Admin.
          </p>
          <div style="display: flex; gap: 16px;">
            <a href="/" style="background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.12); color: #fff; padding: 12px 24px; border-radius: 8px; text-decoration: none; font-weight: 700; font-size: 13px;">◀ Exit to Viewer</a>
            <button id="btn-unauthorized-signout" style="background: var(--brand-primary); border: none; color: #fff; padding: 12px 24px; border-radius: 8px; font-weight: 700; font-size: 13px; cursor: pointer; box-shadow: 0 4px 15px var(--brand-primary-glow);">Sign In as Admin</button>
          </div>
        </div>
      `;

      viewportContainer.querySelector('#btn-unauthorized-signout').addEventListener('click', () => {
        store.signOut();
        sessionStorage.removeItem('gntv_studio_token');
        window.location.reload();
      });
      return;
    }

    // Load Studio OS tabs
    viewportContainer.innerHTML = '';
    const studioWrapper = document.createElement('div');
    viewportContainer.appendChild(studioWrapper);
    initStudioDashboard(studioWrapper);

    // Setup navbar options
    const topNavContainer = document.querySelector('.top-nav-links');
    if (topNavContainer) {
      topNavContainer.innerHTML = `
        <span class="top-nav-item active">📡 GNTV DIGITAL, ALL EVERYWHERE Media OS Console</span>
        <a href="/" class="top-nav-item" style="color: var(--brand-primary); font-weight: 800; text-decoration: none; display: flex; align-items: center; gap: 4px;">◀ Exit to Viewer</a>
      `;
    }

    // Render operator identity pill
    const authSection = document.querySelector('#header-auth-section');
    if (authSection) {
      authSection.innerHTML = `
        <div style="display: flex; align-items: center; gap: 8px; background: rgba(255, 255, 255, 0.04); border: 1px solid rgba(255, 255, 255, 0.08); padding: 6px 14px; border-radius: 20px; font-size: 12px; font-weight: 600;">
          <span style="font-family: var(--font-mono); font-size: 9px; background: var(--brand-secondary); color: #000; padding: 2px 6px; border-radius: 4px; font-weight: 800;">OS: SECURE</span>
          <span style="color: rgba(255,255,255,0.7);">${user.name} (${userRole.toUpperCase()})</span>
          <span style="color: rgba(255,255,255,0.2)">|</span>
          <button id="btn-operator-logout" style="background: transparent; border: none; cursor: pointer; color: var(--brand-primary); font-size: 11px; font-weight: 700;">Lock Console</button>
        </div>
      `;

      authSection.querySelector('#btn-operator-logout').addEventListener('click', () => {
        sessionStorage.removeItem('gntv_studio_token');
        window.location.reload();
      });
    }
  }

  // Active Alert Signal
  store.subscribe('emergencyAlert', (alertState) => {
    if (alertState.active) {
      emergencyBanner.classList.add('active');
      emergencyBannerText.textContent = alertState.message || 'CRITICAL WARNING: BROADCAST SIGNAL INTERCEPTED';
    } else {
      emergencyBanner.classList.remove('active');
    }
  });

  // Reactive Telemetry metrics
  store.subscribe('viewerCount', (count) => {
    if (headerViewerCount) headerViewerCount.textContent = count.toLocaleString();
  });
  store.subscribe('bitrate', (bitrate) => {
    if (headerBitrate) headerBitrate.textContent = bitrate;
  });
  store.subscribe('fps', (fps) => {
    if (headerFps) headerFps.textContent = `${fps} FPS`;
  });
  store.subscribe('activeChannel', (ch) => {
    if (headerActiveChannel) headerActiveChannel.textContent = ch.name;
  });

  // Start Auth Flow
  if (hasStudioToken) {
    bootStudioApp();
  } else {
    checkLockout();
    if (loginDialog) loginDialog.showModal();
  }
};

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initApp);
} else {
  initApp();
}
