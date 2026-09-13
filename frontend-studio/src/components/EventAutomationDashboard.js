export function formatCorrelationId(value) {
  if (!value) return "—";
  return value.length > 18 ? `${value.slice(0, 8)}…${value.slice(-6)}` : value;
}

export function summarizeEventMetrics(metrics = {}) {
  return [
    ["Events Received", metrics.events_received ?? metrics.total_events ?? 0],
    ["Processed", metrics.events_processed ?? metrics.events_by_status?.processed ?? 0],
    ["Failed", metrics.events_failed ?? metrics.events_by_status?.failed ?? 0],
    ["Webhook Deliveries", metrics.total_webhook_deliveries ?? 0],
    ["Dead Letters", metrics.dead_letter_count ?? metrics.pending_dead_letters_count ?? 0],
    ["Active Sources", metrics.active_sources_count ?? 0]
  ];
}

const escapeHTML = (value) => String(value ?? "").replace(/[&<>'"]/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" })[char]);

export function initEventAutomationDashboard(container) {
  let activeTab = "events";
  let loading = true;
  let error = "";
  let search = "";
  let page = 0;
  const pageSize = 20;
  let data = { events: [], sources: [], deliveries: [], subscriptions: [], outboundDeliveries: [], deadLetters: [], metrics: {}, trace: null };
  const apiBase = import.meta.env.VITE_API_URL || "http://localhost:8000";

  const token = () => sessionStorage.getItem("gntv_studio_token") || localStorage.getItem("gntv_auth_token") || localStorage.getItem("gntv_token") || "";
  const api = async (path, options = {}) => {
    const response = await fetch(`${apiBase}${path}`, {
      ...options,
      headers: { "Content-Type": "application/json", ...(token() ? { Authorization: `Bearer ${token()}` } : {}), ...(options.headers || {}) }
    });
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      throw new Error(payload.detail || `Request failed (${response.status})`);
    }
    return response.json();
  };

  const statusBadge = (status) => {
    const color = ["processed", "delivered", "retried"].includes(status) ? "#34d399" : ["failed", "dead_lettered"].includes(status) ? "#fb7185" : "#fbbf24";
    return `<span style="color:${color};font-size:11px;font-weight:800;text-transform:uppercase">${escapeHTML(status || "unknown")}</span>`;
  };

  const empty = (label) => `<div style="padding:44px;text-align:center;color:#64748b">No ${label} found for the current filters.</div>`;
  const table = (headers, rows) => rows.length ? `<div style="overflow:auto"><table style="width:100%;border-collapse:collapse;font-size:12px"><thead><tr>${headers.map((h) => `<th style="text-align:left;padding:10px;border-bottom:1px solid #283244;color:#94a3b8">${h}</th>`).join("")}</tr></thead><tbody>${rows.join("")}</tbody></table></div>` : empty(activeTab);
  const row = (cells) => `<tr>${cells.map((cell) => `<td style="padding:11px 10px;border-bottom:1px solid #172033">${cell}</td>`).join("")}</tr>`;
  const visible = (items) => items
    .filter((item) => !search || JSON.stringify(item).toLowerCase().includes(search.toLowerCase()))
    .slice(page * pageSize, (page + 1) * pageSize);

  function tabContent() {
    if (activeTab === "events") return table(["Event Type", "Source", "State", "Correlation", "Received", "Trace"], visible(data.events).map((item) => row([escapeHTML(item.event_type), escapeHTML(item.source), statusBadge(item.status), `<code>${escapeHTML(formatCorrelationId(item.correlation_id))}</code>`, new Date(item.received_at).toLocaleString(), `<button class="view-trace" data-correlation="${escapeHTML(item.correlation_id)}">View</button>`])));
    if (activeTab === "sources") return table(["Source", "Key", "Verifier", "Enabled", "Updated"], visible(data.sources).map((item) => row([escapeHTML(item.name), `<code>${escapeHTML(item.source_key)}</code>`, escapeHTML(item.provider_type), item.is_enabled ? "Yes" : "No", new Date(item.updated_at).toLocaleString()])));
    if (activeTab === "deliveries") return table(["Provider Event", "Verified", "Mapped Event", "State", "Received"], visible(data.deliveries).map((item) => row([escapeHTML(item.external_event_id || "fingerprint"), item.signature_valid ? "✓ Valid" : `✕ ${escapeHTML(item.rejection_reason)}`, escapeHTML(item.mapped_event_type || "—"), statusBadge(item.status), new Date(item.received_at).toLocaleString()])));
    if (activeTab === "subscriptions") return table(["Subscription", "HTTPS Endpoint", "Patterns", "Retries", "Enabled"], visible(data.subscriptions).map((item) => row([escapeHTML(item.name), escapeHTML(item.endpoint_url), escapeHTML(item.event_patterns_json.join(", ")), item.max_retries, item.is_enabled ? "Yes" : "No"])));
    if (activeTab === "outbound") return table(["Event", "State", "Attempts", "HTTP", "Next Retry"], visible(data.outboundDeliveries).map((item) => row([`<code>${escapeHTML(formatCorrelationId(item.event_id))}</code>`, statusBadge(item.status), item.attempt_count, item.response_status_code ?? "—", item.next_retry_at ? new Date(item.next_retry_at).toLocaleString() : "—"])));
    if (activeTab === "trace") {
      if (!data.trace) return empty("event → workflow trace");
      return `<div style="padding:16px;background:#111827;border-radius:8px"><p><strong>Correlation:</strong> <code>${escapeHTML(data.trace.correlation_id)}</code></p>${table(["Workflow Run", "State", "Trigger", "Created"], (data.trace.workflow_runs || []).map((run) => row([`<code>${escapeHTML(formatCorrelationId(run.id))}</code>`, statusBadge(run.status), escapeHTML(run.trigger_type), new Date(run.created_at).toLocaleString()])))}</div>`;
    }
    return table(["Reason", "Status", "Retries", "Created", "Action"], visible(data.deadLetters).map((item) => row([escapeHTML(item.reason), statusBadge(item.status), item.retry_count, new Date(item.created_at).toLocaleString(), item.status === "pending" ? `<button class="retry-dead-letter" data-id="${item.id}" style="background:#e11d48;color:white;border:0;border-radius:5px;padding:6px 10px;cursor:pointer">Retry</button>` : "—"])));
  }

  function render() {
    container.innerHTML = `<section style="color:#e2e8f0;background:#080d18;min-height:650px;border:1px solid #1e293b;border-radius:12px;padding:22px">
      <header style="display:flex;justify-content:space-between;align-items:center;gap:18px;margin-bottom:20px"><div><h2 style="margin:0;font-size:21px">Event Automation & Webhook Operations</h2><p style="color:#94a3b8;margin:5px 0 0">Secure event → workflow tracing, inbound verification, delivery retries and dead letters.</p></div><button id="event-refresh" style="background:#2563eb;color:white;border:0;border-radius:6px;padding:9px 14px;cursor:pointer">Refresh</button></header>
      ${error ? `<div role="alert" style="background:#7f1d1d55;border:1px solid #ef4444;padding:10px;border-radius:6px;margin-bottom:14px">${escapeHTML(error)}</div>` : ""}
      <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:10px;margin-bottom:18px">${summarizeEventMetrics(data.metrics).map(([label, value]) => `<div style="background:#111827;border:1px solid #263248;border-radius:8px;padding:12px"><div style="font-size:10px;color:#94a3b8;text-transform:uppercase">${label}</div><strong style="font-size:22px">${value}</strong></div>`).join("")}</div>
      <nav style="display:flex;gap:5px;flex-wrap:wrap;margin-bottom:14px">${[["events", "Event Stream"], ["sources", "Webhook Sources"], ["deliveries", "Inbound Deliveries"], ["subscriptions", "Outbound Subscriptions"], ["outbound", "Delivery Attempts"], ["deadLetters", "Dead Letter Queue"], ["trace", "Event → Workflow Trace"]].map(([id, label]) => `<button class="event-tab" data-tab="${id}" style="background:${activeTab === id ? "#2563eb" : "#172033"};color:white;border:0;border-radius:5px;padding:8px 11px;cursor:pointer">${label}</button>`).join("")}</nav>
      <div style="display:flex;gap:8px;margin-bottom:12px"><input id="event-filter" value="${escapeHTML(search)}" placeholder="Filter current view" style="flex:1;padding:8px;background:#111827;color:white;border:1px solid #334155;border-radius:5px"><button id="event-prev" ${page === 0 ? "disabled" : ""}>Previous</button><button id="event-next">Next</button></div>
      <div aria-live="polite">${loading ? `<div style="padding:44px;text-align:center;color:#94a3b8">Loading event operations…</div>` : tabContent()}</div>
    </section>`;
    container.querySelector("#event-refresh")?.addEventListener("click", load);
    container.querySelectorAll(".event-tab").forEach((button) => button.addEventListener("click", () => { activeTab = button.dataset.tab; page = 0; render(); }));
    container.querySelector("#event-filter")?.addEventListener("input", (event) => { search = event.target.value; page = 0; render(); });
    container.querySelector("#event-prev")?.addEventListener("click", () => { page = Math.max(0, page - 1); render(); });
    container.querySelector("#event-next")?.addEventListener("click", () => { page += 1; render(); });
    container.querySelectorAll(".view-trace").forEach((button) => button.addEventListener("click", async () => {
      try { data.trace = await api(`/api/v1/events/trace/${encodeURIComponent(button.dataset.correlation)}`); activeTab = "trace"; render(); } catch (caught) { error = caught.message; render(); }
    }));
    container.querySelectorAll(".retry-dead-letter").forEach((button) => button.addEventListener("click", async () => {
      if (!confirm("Retry this dead-letter item? The operation is idempotent and audited.")) return;
      try { await api(`/api/v1/event-dead-letters/${button.dataset.id}/retry`, { method: "POST" }); await load(); } catch (caught) { error = caught.message; render(); }
    }));
  }

  async function load() {
    loading = true; error = ""; render();
    try {
      const [events, sources, deliveries, subscriptions, outboundDeliveries, deadLetters, metrics] = await Promise.all([
        api("/api/v1/events?limit=100"), api("/api/v1/webhook-sources"), api("/api/v1/webhook-deliveries?limit=100"), api("/api/v1/outbound-webhooks/subscriptions"), api("/api/v1/outbound-webhooks/deliveries?limit=100"), api("/api/v1/event-dead-letters"), api("/api/v1/events/metrics/summary")
      ]);
      data = { ...data, events, sources, deliveries, subscriptions, outboundDeliveries, deadLetters, metrics };
    } catch (caught) { error = caught.message; } finally { loading = false; render(); }
  }

  load();
  return () => { container.innerHTML = ""; };
}
