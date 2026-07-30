import { store } from "../../../shared/src/state.js";
import { VODS, CHANNELS, MOCK_SHORTS } from "../../../shared/src/utils/mockData.js";

export function initAIAssistant(container) {
  let isOpen = false;
  let chatHistory = [
    { sender: "assistant", text: "Maanta barasho wacan! Halkan waa Kaaliyaha GNTV DIGITAL, ALL EVERYWHERE AI. Sideen kuugu caawin karaa? (Welcome! I am your GNTV DIGITAL, ALL EVERYWHERE AI Assistant. How can I help you today?)" }
  ];

  const renderAssistant = () => {
    container.innerHTML = `
      <!-- Floating Action Button -->
      <button class="ai-fab-btn" id="btn-ai-fab">
        <span class="ai-fab-icon">${isOpen ? '✕' : '🤖'}</span>
        <span class="ai-fab-badge" style="display: ${chatHistory.length === 1 ? 'block' : 'none'};">1</span>
      </button>

      <!-- Glassmorphic Chat Panel -->
      <div class="ai-chat-panel glass-card ${isOpen ? 'active' : ''}">
        <div class="chat-panel-header">
          <div style="display: flex; align-items: center; gap: 8px;">
            <span class="brain-pulsing-icon">🧠</span>
            <div>
              <div class="panel-title">GNTV DIGITAL, ALL EVERYWHERE AI Assistant</div>
              <span class="panel-status">ONLINE // MULTILINGUAL</span>
            </div>
          </div>
          <button class="chat-minimize-btn" id="btn-ai-minimize">━</button>
        </div>

        <div class="chat-messages-box" id="ai-chat-box">
          ${chatHistory.map(msg => `
            <div class="chat-bubble-row ${msg.sender}">
              <div class="chat-bubble">
                <span class="bubble-sender">${msg.sender === 'assistant' ? '🤖 GNTV DIGITAL, ALL EVERYWHERE AI' : '👤 You'}</span>
                <p class="bubble-text">${msg.text}</p>
                ${msg.actionsHTML ? `<div class="bubble-actions">${msg.actionsHTML}</div>` : ''}
              </div>
            </div>
          `).join("")}
        </div>

        <form class="chat-input-form" id="form-ai-chat">
          <input type="text" id="input-ai-txt" placeholder="Weydii GNTV DIGITAL, ALL EVERYWHERE AI (e.g. Find news on Ruto)..." required autocomplete="off">
          <button type="submit" class="ai-send-btn">SEND</button>
        </form>
      </div>
    `;

    // FAB click toggle
    container.querySelector("#btn-ai-fab").addEventListener("click", () => {
      isOpen = !isOpen;
      renderAssistant();
    });

    container.querySelector("#btn-ai-minimize").addEventListener("click", () => {
      isOpen = false;
      renderAssistant();
    });

    // Form submission
    const form = container.querySelector("#form-ai-chat");
    const input = container.querySelector("#input-ai-txt");
    const chatBox = container.querySelector("#ai-chat-box");

    // Scroll to bottom
    if (chatBox) chatBox.scrollTop = chatBox.scrollHeight;

    if (form) {
      form.addEventListener("submit", (e) => {
        e.preventDefault();
        const text = input.value.trim();
        if (!text) return;

        // Add user msg
        chatHistory.push({ sender: "user", text });
        input.value = "";
        renderAssistant();

        // Process response with simulated thinking delay
        setTimeout(() => {
          generateAIResponse(text);
        }, 800);
      });
    }
  };

  const generateAIResponse = (query) => {
    const low = query.toLowerCase();
    let responseText = "";
    let actionsHTML = "";

    // 🛡️ SECURITY FIREWALL: Prevent Prompt Injections, Jailbreaks, and Data Leakage
    const blocklist = [
      "ignore previous instructions", "system prompt", "jailbreak", "bypass",
      "leak data", "passwords", "database", "sql injection", "drop table",
      "api key", "secret", "hack", "override"
    ];

    const isAttackDetected = blocklist.some(term => low.includes(term));
    if (isAttackDetected) {
      responseText = "⚠️ SECURITY ALERT: Malicious prompt injection or data leakage attempt detected. Request blocked by GNTV DIGITAL, ALL EVERYWHERE AI Security Firewall.";
      chatHistory.push({ sender: "assistant", text: responseText, actionsHTML: "" });
      renderAssistant();
      return;
    }

    // Keyword parser
    const isSomali = low.includes("hel") || low.includes("so") || low.includes("dhaqan") || low.includes("wararkii");
    const isRuto = low.includes("ruto") || low.includes("kenya") || low.includes("politics");
    const isWater = low.includes("water") || low.includes("wabiga") || low.includes("borehole") || low.includes("ceel");
    const isHistory = low.includes("history") || low.includes("taariikh") || low.includes("saylac") || low.includes("ajuuraan");
    const isSports = low.includes("sports") || low.includes("soccer") || low.includes("cayaar") || low.includes("kubbadda");

    if (isRuto) {
      responseText = isSomali
        ? "Waxaan helay 1 barnaamij gaar ah oo ku saabsan madaxweyne Ruto iyo arrimaha ganacsiga Afrika:"
        : "I found a political briefing short featuring President William Ruto regarding East African trade:";

      const rutoShort = MOCK_SHORTS[0];
      actionsHTML = `<button class="ai-action-link" data-action="shorts" data-id="${rutoShort.id}">📱 Watch: ${rutoShort.title}</button>`;
    }
    else if (isWater) {
      responseText = isSomali
        ? "Waa kuwan warbixinnada ku saabsan wabiyada iyo biyaha gobolka waqooyi bariga Kenya:"
        : "Here is the active broadcast feed covering the water borehole system launching in Northern Kenya:";

      actionsHTML = `<button class="ai-action-link" data-action="channel" data-id="wajir-tv">🌴 Wajir County TV (Borehole Project news)</button>`;
    }
    else if (isHistory) {
      responseText = isSomali
        ? "Muuqaalkan taariikhiga ah wuxuu ka hadlayaa boqortooyooyinkii hore ee Saylac iyo Saldanadda Ajuuraan:"
        : "This documentary details the ancient history of Saylac and Berbera ports:";

      actionsHTML = `<button class="ai-action-link" data-action="vod" data-id="vod7">📼 Play: Diiwaanka Geeska Originals</button>`;
    }
    else if (isSports) {
      responseText = isSomali
        ? "Waa kuwan ciyaarihii kubbadda cagta ee ugu dambeeyay ee laga baahiyay GNTV DIGITAL, ALL EVERYWHERE:"
        : "I found the local East African football tournament highlights on demand:";

      actionsHTML = `<button class="ai-action-link" data-action="vod" data-id="vod9">⚽ Play Highlights: Koobka Kubadda Geeska Afrika</button>`;
    }
    else if (low.includes("summarize") || low.includes("koob")) {
      responseText = isSomali
        ? "Halkan waa koobidda filimka 'Taariikhda Geeska Afrika' (3 qodob):\n1. Saldanaddii Ajuuraan iyo Saylac xeebaha.\n2. Wadooyinka ganacsiga badda Hindiya.\n3. Saamaynta ilbaxnimada casriga ah."
        : "GNTV DIGITAL, ALL EVERYWHERE AI Summary of 'Taariikhda Geeska Afrika':\n• Explores Ajuran Sultanate and Zeila coastal port trades.\n• Outlines early Indian Ocean maritime commerce routes.\n• Details cultural preservation across modern East African cities.";
    }
    else if (low.includes("translate") || low.includes("turjum")) {
      responseText = isSomali
        ? "Turjumaad (Somali to English):\n'Fadlan GNTV DIGITAL, ALL EVERYWHERE kala soco wararkii ugu dambeeyay' ➔ 'Please follow the latest news updates on GNTV DIGITAL, ALL EVERYWHERE.'"
        : "AI Translation (English to Somali):\n'Welcome to GNTV DIGITAL, ALL EVERYWHERE AI Anchor Desk' ➔ 'Ku soo dhawaada miiska AI Anchor ee GNTV DIGITAL, ALL EVERYWHERE.'";
    }
    else {
      // Default fallback helper
      responseText = isSomali
        ? "Waan ku caawin karaa inaan kuu raadiyo filimada, ku siiyo koobitaan degdeg ah, ama aan ku turjumo wararka. Isku day inaad qorto: 'Ruto', 'Water', ama 'History'."
        : "I can search our OTT database, summarize video clips, or perform multilingual translations. Try searching for 'Ruto', 'Water', or 'History'.";
    }

    chatHistory.push({ sender: "assistant", text: responseText, actionsHTML });
    renderAssistant();

    // Attach click events on the response actions links to trigger redirection
    const containerEl = document.querySelector("#gntv-ai-assistant-container");
    if (containerEl) {
      containerEl.querySelectorAll(".ai-action-link").forEach(btn => {
        btn.addEventListener("click", () => {
          const action = btn.getAttribute("data-action");
          const id = btn.getAttribute("data-id");

          if (action === "shorts") {
            store.setState("activeTab", "shorts");
          } else if (action === "channel") {
            const ch = CHANNELS.find(c => c.id === id);
            if (ch) {
              store.setState("activeChannel", ch);
              store.setState("activeCamera", ch.cameras[0]);
              store.setState("activeTab", "dashboard");
            }
          } else if (action === "vod") {
            store.setState("activeTab", "vod");
          }

          isOpen = false;
          renderAssistant();
        });
      });
    }
  };

  renderAssistant();
}
