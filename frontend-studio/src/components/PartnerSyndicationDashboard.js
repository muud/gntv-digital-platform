/**
 * Partner Syndication & Embed SDK control panel (Module 7 Sprint 7.6).
 * Vanilla JS component for the existing Studio dashboard architecture.
 */

export function initPartnerSyndicationDashboard(container) {
  let active = true;
  let isRefreshing = false;
  let fetchError = "";
  let partners = [];
  let analytics = null;
  let selectedPartnerId = "";
  let domains = [];
  let entitlements = [];
  let tokenPreview = null;

  const apiBase = import.meta.env.VITE_API_URL || "http://localhost:8000";

  function getAuthToken() {
    return localStorage.getItem("gntv_auth_token") || localStorage.getItem("token") || "";
  }

  async function api(path, options = {}) {
    const response = await fetch(`${apiBase}${path}`, {
      ...options,
      headers: {
        "Content-Type": "application/json",
        "Authorization": `Bearer ${getAuthToken()}`,
        ...(options.headers || {})
      }
    });
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      throw new Error(body.detail || `API error ${response.status}`);
    }
    return response.json();
  }

  async function refresh() {
    if (!active) return;
    isRefreshing = true;
    fetchError = "";
    render();
    try {
      const [partnerList, overview] = await Promise.all([
        api("/api/v1/partners"),
        api("/api/v1/partners/analytics/overview")
      ]);
      partners = partnerList;
      analytics = overview;
      if (!selectedPartnerId && partners.length) selectedPartnerId = partners[0].id;
      await refreshPartnerDetails();
    } catch (error) {
      fetchError = error.message || "Failed to load partner syndication data";
    } finally {
      isRefreshing = false;
      if (active) render();
    }
  }

  async function refreshPartnerDetails() {
    if (!selectedPartnerId) {
      domains = [];
      entitlements = [];
      return;
    }
    const [domainList, entitlementList] = await Promise.all([
      api(`/api/v1/partners/${selectedPartnerId}/domains`),
      api(`/api/v1/partners/${selectedPartnerId}/entitlements`)
    ]);
    domains = domainList;
    entitlements = entitlementList;
  }

  function selectedPartner() {
    return partners.find((partner) => partner.id === selectedPartnerId) || null;
  }

  function formatNumber(value) {
    if (value === null || value === undefined) return "—";
    return Number(value).toLocaleString();
  }

  function render() {
    if (!active || !container) return;
    const partner = selectedPartner();
    container.innerHTML = `
      <style>
        .partner-shell { padding: 24px; color: #e5e7eb; background: #090a0f; min-height: 100%; box-sizing: border-box; font-family: system-ui, -apple-system, sans-serif; }
        .partner-header { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; flex-wrap: wrap; margin-bottom: 22px; }
        .partner-header h2 { margin: 0 0 6px 0; color: #fff; font-size: 24px; font-weight: 850; letter-spacing: -0.4px; }
        .partner-header p { margin: 0; color: #9ca3af; font-size: 13px; max-width: 760px; }
        .partner-btn { border: 0; border-radius: 9px; background: var(--brand-primary, #ff2a4b); color: #fff; padding: 10px 14px; font-weight: 800; cursor: pointer; }
        .partner-btn.secondary { background: rgba(255,255,255,.06); border: 1px solid rgba(255,255,255,.12); }
        .partner-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); gap: 14px; margin-bottom: 18px; }
        .partner-card { background: rgba(18,20,29,.74); border: 1px solid rgba(255,255,255,.08); border-radius: 12px; padding: 18px; box-shadow: 0 18px 44px rgba(0,0,0,.24); }
        .partner-kpi-label { color: #9ca3af; font-size: 11px; font-weight: 800; text-transform: uppercase; letter-spacing: .5px; }
        .partner-kpi-value { color: #fff; font-size: 27px; font-weight: 900; margin-top: 6px; font-family: ui-monospace, SFMono-Regular, monospace; }
        .partner-layout { display: grid; grid-template-columns: 360px 1fr; gap: 18px; }
        @media (max-width: 1050px) { .partner-layout { grid-template-columns: 1fr; } }
        .partner-list { display: flex; flex-direction: column; gap: 10px; }
        .partner-row { width: 100%; text-align: left; border: 1px solid rgba(255,255,255,.08); background: rgba(255,255,255,.03); color: #e5e7eb; border-radius: 10px; padding: 13px; cursor: pointer; }
        .partner-row.active { border-color: rgba(255,138,0,.55); box-shadow: 0 0 0 1px rgba(255,138,0,.2), 0 0 30px rgba(255,138,0,.08); }
        .partner-row strong { display: block; color: #fff; margin-bottom: 4px; }
        .partner-pill { display: inline-flex; align-items: center; border: 1px solid rgba(255,255,255,.1); border-radius: 999px; padding: 4px 8px; color: #cbd5e1; font-size: 11px; margin: 4px 6px 0 0; }
        .partner-form { display: grid; gap: 10px; margin-top: 14px; }
        .partner-form input, .partner-form select { background: rgba(255,255,255,.06); border: 1px solid rgba(255,255,255,.1); border-radius: 8px; color: #fff; padding: 10px 12px; outline: none; }
        .partner-form label { display: grid; gap: 6px; color: #9ca3af; font-size: 11px; font-weight: 800; text-transform: uppercase; }
        .partner-section-title { color: #fff; font-size: 15px; font-weight: 850; margin: 0 0 12px 0; }
        .partner-code { white-space: pre-wrap; overflow-wrap: anywhere; background: rgba(2,6,23,.8); border: 1px solid rgba(255,255,255,.08); border-radius: 10px; padding: 14px; color: #bae6fd; font-size: 12px; }
        .partner-empty, .partner-error { padding: 16px; border-radius: 10px; background: rgba(255,255,255,.04); color: #9ca3af; border: 1px solid rgba(255,255,255,.08); }
        .partner-error { color: #fecaca; border-color: rgba(239,68,68,.35); background: rgba(127,29,29,.24); }
      </style>
      <section class="partner-shell">
        <div class="partner-header">
          <div>
            <h2>Partner Syndication & Embed SDK</h2>
            <p>Manage B2B partners, server-side domain restrictions, explicit content entitlements and secure short-lived embed tokens.</p>
          </div>
          <button class="partner-btn secondary" id="partner-refresh">${isRefreshing ? "Refreshing..." : "Refresh"}</button>
        </div>
        ${fetchError ? `<div class="partner-error">${fetchError}</div>` : ""}
        <div class="partner-grid">
          <div class="partner-card"><div class="partner-kpi-label">Partners</div><div class="partner-kpi-value">${formatNumber(analytics?.partner_count)}</div></div>
          <div class="partner-card"><div class="partner-kpi-label">Active Partners</div><div class="partner-kpi-value">${formatNumber(analytics?.active_partner_count)}</div></div>
          <div class="partner-card"><div class="partner-kpi-label">Authorized Embeds</div><div class="partner-kpi-value">${formatNumber(analytics?.authorized_embed_count)}</div></div>
          <div class="partner-card"><div class="partner-kpi-label">Playback Starts</div><div class="partner-kpi-value">${formatNumber(analytics?.playback_start_count)}</div></div>
        </div>
        <div class="partner-layout">
          <div class="partner-card">
            <h3 class="partner-section-title">Partners</h3>
            <div class="partner-list">
              ${partners.length ? partners.map((item) => `
                <button class="partner-row ${item.id === selectedPartnerId ? "active" : ""}" data-partner-id="${item.id}">
                  <strong>${item.name}</strong>
                  <span>${item.slug}</span>
                  <span class="partner-pill">${item.status}</span>
                </button>
              `).join("") : `<div class="partner-empty">No partner organizations have been created yet.</div>`}
            </div>
            <form class="partner-form" id="partner-create-form">
              <label>Partner name <input name="name" required placeholder="Example Media Group"></label>
              <label>Slug <input name="slug" required placeholder="example-media"></label>
              <label>Status <select name="status"><option value="active">active</option><option value="pending">pending</option><option value="suspended">suspended</option></select></label>
              <button class="partner-btn" type="submit">Create Partner</button>
            </form>
          </div>
          <div class="partner-card">
            <h3 class="partner-section-title">${partner ? partner.name : "Select a partner"}</h3>
            ${partner ? `
              <div>
                <span class="partner-pill">Brand: ${partner.branding?.display_name || partner.name}</span>
                <span class="partner-pill">Rate limit: ${partner.rate_limit_per_minute}/min</span>
              </div>
              <div class="partner-grid" style="margin-top:16px">
                <div>
                  <h3 class="partner-section-title">Allowed Domains</h3>
                  ${domains.length ? domains.map((domain) => `<span class="partner-pill">${domain.domain_pattern}</span>`).join("") : `<div class="partner-empty">No allowed domains configured.</div>`}
                  <form class="partner-form" id="partner-domain-form">
                    <label>Domain pattern <input name="domain_pattern" required placeholder="*.partner.example.com"></label>
                    <button class="partner-btn secondary" type="submit">Add Domain</button>
                  </form>
                </div>
                <div>
                  <h3 class="partner-section-title">Entitlements</h3>
                  ${entitlements.length ? entitlements.map((item) => `<span class="partner-pill">${item.content_type}: ${item.content_id}</span>`).join("") : `<div class="partner-empty">No content entitlements configured.</div>`}
                  <form class="partner-form" id="partner-entitlement-form">
                    <label>Type <select name="content_type"><option value="live_channel">live_channel</option><option value="vod">vod</option></select></label>
                    <label>Content ID <input name="content_id" required placeholder="channel-001"></label>
                    <button class="partner-btn secondary" type="submit">Grant Entitlement</button>
                  </form>
                </div>
              </div>
              <form class="partner-form" id="partner-token-form">
                <h3 class="partner-section-title">Generate Test Embed Token</h3>
                <label>Domain <input name="domain" required placeholder="partner.example.com"></label>
                <label>Type <select name="content_type"><option value="live_channel">live_channel</option><option value="vod">vod</option></select></label>
                <label>Content ID <input name="content_id" required placeholder="channel-001"></label>
                <button class="partner-btn" type="submit">Issue Short-Lived Token</button>
              </form>
              ${tokenPreview ? `<pre class="partner-code">GNTV.embed({
  target: "#gntv-player",
  token: "${tokenPreview.token}",
  contentId: "${tokenPreview.content_id}"
})</pre>` : ""}
            ` : `<div class="partner-empty">Create or select a partner to manage syndication access.</div>`}
          </div>
        </div>
      </section>
    `;
    bindEvents();
  }

  function bindEvents() {
    container.querySelector("#partner-refresh")?.addEventListener("click", refresh);
    container.querySelectorAll("[data-partner-id]").forEach((button) => {
      button.addEventListener("click", async () => {
        selectedPartnerId = button.dataset.partnerId || "";
        tokenPreview = null;
        try {
          await refreshPartnerDetails();
        } catch (error) {
          fetchError = error.message;
        }
        render();
      });
    });
    container.querySelector("#partner-create-form")?.addEventListener("submit", async (event) => {
      event.preventDefault();
      const data = Object.fromEntries(new FormData(event.target));
      try {
        const created = await api("/api/v1/partners", {
          method: "POST",
          body: JSON.stringify({
            name: data.name,
            slug: data.slug,
            status: data.status,
            branding: { display_name: data.name }
          })
        });
        selectedPartnerId = created.partner.id;
        await refresh();
      } catch (error) {
        fetchError = error.message;
        render();
      }
    });
    container.querySelector("#partner-domain-form")?.addEventListener("submit", async (event) => {
      event.preventDefault();
      const data = Object.fromEntries(new FormData(event.target));
      try {
        await api(`/api/v1/partners/${selectedPartnerId}/domains`, { method: "POST", body: JSON.stringify(data) });
        await refreshPartnerDetails();
      } catch (error) {
        fetchError = error.message;
      }
      render();
    });
    container.querySelector("#partner-entitlement-form")?.addEventListener("submit", async (event) => {
      event.preventDefault();
      const data = Object.fromEntries(new FormData(event.target));
      try {
        await api(`/api/v1/partners/${selectedPartnerId}/entitlements`, {
          method: "POST",
          body: JSON.stringify({ ...data, scopes: ["embed:play"] })
        });
        await refreshPartnerDetails();
      } catch (error) {
        fetchError = error.message;
      }
      render();
    });
    container.querySelector("#partner-token-form")?.addEventListener("submit", async (event) => {
      event.preventDefault();
      const data = Object.fromEntries(new FormData(event.target));
      try {
        tokenPreview = await api(`/api/v1/partners/${selectedPartnerId}/embed-token`, {
          method: "POST",
          body: JSON.stringify({ ...data, scopes: ["embed:play"], ttl_seconds: 300 })
        });
      } catch (error) {
        fetchError = error.message;
      }
      render();
    });
  }

  refresh();

  return () => {
    active = false;
  };
}
