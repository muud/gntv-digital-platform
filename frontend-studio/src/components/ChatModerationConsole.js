import "./ChatModerationConsole.css";

function readEnv(name) {
  try {
    if (typeof import.meta !== "undefined" && import.meta.env && import.meta.env[name]) {
      return import.meta.env[name];
    }
  } catch {
    /* import.meta unavailable */
  }
  if (typeof process !== "undefined" && process.env) {
    return process.env[name] || "";
  }
  return "";
}

function apiBase() {
  return (readEnv("VITE_CHAT_API_URL") || "http://localhost:8000/api/v1/chat").replace(/\/$/, "");
}

function wsBase() {
  const explicit = readEnv("VITE_CHAT_WS_URL");
  if (explicit) return explicit.replace(/\/$/, "");
  return "ws://localhost:8000/ws/chat";
}

function authToken() {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage.getItem("gntv.auth.token") || window.localStorage.getItem("token") || null;
  } catch {
    return null;
  }
}

function authHeaders() {
  const token = authToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

function chatWsUrl(roomId) {
  const token = authToken();
  const query = token ? `?token=${encodeURIComponent(token)}` : "";
  return `${wsBase()}/${encodeURIComponent(roomId)}${query}`;
}

const ACTION_LABEL = {
  delete_message: "Delete message",
  mute_user: "Mute user",
  ban_user: "Ban user",
};

/**
 * Vanilla JS Studio Chat Moderation Console component.
 * Success messages render ONLY after backend REST responses succeed.
 */
export function initChatModerationConsole(container, options = {}) {
  const roomId = options.roomId || "default-room";

  let socket = null;
  let wsState = "disconnected";
  let messages = [];
  let notices = [];
  let rules = [];
  let rulesErr = "";
  let actionOk = "";
  let actionErr = "";
  let ruleOk = "";
  let pendingAction = null; // { action, message }

  container.innerHTML = `
    <div class="gntv-mod">
      <!-- Live Feed Section -->
      <section class="gntv-mod__panel" aria-label="Live chat feed">
        <h2>Live feed — <span id="mod-room-id">${escapeHTML(roomId)}</span></h2>
        <p class="gntv-mod__status" id="mod-ws-status" role="status" aria-live="assertive">
          Connection: disconnected
        </p>

        <div id="mod-action-alerts"></div>

        <ol class="gntv-mod__feed" id="mod-feed-list">
          <p class="gntv-mod__status">Connecting to live message stream…</p>
        </ol>
      </section>

      <!-- Moderation Rules Section -->
      <section class="gntv-mod__panel" aria-label="Moderation rules">
        <h2>Moderation rules</h2>
        <div id="mod-rules-container">
          <p class="gntv-mod__status">Loading moderation rules…</p>
        </div>

        <form class="gntv-mod__form" id="mod-rule-form" style="margin-top: 1rem;">
          <h3>Add New Moderation Rule</h3>
          <input
            id="rule-pattern"
            class="gntv-mod__input"
            placeholder="Regex pattern (e.g. \\bspam\\b)"
            required
          />
          <select id="rule-action" class="gntv-mod__select">
            <option value="block">block</option>
            <option value="flag">flag</option>
            <option value="mute">mute</option>
          </select>
          <button type="submit" class="gntv-mod__btn gntv-mod__btn--primary" id="btn-create-rule">
            Create rule
          </button>
          <div id="mod-rule-feedback"></div>
        </form>
      </section>
    </div>
  `;

  const wsStatusEl = container.querySelector("#mod-ws-status");
  const feedListEl = container.querySelector("#mod-feed-list");
  const actionAlertsEl = container.querySelector("#mod-action-alerts");
  const rulesContainerEl = container.querySelector("#mod-rules-container");
  const ruleFormEl = container.querySelector("#mod-rule-form");
  const rulePatternInput = container.querySelector("#rule-pattern");
  const ruleActionSelect = container.querySelector("#rule-action");
  const ruleFeedbackEl = container.querySelector("#mod-rule-feedback");

  function escapeHTML(str) {
    if (!str) return "";
    return str
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  const renderStatus = () => {
    wsStatusEl.textContent = `Connection: ${wsState}`;
  };

  const renderActionAlerts = () => {
    let html = "";
    if (actionOk) {
      html += `<p class="gntv-mod__ok" role="status">${escapeHTML(actionOk)}</p>`;
    }
    if (actionErr) {
      html += `<p class="gntv-mod__err" role="alert">${escapeHTML(actionErr)}</p>`;
    }
    actionAlertsEl.innerHTML = html;
  };

  const renderFeed = () => {
    if (messages.length === 0) {
      feedListEl.innerHTML = `<p class="gntv-mod__status">No messages received yet.</p>`;
      return;
    }

    feedListEl.innerHTML = "";
    const fragment = document.createDocumentFragment();

    messages.forEach(m => {
      const li = document.createElement("li");
      li.className = `gntv-mod__msg${m.flagged ? " is-flagged" : ""}`;

      const meta = document.createElement("p");
      meta.className = "gntv-mod__meta";

      const userSpan = document.createElement("span");
      userSpan.className = "gntv-mod__user";
      userSpan.textContent = m.username || "User";

      const timeEl = document.createElement("time");
      timeEl.textContent = new Date(m.created_at || Date.now()).toLocaleTimeString();

      meta.appendChild(userSpan);
      meta.appendChild(timeEl);

      if (m.flagged) {
        const flagSpan = document.createElement("span");
        flagSpan.style.color = "#eab308";
        flagSpan.textContent = " Flagged";
        meta.appendChild(flagSpan);
      }

      li.appendChild(meta);

      const bodyP = document.createElement("p");
      bodyP.className = "gntv-mod__body";
      bodyP.textContent = m.deleted ? "Message removed." : (m.text || m.message_text || m.body || "");
      li.appendChild(bodyP);

      const actionsDiv = document.createElement("div");
      actionsDiv.className = "gntv-mod__actions";

      const deleteBtn = document.createElement("button");
      deleteBtn.type = "button";
      deleteBtn.className = "gntv-mod__btn";
      deleteBtn.textContent = "Delete";
      deleteBtn.disabled = m.deleted;
      deleteBtn.addEventListener("click", () => startAction("delete_message", m));

      const muteBtn = document.createElement("button");
      muteBtn.type = "button";
      muteBtn.className = "gntv-mod__btn";
      muteBtn.textContent = "Mute";
      muteBtn.addEventListener("click", () => startAction("mute_user", m));

      const banBtn = document.createElement("button");
      banBtn.type = "button";
      banBtn.className = "gntv-mod__btn";
      banBtn.textContent = "Ban";
      banBtn.addEventListener("click", () => startAction("ban_user", m));

      actionsDiv.appendChild(deleteBtn);
      actionsDiv.appendChild(muteBtn);
      actionsDiv.appendChild(banBtn);
      li.appendChild(actionsDiv);

      // Inline Confirmation Form if pending on this message
      if (pendingAction && pendingAction.message.id === m.id) {
        const confirmForm = document.createElement("form");
        confirmForm.className = "gntv-mod__confirm";
        confirmForm.innerHTML = `
          <input
            id="mod-reason-input"
            class="gntv-mod__input"
            placeholder="Reason for ${ACTION_LABEL[pendingAction.action].toLowerCase()} (required)"
            required
          />
          ${pendingAction.action !== "delete_message" ? `
            <input
              id="mod-duration-input"
              class="gntv-mod__input"
              type="number"
              min="1"
              max="86400"
              placeholder="Duration in seconds (e.g. 300)"
            />
          ` : ""}
          <div class="gntv-mod__actions">
            <button type="submit" class="gntv-mod__btn gntv-mod__btn--primary" id="btn-confirm-action">
              Confirm ${ACTION_LABEL[pendingAction.action]}
            </button>
            <button type="button" class="gntv-mod__btn" id="btn-cancel-action">
              Cancel
            </button>
          </div>
        `;

        confirmForm.querySelector("#btn-cancel-action").addEventListener("click", () => {
          pendingAction = null;
          renderFeed();
        });

        confirmForm.addEventListener("submit", async (e) => {
          e.preventDefault();
          const reasonVal = confirmForm.querySelector("#mod-reason-input").value.trim();
          const durationEl = confirmForm.querySelector("#mod-duration-input");
          const durationVal = durationEl ? parseInt(durationEl.value, 10) : null;

          if (!reasonVal) return;

          const submitBtn = confirmForm.querySelector("#btn-confirm-action");
          submitBtn.disabled = true;
          submitBtn.textContent = "Submitting…";

          actionOk = "";
          actionErr = "";

          try {
            const payload = {
              action: pendingAction.action,
              reason: reasonVal,
            };
            if (pendingAction.action === "delete_message") {
              payload.target_message_id = pendingAction.message.id;
            } else {
              payload.target_user_id = pendingAction.message.user_id || 1;
            }
            if (durationVal && pendingAction.action !== "delete_message") {
              payload.duration_seconds = durationVal;
            }

            const res = await fetch(`${apiBase()}/rooms/${encodeURIComponent(roomId)}/moderation/action`, {
              method: "POST",
              headers: {
                "Content-Type": "application/json",
                ...authHeaders(),
              },
              body: JSON.stringify(payload),
            });

            if (!res.ok) {
              const body = await res.json().catch(() => ({}));
              throw new Error(body.detail || body.message || `HTTP ${res.status}`);
            }

            actionOk = `${ACTION_LABEL[pendingAction.action]} confirmed by the backend.`;
            if (pendingAction.action === "delete_message") {
              m.deleted = true;
            }
            pendingAction = null;
          } catch (e) {
            actionErr = e.message || "Moderation action failed.";
          } finally {
            renderActionAlerts();
            renderFeed();
          }
        });

        li.appendChild(confirmForm);
      }

      fragment.appendChild(li);
    });

    feedListEl.appendChild(fragment);
  };

  const startAction = (action, message) => {
    pendingAction = { action, message };
    actionOk = "";
    actionErr = "";
    renderActionAlerts();
    renderFeed();
  };

  const renderRules = () => {
    if (rulesErr) {
      rulesContainerEl.innerHTML = `<p class="gntv-mod__err" role="alert">${escapeHTML(rulesErr)}</p>`;
      return;
    }
    if (rules.length === 0) {
      rulesContainerEl.innerHTML = `<p class="gntv-mod__status">No moderation rules configured.</p>`;
      return;
    }

    rulesContainerEl.innerHTML = `
      <ul class="gntv-mod__rules">
        ${rules.map(r => `
          <li class="gntv-mod__rule">
            <strong>${escapeHTML(r.pattern)}</strong> → ${escapeHTML(r.action)}
            ${r.reason ? ` · ${escapeHTML(r.reason)}` : ""}
          </li>
        `).join("")}
      </ul>
    `;
  };

  const loadRules = async () => {
    try {
      const res = await fetch(`${apiBase()}/rooms/${encodeURIComponent(roomId)}/moderation/rules`, {
        headers: authHeaders(),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      rules = Array.isArray(data) ? data : (data.rules || []);
      rulesErr = "";
    } catch (e) {
      rulesErr = e.message || "Failed to load moderation rules.";
    } finally {
      renderRules();
    }
  };

  const createRule = async (pattern, action) => {
    ruleOk = "";
    ruleFeedbackEl.innerHTML = "";

    const btn = container.querySelector("#btn-create-rule");
    btn.disabled = true;
    btn.textContent = "Creating…";

    try {
      const res = await fetch(`${apiBase()}/rooms/${encodeURIComponent(roomId)}/moderation/rules`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...authHeaders(),
        },
        body: JSON.stringify({
          pattern,
          match_type: "regex",
          action,
        }),
      });

      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || body.message || `HTTP ${res.status}`);
      }

      const created = await res.json();
      rules.push(created);
      ruleOk = "Rule successfully created in backend.";
      rulePatternInput.value = "";
      renderRules();
      ruleFeedbackEl.innerHTML = `<p class="gntv-mod__ok">${escapeHTML(ruleOk)}</p>`;
    } catch (e) {
      ruleFeedbackEl.innerHTML = `<p class="gntv-mod__err">${escapeHTML(e.message || "Could not create rule.")}</p>`;
    } finally {
      btn.disabled = false;
      btn.textContent = "Create rule";
    }
  };

  ruleFormEl.addEventListener("submit", (e) => {
    e.preventDefault();
    const pattern = rulePatternInput.value.trim();
    const action = ruleActionSelect.value;
    if (pattern) {
      createRule(pattern, action);
    }
  });

  const connectWS = () => {
    wsState = "connecting";
    renderStatus();

    try {
      socket = new WebSocket(chatWsUrl(roomId));
    } catch {
      wsState = "error";
      renderStatus();
      return;
    }

    socket.onopen = () => {
      wsState = "connected";
      renderStatus();
    };

    socket.onmessage = (event) => {
      if (typeof event.data !== "string") return;
      try {
        const frame = JSON.parse(event.data);
        if (frame.type === "chat_message" || frame.type === "message") {
          const item = frame.data || frame;
          const msg = {
            id: item.id || `msg-${Date.now()}`,
            user_id: item.user_id || 1,
            username: item.username || "User",
            text: item.text || item.message_text || item.body || "",
            created_at: item.created_at || new Date().toISOString(),
            status: item.status || "published",
            flagged: item.status === "flagged",
            deleted: item.status === "deleted"
          };
          messages.push(msg);
          if (messages.length > 200) messages.shift();
          renderFeed();
        } else if (frame.type === "moderation_notice") {
          if (frame.action === "message_deleted" && frame.target_msg_id) {
            messages = messages.map(m => (m.id === frame.target_msg_id ? { ...m, deleted: true } : m));
            renderFeed();
          }
        }
      } catch {
        /* ignore invalid JSON */
      }
    };

    socket.onclose = () => {
      wsState = "disconnected";
      renderStatus();
    };
  };

  loadRules();
  connectWS();

  return () => {
    if (socket) {
      socket.onclose = null;
      socket.onmessage = null;
      if (socket.readyState <= WebSocket.OPEN) {
        socket.close(1000, "Studio unmounted");
      }
    }
    container.innerHTML = "";
  };
}
