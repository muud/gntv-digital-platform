import { store } from "../../../shared/src/state.js";
import { CHANNELS } from "../../../shared/src/utils/mockData.js";
import { TelemetryCollector } from "../services/telemetry.js";
import { SpatialNavigationManager } from "../utils/spatialNavigation.js";
import { MobileGestureController } from "../utils/mobileGestures.js";
import { AccessibilityAnnouncer } from "../utils/accessibilityAnnouncer.js";



const MAX_RETRIES = 3;
const NON_RETRYABLE_STATUSES = new Set([400, 403, 404]);
const HLS_MIME_TYPE = "application/vnd.apple.mpegurl";
const DVR_WINDOW_SECONDS = 30 * 60;

class PlaybackError extends Error {
  constructor(message, { status = null, retryable = true } = {}) {
    super(message);
    this.name = "PlaybackError";
    this.status = status;
    this.retryable = retryable;
  }
}

function getDeviceId() {
  const storageKey = "gntv_playback_device_id";
  const existing = localStorage.getItem(storageKey);
  if (existing) return existing;

  const generated = globalThis.crypto?.randomUUID?.() || `web-${Date.now().toString(36)}`;
  localStorage.setItem(storageKey, generated);
  return generated;
}

function mapPlaybackContract(payload) {
  if (!payload || typeof payload !== "object") {
    throw new PlaybackError("The playback service returned an invalid response.", { retryable: false });
  }

  const contract = {
    content_id: payload.content_id,
    playback_url: payload.playback_url,
    manifest_type: payload.manifest_type,
    playback_mode: payload.playback_mode,
    expires_at: payload.expires_at,
  };

  const expiresAt = Date.parse(contract.expires_at);
  if (
    typeof contract.content_id !== "string" ||
    typeof contract.playback_url !== "string" ||
    contract.manifest_type !== "hls" ||
    !["live", "vod"].includes(contract.playback_mode) ||
    !Number.isFinite(expiresAt)
  ) {
    throw new PlaybackError("The playback service returned an unsupported stream contract.", {
      retryable: false,
    });
  }

  if (expiresAt <= Date.now()) {
    throw new PlaybackError("This playback authorization has expired.", {
      status: 403,
      retryable: false,
    });
  }

  let playbackUrl;
  try {
    playbackUrl = new URL(contract.playback_url, window.location.origin);
  } catch {
    throw new PlaybackError("The playback service returned an invalid stream URL.", {
      retryable: false,
    });
  }
  if (!["http:", "https:"].includes(playbackUrl.protocol)) {
    throw new PlaybackError("The playback service returned an unsafe stream URL.", {
      retryable: false,
    });
  }

  return { ...contract, playback_url: playbackUrl.href };
}

function errorMessageForStatus(status, detailCode) {
  if (detailCode === "country_denied" || detailCode === "country_not_allowed" || detailCode === "vpn_detected") {
    return "CONTENT NOT AVAILABLE IN YOUR REGION (GEOGRAPHIC RESTRICTION).";
  }
  if (detailCode === "unsupported_drm_system" || detailCode === "drm_token_expired") {
    return "DRM LICENSE ERROR: UNABLE TO DECRYPT PROTECTED STREAM.";
  }
  if (status === 400) return "This channel cannot be played with the requested stream format.";
  if (status === 403) return "Playback is not authorized, geo-restricted, or the stream link has expired.";
  if (status === 404) return "This channel does not currently have a playable stream.";
  return "The playback service is temporarily unavailable.";
}

export function VisibleWatermark(text = "GNTV • DIGITAL PROTECTED STREAM") {
  return `
    <div class="player-watermark-overlay" id="player-watermark-overlay" aria-hidden="true">
      <span class="watermark-text" id="watermark-text-content">${text}</span>
    </div>
  `;
}

export function AdStateOverlay() {
  return `
    <div class="ad-state-overlay" id="player-ad-state" hidden aria-live="polite">
      <span class="ad-pill">Ad</span>
      <span id="player-ad-position">Ad 1 of 1</span>
      <span id="player-ad-remaining">Ad playing</span>
    </div>
  `;
}

export function LiveBadge(label = "LIVE") {
  return `
    <div class="live-badge" id="player-live-badge">
      <span class="pulse-red-ring"></span>
      <span class="live-label">${label}</span>
    </div>
  `;
}

export function DVRTimelineBar() {
  return `
    <div class="dvr-timeline-bar" aria-label="DVR timeline">
      <span class="dvr-edge-label">-${Math.round(DVR_WINDOW_SECONDS / 60)}m</span>
      <input
        type="range"
        id="slider-dvr-timeline"
        min="0"
        max="${DVR_WINDOW_SECONDS}"
        value="0"
        step="6"
        aria-label="Time-shift seek"
      >
      <span class="dvr-edge-label">LIVE</span>
    </div>
  `;
}

export function DVRControlsOverlay() {
  return `
    <div class="dvr-controls-overlay" id="dvr-controls-overlay">
      ${DVRTimelineBar()}
      <div class="dvr-actions">
        <button class="dvr-chip" id="btn-dvr-minus-30" type="button">-30s</button>
        <button class="dvr-chip" id="btn-dvr-minus-5m" type="button">-5m</button>
        <button class="dvr-chip dvr-live" id="btn-go-live" type="button">Go Live</button>
        <button class="dvr-chip" id="btn-catchup" type="button">Catch-up</button>
      </div>
      <span class="dvr-readout" id="dvr-readout">Live edge</span>
    </div>
  `;
}

export function LiveDVRPlayer(container) {
  return initLivePlayer(container);
}

export function initLivePlayer(container) {
  container.innerHTML = `
    <div class="player-container glass-card">
      <div class="player-screen-wrapper" id="player-screen-wrapper">
        <video id="player-video" playsinline preload="metadata"></video>

        <div class="player-hud">
          <div class="hud-top">
            ${LiveBadge()}
            <div class="hud-channel-info">
              <span id="player-channel-logo">🌐</span>
              <span id="player-channel-name">GNTV DIGITAL, ALL EVERYWHERE News Global</span>
            </div>
          </div>
          <div class="hud-bottom">
            <div class="hud-cam">CAMERA: <span id="player-cam-name">Studio Main</span></div>
            <div class="hud-telemetry">
              <span id="hud-playback-mode">LIVE</span> |
              <span id="hud-manifest-type">HLS</span>
            </div>
          </div>
        </div>

        <div class="player-status-overlay" id="player-loading-overlay" role="status" aria-live="polite">
          <span class="player-spinner" aria-hidden="true"></span>
          <span id="player-loading-message">SECURING LIVE DOWNLINK…</span>
        </div>

        <div class="player-status-overlay player-error-overlay" id="player-error-overlay" role="alert" hidden>
          <div class="player-error-icon" aria-hidden="true">⚠️</div>
          <h2>PLAYBACK INTERRUPTED</h2>
          <p id="player-error-message">The broadcast stream could not be loaded.</p>
          <button class="player-retry-btn" id="btn-player-retry" type="button">RETRY NOW</button>
        </div>

        <div class="emergency-overlay" id="player-emergency-overlay">
          <div class="emergency-scanner"></div>
          <div class="emergency-content">
            <div class="emergency-icon">⚠️</div>
            <h2>GNTV DIGITAL, ALL EVERYWHERE EMERGENCY ALERT SYSTEM</h2>
            <p id="player-emergency-msg">BROADCAST SIGNAL OVERRIDE ACTIVATED</p>
          </div>
        </div>
        ${DVRControlsOverlay()}
        ${AdStateOverlay()}
        ${VisibleWatermark()}
      </div>

      <div class="player-controls">
        <div class="control-left">
          <button class="player-btn" id="btn-play-pause" type="button" aria-label="Play" disabled>▶️</button>
          <button class="player-btn" id="btn-mute" type="button" aria-label="Mute">🔊</button>
          <div class="volume-control">
            <input type="range" class="vol-slider" min="0" max="100" value="80" id="slider-volume" aria-label="Volume">
          </div>
        </div>
        <div class="control-right">
          <span class="player-protocol-label">ADAPTIVE HLS</span>
          <button class="player-btn" id="btn-fullscreen" type="button" aria-label="Enter fullscreen">⛶</button>
        </div>
      </div>

      <div class="channel-selector-bar">
        ${CHANNELS.map(ch => `
          <button class="channel-btn" type="button" data-channel-id="${ch.id}">
            <span class="ch-logo">${ch.logo}</span>
            <span class="ch-name">${ch.name.split(" ")[1] || ch.name}</span>
          </button>
        `).join("")}
      </div>

      <div class="ticker-wrap">
        <div class="ticker-title">GNTV DIGITAL, ALL EVERYWHERE HEADLINES</div>
        <div class="ticker" id="marquee-ticker">
          <div class="ticker__item">Loading ticker items...</div>
        </div>
      </div>
    </div>
  `;

  const video = container.querySelector("#player-video");
  const screenWrapper = container.querySelector("#player-screen-wrapper");
  const playPauseBtn = container.querySelector("#btn-play-pause");
  const muteBtn = container.querySelector("#btn-mute");
  const volumeSlider = container.querySelector("#slider-volume");
  const fullscreenBtn = container.querySelector("#btn-fullscreen");
  const loadingOverlay = container.querySelector("#player-loading-overlay");
  const loadingMessage = container.querySelector("#player-loading-message");
  const errorOverlay = container.querySelector("#player-error-overlay");
  const errorMessage = container.querySelector("#player-error-message");
  const retryBtn = container.querySelector("#btn-player-retry");
  const emergencyOverlay = container.querySelector("#player-emergency-overlay");
  const emergencyMsg = container.querySelector("#player-emergency-msg");
  const channelLogo = container.querySelector("#player-channel-logo");
  const channelName = container.querySelector("#player-channel-name");
  const cameraName = container.querySelector("#player-cam-name");
  const playbackMode = container.querySelector("#hud-playback-mode");
  const manifestType = container.querySelector("#hud-manifest-type");
  const tickerContainer = container.querySelector("#marquee-ticker");
  const channelButtons = container.querySelectorAll(".channel-btn");
  const liveBadgeLabel = container.querySelector("#player-live-badge .live-label");
  const dvrSlider = container.querySelector("#slider-dvr-timeline");
  const dvrReadout = container.querySelector("#dvr-readout");
  const dvrMinus30 = container.querySelector("#btn-dvr-minus-30");
  const dvrMinus5m = container.querySelector("#btn-dvr-minus-5m");
  const goLiveBtn = container.querySelector("#btn-go-live");
  const catchupBtn = container.querySelector("#btn-catchup");
  const adStateOverlay = container.querySelector("#player-ad-state");
  const adPosition = container.querySelector("#player-ad-position");
  const adRemaining = container.querySelector("#player-ad-remaining");

  let abortController = null;
  let hls = null;
  let retryTimer = null;
  let retryCount = 0;
  let activeTargetId = null;
  let loadGeneration = 0;
  let mediaGeneration = 0;
  let destroyed = false;
  let activeSessionId = null;
  let activeChannel = null;
  let activeTimeShift = 0;
  let dvrMode = "live";

  // Sprint 6.4 Watermark Anti-Tampering Observer
  const watermarkObserver = new MutationObserver((mutations) => {
    for (const mutation of mutations) {
      if (mutation.type === "childList") {
        const wm = screenWrapper.querySelector("#player-watermark-overlay");
        if (!wm) {
          video.pause();
          console.warn("[DRM Security] Watermark element removal detected. Playback paused.");
        }
      }
    }
  });
  watermarkObserver.observe(screenWrapper, { childList: true, subtree: true });

  const setLoading = (visible, message = "SECURING LIVE DOWNLINK…") => {
    loadingMessage.textContent = message;
    loadingOverlay.hidden = !visible;
  };

  const setError = (message, { retryable = false, exhausted = false } = {}) => {
    setLoading(false);
    errorMessage.textContent = message;
    retryBtn.hidden = !retryable;
    retryBtn.disabled = exhausted;
    retryBtn.textContent = exhausted ? "RETRY LIMIT REACHED" : "RETRY NOW";
    errorOverlay.hidden = false;
  };

  const clearError = () => {
    errorOverlay.hidden = true;
    retryBtn.hidden = false;
    retryBtn.disabled = false;
    retryBtn.textContent = "RETRY NOW";
  };

  const formatShift = seconds => {
    if (seconds <= 0) return "Live edge";
    const minutes = Math.floor(seconds / 60);
    const remainder = seconds % 60;
    if (minutes === 0) return `${remainder}s behind live`;
    return `${minutes}m ${remainder}s behind live`;
  };

  const updateDVRUI = () => {
    dvrSlider.value = String(activeTimeShift);
    dvrReadout.textContent = dvrMode === "catchup" ? "Catch-up playback" : formatShift(activeTimeShift);
    liveBadgeLabel.textContent = activeTimeShift === 0 && dvrMode === "live" ? "LIVE" : "DVR";
    goLiveBtn.disabled = activeTimeShift === 0 && dvrMode === "live";
  };

  const updateAdStateUI = state => {
    if (!state?.active) {
      adStateOverlay.hidden = true;
      return;
    }
    const index = Number(state.index || 1);
    const total = Number(state.total || 1);
    const remaining = Number(state.remainingSeconds || 0);
    adPosition.textContent = `Ad ${index} of ${total}`;
    adRemaining.textContent = remaining > 0 ? `${Math.ceil(remaining)}s remaining` : "Ad playing";
    adStateOverlay.hidden = false;
  };

  const updateMuteControl = () => {
    const effectivelyMuted = video.muted || video.volume === 0;
    muteBtn.textContent = effectivelyMuted ? "🔇" : video.volume < 0.5 ? "🔉" : "🔊";
    muteBtn.setAttribute("aria-label", effectivelyMuted ? "Unmute" : "Mute");
  };

  const teardownMedia = () => {
    mediaGeneration = 0;
    if (hls) {
      hls.destroy();
      hls = null;
    }
    video.pause();
    video.removeAttribute("src");
    video.load();
    playPauseBtn.disabled = true;
    playPauseBtn.textContent = "▶️";
    playPauseBtn.setAttribute("aria-label", "Play");
  };

  const cancelPendingPlayback = () => {
    abortController?.abort();
    abortController = null;
    if (retryTimer !== null) {
      clearTimeout(retryTimer);
      retryTimer = null;
    }
    teardownMedia();
  };

  const beginPlayback = async (contract, generation) => {
    mediaGeneration = generation;
    playbackMode.textContent = contract.playback_mode.toUpperCase();
    manifestType.textContent = contract.manifest_type.toUpperCase();

    if (video.canPlayType(HLS_MIME_TYPE)) {
      video.src = contract.playback_url;
      video.load();
      return;
    }

    const { default: Hls } = await import("hls.js");
    if (!Hls.isSupported()) {
      throw new PlaybackError("HLS playback is not supported by this browser.", { retryable: false });
    }

    hls = new Hls({
      enableWorker: true,
      lowLatencyMode: contract.playback_mode === "live",
      maxBufferLength: 30,
    });
    hls.on(Hls.Events.ERROR, (_event, data) => {
      if (data.fatal) {
        handleFailure(new PlaybackError("The HLS stream was interrupted."), generation);
      }
    });
    hls.loadSource(contract.playback_url);
    hls.attachMedia(video);
  };

  async function requestManifestPlayback(url, generation, modeLabel) {
    if (destroyed || generation !== loadGeneration) return;
    abortController?.abort();
    abortController = new AbortController();
    clearError();
    setLoading(true, modeLabel === "catchup" ? "OPENING CATCH-UP PLAYLIST…" : "TUNING DVR WINDOW…");
    activeSessionId = null;

    try {
      await beginPlayback(
        {
          playback_url: url,
          playback_mode: modeLabel === "catchup" ? "vod" : "live",
          manifest_type: "hls",
        },
        generation,
      );
      if (destroyed || generation !== loadGeneration) return;
      playPauseBtn.disabled = false;
      await video.play().catch(() => {
        playPauseBtn.textContent = "▶️";
        playPauseBtn.setAttribute("aria-label", "Play");
      });
    } catch (error) {
      handleFailure(error, generation);
    }
  }

  const scheduleRetry = generation => {
    if (retryCount >= MAX_RETRIES) {
      setError("The broadcast could not be restored after 3 retries.", {
        retryable: true,
        exhausted: true,
      });
      return;
    }

    retryCount += 1;
    clearError();
    setLoading(true, `RECONNECTING TO BROADCAST… ${retryCount}/${MAX_RETRIES}`);
    retryTimer = window.setTimeout(() => {
      retryTimer = null;
      void requestPlayback(activeTargetId, generation);
    }, retryCount * 1000);
  };

  const handleFailure = (error, generation) => {
    if (destroyed || generation !== loadGeneration || error?.name === "AbortError") return;
    if (retryTimer !== null) return;
    teardownMedia();
    const retryable = error instanceof PlaybackError ? error.retryable : true;
    if (!retryable) {
      setError(error.message || "Playback could not be started.");
      return;
    }
    setError(error.message || "The broadcast stream was interrupted.", { retryable: true });
    scheduleRetry(generation);
  };

  async function requestPlayback(targetId, generation) {
    if (destroyed || generation !== loadGeneration || !targetId) return;

    abortController?.abort();
    abortController = new AbortController();
    clearError();
    setLoading(true);

    try {
      const apiBase = (import.meta.env.VITE_API_URL || "http://localhost:8000").replace(/\/$/, "");
      const endpoint = new URL(`${apiBase}/api/v1/streaming/playback/${encodeURIComponent(targetId)}`);
      endpoint.searchParams.set("device_id", getDeviceId());
      endpoint.searchParams.set("protocol", "hls");

      const response = await fetch(endpoint, {
        headers: { Accept: "application/json" },
        signal: abortController.signal,
        redirect: "error",
      });

      if (!response.ok) {
        throw new PlaybackError(errorMessageForStatus(response.status), {
          status: response.status,
          retryable: !NON_RETRYABLE_STATUSES.has(response.status),
        });
      }

      const contract = mapPlaybackContract(await response.json());
      activeSessionId = contract.playback_session_id;
      if (contract.content_id !== String(targetId)) {
        throw new PlaybackError("The playback response did not match the selected content.", {
          retryable: false,
        });
      }
      if (destroyed || generation !== loadGeneration) return;

      await beginPlayback(contract, generation);
      if (destroyed || generation !== loadGeneration) return;
      playPauseBtn.disabled = false;
      await video.play().catch(() => {
        playPauseBtn.textContent = "▶️";
        playPauseBtn.setAttribute("aria-label", "Play");
      });
    } catch (error) {
      handleFailure(error, generation);
    }
  }

  const loadContent = targetId => {
    loadGeneration += 1;
    const generation = loadGeneration;
    activeTargetId = targetId ? String(targetId) : null;
    retryCount = 0;
    cancelPendingPlayback();
    clearError();
    if (!activeTargetId) {
      setError("No playback target was selected.");
      return;
    }
    activeTimeShift = 0;
    dvrMode = "live";
    updateDVRUI();
    void requestPlayback(activeTargetId, generation);
  };

  const loadDVRShift = seconds => {
    if (!activeTargetId) return;
    loadGeneration += 1;
    const generation = loadGeneration;
    activeTimeShift = Math.min(DVR_WINDOW_SECONDS, Math.max(0, seconds));
    dvrMode = "live";
    updateDVRUI();
    const apiBase = (import.meta.env.VITE_API_URL || "http://localhost:8000").replace(/\/$/, "");
    const endpoint = new URL(
      `${apiBase}/api/v1/streaming/live/${encodeURIComponent(activeTargetId)}/dvr.m3u8`,
    );
    endpoint.searchParams.set("time_shift", String(activeTimeShift));
    void requestManifestPlayback(endpoint.href, generation, "dvr");
  };

  const loadCatchup = () => {
    const eventId = activeChannel?.liveEventId || activeChannel?.catchupEventId || activeTargetId;
    if (!eventId) return;
    loadGeneration += 1;
    const generation = loadGeneration;
    dvrMode = "catchup";
    updateDVRUI();
    const apiBase = (import.meta.env.VITE_API_URL || "http://localhost:8000").replace(/\/$/, "");
    const endpoint = new URL(
      `${apiBase}/api/v1/streaming/catchup/${encodeURIComponent(eventId)}/playlist.m3u8`,
    );
    void requestManifestPlayback(endpoint.href, generation, "catchup");
  };

  playPauseBtn.addEventListener("click", () => {
    if (video.paused) void video.play();
    else video.pause();
  });

  muteBtn.addEventListener("click", () => {
    video.muted = !video.muted;
    updateMuteControl();
  });

  volumeSlider.addEventListener("input", event => {
    const volume = Number(event.target.value) / 100;
    video.volume = volume;
    if (volume > 0) video.muted = false;
    store.savePreference("prefVolume", Math.round(volume * 100));
    updateMuteControl();
  });

  fullscreenBtn.addEventListener("click", async () => {
    try {
      if (document.fullscreenElement) await document.exitFullscreen();
      else if (screenWrapper.requestFullscreen) await screenWrapper.requestFullscreen();
      else if (video.webkitEnterFullscreen) video.webkitEnterFullscreen();
    } catch {
      setError("Fullscreen mode could not be opened.");
    }
  });

  retryBtn.addEventListener("click", () => {
    if (retryCount >= MAX_RETRIES || !activeTargetId) return;
    if (retryTimer !== null) {
      clearTimeout(retryTimer);
      retryTimer = null;
    }
    void requestPlayback(activeTargetId, loadGeneration);
  });

  dvrSlider.addEventListener("input", event => {
    activeTimeShift = Number(event.target.value);
    dvrReadout.textContent = formatShift(activeTimeShift);
  });

  dvrSlider.addEventListener("change", event => {
    loadDVRShift(Number(event.target.value));
  });

  dvrMinus30.addEventListener("click", () => {
    loadDVRShift(activeTimeShift + 30);
  });

  dvrMinus5m.addEventListener("click", () => {
    loadDVRShift(activeTimeShift + 300);
  });

  goLiveBtn.addEventListener("click", () => {
    if (activeTargetId) loadContent(activeTargetId);
  });

  catchupBtn.addEventListener("click", loadCatchup);

  video.addEventListener("loadstart", () => setLoading(true));
  video.addEventListener("waiting", () => setLoading(true, "BUFFERING BROADCAST…"));
  video.addEventListener("canplay", () => setLoading(false));
  video.addEventListener("playing", () => {
    clearError();
    setLoading(false);
    playPauseBtn.textContent = "⏸️";
    playPauseBtn.setAttribute("aria-label", "Pause");
    if (!store.getState("activeSessionId")) {
      store.startVideoSession(activeTargetId, channelName.textContent, "channel");
    }
  });
  video.addEventListener("pause", () => {
    playPauseBtn.textContent = "▶️";
    playPauseBtn.setAttribute("aria-label", "Play");
    store.endVideoSession();
  });
  video.addEventListener("volumechange", updateMuteControl);
  video.addEventListener("error", () => {
    if (video.error && mediaGeneration === loadGeneration) {
      handleFailure(new PlaybackError("The browser could not decode the stream."), mediaGeneration);
    }
  });

  channelButtons.forEach(button => {
    button.addEventListener("click", () => {
      const matched = CHANNELS.find(channel => channel.id === button.dataset.channelId);
      if (matched) {
        store.setState("activeChannel", matched);
        store.setState("activeCamera", matched.cameras[0]);
      }
    });
  });

  const unsubChannel = store.subscribe("activeChannel", channel => {
    if (!channel) return;
    activeChannel = channel;
    channelLogo.textContent = channel.logo;
    channelName.textContent = channel.name;
    channelButtons.forEach(button => {
      button.classList.toggle("active", button.dataset.channelId === String(channel.id));
    });
    tickerContainer.innerHTML = (channel.ticker || ["Live on GNTV DIGITAL"]).map(
      item => `<div class="ticker__item">${item}</div>`,
    ).join("");
    loadContent(channel.id);
  });

  const unsubCamera = store.subscribe("activeCamera", camera => {
    if (camera) cameraName.textContent = camera.name;
  });

  const unsubAlert = store.subscribe("emergencyAlert", alertState => {
    emergencyOverlay.classList.toggle("active", Boolean(alertState?.active));
    emergencyMsg.textContent = alertState?.message || "BROADCAST OVERRIDE ACTIVATED";
  });

  const unsubAdState = store.subscribe("adPlaybackState", updateAdStateUI);

  const heartbeatInterval = window.setInterval(async () => {
    if (!video.paused && activeSessionId) {
      try {
        const apiBase = (import.meta.env.VITE_API_URL || "http://localhost:8000").replace(/\/$/, "");
        const resp = await fetch(`${apiBase}/api/v1/streaming/playback/${activeSessionId}/heartbeat`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            position_ms: Math.round((video.currentTime || 0) * 1000),
            state: video.paused ? "paused" : "playing",
          }),
        });
        if (resp.status === 409) {
          teardownMedia();
          setError("Stream terminated: Concurrent stream limit reached on another device.", { retryable: false });
        }
      } catch {
        // ignore transient network errors on heartbeat
      }
    }
    if (!video.paused && store.getState("activeSessionId")) store.sendSessionHeartbeat(0);
  }, 30000);

  const initialVolume = Math.min(100, Math.max(0, store.getState("prefVolume") ?? 80));
  volumeSlider.value = String(initialVolume);
  video.volume = initialVolume / 100;
  updateMuteControl();

  const apiBaseUrl = import.meta.env.VITE_API_URL || "http://localhost:8000";
  const telemetryCollector = new TelemetryCollector(apiBaseUrl, activeSessionId);
  video.addEventListener("play", () => telemetryCollector.track("play", (video.currentTime || 0) * 1000));
  video.addEventListener("pause", () => telemetryCollector.track("pause", (video.currentTime || 0) * 1000));
  video.addEventListener("error", () =>
    telemetryCollector.track("error", (video.currentTime || 0) * 1000, null, null, "media_element_error"),
  );

  const announcer = new AccessibilityAnnouncer();
  announcer.announce("GNTV Live Player Ready");

  const spatialNav = new SpatialNavigationManager(container);
  const mobileGestures = new MobileGestureController(video);

  return () => {
    destroyed = true;
    loadGeneration += 1;
    cancelPendingPlayback();
    clearInterval(heartbeatInterval);
    watermarkObserver.disconnect();
    telemetryCollector.destroy();
    spatialNav.destroy();
    mobileGestures.destroy();
    announcer.destroy();
    store.endVideoSession();
    unsubChannel();
    unsubCamera();
    unsubAlert();
    unsubAdState();
  };
}
