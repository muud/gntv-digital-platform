/**
 * GNTV DIGITAL — Multi-Tenant Partner Syndication Embed SDK
 * Lightweight, secure video player and authorization client.
 */

(function (global) {
  'use strict';

  const DEFAULT_CONFIG = {
    apiBaseUrl: '',
    autoplay: false,
    muted: false,
    controls: true,
    playsinline: true,
    showBranding: true,
    retryOnFailure: false,
  };

  /**
   * Generates a unique playback session ID.
   */
  function generateSessionId() {
    return 'gntv_sess_' + Math.random().toString(36).substring(2, 15) + Date.now().toString(36);
  }

  /**
   * Helper to safely escape HTML.
   */
  function escapeHtml(str) {
    if (!str) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  class GNTVSecureEmbedPlayer {
    constructor(options) {
      if (!options) {
        throw new Error('[GNTV Embed SDK] Options object is required.');
      }
      if (!options.target) {
        throw new Error('[GNTV Embed SDK] "target" container or selector is required.');
      }
      if (!options.token) {
        throw new Error('[GNTV Embed SDK] Signed "token" is required.');
      }

      this.config = Object.assign({}, DEFAULT_CONFIG, options);
      this.targetElement = typeof this.config.target === 'string'
        ? document.querySelector(this.config.target)
        : this.config.target;

      if (!this.targetElement) {
        throw new Error(`[GNTV Embed SDK] Target container element "${this.config.target}" not found.`);
      }

      this.token = this.config.token;
      this.contentId = this.config.contentId || '';
      this.apiBaseUrl = (this.config.apiBaseUrl || '').replace(/\/+$/, '');
      this.playbackSessionId = generateSessionId();
      this.authorizationData = null;
      this.videoElement = null;
      this.isDestroyed = false;
      this.hasStarted = false;

      this.init();
    }

    async init() {
      this.renderLoadingState();
      try {
        const authData = await this.authorizeToken();
        if (this.isDestroyed) return;
        this.authorizationData = authData;
        this.renderPlayer(authData);
        if (typeof this.config.onReady === 'function') {
          this.config.onReady(this);
        }
      } catch (err) {
        if (this.isDestroyed) return;
        this.renderErrorState(err.message || 'Authorization failed.');
        this.reportTelemetryEvent('playback_error', err.message);
        if (typeof this.config.onError === 'function') {
          this.config.onError(err);
        }
      }
    }

    async authorizeToken() {
      const domain = window.location.hostname || 'localhost';
      const origin = window.location.origin || '';
      const endpoint = `${this.apiBaseUrl}/api/v1/embed/authorize`;

      const response = await fetch(endpoint, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Accept': 'application/json',
        },
        body: JSON.stringify({
          token: this.token,
          domain: domain,
          origin: origin,
          playback_session_id: this.playbackSessionId,
        }),
      });

      if (!response.ok) {
        let errorDetail = 'Unauthorized embed playback';
        try {
          const body = await response.json();
          if (body && body.detail) {
            errorDetail = body.detail;
          }
        } catch (_) {}
        throw new Error(errorDetail);
      }

      return await response.json();
    }

    renderLoadingState() {
      this.targetElement.innerHTML = `
        <div class="gntv-embed-container" style="position:relative;width:100%;height:100%;min-height:300px;background:#05070a;display:flex;align-items:center;justify-content:center;font-family:system-ui,-apple-system,sans-serif;color:#f3f4f6;border-radius:8px;overflow:hidden;">
          <div style="text-align:center;">
            <div style="width:40px;height:40px;border:3px solid rgba(255,255,255,0.15);border-top-color:#ff8a00;border-radius:50%;animation:gntv-spin 1s linear infinite;margin:0 auto 12px auto;"></div>
            <div style="font-size:13px;font-weight:500;letter-spacing:0.02em;color:#9ca3af;">Verifying secure broadcast ticket...</div>
          </div>
          <style>
            @keyframes gntv-spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
          </style>
        </div>
      `;
    }

    renderErrorState(message) {
      this.targetElement.innerHTML = `
        <div class="gntv-embed-container gntv-embed-error" style="position:relative;width:100%;height:100%;min-height:300px;background:#0d1117;display:flex;align-items:center;justify-content:center;font-family:system-ui,-apple-system,sans-serif;color:#f85149;padding:24px;box-sizing:border-box;border-radius:8px;border:1px solid #30363d;">
          <div style="text-align:center;max-width:380px;">
            <div style="width:48px;height:48px;background:rgba(248,81,73,0.12);border-radius:50%;display:flex;align-items:center;justify-content:center;margin:0 auto 14px auto;">
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="8" x2="12" y2="12"></line><line x1="12" y1="16" x2="12.01" y2="16"></line></svg>
            </div>
            <div style="font-size:15px;font-weight:600;color:#f0f6fc;margin-bottom:6px;">Playback Restricted</div>
            <div style="font-size:13px;line-height:1.5;color:#8b949e;margin-bottom:14px;">${escapeHtml(message)}</div>
            <div style="font-size:11px;color:#6e7681;letter-spacing:0.05em;text-transform:uppercase;">GNTV Digital Security</div>
          </div>
        </div>
      `;
    }

    renderPlayer(authData) {
      const branding = authData.branding || {};
      const accentColor = branding.accent_color || '#ff8a00';
      const displayName = branding.display_name || 'GNTV Partner';
      const logoUrl = branding.logo_url;
      const showAttribution = branding.show_gntv_attribution !== false;

      this.targetElement.innerHTML = `
        <div class="gntv-embed-container" style="position:relative;width:100%;height:100%;min-height:300px;background:#000;border-radius:8px;overflow:hidden;font-family:system-ui,-apple-system,sans-serif;">
          <!-- Video Element -->
          <video
            class="gntv-embed-video"
            style="width:100%;height:100%;object-fit:contain;display:block;"
            ${this.config.autoplay ? 'autoplay' : ''}
            ${this.config.muted ? 'muted' : ''}
            ${this.config.controls ? 'controls' : ''}
            ${this.config.playsinline ? 'playsinline' : ''}
            src="${escapeHtml(authData.playback_url)}"
          ></video>

          <!-- Top White-Label Branding Overlay -->
          <div class="gntv-embed-overlay" style="position:absolute;top:0;left:0;right:0;padding:12px 16px;background:linear-gradient(180deg,rgba(0,0,0,0.7) 0%,rgba(0,0,0,0) 100%);pointer-events:none;display:flex;align-items:center;justify-content:space-between;z-index:10;">
            <div style="display:flex;align-items:center;gap:8px;">
              ${logoUrl ? `<img src="${escapeHtml(logoUrl)}" alt="${escapeHtml(displayName)}" style="max-height:22px;max-width:100px;object-fit:contain;" />` : ''}
              <span style="font-size:12px;font-weight:600;color:#fff;text-shadow:0 1px 2px rgba(0,0,0,0.8);">${escapeHtml(displayName)}</span>
            </div>
            ${showAttribution ? `
              <div style="display:flex;align-items:center;gap:4px;font-size:10px;color:rgba(255,255,255,0.7);background:rgba(0,0,0,0.4);padding:2px 6px;border-radius:4px;border:1px solid rgba(255,255,255,0.1);">
                <span>Powered by</span>
                <span style="font-weight:700;color:${escapeHtml(accentColor)};">GNTV</span>
              </div>
            ` : ''}
          </div>
        </div>
      `;

      this.videoElement = this.targetElement.querySelector('video');
      this.attachVideoListeners();
    }

    attachVideoListeners() {
      if (!this.videoElement) return;

      this.videoElement.addEventListener('play', () => {
        if (!this.hasStarted) {
          this.hasStarted = true;
          this.reportTelemetryEvent('playback_start');
        }
        if (typeof this.config.onPlay === 'function') {
          this.config.onPlay();
        }
      });

      this.videoElement.addEventListener('pause', () => {
        if (typeof this.config.onPause === 'function') {
          this.config.onPause();
        }
      });

      this.videoElement.addEventListener('ended', () => {
        this.reportTelemetryEvent('playback_complete');
        if (typeof this.config.onEnded === 'function') {
          this.config.onEnded();
        }
      });

      this.videoElement.addEventListener('error', (e) => {
        const errorMsg = this.videoElement.error ? this.videoElement.error.message : 'Media playback error';
        this.reportTelemetryEvent('playback_error', errorMsg);
        if (typeof this.config.onError === 'function') {
          this.config.onError(e);
        }
      });
    }

    async reportTelemetryEvent(eventType, errorCode = null) {
      if (this.isDestroyed) return;
      try {
        const domain = window.location.hostname || 'localhost';
        const origin = window.location.origin || '';
        const endpoint = `${this.apiBaseUrl}/api/v1/embed/events`;

        await fetch(endpoint, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            token: this.token,
            event_type: eventType,
            domain: domain,
            origin: origin,
            playback_session_id: this.playbackSessionId,
            error_code: errorCode,
          }),
        });
      } catch (_) {
        // Suppress background analytics logging errors
      }
    }

    play() {
      if (this.videoElement) {
        return this.videoElement.play();
      }
    }

    pause() {
      if (this.videoElement) {
        this.videoElement.pause();
      }
    }

    destroy() {
      this.isDestroyed = true;
      if (this.videoElement) {
        this.videoElement.pause();
        this.videoElement.removeAttribute('src');
        this.videoElement.load();
      }
      if (this.targetElement) {
        this.targetElement.innerHTML = '';
      }
    }
  }

  // Global SDK namespace
  const GNTV = global.GNTV || {};
  GNTV.embed = function (options) {
    return new GNTVSecureEmbedPlayer(options);
  };
  GNTV.Player = GNTVSecureEmbedPlayer;

  global.GNTV = GNTV;

  // ES Module export support
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = { GNTV, embed: GNTV.embed, GNTVSecureEmbedPlayer };
  }
})(typeof window !== 'undefined' ? window : globalThis);
