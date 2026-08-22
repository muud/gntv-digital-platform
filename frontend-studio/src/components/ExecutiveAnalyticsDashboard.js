/**
 * Executive Analytics & Broadcaster Control Panel (Module 7 Sprint 7.5)
 * Vanilla JS Component for GNTV Digital Studio Dashboard.
 */

export function initExecutiveAnalyticsDashboard(container) {
  let active = true;
  let isRefreshing = false;
  let dateRange = "24h"; // 24h, 7d, 30d
  let selectedChannel = "";
  let selectedRegion = "";

  const apiBase = import.meta.env.VITE_API_URL || "http://localhost:8000";

  let analyticsData = null;
  let fetchError = null;

  function getAuthToken() {
    return localStorage.getItem("gntv_auth_token") || localStorage.getItem("token") || "";
  }

  function getDateWindow() {
    const now = new Date();
    let start = new Date();
    if (dateRange === "24h") {
      start.setHours(now.getHours() - 24);
    } else if (dateRange === "7d") {
      start.setDate(now.getDate() - 7);
    } else if (dateRange === "30d") {
      start.setDate(now.getDate() - 30);
    }
    return {
      start_time: encodeURIComponent(start.toISOString()),
      end_time: encodeURIComponent(now.toISOString()),
    };
  }

  async function fetchAnalytics() {
    if (!active) return;
    isRefreshing = true;
    fetchError = null;
    render();

    try {
      const token = getAuthToken();
      const { start_time, end_time } = getDateWindow();
      let queryParams = `start_time=${start_time}&end_time=${end_time}`;
      if (selectedChannel) queryParams += `&channel_id=${encodeURIComponent(selectedChannel)}`;
      if (selectedRegion) queryParams += `&region=${encodeURIComponent(selectedRegion)}`;

      const response = await fetch(`${apiBase}/api/v1/analytics/broadcaster/overview?${queryParams}`, {
        headers: {
          "Content-Type": "application/json",
          "Authorization": `Bearer ${token}`,
        },
      });

      if (!response.ok) {
        const errBody = await response.json().catch(() => ({}));
        throw new Error(errBody.detail || `API error ${response.status}`);
      }

      analyticsData = await response.json();
    } catch (err) {
      fetchError = err.message || "Failed to load executive analytics telemetry";
    } finally {
      isRefreshing = false;
      if (active) render();
    }
  }

  function formatNumber(num) {
    if (num === null || num === undefined) return "—";
    return num.toLocaleString();
  }

  function formatPercent(num) {
    if (num === null || num === undefined) return "—";
    return `${(num * 100).toFixed(1)}%`;
  }

  function formatCurrency(num) {
    if (num === null || num === undefined) return "CPM Unconfigured";
    return `$${num.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  }

  function render() {
    if (!container || !active) return;

    const summary = analyticsData?.summary || {};
    const concurrency = analyticsData?.concurrency || { by_channel: [], by_region: [], by_device: [], trend: [] };
    const qoe = analyticsData?.qoe || { trend: [] };
    const cdn = analyticsData?.cdn || { endpoint_health_counts: {}, regional_performance: [], traffic_allocation: [] };
    const monetization = analyticsData?.monetization || { campaign_performance: [] };
    const topRegions = analyticsData?.top_regions || [];
    const topChannels = analyticsData?.top_channels || [];

    container.innerHTML = `
      <style>
        .exec-analytics-container {
          padding: 24px;
          color: #e5e7eb;
          font-family: system-ui, -apple-system, sans-serif;
          background: #090a0f;
          min-height: 100%;
          box-sizing: border-box;
        }

        .exec-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 24px;
          flex-wrap: wrap;
          gap: 16px;
        }

        .exec-title-group h2 {
          margin: 0 0 6px 0;
          font-size: 24px;
          font-weight: 800;
          letter-spacing: -0.5px;
          display: flex;
          align-items: center;
          gap: 10px;
          color: #ffffff;
        }

        .exec-title-group p {
          margin: 0;
          color: #9ca3af;
          font-size: 13px;
        }

        .exec-controls {
          display: flex;
          align-items: center;
          gap: 12px;
        }

        .exec-select {
          background: rgba(255, 255, 255, 0.06);
          border: 1px solid rgba(255, 255, 255, 0.12);
          color: #ffffff;
          padding: 8px 14px;
          border-radius: 8px;
          font-size: 13px;
          font-weight: 600;
          outline: none;
          cursor: pointer;
        }

        .exec-select option {
          background: #111827;
          color: #ffffff;
        }

        .exec-refresh-btn {
          background: var(--brand-primary, #e11d48);
          border: none;
          color: #ffffff;
          padding: 8px 16px;
          border-radius: 8px;
          font-weight: 700;
          font-size: 13px;
          cursor: pointer;
          transition: all 0.2s;
          display: flex;
          align-items: center;
          gap: 6px;
        }

        .exec-refresh-btn:hover {
          opacity: 0.9;
          transform: translateY(-1px);
        }

        .exec-kpi-grid {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
          gap: 16px;
          margin-bottom: 24px;
        }

        .exec-kpi-card {
          background: rgba(18, 20, 29, 0.7);
          border: 1px solid rgba(255, 255, 255, 0.08);
          border-radius: 12px;
          padding: 18px;
          display: flex;
          flex-direction: column;
          gap: 8px;
          position: relative;
          overflow: hidden;
        }

        .exec-kpi-card::before {
          content: "";
          position: absolute;
          top: 0;
          left: 0;
          width: 100%;
          height: 3px;
          background: linear-gradient(90deg, #e11d48, #3b82f6);
        }

        .exec-kpi-label {
          font-size: 12px;
          font-weight: 600;
          color: #9ca3af;
          text-transform: uppercase;
          letter-spacing: 0.5px;
        }

        .exec-kpi-val {
          font-size: 26px;
          font-weight: 800;
          color: #ffffff;
          font-family: monospace;
        }

        .exec-kpi-sub {
          font-size: 11px;
          color: #6b7280;
        }

        .exec-badge-healthy { color: #10b981; font-weight: 700; }
        .exec-badge-degraded { color: #f59e0b; font-weight: 700; }
        .exec-badge-unhealthy { color: #ef4444; font-weight: 700; }

        .exec-grid-2 {
          display: grid;
          grid-template-columns: 1fr 1fr;
          gap: 20px;
          margin-bottom: 24px;
        }

        @media (max-width: 1024px) {
          .exec-grid-2 { grid-template-columns: 1fr; }
        }

        .exec-card {
          background: rgba(18, 20, 29, 0.7);
          border: 1px solid rgba(255, 255, 255, 0.08);
          border-radius: 12px;
          padding: 20px;
        }

        .exec-card-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 16px;
          padding-bottom: 12px;
          border-bottom: 1px solid rgba(255, 255, 255, 0.06);
        }

        .exec-card-title {
          font-size: 15px;
          font-weight: 750;
          margin: 0;
          color: #ffffff;
          display: flex;
          align-items: center;
          gap: 8px;
        }

        .exec-table {
          width: 100%;
          border-collapse: collapse;
          font-size: 13px;
        }

        .exec-table th {
          text-align: left;
          padding: 10px 12px;
          color: #9ca3af;
          font-size: 11px;
          font-weight: 700;
          text-transform: uppercase;
          border-bottom: 1px solid rgba(255, 255, 255, 0.08);
        }

        .exec-table td {
          padding: 12px;
          border-bottom: 1px solid rgba(255, 255, 255, 0.04);
          color: #d1d5db;
        }

        .exec-table tr:last-child td { border-bottom: none; }

        .exec-bar-bg {
          height: 6px;
          background: rgba(255, 255, 255, 0.08);
          border-radius: 3px;
          overflow: hidden;
          margin-top: 4px;
        }

        .exec-bar-fill {
          height: 100%;
          background: var(--brand-primary, #e11d48);
          border-radius: 3px;
        }

        .exec-empty-state {
          padding: 40px 20px;
          text-align: center;
          color: #6b7280;
          font-size: 13px;
        }

        .exec-error-box {
          background: rgba(239, 68, 68, 0.1);
          border: 1px solid rgba(239, 68, 68, 0.3);
          color: #f87171;
          padding: 14px 18px;
          border-radius: 8px;
          margin-bottom: 20px;
          font-size: 13px;
        }
      </style>

      <div class="exec-analytics-container">
        <!-- Dashboard Header -->
        <div class="exec-header">
          <div class="exec-title-group">
            <h2><span>📈</span> Broadcaster Executive Control & Analytics</h2>
            <p>Unified real-time dashboard aggregating concurrency, QoE performance, Multi-CDN health, and SSAI monetization metrics.</p>
          </div>

          <div class="exec-controls">
            <select id="exec-date-range" class="exec-select">
              <option value="24h" ${dateRange === "24h" ? "selected" : ""}>Past 24 Hours</option>
              <option value="7d" ${dateRange === "7d" ? "selected" : ""}>Past 7 Days</option>
              <option value="30d" ${dateRange === "30d" ? "selected" : ""}>Past 30 Days</option>
            </select>

            <button id="exec-refresh-btn" class="exec-refresh-btn">
              <span>${isRefreshing ? "⏳" : "🔄"}</span> ${isRefreshing ? "Refreshing..." : "Refresh"}
            </button>
          </div>
        </div>

        ${fetchError ? `<div class="exec-error-box">⚠️ ${fetchError}</div>` : ""}

        <!-- Executive KPI Row -->
        <div class="exec-kpi-grid">
          <div class="exec-kpi-card">
            <div class="exec-kpi-label">Active Viewers</div>
            <div class="exec-kpi-val" style="color: #60a5fa;">${formatNumber(summary.active_viewers)}</div>
            <div class="exec-kpi-sub">Peak Concurrency: ${formatNumber(summary.peak_concurrency)}</div>
          </div>

          <div class="exec-kpi-card">
            <div class="exec-kpi-label">QoE Quality Index</div>
            <div class="exec-kpi-val" style="color: #34d399;">${summary.qoe_score !== null && summary.qoe_score !== undefined ? summary.qoe_score : "—"}</div>
            <div class="exec-kpi-sub">Avg Startup: ${qoe.avg_startup_time_ms ? `${qoe.avg_startup_time_ms} ms` : "—"}</div>
          </div>

          <div class="exec-kpi-card">
            <div class="exec-kpi-label">CDN Cache Offload</div>
            <div class="exec-kpi-val" style="color: #a78bfa;">${formatPercent(summary.cdn_offload_ratio)}</div>
            <div class="exec-kpi-sub">Cache Hit Ratio: ${formatPercent(cdn.cache_hit_ratio)}</div>
          </div>

          <div class="exec-kpi-card">
            <div class="exec-kpi-label">Edge Health Status</div>
            <div class="exec-kpi-val">
              <span class="${summary.cdn_health_status === "HEALTHY" ? "exec-badge-healthy" : summary.cdn_health_status === "DEGRADED" ? "exec-badge-degraded" : "exec-badge-unhealthy"}">
                ${summary.cdn_health_status || "HEALTHY"}
              </span>
            </div>
            <div class="exec-kpi-sub">Failovers: ${formatNumber(summary.total_failovers)}</div>
          </div>

          <div class="exec-kpi-card">
            <div class="exec-kpi-label">Ad Impressions</div>
            <div class="exec-kpi-val" style="color: #f472b6;">${formatNumber(summary.ad_impressions)}</div>
            <div class="exec-kpi-sub">Ad Fill Rate: ${formatPercent(monetization.ad_fill_rate)}</div>
          </div>

          <div class="exec-kpi-card">
            <div class="exec-kpi-label">Est. Ad Revenue</div>
            <div class="exec-kpi-val" style="color: #fbbf24; font-size: 20px;">${formatCurrency(summary.estimated_revenue_usd)}</div>
            <div class="exec-kpi-sub">Authoritative CPM persistence</div>
          </div>
        </div>

        <!-- Content Grid Row 1: Concurrency & QoE -->
        <div class="exec-grid-2">
          <!-- Concurrency Breakdown -->
          <div class="exec-card">
            <div class="exec-card-header">
              <h3 class="exec-card-title">📡 Active Concurrency by Channel</h3>
            </div>
            ${concurrency.by_channel && concurrency.by_channel.length > 0 ? `
              <table class="exec-table">
                <thead>
                  <tr>
                    <th>Channel</th>
                    <th>Active Viewers</th>
                    <th>Share</th>
                  </tr>
                </thead>
                <tbody>
                  ${concurrency.by_channel.map(ch => `
                    <tr>
                      <td><strong>${ch.dimension}</strong></td>
                      <td style="font-family: monospace; font-weight: 700;">${formatNumber(ch.count)}</td>
                      <td style="width: 40%;">
                        <div>${(ch.ratio * 100).toFixed(1)}%</div>
                        <div class="exec-bar-bg"><div class="exec-bar-fill" style="width: ${ch.ratio * 100}%;"></div></div>
                      </td>
                    </tr>
                  `).join("")}
                </tbody>
              </table>
            ` : `<div class="exec-empty-state">No active live playback sessions recorded.</div>`}
          </div>

          <!-- QoE Breakdown -->
          <div class="exec-card">
            <div class="exec-card-header">
              <h3 class="exec-card-title">⏱️ QoE Telemetry Summary</h3>
            </div>
            <table class="exec-table">
              <tbody>
                <tr>
                  <td>Avg Startup Latency</td>
                  <td style="font-family: monospace; font-weight: 700;">${qoe.avg_startup_time_ms ? `${qoe.avg_startup_time_ms} ms` : "—"}</td>
                </tr>
                <tr>
                  <td>P95 Startup Latency</td>
                  <td style="font-family: monospace; font-weight: 700;">${qoe.p95_startup_time_ms ? `${qoe.p95_startup_time_ms} ms` : "—"}</td>
                </tr>
                <tr>
                  <td>Rebuffer Ratio</td>
                  <td style="font-family: monospace; font-weight: 700;">${formatPercent(qoe.avg_rebuffer_ratio)}</td>
                </tr>
                <tr>
                  <td>Avg Bitrate</td>
                  <td style="font-family: monospace; font-weight: 700;">${qoe.avg_bitrate_bps ? `${(qoe.avg_bitrate_bps / 1000000).toFixed(2)} Mbps` : "—"}</td>
                </tr>
                <tr>
                  <td>Playback Errors</td>
                  <td style="font-family: monospace; font-weight: 700; color: ${qoe.total_playback_errors > 0 ? '#ef4444' : '#10b981'};">
                    ${formatNumber(qoe.total_playback_errors)}
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>

        <!-- Content Grid Row 2: CDN & Monetization -->
        <div class="exec-grid-2">
          <!-- CDN Performance -->
          <div class="exec-card">
            <div class="exec-card-header">
              <h3 class="exec-card-title">🌐 Multi-CDN Regional Performance</h3>
            </div>
            ${cdn.regional_performance && cdn.regional_performance.length > 0 ? `
              <table class="exec-table">
                <thead>
                  <tr>
                    <th>Region</th>
                    <th>Requests</th>
                    <th>Cache Hit Ratio</th>
                    <th>Avg Latency</th>
                  </tr>
                </thead>
                <tbody>
                  ${cdn.regional_performance.map(r => `
                    <tr>
                      <td><strong>${r.region_code.toUpperCase()}</strong></td>
                      <td style="font-family: monospace;">${formatNumber(r.request_count)}</td>
                      <td style="font-family: monospace;">${formatPercent(r.cache_hit_ratio)}</td>
                      <td style="font-family: monospace;">${r.avg_latency_ms !== null ? `${r.avg_latency_ms} ms` : "—"}</td>
                    </tr>
                  `).join("")}
                </tbody>
              </table>
            ` : `<div class="exec-empty-state">No CDN edge telemetry recorded for selected window.</div>`}
          </div>

          <!-- SSAI Monetization -->
          <div class="exec-card">
            <div class="exec-card-header">
              <h3 class="exec-card-title">💰 SSAI Campaign Performance</h3>
            </div>
            ${monetization.campaign_performance && monetization.campaign_performance.length > 0 ? `
              <table class="exec-table">
                <thead>
                  <tr>
                    <th>Campaign Name</th>
                    <th>Impressions</th>
                    <th>Completed</th>
                    <th>Est. Revenue</th>
                  </tr>
                </thead>
                <tbody>
                  ${monetization.campaign_performance.map(c => `
                    <tr>
                      <td><strong>${c.campaign_name}</strong></td>
                      <td style="font-family: monospace;">${formatNumber(c.impressions)}</td>
                      <td style="font-family: monospace;">${formatNumber(c.completed_ads)}</td>
                      <td style="font-family: monospace; color: #fbbf24;">${formatCurrency(c.estimated_revenue_usd)}</td>
                    </tr>
                  `).join("")}
                </tbody>
              </table>
            ` : `<div class="exec-empty-state">No SSAI ad campaigns or impressions recorded.</div>`}
          </div>
        </div>

        <!-- Regional & Channel Performance Summary Tables -->
        <div class="exec-card" style="margin-bottom: 24px;">
          <div class="exec-card-header">
            <h3 class="exec-card-title">📺 Live Channel Telemetry Matrix</h3>
          </div>
          ${topChannels && topChannels.length > 0 ? `
            <table class="exec-table">
              <thead>
                <tr>
                  <th>Channel Name</th>
                  <th>Slug</th>
                  <th>Active Viewers</th>
                  <th>Total Sessions</th>
                  <th>Avg Startup</th>
                  <th>Rebuffer %</th>
                  <th>Ad Impressions</th>
                </tr>
              </thead>
              <tbody>
                ${topChannels.map(ch => `
                  <tr>
                    <td><strong>${ch.channel_name}</strong></td>
                    <td style="font-family: monospace; color: #9ca3af;">${ch.channel_slug || "—"}</td>
                    <td style="font-family: monospace; font-weight: 700; color: #60a5fa;">${formatNumber(ch.active_viewers)}</td>
                    <td style="font-family: monospace;">${formatNumber(ch.total_sessions)}</td>
                    <td style="font-family: monospace;">${ch.avg_startup_latency_ms ? `${ch.avg_startup_latency_ms} ms` : "—"}</td>
                    <td style="font-family: monospace;">${formatPercent(ch.avg_rebuffer_ratio)}</td>
                    <td style="font-family: monospace;">${formatNumber(ch.ad_impressions)}</td>
                  </tr>
                `).join("")}
              </tbody>
            </table>
          ` : `<div class="exec-empty-state">No active channels registered.</div>`}
        </div>
      </div>
    `;

    // Hook Date Selector
    const dateSel = container.querySelector("#exec-date-range");
    if (dateSel) {
      dateSel.addEventListener("change", (e) => {
        dateRange = e.target.value;
        fetchAnalytics();
      });
    }

    // Hook Refresh Button
    const refreshBtn = container.querySelector("#exec-refresh-btn");
    if (refreshBtn) {
      refreshBtn.addEventListener("click", () => {
        fetchAnalytics();
      });
    }
  }

  // Initial Fetch
  fetchAnalytics();

  // Return Cleanup Callback for Tab Switching
  return () => {
    active = false;
  };
}
