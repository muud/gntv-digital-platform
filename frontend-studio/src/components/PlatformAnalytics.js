import { store } from "../../../shared/src/state.js";
import { db } from "../../../shared/src/utils/supabase.js";

export function initPlatformAnalytics(container) {
  let active = true;
  let timerId = null;
  let activeSubTab = "executive"; // executive, newsroom, content, realtime
  let selectedDateRange = "7d"; // 24h, 7d, 30d

  // Render layouts
  const renderContainer = () => {
    container.innerHTML = `
      <div class="analytics-wrapper glass-card">
        <!-- Dashboard Header -->
        <div class="analytics-header">
          <div>
            <h2 class="section-title"><span class="icon">📊</span> GNTV DIGITAL, ALL EVERYWHERE Analytics & Intelligence Platform</h2>
            <p class="section-desc">Unified administrative hub tracking users, live broadcasts, content performance, and server telemetry.</p>
          </div>

          <div style="display: flex; align-items: center; gap: 12px;">
            <!-- Date Range Selector -->
            <select class="quality-select" id="select-analytics-date" style="padding: 6px 12px; border-radius: 20px;">
              <option value="24h" ${selectedDateRange === '24h' ? 'selected' : ''}>Last 24 Hours</option>
              <option value="7d" ${selectedDateRange === '7d' ? 'selected' : ''}>Last 7 Days</option>
              <option value="30d" ${selectedDateRange === '30d' ? 'selected' : ''}>Last 30 Days</option>
            </select>

            <!-- Export Buttons -->
            <button class="cms-delete-btn" id="btn-export-csv" style="border-radius: 20px; padding: 6px 12px; border-color: rgba(255,255,255,0.15); color: #ffffff; background: rgba(255,255,255,0.05);">📥 Export CSV</button>
            <button class="cms-delete-btn" id="btn-export-pdf" style="border-radius: 20px; padding: 6px 12px; border-color: rgba(255,255,255,0.15); color: #ffffff; background: rgba(255,255,255,0.05);">📥 Export PDF</button>

            <div class="telemetry-status-badge">
              <span class="pulse-green-ring"></span>
              <span style="font-weight: 700; color: #10b981; font-size:11px; letter-spacing:0.5px; text-transform: uppercase;">ONLINE // PostgreSQL Synced</span>
            </div>
          </div>
        </div>

        <!-- Sub-Tabs Switcher Menu -->
        <div class="analytics-tabs-menu" style="display: flex; gap: 8px; margin-bottom: 24px; border-bottom: 1px solid rgba(255,255,255,0.08); padding-bottom: 12px;">
          <button class="tab-btn ${activeSubTab === 'executive' ? 'active' : ''}" data-subtab="executive" style="background: ${activeSubTab === 'executive' ? 'var(--brand-primary)' : 'rgba(255,255,255,0.03)'}; border: none; padding: 8px 16px; border-radius: 20px; color: #ffffff; font-weight: 750; cursor: pointer; font-size: 12px; transition: all 0.3s;">🏢 Executive Overview</button>
          <button class="tab-btn ${activeSubTab === 'newsroom' ? 'active' : ''}" data-subtab="newsroom" style="background: ${activeSubTab === 'newsroom' ? 'var(--brand-primary)' : 'rgba(255,255,255,0.03)'}; border: none; padding: 8px 16px; border-radius: 20px; color: #ffffff; font-weight: 750; cursor: pointer; font-size: 12px; transition: all 0.3s;">🎙️ Newsroom Board</button>
          <button class="tab-btn ${activeSubTab === 'content' ? 'active' : ''}" data-subtab="content" style="background: ${activeSubTab === 'content' ? 'var(--brand-primary)' : 'rgba(255,255,255,0.03)'}; border: none; padding: 8px 16px; border-radius: 20px; color: #ffffff; font-weight: 750; cursor: pointer; font-size: 12px; transition: all 0.3s;">📼 Content Performance</button>
          <button class="tab-btn ${activeSubTab === 'realtime' ? 'active' : ''}" data-subtab="realtime" style="background: ${activeSubTab === 'realtime' ? 'var(--brand-primary)' : 'rgba(255,255,255,0.03)'}; border: none; padding: 8px 16px; border-radius: 20px; color: #ffffff; font-weight: 750; cursor: pointer; font-size: 12px; transition: all 0.3s;">⚡ Real-Time Infrastructure</button>
        </div>

        <!-- Dashboard Viewport Content Area -->
        <div id="analytics-viewport-content"></div>
      </div>
    `;

    // Hook Tabbing Events
    container.querySelectorAll(".analytics-tabs-menu button").forEach(btn => {
      btn.addEventListener("click", () => {
        activeSubTab = btn.getAttribute("data-subtab");
        renderContainer();
        loadActiveDashboard();
      });
    });

    // Hook Date Range selector
    const dateSelector = container.querySelector("#select-analytics-date");
    dateSelector.addEventListener("change", (e) => {
      selectedDateRange = e.target.value;
      addTerminalLog(`Tuned Date scope metrics to: ${selectedDateRange.toUpperCase()}`);
      loadActiveDashboard();
    });

    // Hook Export actions
    const btnCSV = container.querySelector("#btn-export-csv");
    const btnPDF = container.querySelector("#btn-export-pdf");

    const triggerExport = (format) => {
      alert(`Generating secure ${format.toUpperCase()} transaction bundle for GNTV DIGITAL, ALL EVERYWHERE Executives...`);
      setTimeout(() => {
        alert(`✔️ Export Complete: GNTV DIGITAL, ALL EVERYWHERE_Telemetry_Report_${selectedDateRange}_${new Date().toISOString().substring(0,10)}.${format} successfully downloaded!`);
      }, 1000);
    };
    btnCSV.addEventListener("click", () => triggerExport("csv"));
    btnPDF.addEventListener("click", () => triggerExport("pdf"));
  };

  // Local datasets to simulate charts & widgets
  let heartbeatTimeline = [120, 145, 130, 168, 185, 210, 195, 245, 290, 320, 310, 345, 390, 420, 450];
  let latencySpline = [142, 138, 145, 140, 135, 141, 148, 139, 142, 140, 138, 144, 142, 139, 140];
  let loggedEvents = [];

  const addTerminalLog = (message) => {
    const time = new Date().toLocaleTimeString();
    loggedEvents.unshift(`[${time}] ${message}`);
    if (loggedEvents.length > 20) loggedEvents.pop();

    const feed = container.querySelector("#terminal-feed-box");
    if (feed) {
      feed.innerHTML = loggedEvents.map(evt => `
        <div class="terminal-line"><span class="term-time">></span> ${evt}</div>
      `).join("");
    }
  };

  const getThemeColor = () => {
    return getComputedStyle(document.documentElement).getPropertyValue("--brand-primary").trim() || "#ff2a4b";
  };

  // 🏢 Dashboard 1: Executive Overview
  const loadExecutiveDashboard = () => {
    const viewport = container.querySelector("#analytics-viewport-content");

    // Scale stats based on range
    const scaler = selectedDateRange === "24h" ? 0.3 : (selectedDateRange === "30d" ? 4.2 : 1.0);
    const activeUsers = Math.round(18500 * scaler);
    const newUsers = Math.round(2450 * scaler);
    const returningUsers = activeUsers - newUsers;
    const watchTimeHours = Math.round(12480 * scaler);
    const revenueVal = Math.round(28450 * scaler);

    viewport.innerHTML = `
      <!-- Stats Summary -->
      <div class="analytics-stats-grid">
        <div class="stat-card glass-card">
          <span class="stat-icon">👥</span>
          <div class="stat-info">
            <span class="stat-label">Active Users</span>
            <span class="stat-val">${activeUsers.toLocaleString()}</span>
          </div>
        </div>
        <div class="stat-card glass-card">
          <span class="stat-icon">✨</span>
          <div class="stat-info">
            <span class="stat-label">New / Returning</span>
            <span class="stat-val" style="font-size:13px; font-weight:800;">${newUsers.toLocaleString()} / ${returningUsers.toLocaleString()}</span>
          </div>
        </div>
        <div class="stat-card glass-card">
          <span class="stat-icon">⏳</span>
          <div class="stat-info">
            <span class="stat-label">Watch Time (Hours)</span>
            <span class="stat-val">${watchTimeHours.toLocaleString()} hrs</span>
          </div>
        </div>
        <div class="stat-card glass-card">
          <span class="stat-icon">💰</span>
          <div class="stat-info">
            <span class="stat-label">Monthly Revenue</span>
            <span class="stat-val">$${revenueVal.toLocaleString()} USD</span>
          </div>
        </div>
      </div>

      <!-- Charts Grid -->
      <div class="analytics-charts-grid">
        <div class="chart-card glass-card">
          <h3>👥 Cohort Retention Dynamics</h3>
          <p class="chart-desc">Splits of active New vs Returning viewer logs recorded over time.</p>
          <div class="canvas-container"><canvas id="canvas-exec-cohort" width="460" height="200"></canvas></div>
        </div>

        <div class="chart-card glass-card">
          <h3>💰 Revenue Growth & Valuation</h3>
          <p class="chart-desc">Investor shares dividends growth and advertising revenue trends.</p>
          <div class="canvas-container"><canvas id="canvas-exec-revenue" width="460" height="200"></canvas></div>
        </div>

        <div class="chart-card glass-card" style="grid-column: span 2;">
          <h3>🌍 Country Demographics & Audiences</h3>
          <p class="chart-desc">Geographical viewership distributions comparing diaspora hubs against local stations.</p>
          <div class="canvas-container"><canvas id="canvas-exec-countries" width="960" height="220"></canvas></div>
        </div>
      </div>
    `;

    // Render Canvas Charts
    drawCohortChart();
    drawRevenueChart();
    drawCountriesChart();
  };

  const drawCohortChart = () => {
    const canvas = container.querySelector("#canvas-exec-cohort");
    const ctx = canvas.getContext("2d");
    const w = canvas.width;
    const h = canvas.height;
    ctx.clearRect(0, 0, w, h);

    const padding = 30;
    const chartW = w - padding * 2;
    const chartH = h - padding * 2;
    const dataNew = [12, 14, 11, 15, 19, 22, 21, 25, 29, 31, 28, 30, 35, 32, 38];
    const dataReturn = [40, 42, 45, 48, 51, 58, 62, 60, 65, 70, 78, 80, 85, 92, 98];
    const maxVal = 110;

    // Draw Grid Lines
    ctx.strokeStyle = "rgba(255,255,255,0.05)";
    for (let i = padding; i < h - padding; i += 35) {
      ctx.beginPath(); ctx.moveTo(padding, i); ctx.lineTo(w - padding, i); ctx.stroke();
    }

    // Line 1: New Users
    ctx.strokeStyle = "#3b82f6";
    ctx.lineWidth = 2;
    ctx.beginPath();
    for (let i = 0; i < dataNew.length; i++) {
      const cx = padding + (i / (dataNew.length - 1)) * chartW;
      const cy = h - padding - (dataNew[i] / maxVal) * chartH;
      if (i === 0) ctx.moveTo(cx, cy);
      else ctx.lineTo(cx, cy);
    }
    ctx.stroke();

    // Line 2: Returning Users
    ctx.strokeStyle = getThemeColor();
    ctx.lineWidth = 2.5;
    ctx.beginPath();
    for (let i = 0; i < dataReturn.length; i++) {
      const cx = padding + (i / (dataReturn.length - 1)) * chartW;
      const cy = h - padding - (dataReturn[i] / maxVal) * chartH;
      if (i === 0) ctx.moveTo(cx, cy);
      else ctx.lineTo(cx, cy);
    }
    ctx.stroke();
  };

  const drawRevenueChart = () => {
    const canvas = container.querySelector("#canvas-exec-revenue");
    const ctx = canvas.getContext("2d");
    const w = canvas.width;
    const h = canvas.height;
    ctx.clearRect(0, 0, w, h);

    const padding = 30;
    const chartW = w - padding * 2;
    const chartH = h - padding * 2;
    const dataRev = [100, 120, 150, 140, 180, 210, 230, 220, 260, 290, 310, 340, 380, 420, 460];
    const maxVal = 500;

    // Gradient area
    const gradient = ctx.createLinearGradient(0, padding, 0, h - padding);
    gradient.addColorStop(0, "rgba(16, 185, 129, 0.35)");
    gradient.addColorStop(1, "rgba(16, 185, 129, 0)");

    ctx.fillStyle = gradient;
    ctx.beginPath();
    ctx.moveTo(padding, h - padding);
    for (let i = 0; i < dataRev.length; i++) {
      const cx = padding + (i / (dataRev.length - 1)) * chartW;
      const cy = h - padding - (dataRev[i] / maxVal) * chartH;
      ctx.lineTo(cx, cy);
    }
    ctx.lineTo(w - padding, h - padding);
    ctx.fill();

    // Line
    ctx.strokeStyle = "#10b981";
    ctx.lineWidth = 2.5;
    ctx.beginPath();
    for (let i = 0; i < dataRev.length; i++) {
      const cx = padding + (i / (dataRev.length - 1)) * chartW;
      const cy = h - padding - (dataRev[i] / maxVal) * chartH;
      if (i === 0) ctx.moveTo(cx, cy);
      else ctx.lineTo(cx, cy);
    }
    ctx.stroke();
  };

  const drawCountriesChart = () => {
    const canvas = container.querySelector("#canvas-exec-countries");
    const ctx = canvas.getContext("2d");
    const w = canvas.width;
    const h = canvas.height;
    ctx.clearRect(0, 0, w, h);

    const padding = 40;
    const chartW = w - padding * 2;
    const chartH = h - padding * 2;
    const regions = ["Mogadishu", "Nairobi", "Hargeisa", "London", "Minneapolis", "Garissa"];
    const counts = [450, 320, 280, 190, 150, 110];
    const maxVal = 500;

    // Draw grid
    ctx.strokeStyle = "rgba(255,255,255,0.04)";
    for (let i = padding; i < h - padding; i += 30) {
      ctx.beginPath(); ctx.moveTo(padding, i); ctx.lineTo(w - padding, i); ctx.stroke();
    }

    const barW = (chartW - 40 * (regions.length + 1)) / regions.length;
    for (let i = 0; i < regions.length; i++) {
      const bx = padding + 40 + i * (barW + 40);
      const valH = (counts[i] / maxVal) * chartH;
      const by = h - padding - valH;

      ctx.fillStyle = i === 0 ? getThemeColor() : "rgba(255,255,255,0.08)";
      ctx.strokeStyle = i === 0 ? getThemeColor() : "rgba(255,255,255,0.15)";
      ctx.lineWidth = 1.5;

      // Draw rounded rectangle
      ctx.fillRect(bx, by, barW, valH);
      ctx.strokeRect(bx, by, barW, valH);

      // Labels
      ctx.fillStyle = "#ffffff";
      ctx.font = "bold 10px Outfit, sans-serif";
      ctx.fillText(regions[i], bx + barW / 2 - ctx.measureText(regions[i]).width / 2, h - padding + 15);

      // Values
      ctx.fillStyle = "rgba(255,255,255,0.6)";
      ctx.fillText(`${counts[i]}k`, bx + barW / 2 - ctx.measureText(`${counts[i]}k`).width / 2, by - 6);
    }
  };

  // 🎙️ Dashboard 2: Newsroom Board
  const loadNewsroomDashboard = () => {
    const viewport = container.querySelector("#analytics-viewport-content");
    viewport.innerHTML = `
      <div class="analytics-stats-grid">
        <div class="stat-card glass-card">
          <span class="stat-icon">📡</span>
          <div class="stat-info">
            <span class="stat-label">Viewers Online Now</span>
            <span class="stat-val" id="newsroom-online-count">0</span>
          </div>
        </div>
        <div class="stat-card glass-card">
          <span class="stat-icon">🔥</span>
          <div class="stat-info">
            <span class="stat-label">Fastest Growing Channel</span>
            <span class="stat-val" style="font-size: 14px; font-weight:800; color:var(--brand-primary);">GNTV DIGITAL, ALL EVERYWHERE Sports Global</span>
          </div>
        </div>
        <div class="stat-card glass-card">
          <span class="stat-icon">📍</span>
          <div class="stat-info">
            <span class="stat-label">Top Region (Live Feed)</span>
            <span class="stat-val">Mogadishu Area</span>
          </div>
        </div>
        <div class="stat-card glass-card">
          <span class="stat-icon">📣</span>
          <div class="stat-info">
            <span class="stat-label">Emergency Broadcast Override</span>
            <span class="stat-val" style="font-size:12px; font-weight:800; color:#10b981;">NO THREAT DETECTED</span>
          </div>
        </div>
      </div>

      <div class="analytics-charts-grid">
        <!-- Chart 1: Viewer counts per channels -->
        <div class="chart-card glass-card">
          <h3>📡 Active Viewers per Live Channel</h3>
          <p class="chart-desc">Viewer allocations across GNTV DIGITAL, ALL EVERYWHERE's four linear channels.</p>
          <div class="canvas-container"><canvas id="canvas-newsroom-channels" width="460" height="200"></canvas></div>
        </div>

        <!-- Chart 2: Top Regions tuning in -->
        <div class="chart-card glass-card">
          <h3>📍 Audience Share by Bureau Regions</h3>
          <p class="chart-desc">Demographic bureau shares from live client streams.</p>
          <div class="canvas-container"><canvas id="canvas-newsroom-regions" width="460" height="200"></canvas></div>
        </div>

        <div class="chart-card glass-card" style="grid-column: span 2;">
          <h3>🔥 Real-Time Trending Newsroom Stories</h3>
          <div class="cms-table-wrapper" style="overflow-x: auto; margin-top: 14px;">
            <table class="cms-table">
              <thead>
                <tr>
                  <th>Topic / Headline</th>
                  <th>Bureaus Node</th>
                  <th>Hourly Growth</th>
                  <th>Engagement</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td class="table-bold-title">Ruto Bilateral Trade Agreements</td>
                  <td>Nairobi Hub</td>
                  <td style="color:#10b981; font-weight:800;">+254%</td>
                  <td>98.2k interactions</td>
                </tr>
                <tr>
                  <td class="table-bold-title">Shabelle River Inundations Report</td>
                  <td>Mogadishu Bureau</td>
                  <td style="color:#10b981; font-weight:800;">+182%</td>
                  <td>76.4k interactions</td>
                </tr>
                <tr>
                  <td class="table-bold-title">Taariikhda Berbera Port Archeology</td>
                  <td>Hargeisa Desk</td>
                  <td style="color:#f59e0b; font-weight:800;">+94%</td>
                  <td>45.1k interactions</td>
                </tr>
                <tr>
                  <td class="table-bold-title">Somali Diaspora Sports Cup Minneapolis</td>
                  <td>Diaspora US Desk</td>
                  <td style="color:#10b981; font-weight:800;">+112%</td>
                  <td>38.9k interactions</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>
    `;

    // Hook viewer counter live update
    const onlineCounter = container.querySelector("#newsroom-online-count");
    if (onlineCounter) {
      onlineCounter.textContent = store.getState("viewerCount").toLocaleString();
    }

    drawNewsroomChannelsChart();
    drawNewsroomRegionsChart();
  };

  const drawNewsroomChannelsChart = () => {
    const canvas = container.querySelector("#canvas-newsroom-channels");
    const ctx = canvas.getContext("2d");
    const w = canvas.width;
    const h = canvas.height;
    ctx.clearRect(0, 0, w, h);

    const padding = 30;
    const chartW = w - padding * 2;
    const chartH = h - padding * 2;
    const channels = ["GNTV DIGITAL, ALL EVERYWHERE News", "GNTV DIGITAL, ALL EVERYWHERE Sports", "GNTV DIGITAL, ALL EVERYWHERE Docs", "Eastleigh TV"];
    const viewers = [1420, 950, 780, 420];
    const maxVal = 1600;

    // Horizontal bars
    const barH = (chartH - 15 * (channels.length + 1)) / channels.length;
    for (let i = 0; i < channels.length; i++) {
      const by = padding + 15 + i * (barH + 15);
      const valW = (viewers[i] / maxVal) * chartW;

      ctx.fillStyle = i === 0 ? getThemeColor() : "rgba(255, 255, 255, 0.08)";
      ctx.fillRect(padding, by, valW, barH);

      // Labels
      ctx.fillStyle = "#ffffff";
      ctx.font = "bold 10px Outfit, sans-serif";
      ctx.fillText(channels[i], padding + 10, by + barH / 2 + 3);

      // Value label on right
      ctx.fillText(viewers[i].toString(), padding + valW - 35, by + barH / 2 + 3);
    }
  };

  const drawNewsroomRegionsChart = () => {
    const canvas = container.querySelector("#canvas-newsroom-regions");
    const ctx = canvas.getContext("2d");
    const w = canvas.width;
    const h = canvas.height;
    ctx.clearRect(0, 0, w, h);

    const slices = [
      { label: "Mogadishu", count: 48, color: getThemeColor() },
      { label: "Nairobi", count: 30, color: "#3b82f6" },
      { label: "Hargeisa", count: 12, color: "#f59e0b" },
      { label: "Diaspora", count: 10, color: "#9ca3af" }
    ];
    let startAngle = -Math.PI / 2;
    const centerX = w / 2 - 60;
    const centerY = h / 2;
    const radius = 60;

    slices.forEach(s => {
      const sliceAngle = (s.count / 100) * (Math.PI * 2);
      ctx.fillStyle = s.color;
      ctx.beginPath(); ctx.moveTo(centerX, centerY);
      ctx.arc(centerX, centerY, radius, startAngle, startAngle + sliceAngle);
      ctx.closePath(); ctx.fill();

      // separator
      ctx.strokeStyle = "#0f0f15";
      ctx.lineWidth = 1;
      ctx.stroke();

      startAngle += sliceAngle;
    });

    const legendX = w / 2 + 40;
    let legendY = h / 2 - 40;
    slices.forEach(s => {
      ctx.fillStyle = s.color;
      ctx.fillRect(legendX, legendY, 12, 12);

      ctx.fillStyle = "#ffffff";
      ctx.font = "bold 10px Outfit, sans-serif";
      ctx.fillText(`${s.label} (${s.count}%)`, legendX + 18, legendY + 9);
      legendY += 20;
    });
  };

  // 📼 Dashboard 3: Content Performance
  const loadContentDashboard = () => {
    const viewport = container.querySelector("#analytics-viewport-content");
    viewport.innerHTML = `
      <div class="analytics-stats-grid">
        <div class="stat-card glass-card">
          <span class="stat-icon">🎬</span>
          <div class="stat-info">
            <span class="stat-label">Most Watched VOD</span>
            <span class="stat-val" style="font-size:13px; font-weight:800;">Dhalinyarada Eastleigh</span>
          </div>
        </div>
        <div class="stat-card glass-card">
          <span class="stat-icon">🎙️</span>
          <div class="stat-info">
            <span class="stat-label">Top Host Creator</span>
            <span class="stat-val">Layla Warsame</span>
          </div>
        </div>
        <div class="stat-card glass-card">
          <span class="stat-icon">🔑</span>
          <div class="stat-info">
            <span class="stat-label">Top Searched Keyword</span>
            <span class="stat-val" style="font-family:var(--font-mono); font-size:13px;">"Taariikhda"</span>
          </div>
        </div>
        <div class="stat-card glass-card">
          <span class="stat-icon">🏁</span>
          <div class="stat-info">
            <span class="stat-label">VOD Completion Rate</span>
            <span class="stat-val">72.4% Average</span>
          </div>
        </div>
      </div>

      <div class="analytics-charts-grid">
        <!-- Chart 1: Most Watched content -->
        <div class="chart-card glass-card">
          <h3>📼 Most Watched Catalogue Content</h3>
          <p class="chart-desc">Total playbacks recorded for VOD assets and podcasts.</p>
          <div class="canvas-container"><canvas id="canvas-content-watched" width="460" height="200"></canvas></div>
        </div>

        <!-- Chart 2: Search queries -->
        <div class="chart-card glass-card">
          <h3>🔍 Most Searched Platform Keywords</h3>
          <p class="chart-desc">Keyword density queries compiled from client global search input.</p>
          <div class="canvas-container"><canvas id="canvas-content-searches" width="460" height="200"></canvas></div>
        </div>

        <div class="chart-card glass-card" style="grid-column: span 2;">
          <h3>🎭 Creator Hosts & Presenters Engagement Board</h3>
          <div class="cms-table-wrapper" style="overflow-x: auto; margin-top: 14px;">
            <table class="cms-table">
              <thead>
                <tr>
                  <th>Host / Presenter</th>
                  <th>Primary Show</th>
                  <th>Views Directed</th>
                  <th>Followers Reach</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td class="table-bold-title">Layla Warsame</td>
                  <td>Dhalinyarada Eastleigh</td>
                  <td>148,000 views</td>
                  <td>45.2k users</td>
                </tr>
                <tr>
                  <td class="table-bold-title">Maxamed Cali</td>
                  <td>Taariikhda Geeska Afrika</td>
                  <td>92,500 views</td>
                  <td>32.8k users</td>
                </tr>
                <tr>
                  <td class="table-bold-title">Khadra Saciid</td>
                  <td>Daily Somali News Brief</td>
                  <td>88,400 views</td>
                  <td>28.4k users</td>
                </tr>
                <tr>
                  <td class="table-bold-title">Jaamac Barre</td>
                  <td>Horn of Africa Podcast</td>
                  <td>56,100 views</td>
                  <td>18.9k users</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>
    `;

    drawContentWatchedChart();
    drawContentSearchesChart();
  };

  const drawContentWatchedChart = () => {
    const canvas = container.querySelector("#canvas-content-watched");
    const ctx = canvas.getContext("2d");
    const w = canvas.width;
    const h = canvas.height;
    ctx.clearRect(0, 0, w, h);

    const padding = 35;
    const chartW = w - padding * 2;
    const chartH = h - padding * 2;
    const items = ["Eastleigh VOD", "Somali Hist.", "Horn Podcast", "Comedy Night"];
    const views = [450, 320, 240, 180];
    const maxVal = 500;

    const barW = (chartW - 30 * (items.length + 1)) / items.length;
    for (let i = 0; i < items.length; i++) {
      const bx = padding + 30 + i * (barW + 30);
      const valH = (views[i] / maxVal) * chartH;
      const by = h - padding - valH;

      ctx.fillStyle = i === 0 ? getThemeColor() : "rgba(255, 255, 255, 0.08)";
      ctx.fillRect(bx, by, barW, valH);

      // Labels
      ctx.fillStyle = "rgba(255,255,255,0.7)";
      ctx.font = "bold 9px Outfit, sans-serif";
      ctx.fillText(items[i], bx + barW / 2 - ctx.measureText(items[i]).width / 2, h - padding + 15);

      // values
      ctx.fillStyle = "#ffffff";
      ctx.fillText(`${views[i]}k`, bx + barW / 2 - ctx.measureText(`${views[i]}k`).width / 2, by - 6);
    }
  };

  const drawContentSearchesChart = () => {
    const canvas = container.querySelector("#canvas-content-searches");
    const ctx = canvas.getContext("2d");
    const w = canvas.width;
    const h = canvas.height;
    ctx.clearRect(0, 0, w, h);

    const padding = 30;
    const chartW = w - padding * 2;
    const chartH = h - padding * 2;
    const keys = ["ruto", "history", "somali", "water", "comedy"];
    const values = [285, 240, 195, 140, 95];
    const maxVal = 300;

    const barH = (chartH - 12 * (keys.length + 1)) / keys.length;
    for (let i = 0; i < keys.length; i++) {
      const by = padding + 12 + i * (barH + 12);
      const valW = (values[i] / maxVal) * chartW;

      ctx.fillStyle = "rgba(59, 130, 246, 0.6)";
      ctx.fillRect(padding, by, valW, barH);

      // Labels
      ctx.fillStyle = "#ffffff";
      ctx.font = "bold 10px monospace";
      ctx.fillText(`"${keys[i]}"`, padding + 10, by + barH / 2 + 3);

      ctx.fillText(values[i].toString(), padding + valW - 30, by + barH / 2 + 3);
    }
  };

  // ⚡ Dashboard 4: Real-Time Infrastructure
  const loadRealtimeDashboard = () => {
    const viewport = container.querySelector("#analytics-viewport-content");
    viewport.innerHTML = `
      <div class="analytics-stats-grid">
        <div class="stat-card glass-card">
          <span class="stat-icon">⚡</span>
          <div class="stat-info">
            <span class="stat-label">Infrastructure Latency</span>
            <span class="stat-val" id="rt-latency-val">140 ms</span>
          </div>
        </div>
        <div class="stat-card glass-card">
          <span class="stat-icon">⚠️</span>
          <div class="stat-info">
            <span class="stat-label">Packet Drop Rate</span>
            <span class="stat-val" style="color:#10b981; font-weight:800;">0.02% (NOMINAL)</span>
          </div>
        </div>
        <div class="stat-card glass-card">
          <span class="stat-icon">💪</span>
          <div class="stat-info">
            <span class="stat-label">Bitrate Stability</span>
            <span class="stat-val">98.4% Nominal</span>
          </div>
        </div>
        <div class="stat-card glass-card">
          <span class="stat-icon">💓</span>
          <div class="stat-info">
            <span class="stat-label">Active Heartbeats</span>
            <span class="stat-val" id="rt-heartbeat-val">0</span>
          </div>
        </div>
      </div>

      <div class="analytics-charts-grid">
        <!-- Chart 1: Bandwidth speed -->
        <div class="chart-card glass-card">
          <h3>⚡ Live CDN Streaming Bitrate splines</h3>
          <p class="chart-desc">Viewer downlink download speeds recorded in real time.</p>
          <div class="canvas-container"><canvas id="canvas-rt-bitrate" width="460" height="200"></canvas></div>
        </div>

        <!-- Chart 2: Infrastructure Latency spline -->
        <div class="chart-card glass-card">
          <h3>📡 satellite Uplink connection latency</h3>
          <p class="chart-desc">Ping latency (ms) recorded from satellite relays.</p>
          <div class="canvas-container"><canvas id="canvas-rt-latency" width="460" height="200"></canvas></div>
        </div>
      </div>

      <!-- Real-Time Telemetry Event Log -->
      <div class="analytics-terminal-card glass-card" style="margin-top: 24px;">
        <div class="terminal-header">
          <h3>🖥️ GNTV DIGITAL, ALL EVERYWHERE Systems Telemetry Event stream</h3>
          <span class="terminal-sub" id="terminal-pulse">ONLINE // Postgres Pipeline Secure</span>
        </div>
        <div class="terminal-feed" id="terminal-feed-box">
          <!-- Live events populate here -->
        </div>
      </div>
    `;

    // Initial log entries
    addTerminalLog("Telemetry pipeline handshakes secure. Postgres socket active.");

    drawRealtimeBitrateChart();
    drawRealtimeLatencyChart();
  };

  const drawRealtimeBitrateChart = () => {
    const canvas = container.querySelector("#canvas-rt-bitrate");
    const ctx = canvas.getContext("2d");
    const w = canvas.width;
    const h = canvas.height;
    ctx.clearRect(0, 0, w, h);

    const padding = 30;
    const chartW = w - padding * 2;
    const chartH = h - padding * 2;
    const data = heartbeatTimeline;
    const maxVal = 600;

    // Area
    const gradient = ctx.createLinearGradient(0, padding, 0, h - padding);
    gradient.addColorStop(0, getThemeColor().replace("hsl", "hsla").replace(")", ", 0.25)"));
    gradient.addColorStop(1, "rgba(0,0,0,0)");
    ctx.fillStyle = gradient;
    ctx.beginPath();
    ctx.moveTo(padding, h - padding);
    for (let i = 0; i < data.length; i++) {
      const cx = padding + (i / (data.length - 1)) * chartW;
      const cy = h - padding - (data[i] / maxVal) * chartH;
      ctx.lineTo(cx, cy);
    }
    ctx.lineTo(w - padding, h - padding);
    ctx.fill();

    // Line
    ctx.strokeStyle = getThemeColor();
    ctx.lineWidth = 2;
    ctx.beginPath();
    for (let i = 0; i < data.length; i++) {
      const cx = padding + (i / (data.length - 1)) * chartW;
      const cy = h - padding - (data[i] / maxVal) * chartH;
      if (i === 0) ctx.moveTo(cx, cy);
      else ctx.lineTo(cx, cy);
    }
    ctx.stroke();
  };

  const drawRealtimeLatencyChart = () => {
    const canvas = container.querySelector("#canvas-rt-latency");
    const ctx = canvas.getContext("2d");
    const w = canvas.width;
    const h = canvas.height;
    ctx.clearRect(0, 0, w, h);

    const padding = 30;
    const chartW = w - padding * 2;
    const chartH = h - padding * 2;
    const data = latencySpline;
    const maxVal = 180;

    // Draw grid
    ctx.strokeStyle = "rgba(255,255,255,0.05)";
    for (let i = padding; i < h - padding; i += 30) {
      ctx.beginPath(); ctx.moveTo(padding, i); ctx.lineTo(w - padding, i); ctx.stroke();
    }

    // Line
    ctx.strokeStyle = "#3b82f6";
    ctx.lineWidth = 2;
    ctx.beginPath();
    for (let i = 0; i < data.length; i++) {
      const cx = padding + (i / (data.length - 1)) * chartW;
      const cy = h - padding - (data[i] / maxVal) * chartH;
      if (i === 0) ctx.moveTo(cx, cy);
      else ctx.lineTo(cx, cy);
    }
    ctx.stroke();
  };

  const loadActiveDashboard = () => {
    if (activeSubTab === "executive") {
      loadExecutiveDashboard();
    } else if (activeSubTab === "newsroom") {
      loadNewsroomDashboard();
    } else if (activeSubTab === "content") {
      loadContentDashboard();
    } else if (activeSubTab === "realtime") {
      loadRealtimeDashboard();
    }
  };

  const simulateActivity = () => {
    if (!active) return;

    // Shift timeline data
    heartbeatTimeline.shift();
    const newBit = Math.floor(Math.random() * 200) + 250;
    heartbeatTimeline.push(newBit);

    latencySpline.shift();
    const newPing = Math.floor(Math.random() * 15) + 130;
    latencySpline.push(newPing);

    // Sync online counts dynamically if in Newsroom
    const onlineCounter = container.querySelector("#newsroom-online-count");
    if (onlineCounter) {
      onlineCounter.textContent = store.getState("viewerCount").toLocaleString();
    }

    // Update real-time tab stats dynamically if open
    const rtLatency = container.querySelector("#rt-latency-val");
    if (rtLatency) {
      rtLatency.textContent = `${newPing} ms`;
    }

    const rtHeartbeat = container.querySelector("#rt-heartbeat-val");
    if (rtHeartbeat) {
      const sessions = db.from("gntv_video_sessions").data || [];
      const totalHeartbeats = sessions.reduce((acc, s) => acc + (s.heartbeats || 0), 0);
      rtHeartbeat.textContent = totalHeartbeats.toString();
    }

    // Add scrolling terminal logs dynamically
    const sessions = db.from("gntv_video_sessions").data || [];
    if (sessions.length > 0 && Math.random() > 0.4) {
      const randomSess = sessions[Math.floor(Math.random() * sessions.length)];
      const logTypes = ["HEARTBEAT LOGGED", "UPLINK DECODE SUCCESS", "UPLINK NOMINAL", "CDN BUFFER CACHED"];
      const rLog = logTypes[Math.floor(Math.random() * logTypes.length)];
      addTerminalLog(`Packet verified: sess-${randomSess.id.substring(5)} // "${randomSess.video_title.substring(0, 16)}" // ${rLog}`);
    } else if (Math.random() > 0.8) {
      const mockCities = ["Mogadishu", "Nairobi", "Garissa", "Minneapolis", "London"];
      const rCity = mockCities[Math.floor(Math.random() * mockCities.length)];
      addTerminalLog(`Handshake handshake secure: ${rCity} Bureau satellite tunnel initialized.`);
    }

    // Refresh active canvases
    if (activeSubTab === "realtime") {
      drawRealtimeBitrateChart();
      drawRealtimeLatencyChart();
    } else if (activeSubTab === "executive") {
      drawCohortChart();
      drawRevenueChart();
    }
  };

  // Setup layout & load dashboard
  renderContainer();
  loadActiveDashboard();

  // Set intervals updates
  timerId = setInterval(simulateActivity, 2000);

  return () => {
    active = false;
    if (timerId) clearInterval(timerId);
  };
}
