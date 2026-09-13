export const JOB_TABS = [
  ["overview", "Queue Overview"], ["jobs", "Jobs"], ["workers", "Workers"],
  ["schedules", "Schedules"], ["retry", "Retry Queue"], ["dead", "Dead Letter Jobs"]
];

export function summarizeJobMetrics(metrics = {}) {
  return [
    ["Queued", metrics.queued_jobs ?? 0], ["Running", metrics.running_jobs ?? 0],
    ["Scheduled", metrics.scheduled_jobs ?? 0], ["Succeeded", metrics.succeeded_jobs ?? 0],
    ["Failed", metrics.failed_jobs ?? 0], ["Dead Letter", metrics.dead_letter_jobs ?? 0]
  ];
}

export function formatDuration(job) {
  if (!job?.started_at) return "—";
  const end = job.completed_at || job.failed_at || new Date().toISOString();
  return `${Math.max(0, (new Date(end) - new Date(job.started_at)) / 1000).toFixed(1)}s`;
}

const escapeHTML = (value) => String(value ?? "").replace(/[&<>'"]/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" })[char]);
const when = (value) => value ? new Date(value).toLocaleString() : "—";

export function initBackgroundJobsDashboard(container) {
  let activeTab = "overview";
  let loading = true;
  let error = "";
  let filter = "";
  let page = 0;
  let selectedJob = null;
  const pageSize = 20;
  const state = { jobs: [], workers: [], schedules: [], dead: [], metrics: {} };
  const apiBase = import.meta.env.VITE_API_URL || "http://localhost:8000";
  const token = () => sessionStorage.getItem("gntv_studio_token") || localStorage.getItem("gntv_auth_token") || localStorage.getItem("gntv_token") || "";

  async function api(path, options = {}) {
    const response = await fetch(`${apiBase}${path}`, { ...options, headers: { "Content-Type": "application/json", ...(token() ? { Authorization: `Bearer ${token()}` } : {}) } });
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      throw new Error(body.detail || `Request failed (${response.status})`);
    }
    return response.json();
  }

  const badge = (value) => {
    const good = ["online", "succeeded", "enabled", "retried"].includes(value);
    const bad = ["failed", "dead_lettered", "offline", "unhealthy"].includes(value);
    return `<strong style="color:${good ? "#34d399" : bad ? "#fb7185" : "#fbbf24"};text-transform:uppercase;font-size:10px">${escapeHTML(value)}</strong>`;
  };
  const row = (cells) => `<tr>${cells.map((cell) => `<td style="padding:10px;border-bottom:1px solid #1e293b">${cell}</td>`).join("")}</tr>`;
  const table = (headers, rows, label) => rows.length ? `<div style="overflow:auto"><table style="width:100%;border-collapse:collapse;font-size:12px"><thead><tr>${headers.map((header) => `<th style="text-align:left;padding:10px;color:#94a3b8;border-bottom:1px solid #334155">${header}</th>`).join("")}</tr></thead><tbody>${rows.join("")}</tbody></table></div>` : `<div style="padding:48px;text-align:center;color:#64748b">No ${label} found.</div>`;
  const visible = (items) => items.filter((item) => !filter || JSON.stringify(item).toLowerCase().includes(filter.toLowerCase())).slice(page * pageSize, (page + 1) * pageSize);

  function jobRows(items) {
    return visible(items).map((job) => row([
      `<button class="job-detail" data-id="${job.id}" style="background:none;border:0;color:#60a5fa;cursor:pointer">${escapeHTML(job.id.slice(0, 8))}</button>`,
      escapeHTML(job.job_type), escapeHTML(job.queue_name), badge(job.status), job.priority,
      escapeHTML(job.worker_id || "—"), `${job.retry_count}/${job.max_retries}`, formatDuration(job),
      when(job.scheduled_for), `<code>${escapeHTML(job.correlation_id)}</code>`,
      `<button class="cancel-job" data-id="${job.id}" ${["succeeded", "cancelled", "dead_lettered"].includes(job.status) ? "disabled" : ""}>Cancel</button>`
    ]));
  }

  function detail() {
    if (!selectedJob) return "";
    const attempts = selectedJob.attempts || [];
    return `<aside style="margin-top:16px;padding:16px;background:#111827;border:1px solid #334155;border-radius:8px"><button id="close-job" style="float:right">Close</button><h3>Job Detail · ${escapeHTML(selectedJob.id)}</h3><p><b>Lease:</b> ${when(selectedJob.lease_expires_at)} · <b>Correlation:</b> <code>${escapeHTML(selectedJob.correlation_id)}</code></p><p><b>Safe error:</b> ${escapeHTML(selectedJob.error_details_json?.message || "—")}</p><h4>Execution Attempts</h4>${table(["Attempt", "Worker", "Status", "Started", "Completed", "Error"], attempts.map((attempt) => row([attempt.attempt_number, escapeHTML(attempt.worker_id), badge(attempt.status), when(attempt.started_at), when(attempt.completed_at), escapeHTML(attempt.error_message || "—")])), "attempts")}</aside>`;
  }

  function content() {
    if (activeTab === "overview") return `<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(145px,1fr));gap:10px">${summarizeJobMetrics(state.metrics).map(([label, value]) => `<article style="padding:16px;background:#111827;border:1px solid #263248;border-radius:8px"><small style="color:#94a3b8;text-transform:uppercase">${label}</small><div style="font-size:26px;font-weight:800">${value}</div></article>`).join("")}</div><div style="margin-top:18px">${table(["Queue", "Jobs"], Object.entries(state.metrics.jobs_by_queue || {}).map(([name, count]) => row([escapeHTML(name), count])), "queues")}</div>`;
    if (activeTab === "workers") return table(["Worker", "Queues", "State", "Active", "Completed", "Failed", "Heartbeat", "Version"], visible(state.workers).map((worker) => row([escapeHTML(worker.worker_id), escapeHTML(worker.queues_json.join(", ")), badge(worker.status), worker.active_job_count, worker.completed_job_count, worker.failed_job_count, when(worker.last_heartbeat_at), escapeHTML(worker.version)])), "workers");
    if (activeTab === "schedules") return table(["Schedule", "Job Type", "Recurrence", "Timezone", "Next Run", "Policy", "Concurrency", "Action"], visible(state.schedules).map((schedule) => row([escapeHTML(schedule.name), escapeHTML(schedule.job_type), badge(schedule.recurrence_type), escapeHTML(schedule.timezone), when(schedule.next_run_at), escapeHTML(schedule.misfire_policy), schedule.max_concurrent_runs, `<button class="toggle-schedule" data-id="${schedule.id}" data-enabled="${schedule.is_enabled}">${schedule.is_enabled ? "Disable" : "Enable"}</button>`])), "schedules");
    if (activeTab === "dead") return table(["Job", "State", "Reason", "Retries", "Created", "Action"], visible(state.dead).map((letter) => row([escapeHTML(letter.job_id), badge(letter.status), escapeHTML(letter.reason), letter.retry_count, when(letter.created_at), `<button class="retry-job" data-id="${letter.job_id}">Retry</button>`])), "dead letters");
    const jobs = activeTab === "retry" ? state.jobs.filter((job) => job.status === "waiting_retry") : state.jobs;
    return table(["ID", "Type", "Queue", "State", "Priority", "Worker", "Retries", "Duration", "Scheduled", "Correlation", "Action"], jobRows(jobs), "jobs") + detail();
  }

  function bind() {
    container.querySelector("#jobs-refresh")?.addEventListener("click", load);
    container.querySelectorAll(".jobs-tab").forEach((button) => button.addEventListener("click", () => { activeTab = button.dataset.tab; page = 0; selectedJob = null; render(); }));
    container.querySelector("#jobs-filter")?.addEventListener("input", (event) => { filter = event.target.value; page = 0; render(); });
    container.querySelector("#jobs-prev")?.addEventListener("click", () => { page = Math.max(0, page - 1); render(); });
    container.querySelector("#jobs-next")?.addEventListener("click", () => { page += 1; render(); });
    container.querySelector("#close-job")?.addEventListener("click", () => { selectedJob = null; render(); });
    container.querySelectorAll(".job-detail").forEach((button) => button.addEventListener("click", () => { selectedJob = state.jobs.find((job) => job.id === button.dataset.id); render(); }));
    container.querySelectorAll(".cancel-job").forEach((button) => button.addEventListener("click", async () => { if (confirm("Cancel this job? Running work will receive a cooperative cancellation request.")) await mutate(`/api/v1/jobs/${button.dataset.id}/cancel`); }));
    container.querySelectorAll(".retry-job").forEach((button) => button.addEventListener("click", async () => { if (confirm("Retry this dead-letter job? This transition is audited and idempotent.")) await mutate(`/api/v1/jobs/${button.dataset.id}/retry`); }));
    container.querySelectorAll(".toggle-schedule").forEach((button) => button.addEventListener("click", async () => mutate(`/api/v1/jobs/schedules/${button.dataset.id}/${button.dataset.enabled === "true" ? "disable" : "enable"}`)));
  }

  function render() {
    container.innerHTML = `<section style="color:#e2e8f0;background:#080d18;min-height:650px;border:1px solid #1e293b;border-radius:12px;padding:22px"><header style="display:flex;justify-content:space-between"><div><h2 style="margin:0">Background Jobs / Scheduler Operations</h2><p style="color:#94a3b8">Durable queues, workers, retries, leases and recurring execution.</p></div><button id="jobs-refresh">Refresh</button></header>${error ? `<div role="alert" style="padding:10px;background:#7f1d1d66;border:1px solid #ef4444">${escapeHTML(error)}</div>` : ""}<nav style="display:flex;gap:6px;flex-wrap:wrap;margin:15px 0">${JOB_TABS.map(([id, label]) => `<button class="jobs-tab" data-tab="${id}" style="padding:8px;background:${activeTab === id ? "#2563eb" : "#172033"};color:white;border:0;border-radius:5px">${label}</button>`).join("")}</nav><div style="display:flex;gap:8px;margin-bottom:12px"><input id="jobs-filter" value="${escapeHTML(filter)}" placeholder="Filter type, queue, state, correlation" style="flex:1;padding:8px;background:#111827;color:white;border:1px solid #334155"><button id="jobs-prev" ${page === 0 ? "disabled" : ""}>Previous</button><button id="jobs-next">Next</button></div><div aria-live="polite">${loading ? `<div style="padding:48px;text-align:center;color:#94a3b8">Loading background operations…</div>` : content()}</div></section>`;
    bind();
  }

  async function mutate(path) {
    try { await api(path, { method: "POST" }); await load(); } catch (caught) { error = caught.message; render(); }
  }

  async function load() {
    loading = true; error = ""; render();
    try {
      const [jobsResp, workersResp, schedulesResp, deadResp, metricsResp] = await Promise.all([
        api("/api/v1/jobs/?limit=200"),
        api("/api/v1/jobs/workers/"),
        api("/api/v1/jobs/schedules/"),
        api("/api/v1/jobs/dlq/"),
        api("/api/v1/jobs/metrics"),
      ]);
      state.jobs = jobsResp.items ?? jobsResp;
      state.workers = workersResp.items ?? workersResp;
      state.schedules = schedulesResp.items ?? schedulesResp;
      state.dead = deadResp.items ?? deadResp;
      state.metrics = metricsResp;
    } catch (caught) { error = caught.message; }
    loading = false; render();
  }

  load();
  return () => { container.innerHTML = ""; };
}
