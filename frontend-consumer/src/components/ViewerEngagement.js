import { store } from "../../../shared/src/state.js";
import { initLiveChatOverlay } from "./LiveChatOverlay.js";

export function initViewerEngagement(container) {
  container.innerHTML = `
    <div class="engagement-grid">

      <!-- Live Audience Chat -->
      <div class="engagement-section glass-card chat-panel">
        <div class="panel-header">
          <h2 class="section-title"><span class="icon">💬</span> Live Audience Chat</h2>
          <span class="chat-count-badge" id="chat-count">14,500 Viewers</span>
        </div>

        <div class="chat-feed-wrapper" id="chat-feed">
          <!-- Comments rendered dynamically -->
        </div>

        <!-- Producer Input Console -->
        <form class="chat-input-row" id="form-chat-send">
          <input type="text" class="chat-txt" id="input-chat-text" placeholder="Send official broadcast message as PRODUCER..." required>
          <button type="submit" class="chat-send-btn">SEND</button>
        </form>
      </div>

      <!-- Interactive Polling Widget -->
      <div class="engagement-section glass-card polling-panel">
        <h2 class="section-title"><span class="icon">🗳️</span> Live Audience Polling</h2>
        <p class="section-desc">Deploy quick surveys to engage your streaming audience. Results update in real-time.</p>

        <div class="poll-widget-wrapper" id="poll-widget">
          <!-- Rendered dynamically -->
        </div>

        <!-- Producer Custom Poll Creator -->
        <div class="poll-creator-wrapper">
          <h3>Deploy Custom Audience Poll</h3>
          <form class="poll-creator-form" id="form-create-poll">
            <input type="text" class="creator-input" id="poll-question" placeholder="Enter poll question..." required>

            <div class="creator-options-row">
              <input type="text" class="creator-input-opt" id="poll-opt1" placeholder="Option 1" required>
              <input type="text" class="creator-input-opt" id="poll-opt2" placeholder="Option 2" required>
            </div>

            <div class="creator-options-row">
              <input type="text" class="creator-input-opt" id="poll-opt3" placeholder="Option 3 (Optional)">
              <input type="text" class="creator-input-opt" id="poll-opt4" placeholder="Option 4 (Optional)">
            </div>

            <button type="submit" class="poll-deploy-btn">DEPLOY POLL</button>
          </form>
        </div>
      </div>

    </div>
  `;

  const chatFeed = container.querySelector("#chat-feed");
  const pollWidget = container.querySelector("#poll-widget");
  const pollForm = container.querySelector("#form-create-poll");

  // Mount real backend WS & REST LiveChatOverlay component into chat feed
  const chatCleanup = initLiveChatOverlay(chatFeed, { roomId: "default-room" });
  store.subscribe("chatMessages", (messages) => {
    chatFeed.innerHTML = messages.map(msg => {
      const isProducer = msg.user === "PRODUCER [GNTV DIGITAL, ALL EVERYWHERE]";
      return `
        <div class="chat-message ${isProducer ? 'producer-msg' : ''}">
          <span class="chat-user">${msg.user}</span>
          <span class="chat-text">${msg.text}</span>
        </div>
      `;
    }).join("");

    // Auto-scroll chat to bottom
    chatFeed.scrollTop = chatFeed.scrollHeight;
  });

  // Listener for viewer counts in chat panel header
  store.subscribe("viewerCount", (count) => {
    chatViewerCount.textContent = `${count.toLocaleString()} Viewers`;
  });

  // Handle Producer sending official chat
  chatForm.addEventListener("submit", (e) => {
    e.preventDefault();
    const txt = chatInput.value.trim();
    if (txt) {
      store.addChatMessage("PRODUCER [GNTV DIGITAL, ALL EVERYWHERE]", txt);
      chatInput.value = "";
    }
  });

  // 2. Subscribe to active poll changes and handle voting
  store.subscribe("activePoll", (poll) => {
    if (!poll) return;

    const totalVotes = (poll.votes || []).reduce((a, b) => a + b, 0) || 1;

    pollWidget.innerHTML = `
      <div class="active-poll-card">
        <h3 class="poll-question-txt">📊 ${poll.question}</h3>

        <div class="poll-options-list">
          ${poll.options.map((opt, idx) => {
            const votesCount = poll.votes[idx] || 0;
            const pct = Math.round((votesCount / totalVotes) * 100);

            return `
              <button class="poll-option-row" data-opt-idx="${idx}">
                <div class="poll-option-fill" style="width: ${pct}%"></div>
                <div class="poll-option-content">
                  <span class="opt-label">${opt}</span>
                  <span class="opt-stats">${votesCount.toLocaleString()} votes (${pct}%)</span>
                </div>
              </button>
            `;
          }).join("")}
        </div>
        <div class="poll-total-votes">Total Simulated Casts: ${totalVotes.toLocaleString()}</div>
      </div>
    `;

    // Hook up option buttons to record votes
    const optionRows = pollWidget.querySelectorAll(".poll-option-row");
    optionRows.forEach(row => {
      row.addEventListener("click", () => {
        const idx = parseInt(row.getAttribute("data-opt-idx"), 10);
        store.submitPollVote(idx);
        row.classList.add("voted");
        // Disable subsequent clicks
        optionRows.forEach(btn => btn.disabled = true);
      });
    });
  });

  // Handle Producer deploying brand new custom poll
  pollForm.addEventListener("submit", (e) => {
    e.preventDefault();
    const q = container.querySelector("#poll-question").value.trim();
    const opt1 = container.querySelector("#poll-opt1").value.trim();
    const opt2 = container.querySelector("#poll-opt2").value.trim();
    const opt3 = container.querySelector("#poll-opt3").value.trim();
    const opt4 = container.querySelector("#poll-opt4").value.trim();

    const opts = [opt1, opt2];
    if (opt3) opts.push(opt3);
    if (opt4) opts.push(opt4);

    store.deployNewPoll(q, opts);
    pollForm.reset();
    alert("New custom audience poll successfully deployed across the broadcasting node!");
  });
}
