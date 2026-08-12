import "./LiveChatOverlay.css";
import { AccessibilityAnnouncer } from "../utils/accessibilityAnnouncer.js";
import { SpatialNavigationManager } from "../utils/spatialNavigation.js";

const MAX_PAYLOAD_BYTES = 4096;
const MAX_RETRIES = 6;
const BASE_DELAY_MS = 1000;
const MAX_DELAY_MS = 20000;
const MAX_RENDERED = 300;

const STATE_LABEL = {
  connecting: "Connecting to chat…",
  connected: "Live",
  reconnecting: "Reconnecting…",
  disconnected: "Disconnected",
  error: "Chat unavailable",
};

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

function chatWsUrl(roomId) {
  const token = authToken();
  const query = token ? `?token=${encodeURIComponent(token)}` : "";
  return `${wsBase()}/${encodeURIComponent(roomId)}${query}`;
}

function authHeaders() {
  const token = authToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

function byteLength(value) {
  return new TextEncoder().encode(value).length;
}

function formatTime(iso) {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

/**
 * Vanilla JS Component for Live Chat Overlay.
 * Mounts as a sibling component without altering video/player elements.
 */
export function initLiveChatOverlay(container, options = {}) {
  const roomId = options.roomId || "default-room";
  const onClose = options.onClose || null;
  const className = options.className || "";

  let state = "disconnected";
  let messages = [];
  let notices = [];
  let roomState = "active";
  let cooldownSeconds = 0;
  let errorMessage = null;
  let historyError = null;
  let loadingHistory = false;
  let nextBeforeId = null;
  let hasMore = false;
  let muted = false;
  let banned = false;
  let retriesExhausted = false;

  let socket = null;
  let retryCount = 0;
  let reconnectTimer = null;
  let cooldownTimer = null;
  let closedByUs = false;

  // Render Skeleton Layout
  container.innerHTML = `
    <aside className="gntv-chat ${className}".trim() aria-label="Live chat" data-state="disconnected">
      <header class="gntv-chat__header">
        <div class="gntv-chat__title">
          <span class="gntv-chat__dot gntv-chat__dot--disconnected" id="gntv-chat-dot" aria-hidden="true"></span>
          <h2>Live chat</h2>
        </div>
        <p class="gntv-chat__status" id="gntv-chat-status" role="status" aria-live="assertive">
          Disconnected
        </p>
        ${onClose ? `<button type="button" class="gntv-chat__close" id="gntv-chat-close" aria-label="Close live chat">×</button>` : ""}
      </header>

      <div id="gntv-chat-alert-container"></div>
      <ul class="gntv-chat__notices" id="gntv-chat-notices" aria-live="assertive"></ul>

      <div class="gntv-chat__scroll" id="gntv-chat-scroll">
        <div id="gntv-chat-earlier-container"></div>
        <ol class="gntv-chat__list" id="gntv-chat-list"></ol>
      </div>

      <p class="gntv-chat__sr" id="gntv-chat-sr" aria-live="polite"></p>

      <form class="gntv-chat__composer" id="gntv-chat-composer">
        <label class="gntv-chat__sr" for="gntv-chat-input">Write a chat message</label>
        <textarea
          id="gntv-chat-input"
          rows="2"
          placeholder="Say something…"
        ></textarea>
        <div class="gntv-chat__composer-row">
          <span class="gntv-chat__count" id="gntv-chat-count">0/${MAX_PAYLOAD_BYTES} bytes</span>
          <button type="submit" class="gntv-chat__send" id="gntv-chat-send">Send</button>
        </div>
      </form>
    </aside>
  `;

  const dotEl = container.querySelector("#gntv-chat-dot");
  const statusEl = container.querySelector("#gntv-chat-status");
  const closeBtn = container.querySelector("#gntv-chat-close");
  const alertContainer = container.querySelector("#gntv-chat-alert-container");
  const noticesEl = container.querySelector("#gntv-chat-notices");
  const scrollEl = container.querySelector("#gntv-chat-scroll");
  const earlierContainer = container.querySelector("#gntv-chat-earlier-container");
  const listEl = container.querySelector("#gntv-chat-list");
  const srEl = container.querySelector("#gntv-chat-sr");
  const composerForm = container.querySelector("#gntv-chat-composer");
  const textInput = container.querySelector("#gntv-chat-input");
  const countEl = container.querySelector("#gntv-chat-count");
  const sendBtn = container.querySelector("#gntv-chat-send");

  if (closeBtn && onClose) {
    closeBtn.addEventListener("click", onClose);
  }

  const updateHeaderState = () => {
    if (dotEl) {
      dotEl.className = `gntv-chat__dot gntv-chat__dot--${state}`;
    }
    if (statusEl) {
      let label = STATE_LABEL[state] || state;
      if (cooldownSeconds > 0) label += ` · wait ${cooldownSeconds}s`;
      statusEl.textContent = label;
    }
  };

  const updateComposerState = () => {
    const isReadOnly = roomState === "closed" || roomState === "read_only" || muted || banned;
    textInput.disabled = isReadOnly;
    let placeholder = "Say something…";
    if (banned) placeholder = "You are banned from this chat.";
    else if (muted) placeholder = "You are muted.";
    else if (roomState === "closed") placeholder = "This room is closed.";
    else if (roomState === "read_only") placeholder = "This room is read-only.";
    textInput.placeholder = placeholder;

    const val = textInput.value;
    const bytes = byteLength(val);
    const overLimit = bytes > MAX_PAYLOAD_BYTES - 128;
    countEl.textContent = `${bytes}/${MAX_PAYLOAD_BYTES} bytes`;
    countEl.classList.toggle("is-over", overLimit);

    const canSend = !isReadOnly && !overLimit && cooldownSeconds === 0 && val.trim().length > 0;
    sendBtn.disabled = !canSend;
  };

  const pushNotice = (kind, message) => {
    const id = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
    notices.push({ id, kind, message });
    if (notices.length > 5) notices.shift();

    noticesEl.innerHTML = notices
      .map(n => `<li class="gntv-chat__notice gntv-chat__notice--${n.kind}">${escapeHTML(n.message)}</li>`)
      .join("");
  };

  const escapeHTML = (str) => {
    if (!str) return "";
    return str
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  };

  const renderAlerts = () => {
    let html = "";
    if (errorMessage || historyError) {
      html += `<p class="gntv-chat__alert" role="alert">${escapeHTML(errorMessage || historyError)}</p>`;
    }
    if (retriesExhausted) {
      html += `
        <div class="gntv-chat__alert">
          <span>Chat connection lost.</span>
          <button type="button" class="gntv-chat__link" id="btn-reconnect-now">Try again</button>
        </div>
      `;
    }
    alertContainer.innerHTML = html;
    const reconnectBtn = alertContainer.querySelector("#btn-reconnect-now");
    if (reconnectBtn) {
      reconnectBtn.addEventListener("click", reconnectNow);
    }
  };

  const renderMessages = () => {
    listEl.innerHTML = "";
    if (messages.length === 0 && !loadingHistory && !historyError) {
      listEl.innerHTML = `<p class="gntv-chat__empty">No messages yet.</p>`;
      return;
    }
    if (messages.length === 0 && historyError) {
      listEl.innerHTML = `<p class="gntv-chat__empty">Chat history unavailable.</p>`;
      return;
    }

    const fragment = document.createDocumentFragment();
    messages.forEach(m => {
      const li = document.createElement("li");
      li.className = `gntv-chat__msg${m.flagged ? " is-flagged" : ""}${m.pending === "failed" ? " is-failed" : ""}`;

      if (m.deleted || m.status === "deleted") {
        const p = document.createElement("p");
        p.className = "gntv-chat__removed";
        p.textContent = "Message removed by a moderator.";
        li.appendChild(p);
      } else {
        const meta = document.createElement("p");
        meta.className = "gntv-chat__meta";

        const userSpan = document.createElement("span");
        userSpan.className = "gntv-chat__user";
        userSpan.textContent = m.username || "Anonymous";

        const timeEl = document.createElement("time");
        timeEl.setAttribute("dateTime", m.created_at || new Date().toISOString());
        timeEl.textContent = formatTime(m.created_at || new Date());

        meta.appendChild(userSpan);
        meta.appendChild(timeEl);

        if (m.pending === "sending") {
          const pendingSpan = document.createElement("span");
          pendingSpan.className = "gntv-chat__pending";
          pendingSpan.textContent = "Sending…";
          meta.appendChild(pendingSpan);
        }
        li.appendChild(meta);

        const bodyP = document.createElement("p");
        bodyP.className = "gntv-chat__body";
        bodyP.textContent = m.text || m.body || m.message_text || "";
        li.appendChild(bodyP);

        if (m.pending === "failed") {
          const retryBtn = document.createElement("button");
          retryBtn.type = "button";
          retryBtn.className = "gntv-chat__link";
          retryBtn.textContent = "Retry";
          retryBtn.addEventListener("click", () => retryMessage(m.client_id));
          li.appendChild(retryBtn);
        }
      }

      fragment.appendChild(li);
    });

    listEl.appendChild(fragment);

    // Auto scroll near bottom
    const nearBottom = scrollEl.scrollHeight - scrollEl.scrollTop - scrollEl.clientHeight < 120;
    if (nearBottom) {
      scrollEl.scrollTop = scrollEl.scrollHeight;
    }
  };

  const renderEarlierButton = () => {
    if (hasMore) {
      earlierContainer.innerHTML = `
        <button type="button" class="gntv-chat__link gntv-chat__earlier" id="btn-load-earlier" ${loadingHistory ? "disabled" : ""}>
          ${loadingHistory ? "Loading…" : "Load earlier messages"}
        </button>
      `;
      const btn = earlierContainer.querySelector("#btn-load-earlier");
      if (btn) {
        btn.addEventListener("click", loadEarlier);
      }
    } else {
      earlierContainer.innerHTML = "";
    }
  };

  const mergeMessage = (incoming) => {
    const clientId = incoming.client_msg_id || incoming.client_id;
    const msgId = incoming.id;
    const index = messages.findIndex(m => (clientId && m.client_id === clientId) || (msgId && m.id === msgId));

    const normalized = {
      id: msgId || clientId,
      client_id: clientId,
      username: incoming.username || "User",
      text: incoming.text || incoming.message_text || incoming.body || "",
      created_at: incoming.created_at || (incoming.timestamp_ms ? new Date(incoming.timestamp_ms).toISOString() : new Date().toISOString()),
      status: incoming.status || "published",
      flagged: incoming.status === "flagged",
      deleted: incoming.status === "deleted",
      pending: "sent"
    };

    if (index >= 0) {
      messages[index] = normalized;
    } else {
      messages.push(normalized);
    }
    if (messages.length > MAX_RENDERED) {
      messages = messages.slice(-MAX_RENDERED);
    }
    renderMessages();

    // Announce to ARIA live
    if (!normalized.deleted) {
      AccessibilityAnnouncer?.announce?.(`Chat from ${normalized.username}: ${normalized.text}`);
    }
  };

  const handleFrame = (frame) => {
    if (!frame || typeof frame !== "object") return;
    const type = frame.type;

    if (type === "chat_message" || type === "message") {
      mergeMessage(frame.data || frame);
    } else if (type === "presence_update") {
      // presence update received
    } else if (type === "moderation_notice") {
      const action = frame.action;
      if (action === "message_deleted") {
        const targetId = frame.target_msg_id;
        messages = messages.map(m => (m.id === targetId ? { ...m, deleted: true } : m));
        renderMessages();
        pushNotice("delete", frame.reason || "Message was removed by moderator");
      } else if (action === "message_flagged") {
        const targetId = frame.target_msg_id;
        messages = messages.map(m => (m.id === targetId ? { ...m, flagged: true } : m));
        renderMessages();
        pushNotice("warn", frame.reason || "Message flagged for review");
      } else if (action === "mute" || action === "muted") {
        muted = true;
        updateComposerState();
        pushNotice("mute", frame.reason || "You have been muted.");
      } else if (action === "ban" || action === "banned") {
        banned = true;
        updateComposerState();
        pushNotice("ban", frame.reason || "You have been banned.");
      }
    } else if (type === "error") {
      errorMessage = frame.message || frame.code || "Chat error occurred";
      renderAlerts();
    } else if (type === "pong") {
      // pong received
    }
  };

  const fetchHistory = async () => {
    if (!roomId) return;
    loadingHistory = true;
    historyError = null;
    renderEarlierButton();

    try {
      let url = `${apiBase()}/rooms/${encodeURIComponent(roomId)}/messages?limit=50`;
      if (nextBeforeId) {
        url += `&before_id=${encodeURIComponent(nextBeforeId)}`;
      }
      const res = await fetch(url, { headers: authHeaders() });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      const items = data.items || [];
      nextBeforeId = data.next_before_id || null;
      hasMore = Boolean(nextBeforeId);

      const mapped = items.map(m => ({
        id: m.id,
        client_id: m.client_msg_id,
        username: m.username,
        text: m.message_text,
        created_at: m.created_at,
        status: m.status,
        flagged: m.status === "flagged",
        deleted: m.status === "deleted",
        pending: "sent"
      }));

      const knownIds = new Set(messages.map(m => m.id));
      const older = mapped.filter(m => !knownIds.has(m.id));
      messages = [...older, ...messages].slice(-MAX_RENDERED);
    } catch (e) {
      historyError = e.message || "Failed to load chat history";
    } finally {
      loadingHistory = false;
      renderAlerts();
      renderMessages();
      renderEarlierButton();
    }
  };

  const loadEarlier = () => {
    if (nextBeforeId) fetchHistory();
  };

  const connect = () => {
    if (!roomId) return;
    if (socket && socket.readyState <= WebSocket.OPEN) return;

    state = retryCount === 0 ? "connecting" : "reconnecting";
    updateHeaderState();

    try {
      socket = new WebSocket(chatWsUrl(roomId));
    } catch {
      state = "error";
      errorMessage = "Live chat connection failed.";
      updateHeaderState();
      renderAlerts();
      return;
    }

    socket.onopen = () => {
      retryCount = 0;
      retriesExhausted = false;
      errorMessage = null;
      state = "connected";
      updateHeaderState();
      renderAlerts();
      updateComposerState();
    };

    socket.onmessage = (event) => {
      if (typeof event.data !== "string") return;
      try {
        handleFrame(JSON.parse(event.data));
      } catch {
        /* ignore invalid frame */
      }
    };

    socket.onerror = () => {
      errorMessage = "Chat connection error.";
      renderAlerts();
    };

    socket.onclose = (event) => {
      socket = null;
      messages = messages.map(m => (m.pending === "sending" ? { ...m, pending: "failed" } : m));
      renderMessages();

      if (closedByUs) {
        state = "disconnected";
        updateHeaderState();
        return;
      }

      if (event.code === 1008 || event.code === 4401 || event.code === 4403) {
        state = "error";
        errorMessage = "Authentication failed. Please log in.";
        updateHeaderState();
        renderAlerts();
        return;
      }

      if (retryCount >= MAX_RETRIES) {
        retriesExhausted = true;
        state = "disconnected";
        updateHeaderState();
        renderAlerts();
        return;
      }

      const delay = Math.min(MAX_DELAY_MS, BASE_DELAY_MS * Math.pow(2, retryCount));
      retryCount += 1;
      state = "reconnecting";
      updateHeaderState();
      reconnectTimer = setTimeout(connect, delay);
    };
  };

  const reconnectNow = () => {
    retryCount = 0;
    retriesExhausted = false;
    closedByUs = false;
    connect();
  };

  const sendMessage = (rawText) => {
    const text = (rawText || "").trim();
    if (!text) return;

    const clientId = `c-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
    const payloadObj = { type: "send_message", client_msg_id: clientId, text };
    const payloadStr = JSON.stringify(payloadObj);

    if (byteLength(payloadStr) > MAX_PAYLOAD_BYTES) {
      errorMessage = "Message payload exceeds 4KB limit.";
      renderAlerts();
      return;
    }

    const optimistic = {
      id: clientId,
      client_id: clientId,
      username: "You",
      text,
      created_at: new Date().toISOString(),
      status: "published",
      pending: "sending"
    };

    messages.push(optimistic);
    renderMessages();

    if (!socket || socket.readyState !== WebSocket.OPEN) {
      optimistic.pending = "failed";
      renderMessages();
      return;
    }

    socket.send(payloadStr);

    textInput.value = "";
    updateComposerState();

    if (cooldownSeconds > 0) {
      startCooldownTimer();
    }
  };

  const retryMessage = (clientId) => {
    const idx = messages.findIndex(m => m.client_id === clientId);
    if (idx < 0) return;
    const msgText = messages[idx].text;
    messages.splice(idx, 1);
    sendMessage(msgText);
  };

  const startCooldownTimer = () => {
    if (cooldownTimer) clearInterval(cooldownTimer);
    cooldownTimer = setInterval(() => {
      if (cooldownSeconds > 0) {
        cooldownSeconds -= 1;
        updateHeaderState();
        updateComposerState();
      } else {
        clearInterval(cooldownTimer);
        cooldownTimer = null;
      }
    }, 1000);
  };

  // Event Listeners
  textInput.addEventListener("input", updateComposerState);
  textInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      composerForm.dispatchEvent(new Event("submit"));
    }
  });

  composerForm.addEventListener("submit", (e) => {
    e.preventDefault();
    sendMessage(textInput.value);
  });

  // Spatial Navigation for D-Pad
  SpatialNavigationManager?.registerFocusable?.(container);

  // Initial Load & Connect
  fetchHistory();
  connect();

  // Cleanup function
  return () => {
    closedByUs = true;
    if (reconnectTimer) clearTimeout(reconnectTimer);
    if (cooldownTimer) clearInterval(cooldownTimer);
    if (socket) {
      socket.onclose = null;
      socket.onmessage = null;
      socket.onerror = null;
      socket.onopen = null;
      if (socket.readyState <= WebSocket.OPEN) {
        socket.close(1000, "Component unmounted");
      }
    }
    SpatialNavigationManager?.unregisterFocusable?.(container);
    container.innerHTML = "";
  };
}
