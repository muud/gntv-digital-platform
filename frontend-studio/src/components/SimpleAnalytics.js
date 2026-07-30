import { store } from "../../../shared/src/state.js";

export function initSimpleAnalytics(container) {
  const stats = {
    views: "1,248,500",
    watchTime: "458,200 Hrs",
    revenue: "$12,450.80",
    platformsCount: "6 Active"
  };

  const locations = [
    { city: "Mogadishu, Somalia", percentage: 45, count: "561.8k views" },
    { city: "Nairobi, Kenya", percentage: 22, count: "274.6k views" },
    { city: "Garissa, Kenya", percentage: 15, count: "187.2k views" },
    { city: "Minneapolis, USA", percentage: 10, count: "124.8k views" },
    { city: "London, UK", percentage: 8, count: "100.1k views" }
  ];

  const distributionShares = [
    { platform: "YouTube", share: 35, color: "#ff0000" },
    { platform: "GNTV DIGITAL, ALL EVERYWHERE OTT", share: 25, color: "var(--brand-primary)" },
    { platform: "TikTok", share: 20, color: "#00f2fe" },
    { platform: "Facebook", share: 10, color: "#1877f2" },
    { platform: "IPTV Satellite", share: 7, color: "#a855f7" },
    { platform: "Instagram", share: 3, color: "#e1306c" }
  ];

  const render = () => {
    container.innerHTML = `
      <div class="simple-analytics-wrapper" style="padding: 24px; font-family: var(--font-sans); color: #fff; max-width: 1100px; margin: 0 auto;">

        <!-- Header Section -->
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 32px; flex-wrap: wrap; gap: 16px;">
          <div>
            <h2 style="font-size: 26px; font-weight: 850; letter-spacing: -1px; margin: 0; background: linear-gradient(135deg, #fff 0%, #a1a1aa 100%); -webkit-background-clip: text; -webkit-text-fill-color: transparent;">Waxqabadka Kanaalka / Real-Time Creator Analytics</h2>
            <p style="color: rgba(255,255,255,0.5); font-size: 13px; margin: 4px 0 0 0;">
              Investor-friendly metrics showing video propagation, engagement, and automated payouts.
            </p>
          </div>

          <div style="display: flex; gap: 8px;">
            <button class="glass-panel" style="background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.12); padding: 8px 16px; border-radius: 8px; font-size: 12px; font-weight: 700; color: #fff; cursor: pointer;">Last 30 Days ▾</button>
            <button class="glass-panel" id="btn-refresh-analytics" style="background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.12); padding: 8px 12px; border-radius: 8px; font-size: 12px; font-weight: 700; color: #fff; cursor: pointer;">↻ Refresh</button>
          </div>
        </div>

        <!-- KPI Grid -->
        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 20px; margin-bottom: 32px;">

          <div class="glass-card" style="padding: 20px; border-radius: 16px; background: rgba(255, 255, 255, 0.02); border: 1px solid rgba(255, 255, 255, 0.06); transition: transform 0.2s;" onmouseover="this.style.transform='translateY(-2px)'" onmouseout="this.style.transform='translateY(0)'">
            <span style="font-size: 24px; display: block; margin-bottom: 12px;">👁️</span>
            <div style="font-size: 11px; font-weight: 800; color: rgba(255,255,255,0.4); text-transform: uppercase; letter-spacing: 0.5px;">Views (Daawasho)</div>
            <div style="font-size: 28px; font-weight: 850; margin: 4px 0; font-family: var(--font-mono);">${stats.views}</div>
            <span style="font-size: 11px; color: #10b981; font-weight: 700;">↑ 14.2% vs last month</span>
          </div>

          <div class="glass-card" style="padding: 20px; border-radius: 16px; background: rgba(255, 255, 255, 0.02); border: 1px solid rgba(255, 255, 255, 0.06); transition: transform 0.2s;" onmouseover="this.style.transform='translateY(-2px)'" onmouseout="this.style.transform='translateY(0)'">
            <span style="font-size: 24px; display: block; margin-bottom: 12px;">⏳</span>
            <div style="font-size: 11px; font-weight: 800; color: rgba(255,255,255,0.4); text-transform: uppercase; letter-spacing: 0.5px;">Watch Time (Saacadaha)</div>
            <div style="font-size: 28px; font-weight: 850; margin: 4px 0; font-family: var(--font-mono);">${stats.watchTime}</div>
            <span style="font-size: 11px; color: #10b981; font-weight: 700;">↑ 8.4% vs last month</span>
          </div>

          <div class="glass-card" style="padding: 20px; border-radius: 16px; background: rgba(255, 255, 255, 0.02); border: 1px solid rgba(255, 255, 255, 0.06); transition: transform 0.2s;" onmouseover="this.style.transform='translateY(-2px)'" onmouseout="this.style.transform='translateY(0)'">
            <span style="font-size: 24px; display: block; margin-bottom: 12px;">💰</span>
            <div style="font-size: 11px; font-weight: 800; color: rgba(255,255,255,0.4); text-transform: uppercase; letter-spacing: 0.5px;">Estimated Revenue</div>
            <div style="font-size: 28px; font-weight: 850; margin: 4px 0; font-family: var(--font-mono); color: #10b981;">${stats.revenue}</div>
            <span style="font-size: 11px; color: #10b981; font-weight: 700;">↑ 22.8% vs last month</span>
          </div>

          <div class="glass-card" style="padding: 20px; border-radius: 16px; background: rgba(255, 255, 255, 0.02); border: 1px solid rgba(255, 255, 255, 0.06); transition: transform 0.2s;" onmouseover="this.style.transform='translateY(-2px)'" onmouseout="this.style.transform='translateY(0)'">
            <span style="font-size: 24px; display: block; margin-bottom: 12px;">📡</span>
            <div style="font-size: 11px; font-weight: 800; color: rgba(255,255,255,0.4); text-transform: uppercase; letter-spacing: 0.5px;">Broadcasting Channels</div>
            <div style="font-size: 28px; font-weight: 850; margin: 4px 0; font-family: var(--font-mono);">${stats.platformsCount}</div>
            <span style="font-size: 11px; color: rgba(255,255,255,0.5); font-weight: 700;">Uplink channels locked</span>
          </div>

        </div>

        <!-- Charts Layout (Audience & Platforms) -->
        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 24px; flex-wrap: wrap;">

          <!-- Audience Location -->
          <div class="glass-card" style="padding: 24px; border-radius: 16px; background: rgba(10, 10, 15, 0.5); border: 1px solid rgba(255, 255, 255, 0.06); min-width: 320px;">
            <h3 style="font-size: 16px; font-weight: 800; margin-bottom: 16px; display: flex; align-items: center; gap: 8px;">
              📍 Bulshada Daawanaysa / Audience Locations
            </h3>

            <div style="display: flex; flex-direction: column; gap: 16px;">
              ${locations.map(loc => `
                <div>
                  <div style="display: flex; justify-content: space-between; font-size: 12px; margin-bottom: 4px;">
                    <span style="font-weight: 700;">${loc.city}</span>
                    <span style="color: rgba(255,255,255,0.5); font-family: var(--font-mono);">${loc.count} (${loc.percentage}%)</span>
                  </div>
                  <div style="width: 100%; height: 6px; background: rgba(255,255,255,0.06); border-radius: 3px; overflow: hidden;">
                    <div style="width: ${loc.percentage}%; height: 100%; background: linear-gradient(90deg, var(--brand-primary) 0%, rgba(255, 42, 75, 0.6) 100%); border-radius: 3px;"></div>
                  </div>
                </div>
              `).join('')}
            </div>
          </div>

          <!-- Platform performance share -->
          <div class="glass-card" style="padding: 24px; border-radius: 16px; background: rgba(10, 10, 15, 0.5); border: 1px solid rgba(255, 255, 255, 0.06); min-width: 320px;">
            <h3 style="font-size: 16px; font-weight: 800; margin-bottom: 16px; display: flex; align-items: center; gap: 8px;">
              📊 Waddooyinka Faafinta / Platform Revenue Share
            </h3>

            <!-- Pure CSS Visual donut simulation bar -->
            <div style="display: flex; height: 20px; border-radius: 10px; overflow: hidden; margin-bottom: 24px;">
              ${distributionShares.map(sh => `
                <div style="width: ${sh.share}%; background: ${sh.color};" title="${sh.platform}: ${sh.share}%"></div>
              `).join('')}
            </div>

            <!-- Legends -->
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px;">
              ${distributionShares.map(sh => `
                <div style="display: flex; align-items: center; gap: 8px; font-size: 12px;">
                  <span style="width: 10px; height: 10px; border-radius: 50%; background: ${sh.color}; display: inline-block;"></span>
                  <span style="font-weight: 700; flex: 1;">${sh.platform}</span>
                  <span style="font-family: var(--font-mono); color: rgba(255,255,255,0.5); font-weight: 700;">${sh.share}%</span>
                </div>
              `).join('')}
            </div>
          </div>

        </div>

      </div>
    `;

    bindEvents();
  };

  const bindEvents = () => {
    const refreshBtn = container.querySelector("#btn-refresh-analytics");
    if (refreshBtn) {
      refreshBtn.addEventListener("click", () => {
        refreshBtn.textContent = "Loading...";
        setTimeout(() => {
          refreshBtn.textContent = "↻ Refresh";
          render();
        }, 600);
      });
    }
  };

  render();
}
