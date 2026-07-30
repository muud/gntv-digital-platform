import { store } from "../../../shared/src/state.js";
import { MOCK_DOCUMENTS } from "../../../shared/src/utils/mockData.js";

const INVESTMENT_MOTIONS = [
  { id: "motion1", title: "Expand East Africa Correspondent Hubs (Nairobi & Wajir)", description: "Proposing a $150K USD capital expenditure budget to hire 4 full-time reporters and build a permanent broadcast relay tower in Nairobi Kaunti.", yesVotes: 12500, noVotes: 4300 },
  { id: "motion2", title: "Launch Swahili Sports & Culture TV Channel 24/7", description: "Spinning off our sports highlights and local league feeds into a dedicated 24/7 linear RTMP feed targeting Tanzanian and Kenyan viewer markets.", yesVotes: 9800, noVotes: 8700 }
];

export function initInvestorPortal(container) {
  let animFrame = null;

  const renderPortal = () => {
    if (animFrame) cancelAnimationFrame(animFrame);

    const userShares = store.getState("userShares") || { shares: 2500, price: 1.85, dividendPaid: 185.00, referrals: 150.00, motionsVoted: {} };
    const valuation = userShares.shares * userShares.price;

    container.innerHTML = `
      <div class="investor-wrapper">
        <div class="investor-grid">

          <!-- Left: Portfolio Stats & Charts -->
          <div style="display: flex; flex-direction: column; gap: 20px;">

            <!-- Portfolio Summary Card -->
            <div class="investor-section glass-card">
              <div class="portfolio-header">
                <h2>📊 GNTV DIGITAL, ALL EVERYWHERE Shareholder Portfolio</h2>
                <span class="shares-badge">QUALIFIED INVESTOR</span>
              </div>

              <div class="portfolio-stats-row">
                <div class="p-stat">
                  <span class="p-lbl">Shares Owned</span>
                  <span class="p-val" id="user-shares-count">${userShares.shares.toLocaleString()} GNTV DIGITAL, ALL EVERYWHERE</span>
                </div>
                <div class="p-stat">
                  <span class="p-lbl">Current Valuation</span>
                  <span class="p-val" style="color: var(--brand-primary);">$${valuation.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})} USD</span>
                </div>
                <div class="p-stat">
                  <span class="p-lbl">Dividends Paid</span>
                  <span class="p-val" style="color: #10b981;">$${userShares.dividendPaid.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})} USD</span>
                </div>
              </div>

              <div style="height: 1px; background: rgba(255,255,255,0.06); margin: 16px 0;"></div>

              <div class="referral-row">
                <div style="flex: 1;">
                  <span class="p-lbl">Shareholder Affiliate Link</span>
                  <input type="text" class="ref-link-input" readonly value="https://gntv.com/investor?ref=AXMED252">
                </div>
                <div class="p-stat" style="text-align: right; min-width: 120px;">
                  <span class="p-lbl">Referral Income</span>
                  <span class="p-val" style="font-size: 16px; color: #f59e0b;">$${userShares.referrals.toLocaleString()} USD</span>
                </div>
              </div>
            </div>

            <!-- Share purchase checkout portal -->
            <div class="investor-section glass-card">
              <h3>⚡ Purchase Additional GNTV DIGITAL, ALL EVERYWHERE Shares</h3>
              <p class="section-desc">Instantly invest in GNTV DIGITAL, ALL EVERYWHERE shares. Active price is <strong>$1.85 USD / Share</strong>. Dividends distributed quarterly.</p>

              <form class="purchase-shares-form" id="form-buy-shares">
                <div class="form-group" style="flex: 1;">
                  <label for="buy-shares-amount">Amount of Shares</label>
                  <input type="number" id="buy-shares-amount" min="10" max="10000" value="500" required>
                </div>
                <div class="form-group" style="flex: 1;">
                  <label>Total Price (USD)</label>
                  <input type="text" id="buy-shares-cost" readonly value="$925.00 USD" style="background: rgba(0,0,0,0.25); font-weight: 700; color: white;">
                </div>
                <button type="submit" class="buy-shares-submit-btn">PROCEED TO CHECKOUT</button>
              </form>
            </div>

            <!-- Historical Dividends Yield Chart -->
            <div class="investor-section glass-card">
              <h3>📈 Valuation & Dividend Growth History</h3>
              <p class="section-desc">Real-time simulated chart detailing share valuation gains and dividend payout cycles.</p>
              <div class="investor-chart-wrapper">
                <canvas id="canvas-investor-chart" width="450" height="180"></canvas>
              </div>
            </div>

          </div>

          <!-- Right: Shareholder Motions Voting & Documents -->
          <div style="display: flex; flex-direction: column; gap: 20px;">

            <!-- Voting rights motion box -->
            <div class="investor-section glass-card">
              <h2>🗳️ Active Shareholder Resolutions</h2>
              <p class="section-desc">Cast votes on critical corporate decisions. Voting power is proportional to your share count.</p>

              <div class="resolutions-list">
                ${INVESTMENT_MOTIONS.map(motion => {
                  const hasVoted = userShares.motionsVoted && userShares.motionsVoted[motion.id];
                  const userVoteVal = hasVoted ? userShares.motionsVoted[motion.id] : null;

                  const tempYes = userVoteVal === "yes" ? motion.yesVotes + userShares.shares : motion.yesVotes;
                  const tempNo = userVoteVal === "no" ? motion.noVotes + userShares.shares : motion.noVotes;
                  const totalV = tempYes + tempNo;
                  const yesPct = Math.round((tempYes / totalV) * 100);
                  const noPct = Math.round((tempNo / totalV) * 100);

                  return `
                    <div class="resolution-card">
                      <h4 class="res-title">${motion.title}</h4>
                      <p class="res-desc">${motion.description}</p>

                      ${hasVoted ? `
                        <div class="vote-result-bars">
                          <div style="margin-bottom: 6px; font-size: 11px; color: rgba(255,255,255,0.6);">Your vote cast: <strong style="color:var(--brand-primary); text-transform:uppercase;">${userVoteVal}</strong></div>
                          <div class="vote-bar-row">
                            <span class="v-lbl">YES (${yesPct}%)</span>
                            <div class="v-bar-track"><div class="v-bar-fill yes" style="width: ${yesPct}%;"></div></div>
                            <span class="v-count">${tempYes.toLocaleString()} shares</span>
                          </div>
                          <div class="vote-bar-row">
                            <span class="v-lbl">NO (${noPct}%)</span>
                            <div class="v-bar-track"><div class="v-bar-fill no" style="width: ${noPct}%;"></div></div>
                            <span class="v-count">${tempNo.toLocaleString()} shares</span>
                          </div>
                        </div>
                      ` : `
                        <div class="vote-action-buttons" data-motion-id="${motion.id}">
                          <button class="vote-btn btn-yes" data-vote="yes">✔️ VOTE YES</button>
                          <button class="vote-btn btn-no" data-vote="no">✕ VOTE NO</button>
                        </div>
                      `}
                    </div>
                  `;
                }).join("")}
              </div>
            </div>

            <!-- Documents Shelf -->
            <div class="investor-section glass-card">
              <h2>📂 Audited Investor Documents</h2>
              <p class="section-desc">Download secure, official shareholder agreements, filing disclosures, and quarterly statements.</p>

              <div class="investor-docs-list">
                ${MOCK_DOCUMENTS.map(doc => `
                  <div class="investor-doc-row" data-title="${doc.title}">
                    <span class="doc-icon">📄</span>
                    <div style="flex: 1; min-width: 0;">
                      <div class="doc-title">${doc.title}</div>
                      <div class="doc-meta">${doc.type} • ${doc.size} • ${doc.date}</div>
                    </div>
                    <button class="doc-download-btn">📥</button>
                  </div>
                `).join("")}
              </div>
            </div>

          </div>

        </div>
      </div>
    `;

    // Calculate dynamic cost on buy form typing
    const amountInput = container.querySelector("#buy-shares-amount");
    const costInput = container.querySelector("#buy-shares-cost");
    if (amountInput && costInput) {
      amountInput.addEventListener("input", () => {
        const val = parseInt(amountInput.value, 10) || 0;
        const totalCost = val * 1.85;
        costInput.value = `$${totalCost.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})} USD`;
      });
    }

    // Buy shares form submit handler
    const buyForm = container.querySelector("#form-buy-shares");
    if (buyForm) {
      buyForm.addEventListener("submit", (e) => {
        e.preventDefault();
        const amt = parseInt(amountInput.value, 10);
        if (amt > 0) {
          store.purchaseShares(amt);
          alert(`Success: You purchased ${amt.toLocaleString()} GNTV DIGITAL, ALL EVERYWHERE shares! Portfolio updated.`);
          renderPortal();
        }
      });
    }

    // Resolution voting click handlers
    container.querySelectorAll(".vote-action-buttons").forEach(bar => {
      const motionId = bar.getAttribute("data-motion-id");
      bar.querySelectorAll(".vote-btn").forEach(btn => {
        btn.addEventListener("click", () => {
          const vote = btn.getAttribute("data-vote");
          store.submitShareVote(motionId, vote);
          alert(`Cast shareholder vote: "${vote.toUpperCase()}" registered.`);
          renderPortal();
        });
      });
    });

    // Document download simulator
    container.querySelectorAll(".investor-doc-row").forEach(row => {
      row.addEventListener("click", () => {
        const title = row.getAttribute("data-title");
        alert(`Downloading file: "${title}" in PDF format. Secure connection established!`);
      });
    });

    // Render Canvas growth chart
    const chartCanvas = container.querySelector("#canvas-investor-chart");
    if (chartCanvas) {
      drawInvestmentChart(chartCanvas);
    }
  };

  const drawInvestmentChart = (canvas) => {
    const ctx = canvas.getContext("2d");
    const w = canvas.width = 450;
    const h = canvas.height = 180;
    let frame = 0;

    const dataPoints = [80, 85, 95, 110, 125, 140, 160, 185]; // representing $1.85 price growth from $0.80 cents
    const labels = ["Q3-24", "Q4-24", "Q1-25", "Q2-25", "Q3-25", "Q4-25", "Q1-26", "LATEST"];

    const loop = () => {
      ctx.clearRect(0, 0, w, h);

      // Draw background chart grid
      ctx.strokeStyle = "rgba(255,255,255,0.02)";
      ctx.lineWidth = 1;
      for (let y = 30; y < h - 20; y += 30) {
        ctx.beginPath(); ctx.moveTo(30, y); ctx.lineTo(w - 20, y); ctx.stroke();
      }

      // Draw Axes
      ctx.strokeStyle = "rgba(255,255,255,0.1)";
      ctx.beginPath();
      ctx.moveTo(30, 10); ctx.lineTo(30, h - 20); ctx.lineTo(w - 10, h - 20);
      ctx.stroke();

      // Coordinates generator
      const paddingX = 40;
      const spacingX = (w - 70) / (dataPoints.length - 1);
      const points = dataPoints.map((dp, idx) => {
        const x = paddingX + idx * spacingX;
        const normY = (dp - 50) / 150; // normalize
        const y = h - 20 - normY * (h - 40);
        return { x, y };
      });

      // Renders connection line
      ctx.strokeStyle = "var(--brand-primary)";
      ctx.lineWidth = 3;
      ctx.beginPath();
      points.forEach((p, idx) => {
        if (idx === 0) ctx.moveTo(p.x, p.y);
        else ctx.lineTo(p.x, p.y);
      });
      ctx.stroke();

      // Draw shaded area
      const gradient = ctx.createLinearGradient(0, 0, 0, h);
      gradient.addColorStop(0, "var(--brand-primary-glow)");
      gradient.addColorStop(1, "rgba(255, 42, 75, 0)");
      ctx.fillStyle = gradient;
      ctx.beginPath();
      ctx.moveTo(points[0].x, h - 20);
      points.forEach(p => ctx.lineTo(p.x, p.y));
      ctx.lineTo(points[points.length - 1].x, h - 20);
      ctx.closePath();
      ctx.fill();

      // Draw points & labels
      points.forEach((p, idx) => {
        ctx.fillStyle = "#ffffff";
        ctx.beginPath(); ctx.arc(p.x, p.y, 4, 0, 2 * Math.PI); ctx.fill();

        ctx.fillStyle = "rgba(255,255,255,0.5)";
        ctx.font = "9px monospace";
        ctx.textAlign = "center";
        ctx.fillText(labels[idx], p.x, h - 6);

        // Highlight value on hover simulation
        if (idx === dataPoints.length - 1) {
          ctx.fillStyle = "var(--brand-primary)";
          ctx.font = "10px sans-serif";
          ctx.fillText(`$${(dataPoints[idx]/100).toFixed(2)}`, p.x, p.y - 10);
        }
      });

      frame++;
      animFrame = requestAnimationFrame(loop);
    };

    loop();
  };

  renderPortal();

  return () => {
    if (animFrame) cancelAnimationFrame(animFrame);
  };
}
