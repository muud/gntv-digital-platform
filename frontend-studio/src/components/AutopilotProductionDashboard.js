export const AUTOPILOT_TABS = [
  ["overview", "Overview"], ["productions", "Productions"], ["approvals", "Approvals"],
  ["publishing", "Publication Queue"], ["destinations", "Destinations"], ["trace", "Audit / Trace"]
];

export const safeAutopilotText = (value) => String(value ?? "").replace(/[&<>'"]/g, (char) => (
  { "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" }[char]
));

export function summarizeAutopilotMetrics(metrics = {}) {
  const states = metrics.productions_by_state || {};
  return [
    ["Draft", states.draft || 0],
    ["Awaiting Approval", metrics.awaiting_approval || 0],
    ["Publishing Queue", metrics.publishing_queue_depth || 0],
    ["Scheduled", metrics.scheduled_publications || 0],
    ["Partial", metrics.partial_publishing_count || 0],
    ["Published", states.published || 0]
  ];
}

const when = (value) => value ? new Date(value).toLocaleString() : "—";
const badge = (value) => `<strong style="color:${["approved", "published", "verified", "succeeded"].includes(value) ? "#34d399" : ["failed", "rejected", "cancelled"].includes(value) ? "#fb7185" : "#fbbf24"}">${safeAutopilotText(value)}</strong>`;

export function initAutopilotProductionDashboard(container) {
  let active = "overview";
  let loading = true;
  let error = "";
  let filter = "";
  let selected = null;
  const state = { productions: [], approvals: [], publications: [], destinations: [], metrics: {} };
  const base = import.meta.env.VITE_API_URL || "http://localhost:8000";
  const token = () => sessionStorage.getItem("gntv_studio_token") || localStorage.getItem("gntv_auth_token") || "";

  async function api(path, options = {}) {
    const response = await fetch(`${base}${path}`, { ...options, headers: { "Content-Type": "application/json", ...(token() ? { Authorization: `Bearer ${token()}` } : {}) } });
    if (!response.ok) throw new Error((await response.json().catch(() => ({}))).detail || `Request failed (${response.status})`);
    return response.json();
  }
  const visible = (items) => items.filter((item) => !filter || JSON.stringify(item).toLowerCase().includes(filter.toLowerCase()));
  const row = (cells) => `<tr>${cells.map((cell) => `<td style="padding:10px;border-bottom:1px solid #1f2a44;vertical-align:top">${cell}</td>`).join("")}</tr>`;
  const table = (headers, rows, name) => rows.length ? `<div style="overflow:auto"><table style="width:100%;border-collapse:collapse;font-size:12px"><thead><tr>${headers.map((h) => `<th style="text-align:left;padding:10px;color:#93c5fd">${h}</th>`).join("")}</tr></thead><tbody>${rows.join("")}</tbody></table></div>` : `<div style="padding:42px;text-align:center;color:#64748b">No ${name} found.</div>`;

  function content() {
    if (active === "overview") {
      return `<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px">${summarizeAutopilotMetrics(state.metrics).map(([label, value]) => `<article style="padding:16px;background:#101827;border:1px solid #263852;border-radius:8px"><small>${label}</small><div style="font-size:26px;font-weight:850">${value}</div></article>`).join("")}</div>`;
    }
    if (active === "productions") {
      return `<button id="create-production">Create Production</button>` + table(["Production", "Brand", "Type", "Status", "Language", "Target", "Actions"], visible(state.productions).map((p) => row([
        `<button class="select-production" data-id="${p.id}">${safeAutopilotText(p.title)}</button><br><code>${safeAutopilotText(p.correlation_id)}</code>`,
        safeAutopilotText(p.brand), safeAutopilotText(p.content_type), badge(p.status), safeAutopilotText(p.language), when(p.target_publish_at),
        `<button class="production-action" data-id="${p.id}" data-action="start-research">Research</button> <button class="production-action" data-id="${p.id}" data-action="generate-script">Script</button> <button class="approval-request" data-id="${p.id}">Final Approval</button> <button class="publish-action" data-id="${p.id}">Publish</button> <button class="cancel-production" data-id="${p.id}">Cancel</button>`
      ])), "productions") + (selected ? `<aside style="margin-top:12px;padding:12px;background:#111827;border:1px solid #263852"><h3>Production Detail</h3><p>Timeline: Brief → Research → Script → Approval → Production → Assets → Final Approval → Publish → Verify</p><pre>${safeAutopilotText(JSON.stringify(selected, null, 2))}</pre></aside>` : "");
    }
    if (active === "approvals") return table(["Approval", "Production", "Type", "Status", "Requested", "Expires", "Actions"], visible(state.approvals).map((a) => row([a.id.slice(0, 8), a.production_id.slice(0, 8), safeAutopilotText(a.approval_type), badge(a.status), when(a.requested_at), when(a.expires_at), `<button class="approval-action" data-id="${a.id}" data-action="approve">Approve</button> <button class="approval-action" data-id="${a.id}" data-action="reject">Reject</button>`])), "approvals");
    if (active === "publishing") return table(["Attempt", "Production", "Destination", "Status", "Provider", "Scheduled", "Error"], visible(state.publications).map((a) => row([a.id.slice(0, 8), a.production_id.slice(0, 8), a.destination_id.slice(0, 8), badge(a.status), safeAutopilotText(a.provider_reference || "mock pending"), when(a.scheduled_at), safeAutopilotText(a.safe_error_summary || "—")])), "publication attempts");
    if (active === "destinations") return `<button id="create-destination">Add Mock Destination</button>` + table(["Destination", "Platform", "Enabled", "Visibility", "Policy"], visible(state.destinations).map((d) => row([safeAutopilotText(d.name), safeAutopilotText(d.platform), badge(d.enabled ? "approved" : "cancelled"), safeAutopilotText(d.default_visibility), `<code>${safeAutopilotText(JSON.stringify(d.publishing_policy || []))}</code>`])), "destinations");
    return table(["Time", "Signal", "Safe Details"], visible([state.metrics]).map((m) => row([when(new Date()), "autopilot.metrics", `<code>${safeAutopilotText(JSON.stringify(m))}</code>`])), "trace entries");
  }

  function render() {
    container.innerHTML = `<section style="color:#e2e8f0;background:#07111f;min-height:650px;padding:22px;border-radius:12px"><header><h2>GNTV Autopilot</h2><p style="color:#94a3b8">Production and publishing orchestration with approvals, mock distribution, and durable jobs.</p><button id="autopilot-refresh">Refresh</button></header>${error ? `<div role="alert" style="color:#fb7185">${safeAutopilotText(error)}</div>` : ""}<nav style="display:flex;gap:5px;flex-wrap:wrap">${AUTOPILOT_TABS.map(([id, label]) => `<button class="autopilot-tab" data-tab="${id}" style="background:${active === id ? "#f97316" : "#172033"};color:white;padding:8px;border:0;border-radius:6px">${label}</button>`).join("")}</nav><div style="display:flex;margin:12px 0"><input id="autopilot-filter" value="${safeAutopilotText(filter)}" placeholder="Filter productions, approvals, destinations or correlation IDs" style="flex:1;padding:8px;border-radius:6px"></div><div aria-live="polite">${loading ? "Loading Autopilot…" : content()}</div></section>`;
    bind();
  }

  async function mutate(path, body = {}) {
    if (!confirm("Confirm this audited Autopilot action?")) return;
    try { await api(path, { method: "POST", body: JSON.stringify(body) }); await load(); } catch (caught) { error = caught.message; render(); }
  }

  function bind() {
    container.querySelector("#autopilot-refresh")?.addEventListener("click", load);
    container.querySelectorAll(".autopilot-tab").forEach((b) => b.addEventListener("click", () => { active = b.dataset.tab; selected = null; render(); }));
    container.querySelector("#autopilot-filter")?.addEventListener("input", (e) => { filter = e.target.value; render(); });
    container.querySelector("#create-production")?.addEventListener("click", () => mutate("/api/v1/autopilot/productions", { title: `Autopilot Production ${Date.now()}`, slug: `autopilot-${Date.now()}`, brand: "GNTV_DIGITAL", content_type: "NEWS", language: "English", idempotency_key: `ui-${Date.now()}` }));
    container.querySelector("#create-destination")?.addEventListener("click", () => mutate("/api/v1/autopilot/destinations", { name: `Mock Website ${Date.now()}`, platform: "WEBSITE", default_visibility: "private", publishing_policy: ["ALWAYS_REQUIRE_FINAL_APPROVAL"] }));
    container.querySelectorAll(".select-production").forEach((b) => b.addEventListener("click", async () => { selected = await api(`/api/v1/autopilot/productions/${b.dataset.id}`); render(); }));
    container.querySelectorAll(".production-action").forEach((b) => b.addEventListener("click", () => mutate(`/api/v1/autopilot/productions/${b.dataset.id}/${b.dataset.action}`, b.dataset.action === "generate-production-plan" ? {} : { idempotency_key: `${b.dataset.action}-${b.dataset.id}` })));
    container.querySelectorAll(".approval-request").forEach((b) => b.addEventListener("click", () => mutate(`/api/v1/autopilot/productions/${b.dataset.id}/request-approval`, { approval_type: "final_content" })));
    container.querySelectorAll(".publish-action").forEach((b) => b.addEventListener("click", () => mutate(`/api/v1/autopilot/productions/${b.dataset.id}/publish`, { idempotency_key: `publish-${b.dataset.id}` })));
    container.querySelectorAll(".cancel-production").forEach((b) => b.addEventListener("click", () => mutate(`/api/v1/autopilot/productions/${b.dataset.id}/cancel`)));
    container.querySelectorAll(".approval-action").forEach((b) => b.addEventListener("click", () => mutate(`/api/v1/autopilot/approvals/${b.dataset.id}/${b.dataset.action}`, { reason: "Operator decision" })));
  }

  async function load() {
    loading = true; error = ""; render();
    try {
      [state.productions, state.approvals, state.publications, state.destinations, state.metrics] = await Promise.all([
        api("/api/v1/autopilot/productions"), api("/api/v1/autopilot/approvals"),
        api("/api/v1/autopilot/publications"), api("/api/v1/autopilot/destinations"),
        api("/api/v1/autopilot/metrics")
      ]);
    } catch (caught) { error = caught.message; }
    loading = false; render();
  }
  load();
  return () => { container.innerHTML = ""; };
}
