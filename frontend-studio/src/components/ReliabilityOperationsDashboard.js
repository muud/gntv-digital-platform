export const RELIABILITY_TABS = [
  ["overview", "Health & Metrics"],
  ["incidents", "Incidents & Triage"],
  ["recovery", "Recovery Runs"],
  ["alerts", "Alert Rules & Log"],
  ["backups", "Backups & DR Readiness"]
];

export const safeReliabilityText = (value) => String(value ?? "").replace(/[&<>'"]/g, (char) => (
  { "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" }[char]
));

export function summarizeReliabilityMetrics(metrics = {}) {
  return [
    ["Healthy Services", metrics.healthy_component_count ?? 0],
    ["Degraded Services", metrics.degraded_component_count ?? 0],
    ["Unhealthy Services", metrics.unhealthy_component_count ?? 0],
    ["Open Incidents", metrics.unresolved_incident_count ?? 0],
    ["Active Recoveries", metrics.active_recovery_runs ?? 0],
    ["DR Readiness", metrics.dr_readiness ?? "NOT_READY"]
  ];
}

const when = (value) => value ? new Date(value).toLocaleString() : "—";
const badge = (value) => {
  const v = String(value || "").toLowerCase();
  const color = ["healthy", "approved", "succeeded", "verified", "ready", "closed", "resolved"].includes(v)
    ? "#34d399"
    : ["unhealthy", "failed", "critical", "major", "not_ready"].includes(v)
    ? "#fb7185"
    : ["degraded", "recovering", "monitoring", "pending", "pending_approval", "warning", "partially_ready"].includes(v)
    ? "#fbbf24"
    : "#93c5fd";
  return `<strong style="color:${color}">${safeReliabilityText(value)}</strong>`;
};

export function initReliabilityOperationsDashboard(container) {
  let active = "overview";
  let loading = true;
  let error = "";
  let filter = "";
  let selectedIncident = null;

  const state = {
    overview: null,
    components: [],
    incidents: [],
    recoveryRuns: [],
    alertRules: [],
    alertOccurrences: [],
    policies: [],
    backups: [],
    drPlans: [],
    drReadiness: null,
    metrics: {}
  };

  const base = import.meta.env.VITE_API_URL || "http://localhost:8000";
  const token = () => sessionStorage.getItem("gntv_studio_token") || localStorage.getItem("gntv_auth_token") || "";

  async function api(path, options = {}) {
    const response = await fetch(`${base}${path}`, {
      ...options,
      headers: {
        "Content-Type": "application/json",
        ...(token() ? { Authorization: `Bearer ${token()}` } : {})
      }
    });
    if (!response.ok) {
      const err = await response.json().catch(() => ({}));
      throw new Error(err.detail || `Request failed (${response.status})`);
    }
    return response.json();
  }

  const visible = (items) => items.filter((item) => !filter || JSON.stringify(item).toLowerCase().includes(filter.toLowerCase()));
  const row = (cells) => `<tr>${cells.map((cell) => `<td style="padding:10px;border-bottom:1px solid #1f2a44;vertical-align:top">${cell}</td>`).join("")}</tr>`;
  const table = (headers, rows, name) => rows.length
    ? `<div style="overflow:auto"><table style="width:100%;border-collapse:collapse;font-size:12px"><thead><tr>${headers.map((h) => `<th style="text-align:left;padding:10px;color:#93c5fd">${h}</th>`).join("")}</tr></thead><tbody>${rows.join("")}</tbody></table></div>`
    : `<div style="padding:42px;text-align:center;color:#64748b">No ${name} found.</div>`;

  function content() {
    if (active === "overview") {
      const checks = state.overview?.checks || [];
      return `
        <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:10px;margin-bottom:20px">
          ${summarizeReliabilityMetrics(state.metrics).map(([label, value]) => `
            <article style="padding:16px;background:#101827;border:1px solid #263852;border-radius:8px">
              <small style="color:#94a3b8">${label}</small>
              <div style="font-size:24px;font-weight:850;margin-top:6px">${badge(value)}</div>
            </article>
          `).join("")}
        </div>
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">
          <h3 style="margin:0;color:#f8fafc">Monitored Service Components</h3>
          <button id="trigger-health-check" style="background:#2563eb;color:#fff;border:0;padding:8px 14px;border-radius:6px;cursor:pointer">Trigger Health Evaluation</button>
        </div>
        <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:12px">
          ${checks.map((c) => `
            <div style="padding:14px;background:#0d1527;border:1px solid ${c.status === 'HEALTHY' ? '#166534' : c.status === 'DEGRADED' ? '#854d0e' : '#991b1b'};border-radius:8px">
              <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">
                <span style="font-weight:700;color:#f1f5f9">${safeReliabilityText(c.component)}</span>
                ${badge(c.status)}
              </div>
              <div style="font-size:11px;color:#94a3b8">Latency: <strong>${c.latency_ms}ms</strong> | Checked: ${when(c.checked_at)}</div>
              <div style="font-size:11px;color:#cbd5e1;margin-top:6px;background:#050b14;padding:6px;border-radius:4px">${safeReliabilityText(c.message)}</div>
            </div>
          `).join("")}
        </div>
      `;
    }

    if (active === "incidents") {
      return `
        <div style="display:flex;gap:10px;margin-bottom:12px">
          <button id="create-incident-btn" style="background:#dc2626;color:#fff;border:0;padding:8px 14px;border-radius:6px;cursor:pointer">+ Declare Incident</button>
        </div>
        ${table(
          ["Incident", "Component", "Severity", "State", "Created", "Resolved", "Actions"],
          visible(state.incidents).map((i) => row([
            `<button class="view-incident" data-id="${i.id}" style="background:none;border:0;color:#60a5fa;cursor:pointer;text-align:left;font-weight:bold">${safeReliabilityText(i.title)}</button><br><small style="color:#64748b">${i.id.slice(0, 8)}</small>`,
            safeReliabilityText(i.component),
            badge(i.severity),
            badge(i.state),
            when(i.created_at),
            when(i.resolved_at),
            `
              ${i.state === 'DETECTED' ? `<button class="incident-action" data-id="${i.id}" data-action="ack" style="padding:4px 8px;font-size:11px;background:#0284c7;color:#fff;border:0;border-radius:4px;cursor:pointer">Acknowledge</button>` : ''}
              ${['ACKNOWLEDGED', 'RECOVERING', 'MONITORING'].includes(i.state) ? `<button class="incident-action" data-id="${i.id}" data-action="resolve" style="padding:4px 8px;font-size:11px;background:#059669;color:#fff;border:0;border-radius:4px;cursor:pointer">Resolve</button>` : ''}
              ${i.state === 'RESOLVED' ? `<button class="incident-action" data-id="${i.id}" data-action="close" style="padding:4px 8px;font-size:11px;background:#475569;color:#fff;border:0;border-radius:4px;cursor:pointer">Close</button>` : ''}
            `
          ])),
          "incidents"
        )}
        ${selectedIncident ? `
          <aside style="margin-top:16px;padding:16px;background:#111827;border:1px solid #263852;border-radius:8px">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px">
              <h3 style="margin:0;color:#93c5fd">Incident Audit Timeline: ${safeReliabilityText(selectedIncident.title)}</h3>
              <button id="close-incident-drawer" style="background:none;border:0;color:#94a3b8;cursor:pointer">✕ Close</button>
            </div>
            <p style="font-size:12px;color:#cbd5e1">${safeReliabilityText(selectedIncident.description)}</p>
            <div style="margin-top:10px">
              <h4 style="color:#94a3b8;margin-bottom:6px">Timeline Events</h4>
              <div style="display:flex;flex-direction:column;gap:6px">
                ${(selectedIncident.events || []).map((ev) => `
                  <div style="background:#0b1120;padding:8px 12px;border-left:3px solid #3b82f6;border-radius:4px;font-size:11px">
                    <span style="color:#93c5fd;font-weight:700">${safeReliabilityText(ev.event_type)}</span>
                    <span style="color:#64748b;margin-left:8px">${when(ev.created_at)}</span>
                    <div style="color:#e2e8f0;margin-top:2px">${safeReliabilityText(ev.message)}</div>
                  </div>
                `).join("")}
              </div>
            </div>
          </aside>
        ` : ""}
      `;
    }

    if (active === "recovery") {
      return `
        <div style="display:flex;gap:10px;margin-bottom:12px">
          <button id="start-recovery-btn" style="background:#d97706;color:#fff;border:0;padding:8px 14px;border-radius:6px;cursor:pointer">Initiate Allowlisted Recovery</button>
        </div>
        ${table(
          ["Run ID", "Incident", "Action Type", "Status", "Requires Approval", "Approver", "Verification", "Started", "Actions"],
          visible(state.recoveryRuns).map((r) => row([
            `<code>${r.id.slice(0, 8)}</code>`,
            `<code>${r.incident_id.slice(0, 8)}</code>`,
            safeReliabilityText(r.action_type),
            badge(r.status),
            r.requires_approval ? "<span style='color:#fbbf24'>YES</span>" : "NO",
            r.approved_by_user_id ? `User #${r.approved_by_user_id}` : "—",
            badge(r.verification_status),
            when(r.started_at),
            `
              ${r.status === 'PENDING_APPROVAL' ? `<button class="recovery-approve" data-id="${r.id}" style="padding:4px 8px;font-size:11px;background:#16a34a;color:#fff;border:0;border-radius:4px;cursor:pointer">Approve & Exec</button>` : ''}
              ${r.status === 'SUCCEEDED' && r.verification_status !== 'PASSED' ? `<button class="recovery-verify" data-id="${r.id}" style="padding:4px 8px;font-size:11px;background:#2563eb;color:#fff;border:0;border-radius:4px;cursor:pointer">Verify Post-Fix</button>` : ''}
            `
          ])),
          "recovery runs"
        )}
      `;
    }

    if (active === "alerts") {
      return `
        <div style="display:flex;gap:10px;margin-bottom:12px">
          <button id="trigger-test-alert" style="background:#ef4444;color:#fff;border:0;padding:8px 14px;border-radius:6px;cursor:pointer">Trigger Test Alert</button>
        </div>
        <h4 style="color:#93c5fd;margin:12px 0 6px">Configured Alert Rules</h4>
        ${table(
          ["Rule Name", "Type", "Component", "Severity", "Threshold", "Cooldown", "Active", "Actions"],
          visible(state.alertRules).map((rule) => row([
            safeReliabilityText(rule.name),
            safeReliabilityText(rule.rule_type),
            safeReliabilityText(rule.component),
            badge(rule.severity),
            `${rule.threshold_value} / ${rule.window_seconds}s`,
            `${rule.cooldown_seconds}s`,
            rule.is_enabled ? "<strong style='color:#34d399'>ENABLED</strong>" : "<span style='color:#64748b'>DISABLED</span>",
            `<button class="toggle-rule" data-id="${rule.id}" data-enabled="${rule.is_enabled}" style="padding:4px 8px;font-size:11px;background:#334155;color:#fff;border:0;border-radius:4px;cursor:pointer">${rule.is_enabled ? "Disable" : "Enable"}</button>`
          ])),
          "alert rules"
        )}
        <h4 style="color:#93c5fd;margin:24px 0 6px">Recent Triggered Alert Occurrences</h4>
        ${table(
          ["Time", "Component", "Severity", "Dedup Key", "Message"],
          visible(state.alertOccurrences).map((occ) => row([
            when(occ.triggered_at),
            safeReliabilityText(occ.component),
            badge(occ.severity),
            `<code>${safeReliabilityText(occ.dedup_key.slice(0, 16))}…</code>`,
            safeReliabilityText(occ.message)
          ])),
          "alert occurrences"
        )}
      `;
    }

    // active === "backups"
    const readiness = state.drReadiness;
    const checklist = readiness?.checklist_status || {};
    return `
      <div style="display:grid;grid-template-columns:2fr 1fr;gap:16px;margin-bottom:20px">
        <div style="padding:16px;background:#101827;border:1px solid #263852;border-radius:8px">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">
            <h3 style="margin:0;color:#f8fafc">Disaster Recovery Readiness Evaluation</h3>
            <button id="activate-dr-plan" style="background:#b91c1c;color:#fff;border:0;padding:8px 14px;border-radius:6px;cursor:pointer">Activate Primary DR Plan</button>
          </div>
          <div style="display:flex;gap:12px;align-items:center;margin-bottom:14px">
            <div>Status: ${badge(readiness?.overall_status || 'NOT_READY')}</div>
            <div>RTO Target: <strong>${readiness?.rto_target_minutes ?? 30}m</strong></div>
            <div>RPO Target: <strong>${readiness?.rpo_target_minutes ?? 15}m</strong></div>
            <div>Recovery Success: <strong>${(readiness?.recovery_success_rate ?? 100).toFixed(1)}%</strong></div>
          </div>
          <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:8px">
            <div style="background:#070f1e;padding:10px;border-radius:6px;font-size:12px">Active DR Plan: ${checklist.active_dr_plan ? '✅ Ready' : '❌ Missing'}</div>
            <div style="background:#070f1e;padding:10px;border-radius:6px;font-size:12px">Critical Health: ${checklist.critical_services_healthy ? '✅ Healthy' : '⚠️ Degraded'}</div>
            <div style="background:#070f1e;padding:10px;border-radius:6px;font-size:12px">Backup Verified: ${checklist.backup_verified ? '✅ Verified' : '⚠️ Pending'}</div>
            <div style="background:#070f1e;padding:10px;border-radius:6px;font-size:12px">Recovery Stable: ${checklist.recovery_runs_stable ? '✅ >= 80%' : '⚠️ Action Needed'}</div>
          </div>
        </div>
        <div style="padding:16px;background:#101827;border:1px solid #263852;border-radius:8px">
          <h4 style="margin:0 0 8px;color:#93c5fd">Active DR Policy</h4>
          <p style="font-size:12px;color:#cbd5e1">Plan: <strong>${safeReliabilityText(readiness?.active_plan?.name || "Global Failover Standard")}</strong></p>
          <p style="font-size:11px;color:#94a3b8">Criteria: ${safeReliabilityText(readiness?.active_plan?.activation_criteria || "Loss of primary region or database unreachable")}</p>
        </div>
      </div>

      <div style="display:flex;justify-content:space-between;align-items:center;margin:16px 0 8px">
        <h4 style="margin:0;color:#93c5fd">Point-in-Time & Full Backups</h4>
        <button id="create-backup-btn" style="background:#0369a1;color:#fff;border:0;padding:6px 12px;border-radius:6px;cursor:pointer">+ Register Snapshot</button>
      </div>
      ${table(
        ["Identifier", "Resource", "Type", "Status", "Checksum", "Verified At", "Actions"],
        visible(state.backups).map((b) => row([
          safeReliabilityText(b.logical_identifier),
          safeReliabilityText(b.resource_type),
          safeReliabilityText(b.backup_type),
          badge(b.status),
          `<code>${b.checksum ? b.checksum.slice(0, 10) + '…' : '—'}</code>`,
          when(b.verified_at),
          b.status !== 'VERIFIED'
            ? `<button class="verify-backup" data-id="${b.id}" style="padding:4px 8px;font-size:11px;background:#059669;color:#fff;border:0;border-radius:4px;cursor:pointer">Verify Integrity</button>`
            : `<span style="color:#34d399;font-size:11px">Integrity Valid</span>`
        ])),
        "backups"
      )}
    `;
  }

  function render() {
    container.innerHTML = `
      <section style="color:#e2e8f0;background:#07111f;min-height:650px;padding:22px;border-radius:12px">
        <header style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px">
          <div>
            <h2 style="margin:0;font-size:22px;color:#f8fafc">GNTV Digital Reliability & DR Operations</h2>
            <p style="color:#94a3b8;margin:4px 0 0;font-size:13px">Health telemetry, automated incident triage, audited recovery orchestration, and disaster readiness.</p>
          </div>
          <button id="reliability-refresh" style="background:#1e293b;border:1px solid #334155;color:#f1f5f9;padding:8px 16px;border-radius:6px;cursor:pointer">Refresh Telemetry</button>
        </header>
        ${error ? `<div role="alert" style="color:#fb7185;background:#450a0a;padding:10px 14px;border-radius:6px;margin-bottom:14px">${safeReliabilityText(error)}</div>` : ""}
        <nav style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:14px">
          ${RELIABILITY_TABS.map(([id, label]) => `
            <button class="reliability-tab" data-tab="${id}" style="background:${active === id ? '#2563eb' : '#172033'};color:white;padding:8px 14px;border:0;border-radius:6px;cursor:pointer;font-weight:${active === id ? '700' : '400'}">${label}</button>
          `).join("")}
        </nav>
        <div style="display:flex;margin-bottom:16px">
          <input id="reliability-filter" value="${safeReliabilityText(filter)}" placeholder="Search components, incidents, action types, or backup identifiers…" style="flex:1;padding:10px;border-radius:6px;background:#0b1324;border:1px solid #1e293b;color:#f8fafc">
        </div>
        <div aria-live="polite">${loading ? "<div style='padding:40px;text-align:center;color:#64748b'>Loading Reliability Telemetry…</div>" : content()}</div>
      </section>
    `;
    bind();
  }

  async function mutate(path, body = {}, method = "POST") {
    try {
      await api(path, { method, body: JSON.stringify(body) });
      await load();
    } catch (caught) {
      error = caught.message;
      render();
    }
  }

  function bind() {
    container.querySelector("#reliability-refresh")?.addEventListener("click", load);
    container.querySelectorAll(".reliability-tab").forEach((b) => b.addEventListener("click", () => {
      active = b.dataset.tab;
      selectedIncident = null;
      render();
    }));
    container.querySelector("#reliability-filter")?.addEventListener("input", (e) => {
      filter = e.target.value;
      render();
    });

    // Overview bindings
    container.querySelector("#trigger-health-check")?.addEventListener("click", async () => {
      await mutate("/api/v1/reliability/health/check", {});
    });

    // Incident bindings
    container.querySelector("#create-incident-btn")?.addEventListener("click", async () => {
      const title = prompt("Incident Title:", "Elevated API Latency Spike");
      if (!title) return;
      await mutate("/api/v1/reliability/incidents", {
        component: "API",
        severity: "MAJOR",
        title,
        description: "Manually declared via Reliability Dashboard"
      });
    });

    container.querySelectorAll(".view-incident").forEach((b) => b.addEventListener("click", async () => {
      try {
        selectedIncident = await api(`/api/v1/reliability/incidents/${b.dataset.id}`);
        render();
      } catch (caught) {
        error = caught.message;
        render();
      }
    }));

    container.querySelector("#close-incident-drawer")?.addEventListener("click", () => {
      selectedIncident = null;
      render();
    });

    container.querySelectorAll(".incident-action").forEach((b) => b.addEventListener("click", async () => {
      const id = b.dataset.id;
      const act = b.dataset.action;
      if (act === "ack") {
        await mutate(`/api/v1/reliability/incidents/${id}/acknowledge`, { notes: "Acknowledged via Studio Dashboard" });
      } else if (act === "resolve") {
        const summary = prompt("Resolution Summary:", "Issue identified and resolved");
        if (!summary) return;
        await mutate(`/api/v1/reliability/incidents/${id}/resolve`, { resolution_summary: summary });
      } else if (act === "close") {
        const summary = prompt("Recovery Verification Summary:", "Verification checks passed cleanly");
        if (!summary) return;
        await mutate(`/api/v1/reliability/incidents/${id}/close`, { recovery_verification_summary: summary });
      }
    }));

    // Recovery bindings
    container.querySelector("#start-recovery-btn")?.addEventListener("click", async () => {
      const firstInc = state.incidents[0];
      if (!firstInc) {
        alert("No incidents currently exist to attach recovery run to.");
        return;
      }
      await mutate("/api/v1/reliability/recovery/runs", {
        incident_id: firstInc.id,
        action_type: "VERIFY_COMPONENT_HEALTH",
        parameters_json: { component: firstInc.component }
      });
    });

    container.querySelectorAll(".recovery-approve").forEach((b) => b.addEventListener("click", async () => {
      if (!confirm("Approve and execute this critical recovery action?")) return;
      await mutate(`/api/v1/reliability/recovery/runs/${b.dataset.id}/approve`, { comments: "Approved by operator in Studio" });
    }));

    container.querySelectorAll(".recovery-verify").forEach((b) => b.addEventListener("click", async () => {
      await mutate(`/api/v1/reliability/recovery/runs/${b.dataset.id}/verify`, { verification_details: "Post-recovery check clean" });
    }));

    // Alert bindings
    container.querySelector("#trigger-test-alert")?.addEventListener("click", async () => {
      await mutate("/api/v1/reliability/alerts/trigger", {
        rule_type: "test_alert",
        component: "DATABASE",
        severity: "WARNING",
        message: "Manual alert trigger from Reliability Dashboard"
      });
    });

    container.querySelectorAll(".toggle-rule").forEach((b) => b.addEventListener("click", async () => {
      const isEnabled = b.dataset.enabled === "true";
      await mutate(`/api/v1/reliability/alerts/rules/${b.dataset.id}`, { is_enabled: !isEnabled }, "PATCH");
    }));

    // Backup & DR bindings
    container.querySelector("#create-backup-btn")?.addEventListener("click", async () => {
      await mutate("/api/v1/reliability/backups", {
        resource_type: "DATABASE",
        logical_identifier: `snapshot-db-${Date.now()}`,
        backup_type: "SNAPSHOT"
      });
    });

    container.querySelectorAll(".verify-backup").forEach((b) => b.addEventListener("click", async () => {
      await mutate(`/api/v1/reliability/backups/${b.dataset.id}/verify`, { verification_details: "Studio integrity verification" });
    }));

    container.querySelector("#activate-dr-plan")?.addEventListener("click", async () => {
      const plan = state.drPlans[0];
      if (!plan) {
        alert("No DR plans available.");
        return;
      }
      if (!confirm(`Activate disaster recovery failover plan: "${plan.name}"?`)) return;
      await mutate(`/api/v1/reliability/dr/plans/${plan.id}/activate`, {});
    });
  }

  async function load() {
    loading = true;
    error = "";
    render();
    try {
      const [
        overview,
        components,
        incidents,
        recoveryRuns,
        alertRules,
        alertOccurrences,
        backups,
        drPlans,
        drReadiness,
        metrics
      ] = await Promise.all([
        api("/api/v1/reliability/health/overview").catch(() => null),
        api("/api/v1/reliability/components").catch(() => []),
        api("/api/v1/reliability/incidents").catch(() => []),
        api("/api/v1/reliability/recovery/runs").catch(() => []),
        api("/api/v1/reliability/alerts/rules").catch(() => []),
        api("/api/v1/reliability/alerts/occurrences").catch(() => []),
        api("/api/v1/reliability/backups").catch(() => []),
        api("/api/v1/reliability/dr/plans").catch(() => []),
        api("/api/v1/reliability/dr/readiness").catch(() => null),
        api("/api/v1/reliability/metrics").catch(() => ({}))
      ]);

      state.overview = overview;
      state.components = components;
      state.incidents = incidents;
      state.recoveryRuns = recoveryRuns;
      state.alertRules = alertRules;
      state.alertOccurrences = alertOccurrences;
      state.backups = backups;
      state.drPlans = drPlans;
      state.drReadiness = drReadiness;
      state.metrics = metrics;
    } catch (caught) {
      error = caught.message;
    }
    loading = false;
    render();
  }

  load();
  return () => {
    container.innerHTML = "";
  };
}
