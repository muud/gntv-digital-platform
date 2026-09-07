/**
 * Partner self-service portal for Sprint 7.9.
 * This UI is intentionally separate from Studio operator controls.
 */

export function initPartnerPortalDashboard(container) {
  let active = true;
  let activeTab = "overview";
  let loading = false;
  let error = "";
  let portalKey = localStorage.getItem("gntv_partner_portal_key") || "";
  let filters = { period_start: "", period_end: "", currency: "" };
  let data = {
    me: null,
    overview: null,
    usage: null,
    revenue: null,
    statements: [],
    payouts: [],
    reconciliation: [],
    events: []
  };
  const apiBase = import.meta.env.VITE_API_URL || "http://localhost:8000";

  function headers() {
    return {
      "Content-Type": "application/json",
      "X-Partner-Key": portalKey
    };
  }

  function query() {
    const params = new URLSearchParams();
    if (filters.period_start) params.set("period_start", new Date(filters.period_start).toISOString());
    if (filters.period_end) params.set("period_end", new Date(filters.period_end).toISOString());
    if (filters.currency) params.set("currency", filters.currency.toUpperCase());
    return params.toString() ? `?${params.toString()}` : "";
  }

  async function api(path) {
    const response = await fetch(`${apiBase}${path}`, { headers: headers() });
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      throw new Error(body.detail || `Partner portal API error ${response.status}`);
    }
    return response.json();
  }

  async function refresh() {
    if (!active || !portalKey) return;
    loading = true;
    error = "";
    render();
    try {
      const q = query();
      const [me, overview, usage, revenue, statements, payouts, reconciliation, events] = await Promise.all([
        api("/api/v1/partner-portal/me"),
        api(`/api/v1/partner-portal/overview${q}`),
        api(`/api/v1/partner-portal/usage${q}`),
        api(`/api/v1/partner-portal/revenue${q}`),
        api(`/api/v1/partner-portal/statements${q}`),
        api(`/api/v1/partner-portal/payouts${q}`),
        api(`/api/v1/partner-portal/reconciliation${q}`),
        api(`/api/v1/partner-portal/events${q}`)
      ]);
      data = { me, overview, usage, revenue, statements, payouts, reconciliation, events };
    } catch (err) {
      error = err.message || "Unable to load partner portal data.";
    } finally {
      loading = false;
      if (active) render();
    }
  }

  function money(value, currency = "USD") {
    if (value === null || value === undefined || value === "") return "No data";
    return `${currency || "USD"} ${Number(value).toFixed(2)}`;
  }

  function date(value) {
    if (!value) return "No date";
    return new Date(value).toLocaleDateString();
  }

  function statusClass(value) {
    if (["paid", "matched", "verified", "active", "enabled", "success"].includes(value)) return "good";
    if (["failed", "disputed", "void", "reversed", "unknown_transaction"].includes(value)) return "bad";
    return "warn";
  }

  function rows(items, columns, emptyText) {
    if (!items || !items.length) return `<div class="portal-empty">${emptyText}</div>`;
    return `
      <div class="portal-table-wrap">
        <table class="portal-table">
          <thead><tr>${columns.map((c) => `<th>${c.label}</th>`).join("")}</tr></thead>
          <tbody>
            ${items.map((item) => `
              <tr>${columns.map((c) => `<td>${c.render(item)}</td>`).join("")}</tr>
            `).join("")}
          </tbody>
        </table>
      </div>
    `;
  }

  function overview() {
    const o = data.overview;
    if (!o) return `<div class="portal-empty">Connect a partner portal key to view overview data.</div>`;
    return `
      <div class="portal-kpis">
        <div class="portal-card"><span>Usage</span><strong>${o.usage_total ?? "0"}</strong></div>
        <div class="portal-card"><span>Gross Revenue</span><strong>${money(o.gross_revenue_amount, o.currency)}</strong></div>
        <div class="portal-card"><span>Partner Share</span><strong>${money(o.partner_share_amount, o.currency)}</strong></div>
        <div class="portal-card"><span>Finalized Settlements</span><strong>${o.finalized_settlements ?? "0"}</strong></div>
        <div class="portal-card"><span>Pending Payouts</span><strong>${o.pending_payouts ?? "0"}</strong></div>
        <div class="portal-card"><span>Paid Payouts</span><strong>${o.paid_payouts ?? "0"}</strong></div>
      </div>
      <div class="portal-split">
        <section class="portal-panel">
          <h3>Entitlements</h3>
          ${rows(data.me?.entitlements || [], [
            { label: "Type", render: (x) => x.content_type },
            { label: "Content", render: (x) => x.content_id },
            { label: "Status", render: (x) => `<span class="portal-pill ${statusClass(x.status)}">${x.status}</span>` }
          ], "No entitlements are available for this partner.")}
        </section>
        <section class="portal-panel">
          <h3>Status Feed</h3>
          ${eventList()}
        </section>
      </div>
    `;
  }

  function usage() {
    return `
      <section class="portal-panel">
        <h3>Usage Summary</h3>
        <div class="portal-card compact"><span>Total Usage</span><strong>${data.usage?.usage_total ?? "0"}</strong></div>
        ${rows(data.usage?.rows || [], [
          { label: "Date", render: (x) => date(x.occurred_at) },
          { label: "Content", render: (x) => `${x.content_type}: ${x.content_id}` },
          { label: "Event", render: (x) => x.usage_event_type },
          { label: "Qty", render: (x) => x.quantity },
          { label: "Gross", render: (x) => money(x.gross_revenue_amount, x.currency) }
        ], "No persisted usage rows match this filter.")}
      </section>
    `;
  }

  function revenue() {
    const r = data.revenue;
    return `
      <div class="portal-kpis">
        <div class="portal-card"><span>Gross</span><strong>${money(r?.gross_revenue_amount, r?.currency)}</strong></div>
        <div class="portal-card"><span>Platform Share</span><strong>${money(r?.platform_share_amount, r?.currency)}</strong></div>
        <div class="portal-card"><span>Partner Share</span><strong>${money(r?.partner_share_amount, r?.currency)}</strong></div>
        <div class="portal-card"><span>Net Settlement</span><strong>${money(r?.net_settlement_amount, r?.currency)}</strong></div>
      </div>
      <section class="portal-panel">
        <h3>Financial Time Series</h3>
        ${rows(r?.time_series || [], [
          { label: "Date", render: (x) => x.date },
          { label: "Gross", render: (x) => money(x.gross_revenue_amount, x.currency) },
          { label: "Partner Share", render: (x) => money(x.partner_share_amount, x.currency) },
          { label: "Net", render: (x) => money(x.net_settlement_amount, x.currency) }
        ], "No finalized or draft settlement data is available for this period.")}
      </section>
    `;
  }

  function statements() {
    return rows(data.statements || [], [
      { label: "Period", render: (x) => `${date(x.settlement.period_start)} - ${date(x.settlement.period_end)}` },
      { label: "Status", render: (x) => `<span class="portal-pill ${statusClass(x.settlement.status)}">${x.settlement.status}</span>` },
      { label: "Gross", render: (x) => money(x.settlement.gross_revenue_amount, x.settlement.currency) },
      { label: "Partner Share", render: (x) => money(x.settlement.partner_share_amount, x.settlement.currency) },
      { label: "Net", render: (x) => money(x.settlement.net_settlement_amount, x.settlement.currency) },
      { label: "Payout", render: (x) => x.payouts[0]?.status || x.settlement.payout_status || "not created" }
    ], "No statements match this filter.");
  }

  function payouts() {
    return rows(data.payouts || [], [
      { label: "Created", render: (x) => date(x.created_at) },
      { label: "Status", render: (x) => `<span class="portal-pill ${statusClass(x.status)}">${x.status}</span>` },
      { label: "Amount", render: (x) => money(x.amount, x.currency) },
      { label: "Provider", render: (x) => x.provider_type },
      { label: "Reference", render: (x) => x.provider_transaction_reference || "Not available" }
    ], "No payouts match this filter.");
  }

  function reconciliation() {
    return rows(data.reconciliation || [], [
      { label: "Date", render: (x) => date(x.created_at) },
      { label: "Outcome", render: (x) => `<span class="portal-pill ${statusClass(x.outcome)}">${x.outcome}</span>` },
      { label: "Provider Status", render: (x) => x.provider_status },
      { label: "Amount", render: (x) => money(x.reported_amount, x.reported_currency) },
      { label: "Reference", render: (x) => x.provider_transaction_reference }
    ], "No reconciliation records match this filter.");
  }

  function profile() {
    const me = data.me;
    if (!me) return `<div class="portal-empty">Connect a partner portal key to view account details.</div>`;
    return `
      <div class="portal-split">
        <section class="portal-panel">
          <h3>${me.partner.name}</h3>
          <p class="portal-muted">${me.partner.slug} · ${me.partner.status}</p>
          ${rows(me.authorized_domains || [], [
            { label: "Domain", render: (x) => x.domain_pattern },
            { label: "Origin", render: (x) => x.origin_pattern || "Any approved origin" },
            { label: "Status", render: (x) => `<span class="portal-pill ${statusClass(x.status)}">${x.status}</span>` }
          ], "No approved domains are configured.")}
        </section>
        <section class="portal-panel">
          <h3>Payout Destinations</h3>
          ${rows(me.payout_accounts || [], [
            { label: "Label", render: (x) => x.destination_label },
            { label: "Masked Ref", render: (x) => x.masked_destination_reference },
            { label: "Currency", render: (x) => x.currency },
            { label: "Verification", render: (x) => `<span class="portal-pill ${statusClass(x.verification_status)}">${x.verification_status}</span>` }
          ], "No payout destinations are visible yet.")}
        </section>
      </div>
    `;
  }

  function eventList() {
    if (!data.events?.length) return `<div class="portal-empty">No partner-visible status events yet.</div>`;
    return data.events.map((event) => `
      <div class="portal-event">
        <span class="portal-pill ${statusClass(event.severity)}">${event.event_type}</span>
        <strong>${event.title}</strong>
        <p>${event.message}</p>
        <small>${date(event.created_at)}</small>
      </div>
    `).join("");
  }

  function content() {
    if (activeTab === "usage") return usage();
    if (activeTab === "revenue") return revenue();
    if (activeTab === "statements") return `<section class="portal-panel"><h3>Statements</h3>${statements()}</section>`;
    if (activeTab === "payouts") return `<section class="portal-panel"><h3>Payouts</h3>${payouts()}</section>`;
    if (activeTab === "reconciliation") return `<section class="portal-panel"><h3>Reconciliation</h3>${reconciliation()}</section>`;
    if (activeTab === "entitlements") return overview();
    if (activeTab === "profile") return profile();
    return overview();
  }

  function render() {
    if (!active || !container) return;
    container.innerHTML = `
      <style>
        .portal-shell { min-height: 100%; overflow:auto; padding: 28px; color:#eef4ff; font-family: system-ui, -apple-system, sans-serif; background: radial-gradient(circle at 20% 10%, rgba(255,138,0,.18), transparent 28%), radial-gradient(circle at 80% 0%, rgba(20,135,255,.20), transparent 32%), #050814; }
        .portal-hero { display:flex; justify-content:space-between; gap:18px; align-items:flex-start; padding:22px; border:1px solid rgba(255,255,255,.10); border-radius:22px; background:rgba(255,255,255,.06); box-shadow:0 24px 70px rgba(0,0,0,.34); backdrop-filter: blur(18px); margin-bottom:18px; }
        .portal-hero h1 { margin:0 0 8px; font-size: clamp(26px, 4vw, 44px); letter-spacing:0; }
        .portal-hero p, .portal-muted { color:rgba(238,244,255,.68); margin:0; line-height:1.5; }
        .portal-login { display:flex; gap:8px; flex-wrap:wrap; justify-content:flex-end; min-width:min(460px, 100%); }
        .portal-login input, .portal-filter input { min-width:170px; flex:1; color:#fff; background:rgba(255,255,255,.08); border:1px solid rgba(255,255,255,.14); border-radius:12px; padding:11px 12px; outline:none; }
        .portal-btn { border:0; border-radius:12px; padding:11px 15px; color:#06101f; background:#ff8a00; font-weight:850; cursor:pointer; box-shadow:0 12px 28px rgba(255,138,0,.24); }
        .portal-btn.secondary { background:rgba(255,255,255,.08); color:#eaf2ff; border:1px solid rgba(255,255,255,.14); box-shadow:none; }
        .portal-tabs, .portal-filter { display:flex; gap:8px; flex-wrap:wrap; margin: 0 0 18px; }
        .portal-tab { border:1px solid rgba(255,255,255,.10); background:rgba(255,255,255,.05); color:#c8d5e8; border-radius:999px; padding:9px 13px; cursor:pointer; font-weight:800; }
        .portal-tab.active { color:#fff; border-color:rgba(255,138,0,.65); background:rgba(255,138,0,.16); }
        .portal-kpis { display:grid; grid-template-columns:repeat(auto-fit,minmax(180px,1fr)); gap:12px; margin-bottom:16px; }
        .portal-card, .portal-panel { border:1px solid rgba(255,255,255,.10); border-radius:18px; background:rgba(8,16,34,.72); padding:16px; box-shadow:0 18px 44px rgba(0,0,0,.26); }
        .portal-card span { display:block; color:rgba(238,244,255,.62); font-size:11px; text-transform:uppercase; font-weight:850; margin-bottom:8px; }
        .portal-card strong { font-size:23px; color:#fff; }
        .portal-card.compact { display:inline-block; min-width:190px; margin-bottom:12px; }
        .portal-split { display:grid; grid-template-columns:1fr 1fr; gap:14px; }
        .portal-panel h3 { margin:0 0 12px; color:#fff; font-size:17px; }
        .portal-table-wrap { overflow:auto; }
        .portal-table { width:100%; border-collapse:collapse; min-width:720px; }
        .portal-table th, .portal-table td { text-align:left; border-bottom:1px solid rgba(255,255,255,.07); padding:11px 10px; font-size:13px; }
        .portal-table th { color:rgba(238,244,255,.58); text-transform:uppercase; font-size:10px; letter-spacing:.04em; }
        .portal-pill { display:inline-flex; border:1px solid rgba(255,255,255,.14); border-radius:999px; padding:3px 8px; font-size:11px; font-weight:800; color:#dbeafe; }
        .portal-pill.good { color:#86efac; border-color:rgba(34,197,94,.35); background:rgba(34,197,94,.12); }
        .portal-pill.warn { color:#fde68a; border-color:rgba(245,158,11,.35); background:rgba(245,158,11,.12); }
        .portal-pill.bad { color:#fca5a5; border-color:rgba(239,68,68,.35); background:rgba(239,68,68,.12); }
        .portal-empty, .portal-error { padding:15px; border:1px solid rgba(255,255,255,.10); border-radius:14px; color:rgba(238,244,255,.68); background:rgba(255,255,255,.04); }
        .portal-error { color:#fecaca; border-color:rgba(239,68,68,.38); background:rgba(127,29,29,.20); margin-bottom:14px; }
        .portal-event { padding:12px; border-bottom:1px solid rgba(255,255,255,.07); }
        .portal-event strong { display:block; margin-top:8px; }
        .portal-event p { margin:5px 0; color:rgba(238,244,255,.68); }
        .portal-event small { color:rgba(238,244,255,.46); }
        @media (max-width: 850px) { .portal-shell { padding:16px; } .portal-hero, .portal-split { display:block; } .portal-login { margin-top:14px; justify-content:flex-start; } .portal-panel { margin-bottom:14px; } }
      </style>
      <main class="portal-shell">
        <section class="portal-hero">
          <div>
            <span class="portal-pill good">GNTV Partner Portal</span>
            <h1>Statements & Financial Reporting</h1>
            <p>Secure partner-facing access to authorized syndication, usage, revenue, settlements, payouts, and reconciliation data.</p>
          </div>
          <form class="portal-login" id="portal-key-form">
            <input name="portalKey" type="password" value="${portalKey}" placeholder="Partner portal key" autocomplete="off">
            <button class="portal-btn" type="submit">${portalKey ? "Refresh Portal" : "Connect"}</button>
            <button class="portal-btn secondary" id="portal-clear-key" type="button">Clear</button>
          </form>
        </section>
        <form class="portal-filter" id="portal-filter-form">
          <input name="period_start" type="date" value="${filters.period_start}">
          <input name="period_end" type="date" value="${filters.period_end}">
          <input name="currency" maxlength="3" placeholder="Currency" value="${filters.currency}">
          <button class="portal-btn secondary" type="submit">Apply Filters</button>
          <a class="portal-btn" style="text-decoration:none" href="${apiBase}/api/v1/partner-portal/exports?report_type=statements&format=csv" id="portal-export-link">Export CSV</a>
        </form>
        <nav class="portal-tabs">
          ${["overview","usage","revenue","statements","payouts","reconciliation","entitlements","profile"].map((tab) => `
            <button class="portal-tab ${activeTab === tab ? "active" : ""}" data-tab="${tab}">${tab.replace("-", " ")}</button>
          `).join("")}
        </nav>
        ${loading ? `<div class="portal-empty">Loading partner data...</div>` : ""}
        ${error ? `<div class="portal-error">${error}</div>` : ""}
        ${content()}
      </main>
    `;
    bind();
  }

  function bind() {
    container.querySelectorAll(".portal-tab").forEach((button) => {
      button.addEventListener("click", () => {
        activeTab = button.dataset.tab;
        render();
      });
    });
    const keyForm = container.querySelector("#portal-key-form");
    if (keyForm) {
      keyForm.addEventListener("submit", (event) => {
        event.preventDefault();
        const form = new FormData(keyForm);
        portalKey = String(form.get("portalKey") || "").trim();
        localStorage.setItem("gntv_partner_portal_key", portalKey);
        refresh();
      });
    }
    const clear = container.querySelector("#portal-clear-key");
    if (clear) {
      clear.addEventListener("click", () => {
        portalKey = "";
        localStorage.removeItem("gntv_partner_portal_key");
        data = { me: null, overview: null, usage: null, revenue: null, statements: [], payouts: [], reconciliation: [], events: [] };
        render();
      });
    }
    const filterForm = container.querySelector("#portal-filter-form");
    if (filterForm) {
      filterForm.addEventListener("submit", (event) => {
        event.preventDefault();
        const form = new FormData(filterForm);
        filters = {
          period_start: String(form.get("period_start") || ""),
          period_end: String(form.get("period_end") || ""),
          currency: String(form.get("currency") || "").trim().toUpperCase()
        };
        refresh();
      });
    }
    const exportLink = container.querySelector("#portal-export-link");
    if (exportLink) {
      exportLink.addEventListener("click", (event) => {
        if (!portalKey) {
          event.preventDefault();
          error = "Connect a partner portal key before exporting.";
          render();
          return;
        }
        event.preventDefault();
        fetch(`${apiBase}/api/v1/partner-portal/exports?report_type=statements&format=csv`, { headers: headers() })
          .then((response) => {
            if (!response.ok) throw new Error("Export failed");
            return response.blob();
          })
          .then((blob) => {
            const url = URL.createObjectURL(blob);
            const link = document.createElement("a");
            link.href = url;
            link.download = "gntv-partner-statements.csv";
            link.click();
            URL.revokeObjectURL(url);
          })
          .catch((err) => {
            error = err.message || "Export failed";
            render();
          });
      });
    }
  }

  render();
  refresh();
  return () => {
    active = false;
  };
}
