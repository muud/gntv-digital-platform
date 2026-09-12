export function formatWorkflowDuration(startedAt, endedAt, now = Date.now()) {
  if (!startedAt) return "—";
  const start = new Date(startedAt).getTime();
  const end = endedAt ? new Date(endedAt).getTime() : now;
  if (!Number.isFinite(start) || !Number.isFinite(end) || end < start) return "—";
  const totalSeconds = Math.floor((end - start) / 1000);
  if (totalSeconds < 60) return `${totalSeconds}s`;
  const minutes = Math.floor(totalSeconds / 60);
  return `${minutes}m ${totalSeconds % 60}s`;
}

export function collectPendingApprovals(runs) {
  return runs.filter((run) => run.status === "waiting");
}

export function initWorkflowOperationsDashboard(container) {
  let activeTab = "overview"; // "overview" | "workflows" | "runs" | "approvals" | "schedules"
  let selectedWorkflowId = null;
  let selectedRunId = null;
  let isLoading = false;
  let errorMessage = null;
  let successMessage = null;

  let metrics = {
    runs_queued: 0,
    runs_running: 0,
    runs_waiting: 0,
    runs_succeeded: 0,
    runs_failed: 0,
    runs_cancelled: 0,
    total_runs: 0,
    average_duration_seconds: 0.0,
    total_retries: 0,
    pending_approvals: 0
  };

  let workflows = [];
  let workflowRuns = [];
  let selectedWorkflow = null;
  let selectedRun = null;
  let schedules = [];

  const apiBase = import.meta.env.VITE_API_URL || "http://localhost:8000";

  function getAuthToken() {
    return (
      sessionStorage.getItem("gntv_studio_token") ||
      localStorage.getItem("gntv_auth_token") ||
      localStorage.getItem("gntv_token") ||
      ""
    );
  }

  async function api(path, options = {}) {
    const token = getAuthToken();
    const headers = {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(options.headers || {})
    };
    const response = await fetch(`${apiBase}${path}`, { ...options, headers });
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      throw new Error(body.detail || `Request failed with status ${response.status}`);
    }
    return response.json();
  }

  async function loadData() {
    isLoading = true;
    errorMessage = null;
    render();
    try {
      const [m, wfList, rList] = await Promise.all([
        api("/api/v1/workflows/metrics/summary"),
        api("/api/v1/workflows"),
        api("/api/v1/workflow-runs?limit=50")
      ]);
      metrics = m;
      workflows = wfList;
      workflowRuns = rList;
      const scheduleGroups = await Promise.all(
        workflows.map((workflow) =>
          api(`/api/v1/workflows/${workflow.id}/schedules`).then((items) =>
            items.map((schedule) => ({ ...schedule, workflow_name: workflow.name }))
          )
        )
      );
      schedules = scheduleGroups.flat();

      if (selectedWorkflowId) {
        selectedWorkflow = await api(`/api/v1/workflows/${selectedWorkflowId}`).catch(() => null);
      }
      if (selectedRunId) {
        selectedRun = await api(`/api/v1/workflow-runs/${selectedRunId}`).catch(() => null);
      }
    } catch (err) {
      errorMessage = err.message;
    } finally {
      isLoading = false;
      render();
    }
  }

  function renderKPIs() {
    return `
      <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 14px; margin-bottom: 24px;">
        <div style="background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.08); border-radius: 10px; padding: 14px 18px;">
          <div style="font-size: 11px; text-transform: uppercase; letter-spacing: 0.8px; color: rgba(255,255,255,0.5);">Total Runs</div>
          <div style="font-size: 24px; font-weight: 800; color: #fff; margin-top: 4px;">${metrics.total_runs}</div>
        </div>
        <div style="background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.08); border-radius: 10px; padding: 14px 18px;">
          <div style="font-size: 11px; text-transform: uppercase; letter-spacing: 0.8px; color: rgba(255,255,255,0.5);">Running</div>
          <div style="font-size: 24px; font-weight: 800; color: #38bdf8; margin-top: 4px;">${metrics.runs_running}</div>
        </div>
        <div style="background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.08); border-radius: 10px; padding: 14px 18px;">
          <div style="font-size: 11px; text-transform: uppercase; letter-spacing: 0.8px; color: rgba(255,255,255,0.5);">Pending Approvals</div>
          <div style="font-size: 24px; font-weight: 800; color: #fbbf24; margin-top: 4px;">${metrics.pending_approvals}</div>
        </div>
        <div style="background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.08); border-radius: 10px; padding: 14px 18px;">
          <div style="font-size: 11px; text-transform: uppercase; letter-spacing: 0.8px; color: rgba(255,255,255,0.5);">Succeeded</div>
          <div style="font-size: 24px; font-weight: 800; color: #34d399; margin-top: 4px;">${metrics.runs_succeeded}</div>
        </div>
        <div style="background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.08); border-radius: 10px; padding: 14px 18px;">
          <div style="font-size: 11px; text-transform: uppercase; letter-spacing: 0.8px; color: rgba(255,255,255,0.5);">Failed</div>
          <div style="font-size: 24px; font-weight: 800; color: #f87171; margin-top: 4px;">${metrics.runs_failed}</div>
        </div>
        <div style="background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.08); border-radius: 10px; padding: 14px 18px;">
          <div style="font-size: 11px; text-transform: uppercase; letter-spacing: 0.8px; color: rgba(255,255,255,0.5);">Total Retries</div>
          <div style="font-size: 24px; font-weight: 800; color: #a78bfa; margin-top: 4px;">${metrics.total_retries}</div>
        </div>
      </div>
    `;
  }

  function getStatusBadge(status) {
    const colors = {
      active: "#34d399",
      succeeded: "#34d399",
      running: "#38bdf8",
      queued: "#94a3b8",
      waiting: "#fbbf24",
      failed: "#f87171",
      cancelled: "#94a3b8",
      draft: "#94a3b8",
      paused: "#fbbf24",
      archived: "#64748b"
    };
    const color = colors[status] || "#94a3b8";
    return `<span style="display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: 700; text-transform: uppercase; background: ${color}20; color: ${color}; border: 1px solid ${color}40;">${status}</span>`;
  }

  function renderWorkflowsTab() {
    if (workflows.length === 0) {
      return `<div style="padding: 40px; text-align: center; color: rgba(255,255,255,0.5); font-size: 14px;">No workflow definitions found. Click "Create Workflow" to initialize one.</div>`;
    }
    return `
      <div style="overflow-x: auto;">
        <table style="width: 100%; border-collapse: collapse; text-align: left; font-size: 13px;">
          <thead>
            <tr style="border-bottom: 1px solid rgba(255,255,255,0.1); color: rgba(255,255,255,0.6); font-size: 11px; text-transform: uppercase;">
              <th style="padding: 10px 14px;">Name</th>
              <th style="padding: 10px 14px;">Status</th>
              <th style="padding: 10px 14px;">Version</th>
              <th style="padding: 10px 14px;">Steps</th>
              <th style="padding: 10px 14px;">Type</th>
              <th style="padding: 10px 14px;">Updated</th>
              <th style="padding: 10px 14px; text-align: right;">Actions</th>
            </tr>
          </thead>
          <tbody>
            ${workflows
              .map(
                (w) => `
              <tr style="border-bottom: 1px solid rgba(255,255,255,0.05); cursor: pointer;" class="workflow-row" data-id="${w.id}">
                <td style="padding: 12px 14px; font-weight: 700; color: #fff;">${w.name}</td>
                <td style="padding: 12px 14px;">${getStatusBadge(w.status)}</td>
                <td style="padding: 12px 14px; color: rgba(255,255,255,0.7);">v${w.version}</td>
                <td style="padding: 12px 14px; color: rgba(255,255,255,0.7);">${w.steps ? w.steps.length : 0}</td>
                <td style="padding: 12px 14px; color: rgba(255,255,255,0.7);">${w.workflow_type}</td>
                <td style="padding: 12px 14px; color: rgba(255,255,255,0.5);">${new Date(w.updated_at).toLocaleString()}</td>
                <td style="padding: 12px 14px; text-align: right;">
                  <button class="btn-run-wf" data-id="${w.id}" style="background: var(--brand-primary, #e50914); border: none; color: #fff; padding: 6px 12px; border-radius: 4px; font-size: 11px; font-weight: 700; cursor: pointer;">Run</button>
                  ${
                    w.status === "draft" || w.status === "paused"
                      ? `<button class="btn-activate-wf" data-id="${w.id}" style="background: #059669; border: none; color: #fff; padding: 6px 10px; border-radius: 4px; font-size: 11px; font-weight: 700; cursor: pointer; margin-left: 6px;">Activate</button>`
                      : ""
                  }
                  ${
                    w.status === "active"
                      ? `<button class="btn-pause-wf" data-id="${w.id}" style="background: #d97706; border: none; color: #fff; padding: 6px 10px; border-radius: 4px; font-size: 11px; font-weight: 700; cursor: pointer; margin-left: 6px;">Pause</button>`
                      : ""
                  }
                </td>
              </tr>
            `
              )
              .join("")}
          </tbody>
        </table>
      </div>
    `;
  }

  function renderRunsTab() {
    if (workflowRuns.length === 0) {
      return `<div style="padding: 40px; text-align: center; color: rgba(255,255,255,0.5); font-size: 14px;">No workflow runs recorded yet.</div>`;
    }
    return `
      <div style="overflow-x: auto;">
        <table style="width: 100%; border-collapse: collapse; text-align: left; font-size: 13px;">
          <thead>
            <tr style="border-bottom: 1px solid rgba(255,255,255,0.1); color: rgba(255,255,255,0.6); font-size: 11px; text-transform: uppercase;">
              <th style="padding: 10px 14px;">Run ID</th>
              <th style="padding: 10px 14px;">Status</th>
              <th style="padding: 10px 14px;">Trigger</th>
              <th style="padding: 10px 14px;">Step</th>
              <th style="padding: 10px 14px;">Retries</th>
              <th style="padding: 10px 14px;">Duration</th>
              <th style="padding: 10px 14px;">Created</th>
              <th style="padding: 10px 14px; text-align: right;">Action</th>
            </tr>
          </thead>
          <tbody>
            ${workflowRuns
              .map(
                (r) => `
              <tr style="border-bottom: 1px solid rgba(255,255,255,0.05); cursor: pointer;" class="run-row" data-id="${r.id}">
                <td style="padding: 12px 14px; font-family: monospace; color: #38bdf8;">${r.id.substring(0, 8)}...</td>
                <td style="padding: 12px 14px;">${getStatusBadge(r.status)}</td>
                <td style="padding: 12px 14px; color: rgba(255,255,255,0.7); text-transform: capitalize;">${r.trigger_type}</td>
                <td style="padding: 12px 14px; color: rgba(255,255,255,0.7);">Step ${r.current_step_order}</td>
                <td style="padding: 12px 14px; color: rgba(255,255,255,0.7);">${r.retry_count}</td>
                <td style="padding: 12px 14px; color: rgba(255,255,255,0.7);">${formatWorkflowDuration(r.started_at, r.ended_at)}</td>
                <td style="padding: 12px 14px; color: rgba(255,255,255,0.5);">${new Date(r.created_at).toLocaleString()}</td>
                <td style="padding: 12px 14px; text-align: right;">
                  ${
                    r.status === "running" || r.status === "waiting" || r.status === "queued"
                      ? `<button class="btn-cancel-run" data-id="${r.id}" style="background: rgba(239, 68, 68, 0.2); border: 1px solid rgba(239, 68, 68, 0.4); color: #f87171; padding: 4px 10px; border-radius: 4px; font-size: 11px; font-weight: 700; cursor: pointer;">Cancel</button>`
                      : ""
                  }
                </td>
              </tr>
            `
              )
              .join("")}
          </tbody>
        </table>
      </div>
    `;
  }

  function renderApprovalsTab() {
    const waitingRuns = collectPendingApprovals(workflowRuns);
    if (waitingRuns.length === 0) {
      return `<div style="padding: 40px; text-align: center; color: rgba(255,255,255,0.5); font-size: 14px;">No pending manual approvals in queue. All workflows are clear.</div>`;
    }
    return `
      <div style="display: flex; flex-direction: column; gap: 16px;">
        ${waitingRuns
          .map(
            (r) => `
          <div style="background: rgba(251, 191, 36, 0.05); border: 1px solid rgba(251, 191, 36, 0.2); border-radius: 8px; padding: 18px; display: flex; justify-content: space-between; align-items: center;">
            <div>
              <div style="display: flex; align-items: center; gap: 10px;">
                <span style="font-weight: 800; color: #fbbf24; font-size: 14px;">APPROVAL REQUIRED</span>
                <span style="font-family: monospace; color: rgba(255,255,255,0.6); font-size: 12px;">Run: ${r.id}</span>
              </div>
              <div style="color: rgba(255,255,255,0.8); font-size: 13px; margin-top: 6px;">
                Workflow waiting at Step ${r.current_step_order}. Operator authorization needed to resume.
              </div>
              <div style="color: rgba(255,255,255,0.4); font-size: 11px; margin-top: 4px;">
                Triggered via ${r.trigger_type} at ${new Date(r.created_at).toLocaleString()}
              </div>
            </div>
            <div style="display: flex; gap: 8px;">
              <button class="btn-inspect-approval" data-run-id="${r.id}" style="background: rgba(255,255,255,0.1); border: 1px solid rgba(255,255,255,0.2); color: #fff; padding: 8px 14px; border-radius: 6px; font-size: 12px; font-weight: 700; cursor: pointer;">Inspect & Decide</button>
            </div>
          </div>
        `
          )
          .join("")}
      </div>
    `;
  }

  function renderSchedulesTab() {
    if (schedules.length === 0) {
      return `<div style="padding: 40px; text-align: center; color: rgba(255,255,255,0.5); font-size: 14px;">No one-time or recurring schedules configured.</div>`;
    }
    return `
      <div style="overflow-x:auto">
        <table style="width:100%;border-collapse:collapse;text-align:left;font-size:13px">
          <thead><tr style="border-bottom:1px solid rgba(255,255,255,.1);color:rgba(255,255,255,.6);font-size:11px;text-transform:uppercase">
            <th style="padding:10px 14px">Workflow</th><th>Type</th><th>Expression / Next Run</th><th>Timezone</th><th>Status</th>
          </tr></thead>
          <tbody>${schedules.map((schedule) => `
            <tr style="border-bottom:1px solid rgba(255,255,255,.05)">
              <td style="padding:12px 14px;font-weight:700">${schedule.workflow_name}</td>
              <td>${schedule.schedule_type}</td>
              <td style="font-family:monospace">${schedule.cron_expression || new Date(schedule.next_run_at).toLocaleString()}</td>
              <td>${schedule.timezone}</td><td>${schedule.is_enabled ? "Enabled" : "Disabled"}</td>
            </tr>`).join("")}</tbody>
        </table>
      </div>`;
  }

  function renderWorkflowDetailModal() {
    if (!selectedWorkflow) return "";
    return `
      <div style="position:fixed;inset:0;background:rgba(0,0,0,.8);display:flex;align-items:center;justify-content:center;z-index:9999;padding:24px">
        <div style="background:#111;border:1px solid rgba(255,255,255,.15);border-radius:12px;max-width:720px;width:100%;padding:24px">
          <div style="display:flex;justify-content:space-between"><div><h2 style="margin:0">${selectedWorkflow.name}</h2><p style="color:rgba(255,255,255,.55)">${selectedWorkflow.description || "No description"}</p></div><button id="btn-close-workflow-detail" style="background:none;border:0;color:#fff;font-size:20px;cursor:pointer">✕</button></div>
          <div style="display:flex;gap:12px;margin:14px 0">${getStatusBadge(selectedWorkflow.status)}<span>Version ${selectedWorkflow.version}</span><span>${selectedWorkflow.workflow_type}</span></div>
          <h3 style="font-size:13px;text-transform:uppercase">Ordered Steps</h3>
          ${(selectedWorkflow.steps || []).map((step) => `<div style="padding:10px;border-top:1px solid rgba(255,255,255,.08)">${step.step_order}. <strong>${step.name}</strong> · ${step.step_type} · retries ${step.max_retries}</div>`).join("")}
        </div>
      </div>`;
  }

  function renderRunDetailModal() {
    if (!selectedRun) return "";
    const steps = selectedRun.step_executions || [];
    return `
      <div style="position: fixed; inset: 0; background: rgba(0,0,0,0.8); backdrop-filter: blur(4px); display: flex; align-items: center; justify-content: center; z-index: 9999; padding: 24px;">
        <div style="background: #111; border: 1px solid rgba(255,255,255,0.15); border-radius: 12px; max-width: 800px; width: 100%; max-height: 85vh; overflow-y: auto; padding: 24px;">
          <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 20px;">
            <div>
              <div style="font-size: 18px; font-weight: 800; color: #fff;">Workflow Run Timeline</div>
              <div style="font-family: monospace; font-size: 12px; color: rgba(255,255,255,0.5); margin-top: 4px;">ID: ${selectedRun.id}</div>
            </div>
            <button id="btn-close-modal" style="background: none; border: none; font-size: 20px; color: #fff; cursor: pointer;">✕</button>
          </div>

          <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin-bottom: 20px; background: rgba(255,255,255,0.02); padding: 12px; border-radius: 8px;">
            <div><span style="color: rgba(255,255,255,0.4); font-size: 11px;">STATUS</span><div>${getStatusBadge(selectedRun.status)}</div></div>
            <div><span style="color: rgba(255,255,255,0.4); font-size: 11px;">TRIGGER</span><div style="color: #fff; font-size: 13px;">${selectedRun.trigger_type}</div></div>
            <div><span style="color: rgba(255,255,255,0.4); font-size: 11px;">RETRIES</span><div style="color: #fff; font-size: 13px;">${selectedRun.retry_count}</div></div>
          </div>

          ${selectedRun.error_summary ? `<div style="background: rgba(239,68,68,0.1); border: 1px solid rgba(239,68,68,0.3); color: #f87171; padding: 10px 14px; border-radius: 6px; font-size: 12px; margin-bottom: 18px;">${selectedRun.error_summary}</div>` : ""}

          <div style="font-size: 13px; font-weight: 700; color: rgba(255,255,255,0.8); margin-bottom: 12px; text-transform: uppercase;">Step Execution Sequence</div>
          <div style="display: flex; flex-direction: column; gap: 10px;">
            ${steps
              .map(
                (s) => `
              <div style="background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.08); border-radius: 8px; padding: 14px;">
                <div style="display: flex; justify-content: space-between; align-items: center;">
                  <div style="display: flex; align-items: center; gap: 10px;">
                    <span style="font-weight: 800; font-size: 13px; color: #fff;">${s.step_order}. ${s.step_name}</span>
                    <span style="font-size: 10px; font-family: monospace; background: rgba(255,255,255,0.08); padding: 2px 6px; border-radius: 3px; color: rgba(255,255,255,0.7);">${s.step_type}</span>
                  </div>
                  <div>${getStatusBadge(s.status)}</div>
                </div>
                ${
                  s.status === "waiting"
                    ? `
                  <div style="margin-top: 14px; padding-top: 12px; border-top: 1px solid rgba(255,255,255,0.1); display: flex; gap: 10px;">
                    <input type="text" id="approval-notes-${s.id}" placeholder="Optional operator review notes" style="flex: 1; background: rgba(0,0,0,0.5); border: 1px solid rgba(255,255,255,0.2); color: #fff; padding: 6px 10px; border-radius: 4px; font-size: 12px;">
                    <button class="btn-approve-step" data-run-id="${selectedRun.id}" data-step-id="${s.id}" style="background: #059669; border: none; color: #fff; padding: 6px 14px; border-radius: 4px; font-weight: 700; font-size: 12px; cursor: pointer;">Approve</button>
                    <button class="btn-reject-step" data-run-id="${selectedRun.id}" data-step-id="${s.id}" style="background: #dc2626; border: none; color: #fff; padding: 6px 14px; border-radius: 4px; font-weight: 700; font-size: 12px; cursor: pointer;">Reject</button>
                  </div>
                `
                    : ""
                }
              </div>
            `
              )
              .join("")}
          </div>
        </div>
      </div>
    `;
  }

  function renderCreateWorkflowModal() {
    return `
      <div id="modal-create-wf" style="display: none; position: fixed; inset: 0; background: rgba(0,0,0,0.8); backdrop-filter: blur(4px); align-items: center; justify-content: center; z-index: 9999; padding: 24px;">
        <div style="background: #111; border: 1px solid rgba(255,255,255,0.15); border-radius: 12px; max-width: 600px; width: 100%; padding: 24px;">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 18px;">
            <div style="font-size: 16px; font-weight: 800; color: #fff;">Create Workflow Definition</div>
            <button id="btn-close-create-wf" style="background: none; border: none; font-size: 20px; color: #fff; cursor: pointer;">✕</button>
          </div>
          <form id="form-create-wf" style="display: flex; flex-direction: column; gap: 14px;">
            <div>
              <label style="display: block; font-size: 11px; text-transform: uppercase; color: rgba(255,255,255,0.6); margin-bottom: 4px;">Name</label>
              <input type="text" name="name" required style="width: 100%; background: rgba(0,0,0,0.5); border: 1px solid rgba(255,255,255,0.2); color: #fff; padding: 8px 12px; border-radius: 6px; font-size: 13px;">
            </div>
            <div>
              <label style="display: block; font-size: 11px; text-transform: uppercase; color: rgba(255,255,255,0.6); margin-bottom: 4px;">Description</label>
              <input type="text" name="description" style="width: 100%; background: rgba(0,0,0,0.5); border: 1px solid rgba(255,255,255,0.2); color: #fff; padding: 8px 12px; border-radius: 6px; font-size: 13px;">
            </div>
            <div>
              <label style="display: block; font-size: 11px; text-transform: uppercase; color: rgba(255,255,255,0.6); margin-bottom: 4px;">Workflow Type</label>
              <select name="workflow_type" style="width: 100%; background: rgba(0,0,0,0.5); border: 1px solid rgba(255,255,255,0.2); color: #fff; padding: 8px 12px; border-radius: 6px; font-size: 13px;">
                <option value="content_publishing">Content Publishing</option>
                <option value="syndication_sync">Syndication Sync</option>
                <option value="reporting_batch">Reporting Batch</option>
                <option value="standard">Standard Internal</option>
              </select>
            </div>
            <div style="display: flex; justify-content: flex-end; gap: 10px; margin-top: 10px;">
              <button type="button" id="btn-cancel-create-wf" style="background: transparent; border: 1px solid rgba(255,255,255,0.2); color: #fff; padding: 8px 16px; border-radius: 6px; font-size: 12px; cursor: pointer;">Cancel</button>
              <button type="submit" style="background: var(--brand-primary, #e50914); border: none; color: #fff; padding: 8px 16px; border-radius: 6px; font-size: 12px; font-weight: 700; cursor: pointer;">Create Workflow</button>
            </div>
          </form>
        </div>
      </div>
    `;
  }

  function render() {
    container.innerHTML = `
      <div style="display: flex; flex-direction: column; width: 100%; min-height: 100%; font-family: var(--font-sans, system-ui); color: #fff; padding: 24px;">
        <!-- Header -->
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px;">
          <div>
            <h1 style="font-size: 22px; font-weight: 800; letter-spacing: -0.5px; margin: 0; display: flex; align-items: center; gap: 8px;">
              ⚡ Workflow Orchestration & Job Execution
            </h1>
            <p style="color: rgba(255,255,255,0.5); font-size: 13px; margin: 4px 0 0 0;">
              Infrastructure for multi-step automated operational workflows, idempotent executions, and operator approvals.
            </p>
          </div>
          <div style="display: flex; gap: 10px;">
            <button id="btn-refresh" style="background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.12); color: #fff; padding: 8px 16px; border-radius: 6px; font-size: 12px; font-weight: 700; cursor: pointer;">
              🔄 Refresh
            </button>
            <button id="btn-open-create-wf" style="background: var(--brand-primary, #e50914); border: none; color: #fff; padding: 8px 16px; border-radius: 6px; font-size: 12px; font-weight: 700; cursor: pointer;">
              + New Workflow
            </button>
          </div>
        </div>

        <!-- Alert messages -->
        ${errorMessage ? `<div style="background: rgba(239, 68, 68, 0.15); border: 1px solid rgba(239, 68, 68, 0.3); color: #fca5a5; padding: 12px 16px; border-radius: 8px; font-size: 13px; margin-bottom: 20px;">${errorMessage}</div>` : ""}
        ${successMessage ? `<div style="background: rgba(16, 185, 129, 0.15); border: 1px solid rgba(16, 185, 129, 0.3); color: #6ee7b7; padding: 12px 16px; border-radius: 8px; font-size: 13px; margin-bottom: 20px;">${successMessage}</div>` : ""}

        <!-- KPIs -->
        ${renderKPIs()}

        <!-- Nav Tabs -->
        <div style="display: flex; gap: 8px; border-bottom: 1px solid rgba(255,255,255,0.1); margin-bottom: 20px;">
          <button class="nav-tab ${activeTab === "overview" ? "active" : ""}" data-tab="overview" style="background: none; border: none; border-bottom: 2px solid ${activeTab === "overview" ? "var(--brand-primary, #e50914)" : "transparent"}; color: ${activeTab === "overview" ? "#fff" : "rgba(255,255,255,0.6)"}; padding: 10px 16px; font-size: 13px; font-weight: 700; cursor: pointer;">Workflows</button>
          <button class="nav-tab ${activeTab === "runs" ? "active" : ""}" data-tab="runs" style="background: none; border: none; border-bottom: 2px solid ${activeTab === "runs" ? "var(--brand-primary, #e50914)" : "transparent"}; color: ${activeTab === "runs" ? "#fff" : "rgba(255,255,255,0.6)"}; padding: 10px 16px; font-size: 13px; font-weight: 700; cursor: pointer;">Runs History</button>
          <button class="nav-tab ${activeTab === "approvals" ? "active" : ""}" data-tab="approvals" style="background: none; border: none; border-bottom: 2px solid ${activeTab === "approvals" ? "var(--brand-primary, #e50914)" : "transparent"}; color: ${activeTab === "approvals" ? "#fff" : "rgba(255,255,255,0.6)"}; padding: 10px 16px; font-size: 13px; font-weight: 700; cursor: pointer;">Approval Queue ${metrics.pending_approvals > 0 ? `(${metrics.pending_approvals})` : ""}</button>
          <button class="nav-tab ${activeTab === "schedules" ? "active" : ""}" data-tab="schedules" style="background:none;border:none;border-bottom:2px solid ${activeTab === "schedules" ? "var(--brand-primary, #e50914)" : "transparent"};color:${activeTab === "schedules" ? "#fff" : "rgba(255,255,255,.6)"};padding:10px 16px;font-size:13px;font-weight:700;cursor:pointer">Schedules</button>
        </div>

        <!-- Main Content Area -->
        <div style="background: rgba(255,255,255,0.02); border: 1px solid rgba(255,255,255,0.06); border-radius: 10px; padding: 20px;">
          ${isLoading ? `<div style="text-align: center; padding: 40px; color: rgba(255,255,255,0.5);">Loading workflow data...</div>` : ""}
          ${!isLoading && activeTab === "overview" ? renderWorkflowsTab() : ""}
          ${!isLoading && activeTab === "runs" ? renderRunsTab() : ""}
          ${!isLoading && activeTab === "approvals" ? renderApprovalsTab() : ""}
          ${!isLoading && activeTab === "schedules" ? renderSchedulesTab() : ""}
        </div>

        ${renderRunDetailModal()}
        ${renderWorkflowDetailModal()}
        ${renderCreateWorkflowModal()}
      </div>
    `;

    bindEvents();
  }

  function bindEvents() {
    // Tab switching
    container.querySelectorAll(".nav-tab").forEach((btn) => {
      btn.addEventListener("click", () => {
        activeTab = btn.getAttribute("data-tab");
        render();
      });
    });

    // Refresh
    container.querySelector("#btn-refresh")?.addEventListener("click", () => {
      loadData();
    });

    // Run workflow button
    container.querySelectorAll(".btn-run-wf").forEach((btn) => {
      btn.addEventListener("click", async (e) => {
        e.stopPropagation();
        const id = btn.getAttribute("data-id");
        if (!window.confirm("Run this active workflow now?")) return;
        try {
          await api(`/api/v1/workflows/${id}/run`, {
            method: "POST",
            body: JSON.stringify({ input_metadata: { content_id: "demo-content-01" } })
          });
          successMessage = "Workflow run dispatched successfully.";
          loadData();
        } catch (err) {
          errorMessage = err.message;
          render();
        }
      });
    });

    // Activate workflow button
    container.querySelectorAll(".btn-activate-wf").forEach((btn) => {
      btn.addEventListener("click", async (e) => {
        e.stopPropagation();
        const id = btn.getAttribute("data-id");
        try {
          await api(`/api/v1/workflows/${id}/activate`, { method: "POST" });
          successMessage = "Workflow activated.";
          loadData();
        } catch (err) {
          errorMessage = err.message;
          render();
        }
      });
    });

    // Pause workflow button
    container.querySelectorAll(".btn-pause-wf").forEach((btn) => {
      btn.addEventListener("click", async (e) => {
        e.stopPropagation();
        const id = btn.getAttribute("data-id");
        if (!window.confirm("Pause this workflow? Scheduled and manual execution will stop.")) return;
        try {
          await api(`/api/v1/workflows/${id}/pause`, { method: "POST" });
          successMessage = "Workflow paused.";
          loadData();
        } catch (err) {
          errorMessage = err.message;
          render();
        }
      });
    });

    // Cancel run button
    container.querySelectorAll(".btn-cancel-run").forEach((btn) => {
      btn.addEventListener("click", async (e) => {
        e.stopPropagation();
        const id = btn.getAttribute("data-id");
        if (!window.confirm("Cancel this workflow run? This action cannot be resumed.")) return;
        try {
          await api(`/api/v1/workflow-runs/${id}/cancel`, { method: "POST" });
          successMessage = "Workflow run cancelled.";
          loadData();
        } catch (err) {
          errorMessage = err.message;
          render();
        }
      });
    });

    // Inspect Run Row or Approval
    container.querySelectorAll(".run-row, .btn-inspect-approval").forEach((el) => {
      el.addEventListener("click", async () => {
        const id = el.getAttribute("data-id") || el.getAttribute("data-run-id");
        if (id) {
          selectedRunId = id;
          selectedRun = await api(`/api/v1/workflow-runs/${id}`).catch(() => null);
          render();
        }
      });
    });

    container.querySelectorAll(".workflow-row").forEach((row) => {
      row.addEventListener("click", async () => {
        selectedWorkflowId = row.getAttribute("data-id");
        selectedWorkflow = await api(`/api/v1/workflows/${selectedWorkflowId}`).catch((err) => {
          errorMessage = err.message;
          return null;
        });
        render();
      });
    });

    container.querySelector("#btn-close-workflow-detail")?.addEventListener("click", () => {
      selectedWorkflow = null;
      selectedWorkflowId = null;
      render();
    });

    // Close modal
    container.querySelector("#btn-close-modal")?.addEventListener("click", () => {
      selectedRun = null;
      selectedRunId = null;
      render();
    });

    // Approve step
    container.querySelectorAll(".btn-approve-step").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const runId = btn.getAttribute("data-run-id");
        const stepId = btn.getAttribute("data-step-id");
        const notesInput = container.querySelector(`#approval-notes-${stepId}`);
        const notes = notesInput ? notesInput.value : "";
        if (!window.confirm("Approve this step and resume the workflow?")) return;
        try {
          await api(`/api/v1/workflow-runs/${runId}/steps/${stepId}/approve`, {
            method: "POST",
            body: JSON.stringify({ notes })
          });
          successMessage = "Step approved. Workflow resumed.";
          selectedRun = null;
          selectedRunId = null;
          loadData();
        } catch (err) {
          errorMessage = err.message;
          render();
        }
      });
    });

    // Reject step
    container.querySelectorAll(".btn-reject-step").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const runId = btn.getAttribute("data-run-id");
        const stepId = btn.getAttribute("data-step-id");
        const notesInput = container.querySelector(`#approval-notes-${stepId}`);
        const notes = notesInput ? notesInput.value : "";
        if (!window.confirm("Reject this approval and fail the workflow?")) return;
        try {
          await api(`/api/v1/workflow-runs/${runId}/steps/${stepId}/reject`, {
            method: "POST",
            body: JSON.stringify({ notes })
          });
          successMessage = "Step rejected. Workflow halted.";
          selectedRun = null;
          selectedRunId = null;
          loadData();
        } catch (err) {
          errorMessage = err.message;
          render();
        }
      });
    });

    // Modal Create WF Open/Close
    const createModal = container.querySelector("#modal-create-wf");
    container.querySelector("#btn-open-create-wf")?.addEventListener("click", () => {
      if (createModal) createModal.style.display = "flex";
    });
    container.querySelector("#btn-close-create-wf")?.addEventListener("click", () => {
      if (createModal) createModal.style.display = "none";
    });
    container.querySelector("#btn-cancel-create-wf")?.addEventListener("click", () => {
      if (createModal) createModal.style.display = "none";
    });

    // Form submit create WF
    container.querySelector("#form-create-wf")?.addEventListener("submit", async (e) => {
      e.preventDefault();
      const form = new FormData(e.target);
      const name = form.get("name");
      const description = form.get("description");
      const workflow_type = form.get("workflow_type");
      try {
        await api("/api/v1/workflows", {
          method: "POST",
          body: JSON.stringify({
            name,
            description,
            workflow_type,
            steps: [
              {
                step_order: 1,
                name: "Validate Content Payload",
                step_type: "CONTENT_VALIDATE",
                config_json: { content_type: "vod" }
              },
              {
                step_order: 2,
                name: "Editorial Manual Approval",
                step_type: "MANUAL_APPROVAL",
                config_json: { prompt: "Confirm editorial broadcast clearance" }
              },
              {
                step_order: 3,
                name: "Publish To Media Catalog",
                step_type: "CONTENT_PUBLISH_REQUEST",
                config_json: { channels: ["gntv-main"] }
              }
            ]
          })
        });
        if (createModal) createModal.style.display = "none";
        successMessage = "Workflow created with standard sequential steps.";
        loadData();
      } catch (err) {
        errorMessage = err.message;
        render();
      }
    });
  }

  loadData();
  return () => {
    container.innerHTML = "";
  };
}
