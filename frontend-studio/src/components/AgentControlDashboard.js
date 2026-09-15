export const AGENT_TABS = [
  ["overview", "Overview"], ["agents", "Agents"], ["runs", "Runs"], ["tools", "Tool Calls"],
  ["approvals", "Approvals"], ["models", "Model Policies"], ["tool-policies", "Tool Policies"],
  ["approval-policies", "Approval Policies"], ["audit", "Audit / Trace"]
];

export function summarizeAgentMetrics(metrics = {}) {
  return [
    ["Active Agents", metrics.active_agents ?? 0], ["Paused Agents", metrics.paused_agents ?? 0],
    ["Queued Runs", metrics.queued_runs ?? 0], ["Running Runs", metrics.running_runs ?? 0],
    ["Awaiting Approval", metrics.awaiting_approval_runs ?? 0], ["Succeeded", metrics.succeeded_runs ?? 0],
    ["Failed", metrics.failed_runs ?? 0], ["Blocked", metrics.blocked_runs ?? 0]
  ];
}

export const safeAgentText = (value) => String(value ?? "").replace(/[&<>'"]/g, (char) => (
  { "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" }[char]
));

const when = (value) => value ? new Date(value).toLocaleString() : "—";
const badge = (value) => `<strong style="color:${["active", "succeeded", "approved"].includes(value) ? "#34d399" : ["failed", "blocked", "rejected", "archived"].includes(value) ? "#fb7185" : "#fbbf24"}">${safeAgentText(value)}</strong>`;

export function initAgentControlDashboard(container) {
  let active = "overview";
  let loading = true;
  let error = "";
  let filter = "";
  let page = 0;
  let selected = null;
  const size = 20;
  const state = { agents: [], runs: [], approvals: [], models: [], toolPolicies: [], approvalPolicies: [], audit: [], metrics: {} };
  const base = import.meta.env.VITE_API_URL || "http://localhost:8000";
  const token = () => sessionStorage.getItem("gntv_studio_token") || localStorage.getItem("gntv_auth_token") || "";

  async function api(path, options = {}) {
    const response = await fetch(`${base}${path}`, { ...options, headers: { "Content-Type": "application/json", ...(token() ? { Authorization: `Bearer ${token()}` } : {}) } });
    if (!response.ok) throw new Error((await response.json().catch(() => ({}))).detail || `Request failed (${response.status})`);
    return response.json();
  }
  const visible = (items) => items.filter((item) => !filter || JSON.stringify(item).toLowerCase().includes(filter.toLowerCase())).slice(page * size, (page + 1) * size);
  const row = (cells) => `<tr>${cells.map((cell) => `<td style="padding:9px;border-bottom:1px solid #243047">${cell}</td>`).join("")}</tr>`;
  const table = (headers, rows, name) => rows.length ? `<div style="overflow:auto"><table style="width:100%;border-collapse:collapse;font-size:12px"><thead><tr>${headers.map((h) => `<th style="text-align:left;padding:9px;color:#94a3b8">${h}</th>`).join("")}</tr></thead><tbody>${rows.join("")}</tbody></table></div>` : `<div style="padding:42px;text-align:center;color:#64748b">No ${name} found.</div>`;

  function content() {
    if (active === "overview") return `<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:9px">${summarizeAgentMetrics(state.metrics).map(([label, value]) => `<article style="padding:15px;background:#111827;border:1px solid #263248;border-radius:8px"><small>${label}</small><div style="font-size:25px;font-weight:800">${value}</div></article>`).join("")}</div>`;
    if (active === "agents") return table(["Agent", "Type", "Status", "Model / Tool / Approval", "Instruction", "Limits", "Actions"], visible(state.agents).map((a) => row([
      `<button class="select-agent" data-id="${a.id}">${safeAgentText(a.name)}</button><br><code>${safeAgentText(a.slug)}</code>`,
      safeAgentText(a.agent_type), badge(a.status),
      [state.models.find((p) => p.id === a.model_policy_id)?.name, state.toolPolicies.find((p) => p.id === a.tool_policy_id)?.name, state.approvalPolicies.find((p) => p.id === a.approval_policy_id)?.name].map((value) => safeAgentText(value || "—")).join(" / "),
      `v${a.instruction_version}`,
      `${a.max_iterations} iterations / ${a.max_tool_calls} tools / ${a.max_total_tokens} tokens`,
      `<button class="agent-action" data-id="${a.id}" data-action="activate">Activate</button> <button class="agent-action" data-id="${a.id}" data-action="pause">Pause</button> <button class="agent-action" data-id="${a.id}" data-action="archive">Archive</button> <button class="run-agent" data-id="${a.id}">Run</button>`
    ])), "agents") + (selected ? `<aside style="padding:12px;background:#111827"><h3>Agent Detail</h3><pre>${safeAgentText(JSON.stringify(selected, null, 2))}</pre></aside>` : "");
    if (active === "runs") return table(["Run", "Agent", "State", "Iterations", "Tools", "Tokens", "Cost", "Runtime", "Correlation", "Actions"], visible(state.runs).map((r) => row([
      `<button class="select-run" data-id="${r.id}">${r.id.slice(0, 8)}</button>`, r.agent_id.slice(0, 8), badge(r.status), r.current_iteration,
      r.tool_call_count, r.total_tokens, r.cost_units, `${Number(r.runtime_seconds).toFixed(2)}s`, `<code>${safeAgentText(r.correlation_id)}</code>`,
      `<button class="run-action" data-id="${r.id}" data-action="cancel">Cancel</button> <button class="run-action" data-id="${r.id}" data-action="retry">Retry</button>`
    ])), "runs") + (selected ? `<aside style="padding:12px;background:#111827"><h3>Run Detail / Trace</h3><p><b>Durable job:</b> ${badge(selected.durable_job_status || (selected.job_id ? "queued" : "—"))} · <b>Safe error:</b> ${safeAgentText(selected.safe_error_summary || "—")}</p><pre>${safeAgentText(JSON.stringify(selected, null, 2))}</pre></aside>` : "");
    if (active === "approvals") return table(["Request", "Run", "Type", "Status", "Requested", "Expires", "Actions"], visible(state.approvals).map((a) => row([
      a.id.slice(0, 8), a.agent_run_id.slice(0, 8), safeAgentText(a.approval_type), badge(a.status), when(a.requested_at), when(a.expires_at),
      `<button class="approval-action" data-id="${a.id}" data-action="approve">Approve</button> <button class="approval-action" data-id="${a.id}" data-action="reject">Reject</button>`
    ])), "approvals");
    if (active === "tools") return table(["Run", "Tool", "Status", "Approval", "Safe Error"], state.runs.flatMap((r) => r.tool_calls || []).map((t) => row([t.agent_run_id.slice(0, 8), safeAgentText(t.tool_name), badge(t.status), String(t.requires_approval), safeAgentText(t.safe_error_summary || "—")])), "tool calls");
    if (active === "audit") return table(["Time", "Action", "Correlation", "Sanitized metadata"], visible(state.audit).map((entry) => row([when(entry.created_at), safeAgentText(entry.action), `<code>${safeAgentText(entry.correlation_id || "—")}</code>`, `<code>${safeAgentText(JSON.stringify(entry.metadata || {}))}</code>`])), "audit events");
    const policies = active === "models" ? state.models : active === "tool-policies" ? state.toolPolicies : state.approvalPolicies;
    return table(["Policy", "Enabled", "Configuration"], visible(policies).map((p) => row([safeAgentText(p.name), badge(p.enabled ? "active" : "paused"), `<code>${safeAgentText(JSON.stringify(p))}</code>`])), "policies");
  }

  function render() {
    container.innerHTML = `<section style="color:#e2e8f0;background:#080d18;min-height:650px;padding:22px;border-radius:12px"><header><h2>AI Agent Control Plane</h2><p style="color:#94a3b8">Policy-bound agents, durable execution, approvals, tools and traces.</p><button id="agents-refresh">Refresh</button></header>${error ? `<div role="alert">${safeAgentText(error)}</div>` : ""}<nav style="display:flex;gap:5px;flex-wrap:wrap">${AGENT_TABS.map(([id, label]) => `<button class="agent-tab" data-tab="${id}" style="background:${active === id ? "#2563eb" : "#172033"};color:white;padding:8px;border:0">${label}</button>`).join("")}</nav><div style="display:flex;margin:12px 0"><input id="agent-filter" value="${safeAgentText(filter)}" placeholder="Filter agents, runs, policies or correlation IDs" style="flex:1;padding:8px"><button id="agent-prev">Previous</button><button id="agent-next">Next</button></div><div aria-live="polite">${loading ? "Loading AI agent operations…" : content()}</div></section>`;
    bind();
  }
  async function mutate(path, body = {}) {
    if (!confirm("Confirm this audited AI Agent Control Plane action?")) return;
    try { await api(path, { method: "POST", body: JSON.stringify(body) }); await load(); } catch (caught) { error = caught.message; render(); }
  }
  function bind() {
    container.querySelector("#agents-refresh")?.addEventListener("click", load);
    container.querySelectorAll(".agent-tab").forEach((b) => b.addEventListener("click", () => { active = b.dataset.tab; selected = null; page = 0; render(); }));
    container.querySelector("#agent-filter")?.addEventListener("input", (e) => { filter = e.target.value; page = 0; render(); });
    container.querySelector("#agent-prev")?.addEventListener("click", () => { page = Math.max(0, page - 1); render(); });
    container.querySelector("#agent-next")?.addEventListener("click", () => { page += 1; render(); });
    container.querySelectorAll(".select-agent").forEach((b) => b.addEventListener("click", async () => { selected = state.agents.find((a) => a.id === b.dataset.id); state.audit = await api(`/api/v1/agents/${b.dataset.id}/audit`).catch(() => []); render(); }));
    container.querySelectorAll(".select-run").forEach((b) => b.addEventListener("click", async () => { const run = state.runs.find((r) => r.id === b.dataset.id); let job = null; if (run?.job_id) job = await api(`/api/v1/jobs/${run.job_id}`).catch(() => null); selected = { ...run, durable_job_status: job?.status }; render(); }));
    container.querySelectorAll(".agent-action").forEach((b) => b.addEventListener("click", () => mutate(`/api/v1/agents/${b.dataset.id}/${b.dataset.action}`)));
    container.querySelectorAll(".run-agent").forEach((b) => b.addEventListener("click", () => mutate(`/api/v1/agents/${b.dataset.id}/runs`, { input_json: { request: "Operator initiated run" } })));
    container.querySelectorAll(".run-action").forEach((b) => b.addEventListener("click", () => mutate(`/api/v1/agent-runs/${b.dataset.id}/${b.dataset.action}`)));
    container.querySelectorAll(".approval-action").forEach((b) => b.addEventListener("click", () => mutate(`/api/v1/agent-approvals/${b.dataset.id}/${b.dataset.action}`, { reason: "Operator decision" })));
  }
  async function load() {
    loading = true; error = ""; render();
    try {
      [state.agents, state.runs, state.approvals, state.models, state.toolPolicies, state.approvalPolicies, state.metrics] = await Promise.all([
        api("/api/v1/agents"), api("/api/v1/agent-runs"), api("/api/v1/agent-approvals"),
        api("/api/v1/agent-model-policies"), api("/api/v1/agent-tool-policies"),
        api("/api/v1/agent-approval-policies"), api("/api/v1/agent-metrics")
      ]);
      state.audit = state.agents[0] ? await api(`/api/v1/agents/${state.agents[0].id}/audit`).catch(() => []) : [];
    } catch (caught) { error = caught.message; }
    loading = false; render();
  }
  load();
  return () => { container.innerHTML = ""; };
}
