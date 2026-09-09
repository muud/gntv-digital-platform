/**
 * Partner Syndication, Embed SDK, Partner Billing & Payout Orchestration (Sprint 7.6, 7.7, 7.8).
 * Vanilla JS component for GNTV Studio dashboard architecture.
 */

export function initPartnerSyndicationDashboard(container) {
  let active = true;
  let isRefreshing = false;
  let fetchError = "";
  let activeSubSection = "lifecycle"; // "lifecycle" | "billing" | "payouts" | "syndication"
  let partners = [];
  let analytics = null;
  let selectedPartnerId = "";
  let domains = [];
  let entitlements = [];
  let tokenPreview = null;
  let agreements = [];
  let settlements = [];
  let usageRows = [];
  let auditLogs = [];
  let payoutAccounts = [];
  let payouts = [];
  let reconciliations = [];
  let payoutAudits = [];
  let lifecycle = null;

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
      agreements = [];
      settlements = [];
      usageRows = [];
      auditLogs = [];
      payoutAccounts = [];
      payouts = [];
      reconciliations = [];
      payoutAudits = [];
      lifecycle = null;
      return;
    }
    try {
      const [domainList, entitlementList, agreementList, settlementList, usageList, auditList, accountList, payoutList, reconList, pAuditList, lifecycleState] =
        await Promise.all([
          api(`/api/v1/partners/${selectedPartnerId}/domains`).catch(() => []),
          api(`/api/v1/partners/${selectedPartnerId}/entitlements`).catch(() => []),
          api(`/api/v1/partners/${selectedPartnerId}/billing/revenue-share-agreements`).catch(() => []),
          api(`/api/v1/partners/${selectedPartnerId}/billing/settlements`).catch(() => []),
          api(`/api/v1/partners/${selectedPartnerId}/billing/usage`).catch(() => []),
          api(`/api/v1/partners/${selectedPartnerId}/billing/audit`).catch(() => []),
          api(`/api/v1/partners/${selectedPartnerId}/payout-accounts`).catch(() => []),
          api(`/api/v1/partners/${selectedPartnerId}/payouts`).catch(() => []),
          api(`/api/v1/partners/${selectedPartnerId}/reconciliation`).catch(() => []),
          api(`/api/v1/partners/${selectedPartnerId}/payouts-audit`).catch(() => []),
          api(`/api/v1/partners/${selectedPartnerId}/lifecycle`).catch(() => null)
        ]);
      domains = domainList;
      entitlements = entitlementList;
      agreements = agreementList;
      settlements = settlementList;
      usageRows = usageList;
      auditLogs = auditList;
      payoutAccounts = accountList;
      payouts = payoutList;
      reconciliations = reconList;
      payoutAudits = pAuditList;
      lifecycle = lifecycleState;
    } catch (error) {
      fetchError = error.message || "Failed to load partner details";
    }
  }

  function selectedPartner() {
    return partners.find((partner) => partner.id === selectedPartnerId) || null;
  }

  function formatNumber(value) {
    if (value === null || value === undefined) return "—";
    return Number(value).toLocaleString();
  }

  function formatMoney(value, currency = "USD") {
    if (value === null || value === undefined) return "—";
    return `${currency} ${Number(value).toFixed(2)}`;
  }

  function lifecycleSection() {
    if (!lifecycle) {
      return `<div class="partner-card partner-empty">Lifecycle data is not available for this partner yet.</div>`;
    }
    const profile = lifecycle.profile || {};
    const checklist = lifecycle.checklist || [];
    const audits = lifecycle.audit || [];
    return `
      <div class="partner-card">
        <h3 class="partner-section-title">Partner Lifecycle Control</h3>
        <div class="partner-grid">
          <div class="partner-card"><div class="partner-kpi-label">Lifecycle State</div><div class="partner-kpi-value">${lifecycle.partner.lifecycle_status}</div></div>
          <div class="partner-card"><div class="partner-kpi-label">Checklist</div><div class="partner-kpi-value">${lifecycle.checklist_complete_count}/${lifecycle.checklist_total_count}</div></div>
          <div class="partner-card"><div class="partner-kpi-label">Can Approve</div><div class="partner-kpi-value">${lifecycle.can_approve ? "Yes" : "No"}</div></div>
          <div class="partner-card"><div class="partner-kpi-label">Can Activate</div><div class="partner-kpi-value">${lifecycle.can_activate ? "Yes" : "No"}</div></div>
        </div>
        <div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:16px">
          <button class="partner-btn secondary btn-life-return" type="button">Request Changes</button>
          <button class="partner-btn btn-life-approve" type="button">Approve</button>
          <button class="partner-btn btn-life-activate" type="button">Activate</button>
          <button class="partner-btn secondary btn-life-reactivate" type="button">Reactivate</button>
          <button class="partner-btn danger btn-life-suspend" type="button">Suspend</button>
          <button class="partner-btn danger btn-life-terminate" type="button">Terminate</button>
        </div>
        <form class="partner-form" id="operator-onboarding-form">
          <h4 style="margin:0;color:#fff;font-size:13px">Operator Review Fields</h4>
          <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:10px">
            <label>Approved Domains <input name="approved_domains" placeholder="player.partner.test, *.partner.org" value="${(profile.approved_domains_json || []).join(", ")}"></label>
            <label>Payout Readiness
              <select name="payout_readiness_status">
                ${["not_started","configured","verified","blocked"].map((value) => `<option value="${value}" ${profile.payout_readiness_status === value ? "selected" : ""}>${value}</option>`).join("")}
              </select>
            </label>
            <label>Review Notes <input name="review_notes" placeholder="Notes visible in lifecycle review" value="${profile.review_notes || ""}"></label>
          </div>
          <button class="partner-btn secondary" type="submit">Save Review Fields</button>
        </form>
      </div>
      <div class="partner-card">
        <h3 class="partner-section-title">Onboarding Checklist</h3>
        ${checklist.length ? `
          <table class="partner-table">
            <thead><tr><th>Item</th><th>Status</th><th>Derived From</th></tr></thead>
            <tbody>${checklist.map((item) => `
              <tr>
                <td>${item.title}</td>
                <td><span class="partner-pill ${item.is_complete ? "success" : "warning"}">${item.is_complete ? "Complete" : "Open"}</span></td>
                <td>${item.derived_from || "manual"}</td>
              </tr>
            `).join("")}</tbody>
          </table>
        ` : `<div class="partner-empty">No lifecycle checklist exists yet.</div>`}
      </div>
      <div class="partner-card">
        <h3 class="partner-section-title">Lifecycle Audit</h3>
        ${audits.length ? `
          <table class="partner-table">
            <thead><tr><th>Action</th><th>Actor</th><th>Date</th><th>Metadata</th></tr></thead>
            <tbody>${audits.slice(0, 12).map((audit) => `
              <tr>
                <td><span class="partner-pill">${audit.action}</span></td>
                <td>User #${audit.actor_user_id || "System"}</td>
                <td>${new Date(audit.created_at).toLocaleString()}</td>
                <td><code style="font-size:11px;color:#bae6fd">${JSON.stringify(audit.metadata_json || audit.after_json || {})}</code></td>
              </tr>
            `).join("")}</tbody>
          </table>
        ` : `<div class="partner-empty">No lifecycle audit events yet.</div>`}
      </div>
    `;
  }

  function render() {
    if (!active || !container) return;
    const partner = selectedPartner();

    const totalSettled = settlements
      .filter((s) => s.status === "finalized" || s.status === "paid")
      .reduce((acc, s) => acc + Number(s.net_settlement_amount || 0), 0);

    const totalGross = usageRows.reduce(
      (acc, u) => acc + Number(u.gross_revenue_amount || 0),
      0
    );

    const totalDisbursed = payouts
      .filter((p) => p.status === "paid")
      .reduce((acc, p) => acc + Number(p.amount || 0), 0);

    container.innerHTML = `
      <style>
        .partner-shell { padding: 24px; color: #e5e7eb; background: #090a0f; min-height: 100%; box-sizing: border-box; font-family: system-ui, -apple-system, sans-serif; }
        .partner-header { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; flex-wrap: wrap; margin-bottom: 20px; }
        .partner-header h2 { margin: 0 0 6px 0; color: #fff; font-size: 24px; font-weight: 850; letter-spacing: -0.4px; }
        .partner-header p { margin: 0; color: #9ca3af; font-size: 13px; max-width: 760px; }
        .partner-btn { border: 0; border-radius: 9px; background: var(--brand-primary, #ff2a4b); color: #fff; padding: 10px 14px; font-weight: 800; cursor: pointer; transition: all .15s ease; }
        .partner-btn:hover { filter: brightness(1.1); transform: translateY(-1px); }
        .partner-btn.secondary { background: rgba(255,255,255,.06); border: 1px solid rgba(255,255,255,.12); }
        .partner-btn.secondary:hover { background: rgba(255,255,255,.1); }
        .partner-btn.sm { padding: 6px 10px; font-size: 12px; border-radius: 6px; }
        .partner-btn.danger { background: rgba(239,68,68,.25); border: 1px solid rgba(239,68,68,.4); color: #fca5a5; }
        .partner-btn.danger:hover { background: rgba(239,68,68,.4); }
        .partner-nav { display: flex; gap: 8px; margin-bottom: 20px; border-bottom: 1px solid rgba(255,255,255,.08); padding-bottom: 8px; }
        .partner-nav-btn { background: transparent; border: 0; color: #9ca3af; padding: 8px 14px; border-radius: 8px; font-weight: 700; cursor: pointer; }
        .partner-nav-btn.active { color: #fff; background: rgba(255,255,255,.08); }
        .partner-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 14px; margin-bottom: 18px; }
        .partner-card { background: rgba(18,20,29,.74); border: 1px solid rgba(255,255,255,.08); border-radius: 12px; padding: 18px; box-shadow: 0 18px 44px rgba(0,0,0,.24); margin-bottom: 16px; }
        .partner-kpi-label { color: #9ca3af; font-size: 11px; font-weight: 800; text-transform: uppercase; letter-spacing: .5px; }
        .partner-kpi-value { color: #fff; font-size: 26px; font-weight: 900; margin-top: 6px; font-family: ui-monospace, SFMono-Regular, monospace; }
        .partner-layout { display: grid; grid-template-columns: 340px 1fr; gap: 18px; }
        @media (max-width: 1050px) { .partner-layout { grid-template-columns: 1fr; } }
        .partner-list { display: flex; flex-direction: column; gap: 8px; max-height: 480px; overflow-y: auto; }
        .partner-row { width: 100%; text-align: left; border: 1px solid rgba(255,255,255,.08); background: rgba(255,255,255,.03); color: #e5e7eb; border-radius: 10px; padding: 12px; cursor: pointer; }
        .partner-row.active { border-color: rgba(255,138,0,.55); box-shadow: 0 0 0 1px rgba(255,138,0,.2), 0 0 30px rgba(255,138,0,.08); }
        .partner-row strong { display: block; color: #fff; margin-bottom: 4px; }
        .partner-pill { display: inline-flex; align-items: center; border: 1px solid rgba(255,255,255,.1); border-radius: 999px; padding: 3px 8px; color: #cbd5e1; font-size: 11px; margin: 4px 4px 0 0; }
        .partner-pill.success { background: rgba(16,185,129,.15); color: #6ee7b7; border-color: rgba(16,185,129,.3); }
        .partner-pill.warning { background: rgba(245,158,11,.15); color: #fcd34d; border-color: rgba(245,158,11,.3); }
        .partner-pill.danger { background: rgba(239,68,68,.15); color: #fca5a5; border-color: rgba(239,68,68,.3); }
        .partner-pill.info { background: rgba(59,130,246,.15); color: #93c5fd; border-color: rgba(59,130,246,.3); }
        .partner-form { display: grid; gap: 10px; margin-top: 14px; }
        .partner-form input, .partner-form select, .partner-form textarea { background: rgba(255,255,255,.06); border: 1px solid rgba(255,255,255,.1); border-radius: 8px; color: #fff; padding: 10px 12px; outline: none; }
        .partner-form label { display: grid; gap: 6px; color: #9ca3af; font-size: 11px; font-weight: 800; text-transform: uppercase; }
        .partner-section-title { color: #fff; font-size: 15px; font-weight: 850; margin: 0 0 12px 0; }
        .partner-table { width: 100%; border-collapse: collapse; font-size: 13px; margin-top: 8px; }
        .partner-table th { text-align: left; padding: 10px 12px; color: #9ca3af; font-size: 11px; font-weight: 800; text-transform: uppercase; border-bottom: 1px solid rgba(255,255,255,.08); }
        .partner-table td { padding: 10px 12px; border-bottom: 1px solid rgba(255,255,255,.05); }
        .partner-code { white-space: pre-wrap; overflow-wrap: anywhere; background: rgba(2,6,23,.8); border: 1px solid rgba(255,255,255,.08); border-radius: 10px; padding: 14px; color: #bae6fd; font-size: 12px; }
        .partner-empty, .partner-error { padding: 14px; border-radius: 10px; background: rgba(255,255,255,.04); color: #9ca3af; border: 1px solid rgba(255,255,255,.08); }
        .partner-error { color: #fecaca; border-color: rgba(239,68,68,.35); background: rgba(127,29,29,.24); }
      </style>
      <section class="partner-shell">
        <div class="partner-header">
          <div>
            <h2>Partner Syndication & Revenue Settlement</h2>
            <p>B2B syndication, server-side access controls, tiered revenue-share agreements, deterministic settlements, and payout orchestration.</p>
          </div>
          <button class="partner-btn secondary" id="partner-refresh">${isRefreshing ? "Refreshing..." : "Refresh"}</button>
        </div>
        ${fetchError ? `<div class="partner-error">${fetchError}</div>` : ""}
        <div class="partner-grid">
          <div class="partner-card"><div class="partner-kpi-label">Partners</div><div class="partner-kpi-value">${formatNumber(analytics?.partner_count)}</div></div>
          <div class="partner-card"><div class="partner-kpi-label">Active Partners</div><div class="partner-kpi-value">${formatNumber(analytics?.active_partner_count)}</div></div>
          <div class="partner-card"><div class="partner-kpi-label">Persisted Gross Revenue</div><div class="partner-kpi-value">${formatMoney(totalGross)}</div></div>
          <div class="partner-card"><div class="partner-kpi-label">Disbursed Payouts</div><div class="partner-kpi-value">${formatMoney(totalDisbursed)}</div></div>
        </div>
        <div class="partner-layout">
          <div class="partner-card">
            <h3 class="partner-section-title">Partners Directory</h3>
            <div class="partner-list">
              ${partners.length ? partners.map((item) => `
                <button class="partner-row ${item.id === selectedPartnerId ? "active" : ""}" data-partner-id="${item.id}">
                  <strong>${item.name}</strong>
                  <span>${item.slug}</span>
                  <span class="partner-pill">${item.status}</span>
                </button>
              `).join("") : `<div class="partner-empty">No partner organizations registered yet.</div>`}
            </div>
            <form class="partner-form" id="partner-create-form">
              <label>Partner name <input name="name" required placeholder="Premier Media Corp"></label>
              <label>Slug <input name="slug" required placeholder="example-media"></label>
              <label>Status <select name="status"><option value="active">active</option><option value="pending">pending</option><option value="suspended">suspended</option></select></label>
              <button class="partner-btn" type="submit">Create Partner</button>
            </form>
          </div>
          <div>
            ${partner ? `
              <div class="partner-card">
                <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px;">
                  <div>
                    <h3 class="partner-section-title" style="margin:0">${partner.name}</h3>
                    <span class="partner-pill">Slug: ${partner.slug}</span>
                    <span class="partner-pill">Rate limit: ${partner.rate_limit_per_minute}/min</span>
                    <span class="partner-pill ${partner.status === 'active' ? 'success' : 'warning'}">${partner.status}</span>
                    <span class="partner-pill info">Lifecycle: ${partner.lifecycle_status || lifecycle?.partner?.lifecycle_status || 'unknown'}</span>
                  </div>
                  <div class="partner-nav">
                    <button class="partner-nav-btn ${activeSubSection === 'lifecycle' ? 'active' : ''}" id="tab-lifecycle">Lifecycle</button>
                    <button class="partner-nav-btn ${activeSubSection === 'billing' ? 'active' : ''}" id="tab-billing">Billing & Settlement</button>
                    <button class="partner-nav-btn ${activeSubSection === 'payouts' ? 'active' : ''}" id="tab-payouts">Payouts & Reconciliation</button>
                    <button class="partner-nav-btn ${activeSubSection === 'syndication' ? 'active' : ''}" id="tab-syndication">Syndication & Embeds</button>
                  </div>
                </div>
              </div>

              ${activeSubSection === 'lifecycle' ? lifecycleSection() : activeSubSection === 'billing' ? `
                <!-- Billing & Settlement Section -->
                <div class="partner-card">
                  <h3 class="partner-section-title">Revenue Share Agreements</h3>
                  ${agreements.length ? `
                    <table class="partner-table">
                      <thead><tr><th>Name</th><th>Type</th><th>Rate / Tiers</th><th>Currency</th><th>Validity</th><th>Status</th></tr></thead>
                      <tbody>
                        ${agreements.map((a) => `
                          <tr>
                            <td><strong>${a.name}</strong></td>
                            <td><span class="partner-pill">${a.rule_type}</span></td>
                            <td>${a.rule_type === 'fixed_percentage' ? `${(Number(a.fixed_partner_percentage) * 100).toFixed(1)}%` : `${a.tiers_json?.length || 0} tiers`}</td>
                            <td>${a.currency}</td>
                            <td>${a.starts_at ? new Date(a.starts_at).toLocaleDateString() : '—'}</td>
                            <td><span class="partner-pill ${a.is_active ? 'success' : 'warning'}">${a.is_active ? 'Active' : 'Inactive'}</span></td>
                          </tr>
                        `).join('')}
                      </tbody>
                    </table>
                  ` : `<div class="partner-empty">No revenue-share agreement active for this partner.</div>`}
                  <form class="partner-form" id="agreement-create-form" style="margin-top:16px">
                    <h4 style="margin:0;color:#fff;font-size:13px">Create Revenue-Share Agreement</h4>
                    <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:10px">
                      <label>Agreement name <input name="name" required placeholder="2026 Commercial Syndication"></label>
                      <label>Rule Type
                        <select name="rule_type" id="agreement-rule-type">
                          <option value="fixed_percentage">Fixed Percentage</option>
                          <option value="tiered_percentage">Tiered Percentage</option>
                        </select>
                      </label>
                      <label id="agreement-fixed-pct-label">Partner Share % (0.0 - 1.0)
                        <input name="fixed_partner_percentage" type="number" step="0.0001" min="0" max="1" value="0.3000">
                      </label>
                      <label>Starts At <input name="starts_at" type="datetime-local" required></label>
                    </div>
                    <label id="agreement-tiers-label" style="display:none">Tiers (JSON: [{"threshold_amount": "0", "partner_percentage": "0.20"}])
                      <textarea name="tiers" rows="2" placeholder='[{"threshold_amount": "0", "partner_percentage": "0.2000"}, {"threshold_amount": "1000", "partner_percentage": "0.3500"}]'></textarea>
                    </label>
                    <button class="partner-btn" type="submit">Activate Agreement</button>
                  </form>
                </div>

                <div class="partner-card">
                  <h3 class="partner-section-title">Settlement Statements</h3>
                  ${settlements.length ? `
                    <table class="partner-table">
                      <thead><tr><th>Period</th><th>Usage</th><th>Gross</th><th>Platform</th><th>Partner</th><th>Adjustment</th><th>Net Payout</th><th>Status</th><th>Actions</th></tr></thead>
                      <tbody>
                        ${settlements.map((s) => `
                          <tr>
                            <td>${new Date(s.period_start).toLocaleDateString()} - ${new Date(s.period_end).toLocaleDateString()}</td>
                            <td>${s.usage_count}</td>
                            <td>${formatMoney(s.gross_revenue_amount, s.currency)}</td>
                            <td>${formatMoney(s.platform_share_amount, s.currency)}</td>
                            <td>${formatMoney(s.partner_share_amount, s.currency)}</td>
                            <td>${formatMoney(s.adjustment_amount, s.currency)}</td>
                            <td><strong>${formatMoney(s.net_settlement_amount, s.currency)}</strong></td>
                            <td><span class="partner-pill ${s.status === 'paid' ? 'success' : s.status === 'finalized' ? 'warning' : s.status === 'disputed' ? 'danger' : ''}">${s.status}</span></td>
                            <td>
                              ${s.status === 'draft' ? `<button class="partner-btn secondary sm btn-stmt-status" data-id="${s.id}" data-target="finalized">Finalize</button>` : ''}
                              ${s.status === 'finalized' ? `<button class="partner-btn sm btn-stmt-status" data-id="${s.id}" data-target="paid">Mark Paid</button>` : ''}
                              ${s.status === 'draft' || s.status === 'finalized' ? `<button class="partner-btn secondary sm btn-stmt-status" data-id="${s.id}" data-target="disputed">Dispute</button>` : ''}
                            </td>
                          </tr>
                        `).join('')}
                      </tbody>
                    </table>
                  ` : `<div class="partner-empty">No settlement statements generated yet.</div>`}

                  <form class="partner-form" id="settlement-generate-form" style="margin-top:16px">
                    <h4 style="margin:0;color:#fff;font-size:13px">Generate Settlement Statement</h4>
                    <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:10px">
                      <label>Period Start <input name="period_start" type="datetime-local" required></label>
                      <label>Period End <input name="period_end" type="datetime-local" required></label>
                      <label>Adjustment Amount <input name="adjustment_amount" type="number" step="0.01" value="0.00"></label>
                      <label>Idempotency Key <input name="idempotency_key" required placeholder="settlement-2026-08"></label>
                    </div>
                    <button class="partner-btn" type="submit">Compute Deterministic Settlement</button>
                  </form>
                </div>

                <div class="partner-card">
                  <h3 class="partner-section-title">Persisted Usage Metering (${usageRows.length} events)</h3>
                  <form class="partner-form" id="usage-record-form" style="margin-bottom:16px">
                    <h4 style="margin:0;color:#fff;font-size:13px">Record Usage Metric (Billing Ingestion)</h4>
                    <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:10px">
                      <label>Content Type <select name="content_type"><option value="live_channel">live_channel</option><option value="vod">vod</option></select></label>
                      <label>Content ID <input name="content_id" required placeholder="channel-main"></label>
                      <label>Event Type <select name="usage_event_type"><option value="ad_revenue">ad_revenue</option><option value="playback_start">playback_start</option><option value="playback_complete">playback_complete</option></select></label>
                      <label>Quantity <input name="quantity" type="number" min="1" value="1"></label>
                      <label>Gross Amount <input name="gross_revenue_amount" type="number" step="0.01" value="50.00"></label>
                      <label>Idempotency Key <input name="idempotency_key" required placeholder="evt-${Date.now()}"></label>
                    </div>
                    <button class="partner-btn secondary" type="submit">Ingest Meter Event</button>
                  </form>
                </div>

                <div class="partner-card">
                  <h3 class="partner-section-title">Financial Audit Log</h3>
                  ${auditLogs.length ? `
                    <table class="partner-table">
                      <thead><tr><th>Action</th><th>Actor</th><th>Date</th><th>Audit Metadata</th></tr></thead>
                      <tbody>
                        ${auditLogs.map((log) => `
                          <tr>
                            <td><span class="partner-pill">${log.action}</span></td>
                            <td>User #${log.actor_user_id || 'System'}</td>
                            <td>${new Date(log.created_at).toLocaleString()}</td>
                            <td><code style="font-size:11px;color:#bae6fd">${JSON.stringify(log.after_json || log.before_json || {})}</code></td>
                          </tr>
                        `).join('')}
                      </tbody>
                    </table>
                  ` : `<div class="partner-empty">No financial audit records recorded yet.</div>`}
                </div>
              ` : activeSubSection === 'payouts' ? `
                <!-- Payouts & Reconciliation Section (Sprint 7.8) -->
                <div class="partner-card">
                  <h3 class="partner-section-title">Registered Payout Accounts</h3>
                  ${payoutAccounts.length ? `
                    <table class="partner-table">
                      <thead><tr><th>Label</th><th>Destination Ref</th><th>Provider</th><th>Currency</th><th>Status</th><th>Verification</th></tr></thead>
                      <tbody>
                        ${payoutAccounts.map((acc) => `
                          <tr>
                            <td><strong>${acc.destination_label}</strong></td>
                            <td><code>${acc.destination_reference}</code></td>
                            <td><span class="partner-pill">${acc.provider_type}</span></td>
                            <td>${acc.currency}</td>
                            <td><span class="partner-pill ${acc.status === 'enabled' ? 'success' : 'warning'}">${acc.status}</span></td>
                            <td><span class="partner-pill ${acc.verification_status === 'verified' ? 'success' : acc.verification_status === 'pending' ? 'warning' : ''}">${acc.verification_status}</span></td>
                          </tr>
                        `).join('')}
                      </tbody>
                    </table>
                  ` : `<div class="partner-empty">No payout destination accounts configured yet.</div>`}

                  <form class="partner-form" id="payout-account-form" style="margin-top:16px">
                    <h4 style="margin:0;color:#fff;font-size:13px">Register Payout Account</h4>
                    <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:10px">
                      <label>Account Label <input name="destination_label" required placeholder="Corporate Wire Account"></label>
                      <label>Masked Reference <input name="destination_reference" required placeholder="bank_wire:****4321"></label>
                      <label>Provider <select name="provider_type"><option value="mock">mock</option><option value="external_reference">external_reference</option></select></label>
                      <label>Currency <input name="currency" value="USD" maxlength="3" required></label>
                      <label>Idempotency Key <input name="idempotency_key" required placeholder="acct-key-${Date.now()}"></label>
                    </div>
                    <button class="partner-btn" type="submit">Save Destination Account</button>
                  </form>
                </div>

                <div class="partner-card">
                  <h3 class="partner-section-title">Payout Instructions Queue</h3>
                  ${payouts.length ? `
                    <table class="partner-table">
                      <thead><tr><th>Payout ID</th><th>Amount</th><th>Status</th><th>Provider Ref</th><th>Created</th><th>Actions</th></tr></thead>
                      <tbody>
                        ${payouts.map((p) => `
                          <tr>
                            <td><code style="font-size:11px">${p.id.slice(0, 8)}...</code></td>
                            <td><strong>${formatMoney(p.amount, p.currency)}</strong></td>
                            <td><span class="partner-pill ${p.status === 'paid' ? 'success' : p.status === 'approved' ? 'info' : p.status === 'failed' ? 'danger' : 'warning'}">${p.status}</span></td>
                            <td>${p.provider_transaction_id || p.provider_payout_id || '—'}</td>
                            <td>${new Date(p.created_at).toLocaleDateString()}</td>
                            <td>
                              ${p.status === 'pending' ? `
                                <button class="partner-btn sm btn-payout-approve" data-id="${p.id}">Approve</button>
                                <button class="partner-btn danger sm btn-payout-cancel" data-id="${p.id}">Cancel</button>
                              ` : ''}
                              ${p.status === 'approved' ? `
                                <button class="partner-btn sm btn-payout-execute" data-id="${p.id}">Execute</button>
                                <button class="partner-btn danger sm btn-payout-cancel" data-id="${p.id}">Cancel</button>
                              ` : ''}
                              ${p.status === 'failed' ? `<span style="font-size:11px;color:#fca5a5">${p.failure_code || 'Error'}</span>` : ''}
                            </td>
                          </tr>
                        `).join('')}
                      </tbody>
                    </table>
                  ` : `<div class="partner-empty">No payout instructions queued yet.</div>`}

                  <form class="partner-form" id="payout-create-form" style="margin-top:16px">
                    <h4 style="margin:0;color:#fff;font-size:13px">Create Payout from Finalized Settlement</h4>
                    <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:10px">
                      <label>Finalized Statement
                        <select name="settlement_id" required>
                          <option value="">Select statement...</option>
                          ${settlements.filter((s) => s.status === 'finalized').map((s) => `
                            <option value="${s.id}">${new Date(s.period_start).toLocaleDateString()} - ${new Date(s.period_end).toLocaleDateString()} (${formatMoney(s.net_settlement_amount, s.currency)})</option>
                          `).join('')}
                        </select>
                      </label>
                      <label>Payout Destination Account
                        <select name="payout_account_id" required>
                          <option value="">Select account...</option>
                          ${payoutAccounts.filter((a) => a.status === 'enabled').map((a) => `
                            <option value="${a.id}">${a.destination_label} (${a.destination_reference})</option>
                          `).join('')}
                        </select>
                      </label>
                      <label>Idempotency Key <input name="idempotency_key" required placeholder="payout-instr-${Date.now()}"></label>
                    </div>
                    <button class="partner-btn" type="submit">Queue Payout Instruction</button>
                  </form>
                </div>

                <div class="partner-card">
                  <h3 class="partner-section-title">Reconciliation Feed</h3>
                  ${reconciliations.length ? `
                    <table class="partner-table">
                      <thead><tr><th>Tx ID</th><th>Reported Amount</th><th>Provider Status</th><th>Outcome</th><th>Details</th></tr></thead>
                      <tbody>
                        ${reconciliations.map((r) => `
                          <tr>
                            <td><code>${r.provider_transaction_id}</code></td>
                            <td>${formatMoney(r.reported_amount, r.reported_currency)}</td>
                            <td>${r.provider_status}</td>
                            <td><span class="partner-pill ${r.outcome === 'matched' ? 'success' : r.outcome === 'duplicate_provider_transaction' ? 'warning' : 'danger'}">${r.outcome}</span></td>
                            <td><code style="font-size:11px;color:#bae6fd">${JSON.stringify(r.details_json || {})}</code></td>
                          </tr>
                        `).join('')}
                      </tbody>
                    </table>
                  ` : `<div class="partner-empty">No reconciliation records processed yet.</div>`}

                  <form class="partner-form" id="reconciliation-form" style="margin-top:16px">
                    <h4 style="margin:0;color:#fff;font-size:13px">Ingest External Reconciliation Record</h4>
                    <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:10px">
                      <label>Provider Tx ID <input name="provider_transaction_id" required placeholder="tx_mock_12345"></label>
                      <label>Reported Amount <input name="reported_amount" type="number" step="0.01" required value="100.00"></label>
                      <label>Currency <input name="reported_currency" maxlength="3" required value="USD"></label>
                      <label>Provider Status <input name="provider_status" required value="success"></label>
                      <label>Idempotency Key <input name="idempotency_key" required placeholder="recon-key-${Date.now()}"></label>
                    </div>
                    <button class="partner-btn secondary" type="submit">Reconcile External Transaction</button>
                  </form>
                </div>

                <div class="partner-card">
                  <h3 class="partner-section-title">Payout Audit Trail</h3>
                  ${payoutAudits.length ? `
                    <table class="partner-table">
                      <thead><tr><th>Action</th><th>Actor</th><th>Date</th><th>Provider Ref</th><th>Snapshot</th></tr></thead>
                      <tbody>
                        ${payoutAudits.map((log) => `
                          <tr>
                            <td><span class="partner-pill">${log.action}</span></td>
                            <td>User #${log.actor_user_id || 'System'}</td>
                            <td>${new Date(log.created_at).toLocaleString()}</td>
                            <td>${log.provider_reference || '—'}</td>
                            <td><code style="font-size:11px;color:#bae6fd">${JSON.stringify(log.after_json || log.before_json || {})}</code></td>
                          </tr>
                        `).join('')}
                      </tbody>
                    </table>
                  ` : `<div class="partner-empty">No payout audit events recorded yet.</div>`}
                </div>
              ` : `
                <!-- Syndication & Embeds Section -->
                <div class="partner-grid">
                  <div class="partner-card">
                    <h3 class="partner-section-title">Allowed Domains</h3>
                    ${domains.length ? domains.map((domain) => `<span class="partner-pill">${domain.domain_pattern}</span>`).join("") : `<div class="partner-empty">No allowed domains configured.</div>`}
                    <form class="partner-form" id="partner-domain-form">
                      <label>Domain pattern <input name="domain_pattern" required placeholder="*.partner.example.com"></label>
                      <button class="partner-btn secondary" type="submit">Add Domain</button>
                    </form>
                  </div>
                  <div class="partner-card">
                    <h3 class="partner-section-title">Entitlements</h3>
                    ${entitlements.length ? entitlements.map((item) => `<span class="partner-pill">${item.content_type}: ${item.content_id}</span>`).join("") : `<div class="partner-empty">No content entitlements configured.</div>`}
                    <form class="partner-form" id="partner-entitlement-form">
                      <label>Type <select name="content_type"><option value="live_channel">live_channel</option><option value="vod">vod</option></select></label>
                      <label>Content ID <input name="content_id" required placeholder="channel-001"></label>
                      <button class="partner-btn secondary" type="submit">Grant Entitlement</button>
                    </form>
                  </div>
                </div>

                <div class="partner-card">
                  <form class="partner-form" id="partner-token-form">
                    <h3 class="partner-section-title">Generate Test Embed Token</h3>
                    <label>Domain <input name="domain" required placeholder="partner.example.com"></label>
                    <label>Type <select name="content_type"><option value="live_channel">live_channel</option><option value="vod">vod</option></select></label>
                    <label>Content ID <input name="content_id" required placeholder="channel-001"></label>
                    <button class="partner-btn" type="submit">Issue Short-Lived Token</button>
                  </form>
                  ${tokenPreview ? `<pre class="partner-code" style="margin-top:14px">GNTV.embed({
  target: "#gntv-player",
  token: "${tokenPreview.token}",
  contentId: "${tokenPreview.content_id}"
})</pre>` : ""}
                </div>
              `}
            ` : `<div class="partner-card partner-empty">Create or select a partner from the directory to manage access, revenue share, and settlements.</div>`}
          </div>
        </div>
      </section>
    `;
    bindEvents();
  }

  function bindEvents() {
    container.querySelector("#partner-refresh")?.addEventListener("click", refresh);
    container.querySelector("#tab-lifecycle")?.addEventListener("click", () => {
      activeSubSection = "lifecycle";
      render();
    });
    container.querySelector("#tab-billing")?.addEventListener("click", () => {
      activeSubSection = "billing";
      render();
    });
    container.querySelector("#tab-payouts")?.addEventListener("click", () => {
      activeSubSection = "payouts";
      render();
    });
    container.querySelector("#tab-syndication")?.addEventListener("click", () => {
      activeSubSection = "syndication";
      render();
    });

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

    const ruleTypeSelect = container.querySelector("#agreement-rule-type");
    if (ruleTypeSelect) {
      ruleTypeSelect.addEventListener("change", (e) => {
        const isTiered = e.target.value === "tiered_percentage";
        const tiersLabel = container.querySelector("#agreement-tiers-label");
        const fixedLabel = container.querySelector("#agreement-fixed-pct-label");
        if (tiersLabel) tiersLabel.style.display = isTiered ? "grid" : "none";
        if (fixedLabel) fixedLabel.style.display = isTiered ? "none" : "grid";
      });
    }

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

    container.querySelector("#operator-onboarding-form")?.addEventListener("submit", async (event) => {
      event.preventDefault();
      const data = Object.fromEntries(new FormData(event.target));
      const approvedDomains = String(data.approved_domains || "")
        .split(",")
        .map((item) => item.trim())
        .filter(Boolean);
      try {
        await api(`/api/v1/partners/${selectedPartnerId}/lifecycle/onboarding`, {
          method: "PATCH",
          body: JSON.stringify({
            approved_domains: approvedDomains,
            payout_readiness_status: data.payout_readiness_status,
            review_notes: data.review_notes || null
          })
        });
        await refreshPartnerDetails();
        render();
      } catch (error) {
        fetchError = error.message;
        render();
      }
    });

    async function lifecycleAction(action, payload = null) {
      try {
        await api(`/api/v1/partners/${selectedPartnerId}/lifecycle/${action}`, {
          method: "POST",
          body: payload ? JSON.stringify(payload) : undefined
        });
        await refreshPartnerDetails();
        render();
      } catch (error) {
        fetchError = error.message;
        render();
      }
    }

    container.querySelector(".btn-life-return")?.addEventListener("click", () => {
      const review_notes = window.prompt("What changes should the partner make?") || "Operator requested changes";
      lifecycleAction("return", { review_notes });
    });
    container.querySelector(".btn-life-approve")?.addEventListener("click", () => {
      lifecycleAction("approve", { review_notes: "Approved by operator" });
    });
    container.querySelector(".btn-life-activate")?.addEventListener("click", () => {
      lifecycleAction("activate");
    });
    container.querySelector(".btn-life-reactivate")?.addEventListener("click", () => {
      lifecycleAction("reactivate");
    });
    container.querySelector(".btn-life-suspend")?.addEventListener("click", () => {
      if (window.confirm("Suspend this partner and revoke operational embed/API access?")) {
        lifecycleAction("suspend", { reason: "Operator suspension" });
      }
    });
    container.querySelector(".btn-life-terminate")?.addEventListener("click", () => {
      if (window.confirm("Terminate this partner and revoke active access while preserving history?")) {
        lifecycleAction("terminate", { reason: "Operator termination" });
      }
    });

    container.querySelector("#agreement-create-form")?.addEventListener("submit", async (event) => {
      event.preventDefault();
      const form = event.target;
      const data = Object.fromEntries(new FormData(form));
      const payload = {
        name: data.name,
        rule_type: data.rule_type,
        starts_at: new Date(data.starts_at).toISOString(),
        currency: "USD"
      };
      if (data.rule_type === "fixed_percentage") {
        payload.fixed_partner_percentage = data.fixed_partner_percentage;
      } else {
        try {
          payload.tiers = JSON.parse(data.tiers || "[]");
        } catch (_) {
          fetchError = "Tiers must be valid JSON array of {threshold_amount, partner_percentage}";
          render();
          return;
        }
      }
      try {
        await api(`/api/v1/partners/${selectedPartnerId}/billing/revenue-share-agreements`, {
          method: "POST",
          body: JSON.stringify(payload)
        });
        await refreshPartnerDetails();
        render();
      } catch (error) {
        fetchError = error.message;
        render();
      }
    });

    container.querySelector("#settlement-generate-form")?.addEventListener("submit", async (event) => {
      event.preventDefault();
      const data = Object.fromEntries(new FormData(event.target));
      try {
        await api(`/api/v1/partners/${selectedPartnerId}/billing/settlements`, {
          method: "POST",
          body: JSON.stringify({
            period_start: new Date(data.period_start).toISOString(),
            period_end: new Date(data.period_end).toISOString(),
            adjustment_amount: data.adjustment_amount || "0",
            idempotency_key: data.idempotency_key
          })
        });
        await refreshPartnerDetails();
        render();
      } catch (error) {
        fetchError = error.message;
        render();
      }
    });

    container.querySelector("#usage-record-form")?.addEventListener("submit", async (event) => {
      event.preventDefault();
      const data = Object.fromEntries(new FormData(event.target));
      try {
        await api(`/api/v1/partners/${selectedPartnerId}/billing/usage`, {
          method: "POST",
          body: JSON.stringify({
            content_type: data.content_type,
            content_id: data.content_id,
            usage_event_type: data.usage_event_type,
            quantity: Number(data.quantity || 1),
            gross_revenue_amount: data.gross_revenue_amount || "0",
            idempotency_key: data.idempotency_key,
            occurred_at: new Date().toISOString(),
            currency: "USD"
          })
        });
        await refreshPartnerDetails();
        render();
      } catch (error) {
        fetchError = error.message;
        render();
      }
    });

    container.querySelectorAll(".btn-stmt-status").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const stmtId = btn.dataset.id;
        const targetStatus = btn.dataset.target;
        const reason = window.prompt(`Reason for transition to ${targetStatus}:`) || "Operator action";
        try {
          await api(`/api/v1/partners/${selectedPartnerId}/billing/settlements/${stmtId}/status`, {
            method: "POST",
            body: JSON.stringify({ status: targetStatus, reason })
          });
          await refreshPartnerDetails();
          render();
        } catch (error) {
          fetchError = error.message;
          render();
        }
      });
    });

    // Payout Account Create
    container.querySelector("#payout-account-form")?.addEventListener("submit", async (event) => {
      event.preventDefault();
      const data = Object.fromEntries(new FormData(event.target));
      try {
        await api(`/api/v1/partners/${selectedPartnerId}/payout-accounts`, {
          method: "POST",
          body: JSON.stringify({
            destination_label: data.destination_label,
            destination_reference: data.destination_reference,
            provider_type: data.provider_type || "mock",
            currency: data.currency || "USD",
            idempotency_key: data.idempotency_key
          })
        });
        await refreshPartnerDetails();
        render();
      } catch (error) {
        fetchError = error.message;
        render();
      }
    });

    // Payout Create
    container.querySelector("#payout-create-form")?.addEventListener("submit", async (event) => {
      event.preventDefault();
      const data = Object.fromEntries(new FormData(event.target));
      try {
        await api(`/api/v1/partners/${selectedPartnerId}/payouts`, {
          method: "POST",
          body: JSON.stringify({
            settlement_id: data.settlement_id,
            payout_account_id: data.payout_account_id,
            idempotency_key: data.idempotency_key
          })
        });
        await refreshPartnerDetails();
        render();
      } catch (error) {
        fetchError = error.message;
        render();
      }
    });

    // Payout Approve
    container.querySelectorAll(".btn-payout-approve").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const payoutId = btn.dataset.id;
        try {
          await api(`/api/v1/partners/${selectedPartnerId}/payouts/${payoutId}/approve`, {
            method: "POST"
          });
          await refreshPartnerDetails();
          render();
        } catch (error) {
          fetchError = error.message;
          render();
        }
      });
    });

    // Payout Execute
    container.querySelectorAll(".btn-payout-execute").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const payoutId = btn.dataset.id;
        const execKey = `exec-${Date.now()}`;
        try {
          await api(`/api/v1/partners/${selectedPartnerId}/payouts/${payoutId}/execute`, {
            method: "POST",
            body: JSON.stringify({ idempotency_key: execKey })
          });
          await refreshPartnerDetails();
          render();
        } catch (error) {
          fetchError = error.message;
          render();
        }
      });
    });

    // Payout Cancel
    container.querySelectorAll(".btn-payout-cancel").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const payoutId = btn.dataset.id;
        const reason = window.prompt("Reason for cancellation:") || "Operator cancellation";
        try {
          await api(`/api/v1/partners/${selectedPartnerId}/payouts/${payoutId}/cancel?reason=${encodeURIComponent(reason)}`, {
            method: "POST"
          });
          await refreshPartnerDetails();
          render();
        } catch (error) {
          fetchError = error.message;
          render();
        }
      });
    });

    // Reconciliation Ingest
    container.querySelector("#reconciliation-form")?.addEventListener("submit", async (event) => {
      event.preventDefault();
      const data = Object.fromEntries(new FormData(event.target));
      try {
        await api(`/api/v1/partners/${selectedPartnerId}/reconciliation`, {
          method: "POST",
          body: JSON.stringify({
            provider_type: "mock",
            provider_transaction_id: data.provider_transaction_id,
            reported_amount: data.reported_amount,
            reported_currency: data.reported_currency,
            provider_status: data.provider_status,
            idempotency_key: data.idempotency_key
          })
        });
        await refreshPartnerDetails();
        render();
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
