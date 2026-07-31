import { store } from "../../../shared/src/state.js";
import { CHANNELS } from "../../../shared/src/utils/mockData.js";
import { audioAlert } from "../../../shared/src/utils/audio.js";

export function initControlPanel(container) {
  container.innerHTML = `
    <div class="control-panel-grid">

      <!-- Camera Mixer Section -->
      <div class="control-section glass-card">
        <h2 class="section-title"><span class="icon">🎙️</span> Multi-Camera Stream Mixer</h2>
        <p class="section-desc">Select active live input source to broadcast over the primary GNTV DIGITAL, ALL EVERYWHERE downlink.</p>

        <div class="camera-mixer-grid" id="mixer-cam-grid">
          <!-- Populated by JS -->
        </div>
      </div>

      <!-- Emergency Warning Section (EABS) -->
      <div class="control-section glass-card alert-panel">
        <h2 class="section-title"><span class="icon">⚠️</span> Emergency Alert System (EABS)</h2>
        <p class="section-desc">Push high-priority warning alerts over the live signal with synthesized dual-frequency sound overlay.</p>

        <div class="alert-form">
          <input type="text" class="alert-input" id="input-alert-msg" placeholder="ENTER WARNING TEXT (e.g. SEVERE STORM ALERT)..." value="CRITICAL UPDATE: SEVERE WEATHER WARNINGS ISSUED NATIONWIDE">
          <button class="alert-trigger-btn" id="btn-trigger-alert">TRIGGER BROADCAST ALARM</button>
        </div>
      </div>

      <!-- Live Video FX & Mixer Console -->
      <div class="control-section glass-card fx-panel">
        <h2 class="section-title"><span class="icon">🎨</span> Live Video FX & Mixer Console</h2>
        <p class="section-desc">Apply procedural green-screen backdrops, configure picture-in-picture angles, or deploy real-time crawler tickers.</p>

        <div class="fx-form" style="display: flex; flex-direction: column; gap: 16px;">
          <!-- 1. Chroma Key Backdrop Selector -->
          <div class="form-group">
            <label style="font-size: 11px; font-weight: 600; color: rgba(255, 255, 255, 0.5); letter-spacing: 0.5px; margin-bottom: 6px;">Chroma Key Procedural Backdrop</label>
            <div class="fx-select-group" style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px;">
              <button type="button" class="fx-btn active" data-fx-filter="none" style="padding: 8px 4px; font-size: 11px; font-weight: 600; border-radius: 4px; border: 1px solid rgba(255,255,255,0.08); background: rgba(255,255,255,0.02); color: #ffffff; cursor: pointer; transition: all 0.2s ease;">🔳 None</button>
              <button type="button" class="fx-btn" data-fx-filter="neon-matrix" style="padding: 8px 4px; font-size: 11px; font-weight: 600; border-radius: 4px; border: 1px solid rgba(255,255,255,0.08); background: rgba(255,255,255,0.02); color: #ffffff; cursor: pointer; transition: all 0.2s ease;">🟢 Matrix</button>
              <button type="button" class="fx-btn" data-fx-filter="cosmic-orbit" style="padding: 8px 4px; font-size: 11px; font-weight: 600; border-radius: 4px; border: 1px solid rgba(255,255,255,0.08); background: rgba(255,255,255,0.02); color: #ffffff; cursor: pointer; transition: all 0.2s ease;">🌌 Cosmic</button>
              <button type="button" class="fx-btn" data-fx-filter="hyper-grid" style="padding: 8px 4px; font-size: 11px; font-weight: 600; border-radius: 4px; border: 1px solid rgba(255,255,255,0.08); background: rgba(255,255,255,0.02); color: #ffffff; cursor: pointer; transition: all 0.2s ease;">📈 Grid</button>
            </div>
          </div>

          <!-- 2. Picture-in-Picture Control Group -->
          <div class="form-row" style="display: grid; grid-template-columns: 1fr 1.2fr; gap: 16px; align-items: end;">
            <div class="form-group" style="flex-direction: row; align-items: center; gap: 8px; margin-bottom: 6px;">
              <input type="checkbox" id="check-pip-active" style="width: 16px; height: 16px; cursor: pointer; accent-color: var(--brand-primary);">
              <label for="check-pip-active" style="font-size: 12px; font-weight: 700; cursor: pointer; color: #ffffff; margin-bottom: 0;">Activate PiP Overlay</label>
            </div>
            <div class="form-group">
              <label for="select-pip-camera" style="font-size: 11px; font-weight: 600; color: rgba(255, 255, 255, 0.5); letter-spacing: 0.5px;">Choose PiP Secondary Angle</label>
              <select id="select-pip-camera" style="background: rgba(0,0,0,0.2); border: 1px solid rgba(255,255,255,0.08); border-radius: 6px; padding: 6px 10px; font-size: 12px; outline: none; color: #ffffff; width: 100%;">
                <!-- Populated dynamically by JS -->
              </select>
            </div>
          </div>

          <!-- 3. Scrolling Lower-Third Crawler Ticker -->
          <div class="form-group">
            <label style="font-size: 11px; font-weight: 600; color: rgba(255, 255, 255, 0.5); letter-spacing: 0.5px; margin-bottom: 6px;">Lower-Third Ticker Crawler</label>
            <div class="crawler-input-row" style="display: flex; gap: 8px; align-items: center; width: 100%;">
              <input type="checkbox" id="check-scroll-active" style="width: 16px; height: 16px; cursor: pointer; accent-color: var(--brand-primary); flex-shrink: 0;">
              <input type="text" id="input-scroll-text" style="flex-grow: 1; background: rgba(0,0,0,0.2); border: 1px solid rgba(255,255,255,0.08); border-radius: 6px; padding: 8px 12px; font-size: 12px; outline: none; color: #ffffff; min-width: 0;" placeholder="Enter custom marquee crawl alert text...">
              <button type="button" id="btn-update-scroll" class="submit-btn" style="padding: 8px 16px; flex-shrink: 0; margin-top: 0; font-size: 11px;">UPDATE</button>
            </div>
          </div>
        </div>
      </div>

      <!-- Real-time Analytics Canvas -->
      <div class="control-section glass-card telemetry-panel">
        <h2 class="section-title"><span class="icon">📈</span> Live Stream Telemetry & Bandwidth</h2>
        <p class="section-desc">Real-time downlink bitrate stability and frame render metrics.</p>
        <div class="analytics-canvas-wrapper">
          <canvas id="analytics-canvas" width="400" height="150"></canvas>
        </div>
        <div class="telemetry-stats">
          <div class="stat-box">
            <span class="stat-val" id="stat-viewer-count">14,500</span>
            <span class="stat-lbl">Active Viewers</span>
          </div>
          <div class="stat-box">
            <span class="stat-val" id="stat-latency">34 ms</span>
            <span class="stat-lbl">Broadcast Latency</span>
          </div>
          <div class="stat-box">
            <span class="stat-val" id="stat-jitter">0.4 ms</span>
            <span class="stat-lbl">Packet Jitter</span>
          </div>
        </div>
      </div>

      <!-- EPG Program Injector -->
      <div class="control-section glass-card scheduler-panel">
        <h2 class="section-title"><span class="icon">📅</span> EPG Broadcast Scheduler</h2>
        <p class="section-desc">Inject custom time blocks directly into the Electronic Program Guide.</p>

        <form class="scheduler-form" id="form-inject-epg">
          <div class="form-row">
            <div class="form-group">
              <label for="sched-channel">Channel Target</label>
              <select id="sched-channel" required>
                ${CHANNELS.map(ch => `<option value="${ch.id}">${ch.name}</option>`).join("")}
              </select>
            </div>
            <div class="form-group">
              <label for="sched-genre">Genre</label>
              <select id="sched-genre" required>
                <option value="News">News</option>
                <option value="Sports">Sports</option>
                <option value="Documentary">Documentary</option>
                <option value="Entertainment">Entertainment</option>
              </select>
            </div>
          </div>

          <div class="form-row">
            <div class="form-group">
              <label for="sched-title">Program Title</label>
              <input type="text" id="sched-title" placeholder="e.g. Live Prime Debate" required>
            </div>
            <div class="form-group">
              <label for="sched-start">Start Time</label>
              <input type="time" id="sched-start" value="16:30" required>
            </div>
            <div class="form-group">
              <label for="sched-duration">Duration (mins)</label>
              <input type="number" id="sched-duration" value="60" min="5" max="300" required>
            </div>
          </div>

          <div class="form-group">
            <label for="sched-desc">Program Description</label>
            <textarea id="sched-desc" placeholder="Brief outline of topics, hosts, and guest panels..." rows="2" required></textarea>
          </div>

          <button type="submit" class="submit-btn">SCHEDULE BROADCAST BLOCK</button>
        </form>
      </div>

      <!-- Viewer Preferences & Account Console -->
      <div class="control-section glass-card preferences-panel">
        <h2 class="section-title"><span class="icon">⚙️</span> Viewer Preferences & Account Console</h2>
        <p class="section-desc">Manage system preferences, configure theme skin repainters, and adjust connection presets with localStorage memory persistence.</p>

        <div class="preferences-form" style="display: flex; flex-direction: column; gap: 16px;">
          <!-- Theme Skin Selection -->
          <div class="form-group">
            <label style="font-size: 11px; font-weight: 600; color: rgba(255, 255, 255, 0.5); letter-spacing: 0.5px; margin-bottom: 6px;">Select Site-Wide Brand Skin</label>
            <div class="theme-select-grid" style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px;">
              <button type="button" class="theme-btn" data-theme-id="red" style="padding: 8px 4px; font-size: 11px; font-weight: 600; border-radius: 4px; border: 1px solid rgba(255,255,255,0.08); background: rgba(255,255,255,0.02); color: #ffffff; cursor: pointer; transition: all 0.2s ease; display: flex; align-items: center; justify-content: center; gap: 4px;"><span style="width: 8px; height: 8px; background: hsl(348 100% 58%); border-radius: 50%; display: inline-block;"></span> Cyber</button>
              <button type="button" class="theme-btn" data-theme-id="blue" style="padding: 8px 4px; font-size: 11px; font-weight: 600; border-radius: 4px; border: 1px solid rgba(255,255,255,0.08); background: rgba(255,255,255,0.02); color: #ffffff; cursor: pointer; transition: all 0.2s ease; display: flex; align-items: center; justify-content: center; gap: 4px;"><span style="width: 8px; height: 8px; background: hsl(210 100% 55%); border-radius: 50%; display: inline-block;"></span> Space</button>
              <button type="button" class="theme-btn" data-theme-id="green" style="padding: 8px 4px; font-size: 11px; font-weight: 600; border-radius: 4px; border: 1px solid rgba(255,255,255,0.08); background: rgba(255,255,255,0.02); color: #ffffff; cursor: pointer; transition: all 0.2s ease; display: flex; align-items: center; justify-content: center; gap: 4px;"><span style="width: 8px; height: 8px; background: hsl(145 100% 48%); border-radius: 50%; display: inline-block;"></span> Aurora</button>
              <button type="button" class="theme-btn" data-theme-id="gold" style="padding: 8px 4px; font-size: 11px; font-weight: 600; border-radius: 4px; border: 1px solid rgba(255,255,255,0.08); background: rgba(255,255,255,0.02); color: #ffffff; cursor: pointer; transition: all 0.2s ease; display: flex; align-items: center; justify-content: center; gap: 4px;"><span style="width: 8px; height: 8px; background: hsl(40 100% 52%); border-radius: 50%; display: inline-block;"></span> Royal</button>
            </div>
          </div>

          <!-- Volume Default -->
          <div class="form-group">
            <label for="pref-volume-slider" style="font-size: 11px; font-weight: 600; color: rgba(255, 255, 255, 0.5); letter-spacing: 0.5px;">Default Audio Volume (<span id="pref-volume-val">80</span>%)</label>
            <div style="display: flex; align-items: center; gap: 12px;">
              <span style="font-size: 14px;">🔈</span>
              <input type="range" id="pref-volume-slider" min="0" max="100" value="80" style="flex-grow: 1; -webkit-appearance: none; appearance: none; background: rgba(255,255,255,0.1); height: 4px; border-radius: 2px; outline: none; cursor: pointer; accent-color: var(--brand-primary);">
              <span style="font-size: 14px;">🔊</span>
            </div>
          </div>

          <!-- Quality default -->
          <div class="form-group">
            <label for="pref-quality-select" style="font-size: 11px; font-weight: 600; color: rgba(255, 255, 255, 0.5); letter-spacing: 0.5px;">Default Streaming Downlink Resolution</label>
            <select id="pref-quality-select" style="background: rgba(0,0,0,0.2); border: 1px solid rgba(255,255,255,0.08); border-radius: 6px; padding: 8px 12px; font-size: 12px; outline: none; color: #ffffff; width: 100%;">
              <option value="1080p">1080p Full HD (60 FPS)</option>
              <option value="720p">720p HD Ready (60 FPS)</option>
              <option value="480p">480p SD Mobile (30 FPS)</option>
            </select>
          </div>
        </div>
      </div>

      <!-- RTMP Multi-Destination Stream Splitter & Scheduler Console -->
      <div class="splitter-card glass-card">
        <h2 class="section-title"><span class="icon">📡</span> GNTV DIGITAL, ALL EVERYWHERE Enterprise Stream Splitter Console</h2>
        <p class="section-desc">Broadcast your primary feed or scheduled local playlist to 3 YouTube channels simultaneously with real-time failover multiplexing.</p>

        <!-- Ingest Mode Selector Pills -->
        <div style="display: flex; gap: 8px; margin-bottom: 20px; background: rgba(255,255,255,0.03); padding: 4px; border-radius: 8px; border: 1px solid rgba(255,255,255,0.05); width: fit-content;">
          <button type="button" class="fx-btn active" id="btn-mode-relay" style="padding: 6px 16px; font-size: 11px; font-weight: 700; border-radius: 6px; border: none; cursor: pointer; transition: all 0.2s ease;">📡 Studio Live Relay</button>
          <button type="button" class="fx-btn" id="btn-mode-playlist" style="padding: 6px 16px; font-size: 11px; font-weight: 700; border-radius: 6px; border: none; cursor: pointer; transition: all 0.2s ease;">📂 Playlist Concat Loop</button>
        </div>

        <div class="splitter-layout">
          <!-- Left: Configurations & Script Generator -->
          <div style="display: flex; flex-direction: column; gap: 20px;">

            <!-- Ingest Settings Form -->
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 16px;">

              <!-- Source URL (Show when Mode is Live Relay) -->
              <div class="splitter-form-group" id="group-source-url" style="grid-column: 1 / -1;">
                <label class="splitter-label" for="split-source-url">Alibaba Cloud Studio Ingest URL</label>
                <input type="text" id="split-source-url" class="splitter-input" value="rtmp://your-alibaba-cloud-ip/live/gntv_main">
              </div>

              <!-- Playlist File & Remote Hosts (Show when Mode is Playlist Loop) -->
              <div class="splitter-form-group" id="group-playlist-file" style="grid-column: 1 / -1; display: none;">
                <label class="splitter-label" for="split-playlist-path">Concat Playlist Path ('/opt/gntv/playlist.txt')</label>
                <input type="text" id="split-playlist-path" class="splitter-input" value="/opt/gntv/playlist.txt">
              </div>

              <div class="splitter-form-group" id="group-remote-hosts" style="grid-column: 1 / -1; display: none;">
                <label class="splitter-label" for="split-remote-hosts">Asset Origin Protocol Whitelist</label>
                <input type="text" id="split-remote-hosts" class="splitter-input" value="file,http,https,tcp,tls">
              </div>

              <!-- Platform Preset -->
              <div class="splitter-form-group">
                <label class="splitter-label" for="split-platform">Destination Platform</label>
                <select id="split-platform" class="splitter-select">
                  <option value="youtube" selected>YouTube Live (RTMP/S)</option>
                  <option value="facebook">Facebook Live (RTMPS)</option>
                  <option value="custom">Custom RTMP Endpoint</option>
                </select>
              </div>

              <!-- Dest URL -->
              <div class="splitter-form-group">
                <label class="splitter-label" id="label-dest-url" for="split-dest-url">Platform Ingest Server URL</label>
                <input type="text" id="split-dest-url" class="splitter-input" value="rtmp://a.rtmp.youtube.com/live2">
              </div>

              <!-- Stream Key 1 -->
              <div class="splitter-form-group">
                <label class="splitter-label" id="label-key-1" for="split-key-1">YT Somali Core Stream Key</label>
                <input type="text" id="split-key-1" class="splitter-input" value="aaaa-bbbb-cccc-dddd-eeee">
              </div>

              <!-- Stream Key 2 -->
              <div class="splitter-form-group">
                <label class="splitter-label" id="label-key-2" for="split-key-2">YT Kiswahili Stream Key</label>
                <input type="text" id="split-key-2" class="splitter-input" value="ffff-gggg-hhhh-iiii-jjjj">
              </div>

              <!-- Stream Key 3 -->
              <div class="splitter-form-group" style="grid-column: 1 / -1;">
                <label class="splitter-label" id="label-key-3" for="split-key-3">YT Sports & Culture Stream Key</label>
                <input type="text" id="split-key-3" class="splitter-input" value="kkkk-llll-mmmm-nnnn-oooo">
              </div>
            </div>

            <!-- Terminal script display -->
            <div class="terminal-window">
              <div class="terminal-header">
                <div class="terminal-dots">
                  <span class="terminal-dot red"></span>
                  <span class="terminal-dot yellow"></span>
                  <span class="terminal-dot green"></span>
                </div>
                <span class="terminal-title">gntv-splitter-engine (~/restream.sh)</span>
                <span style="font-size: 10px; color: rgba(255,255,255,0.2); font-family: var(--font-mono);">BASH</span>
              </div>
              <pre class="terminal-body" id="shell-script-body" style="white-space: pre-wrap; word-break: break-all; margin: 0;"></pre>
            </div>

            <!-- Quick Action Row -->
            <div class="splitter-actions-row">
              <button type="button" id="btn-toggle-splitter-sim" class="splitter-btn-primary">
                <span id="sim-btn-icon">⚡</span> <span id="sim-btn-text">Start Simulated Splitter</span>
              </button>
              <button type="button" id="btn-copy-splitter-script" class="splitter-btn-secondary">
                📋 Copy Script
              </button>
              <button type="button" id="btn-download-splitter-script" class="splitter-btn-secondary">
                💾 Download '.sh'
              </button>
            </div>

          </div>

          <!-- Right: Visual Diagram, Telemetry Status, Scrolling Logs -->
          <div style="display: flex; flex-direction: column; gap: 20px;">

            <!-- Pipeline Flow Diagram -->
            <div class="pipeline-container">
              <span class="splitter-label" style="margin-bottom: -10px;">Visual Live Stream Pipeline Flow</span>
              <div class="pipeline-diagram">

                <svg class="pipeline-flow-svg">
                  <!-- Studio/Playlist to Cloud/Engine -->
                  <path id="path-studio-cloud" class="pipeline-path" d="M 38 60 H 130" />
                  <path id="path-cloud-splitter" class="pipeline-path" d="M 130 60 H 222" />

                  <!-- Outputs branches -->
                  <path id="path-splitter-yt1" class="pipeline-path" d="M 222 60 Q 260 15, 306 20" />
                  <path id="path-splitter-yt2" class="pipeline-path" d="M 222 60 H 306" />
                  <path id="path-splitter-yt3" class="pipeline-path" d="M 222 60 Q 260 105, 306 100" />
                </svg>

                <div class="pipeline-node source" id="node-studio">
                  <span class="pipeline-node-icon" id="node-studio-icon">🎙️</span>
                  <span class="pipeline-node-label" id="node-studio-label">Live Ingest</span>
                </div>

                <div class="pipeline-node" id="node-cloud">
                  <span class="pipeline-node-icon" id="node-cloud-icon">☁️</span>
                  <span class="pipeline-node-label" id="node-cloud-label">Alibaba Cloud</span>
                </div>

                <div class="pipeline-node engine" id="node-engine">
                  <span class="pipeline-node-icon">⚙️</span>
                  <span class="pipeline-node-label">FFmpeg Engine</span>
                </div>

                <div class="pipeline-node" id="node-outputs">
                  <span class="pipeline-node-icon">📺</span>
                  <span class="pipeline-node-label">Outputs Hub</span>
                </div>

              </div>
            </div>

            <!-- Destinations Grid -->
            <div class="splitter-destinations-grid">

              <!-- Somali Card -->
              <div class="dest-status-card" id="dest-card-1">
                <div class="dest-header">
                  <div class="dest-title-wrap">
                    <span class="status-indicator-dot offline" id="dest-dot-1"></span>
                    <div>
                      <div class="dest-title" id="dest-title-1">Somali Channel</div>
                      <div class="dest-subtitle" id="dest-sub-1">YouTube Live</div>
                    </div>
                  </div>
                </div>
                <div class="dest-telemetry-row">
                  <div class="dest-telemetry-item">
                    <span class="dest-tel-label">Bitrate</span>
                    <span class="dest-tel-value" id="dest-bitrate-1">0.0 Mbps</span>
                  </div>
                  <div class="dest-telemetry-item">
                    <span class="dest-tel-label">Latency</span>
                    <span class="dest-tel-value" id="dest-latency-1">0ms</span>
                  </div>
                </div>
                <div class="dest-actions">
                  <button type="button" class="dest-btn-toggle" id="btn-toggle-dest-1" disabled>
                    🚫 Drop Stream
                  </button>
                </div>
              </div>

              <!-- Kiswahili Card -->
              <div class="dest-status-card" id="dest-card-2">
                <div class="dest-header">
                  <div class="dest-title-wrap">
                    <span class="status-indicator-dot offline" id="dest-dot-2"></span>
                    <div>
                      <div class="dest-title" id="dest-title-2">Kiswahili Channel</div>
                      <div class="dest-subtitle" id="dest-sub-2">YouTube Live</div>
                    </div>
                  </div>
                </div>
                <div class="dest-telemetry-row">
                  <div class="dest-telemetry-item">
                    <span class="dest-tel-label">Bitrate</span>
                    <span class="dest-tel-value" id="dest-bitrate-2">0.0 Mbps</span>
                  </div>
                  <div class="dest-telemetry-item">
                    <span class="dest-tel-label">Latency</span>
                    <span class="dest-tel-value" id="dest-latency-2">0ms</span>
                  </div>
                </div>
                <div class="dest-actions">
                  <button type="button" class="dest-btn-toggle" id="btn-toggle-dest-2" disabled>
                    🚫 Drop Stream
                  </button>
                </div>
              </div>

              <!-- Sports Card -->
              <div class="dest-status-card" id="dest-card-3">
                <div class="dest-header">
                  <div class="dest-title-wrap">
                    <span class="status-indicator-dot offline" id="dest-dot-3"></span>
                    <div>
                      <div class="dest-title" id="dest-title-3">Sports Channel</div>
                      <div class="dest-subtitle" id="dest-sub-3">YouTube Live</div>
                    </div>
                  </div>
                </div>
                <div class="dest-telemetry-row">
                  <div class="dest-telemetry-item">
                    <span class="dest-tel-label">Bitrate</span>
                    <span class="dest-tel-value" id="dest-bitrate-3">0.0 Mbps</span>
                  </div>
                  <div class="dest-telemetry-item">
                    <span class="dest-tel-label">Latency</span>
                    <span class="dest-tel-value" id="dest-latency-3">0ms</span>
                  </div>
                </div>
                <div class="dest-actions">
                  <button type="button" class="dest-btn-toggle" id="btn-toggle-dest-3" disabled>
                    🚫 Drop Stream
                  </button>
                </div>
              </div>

            </div>

            <!-- Telemetry Output Logs -->
            <div style="display: flex; flex-direction: column; gap: 4px;">
              <span class="splitter-label">Broadcaster Stream Signal Engine Logs</span>
              <div class="terminal-live-logs" id="splitter-terminal-logs">
                <div class="log-line info">Restreamer simulator is IDLE. Click "Start Simulated Splitter" to spin up the local dual-codec pipeline.</div>
              </div>
            </div>

          </div>
        </div>

      </div>

    </div>
  `;

  const camGrid = container.querySelector("#mixer-cam-grid");
  const alertInput = container.querySelector("#input-alert-msg");
  const alertBtn = container.querySelector("#btn-trigger-alert");
  const formEpg = container.querySelector("#form-inject-epg");
  const analyticsCanvas = container.querySelector("#analytics-canvas");
  const analyticsCtx = analyticsCanvas.getContext("2d");

  const statViewerCount = container.querySelector("#stat-viewer-count");

  // New Live FX Panel DOM Queries
  const checkPipActive = container.querySelector("#check-pip-active");
  const selectPipCamera = container.querySelector("#select-pip-camera");
  const checkScrollActive = container.querySelector("#check-scroll-active");
  const inputScrollText = container.querySelector("#input-scroll-text");
  const btnUpdateScroll = container.querySelector("#btn-update-scroll");
  const fxBtns = container.querySelectorAll(".fx-btn");

  // New Preferences Panel DOM Queries
  const themeBtns = container.querySelectorAll(".theme-btn");
  const prefVolumeSlider = container.querySelector("#pref-volume-slider");
  const prefVolumeVal = container.querySelector("#pref-volume-val");
  const prefQualitySelect = container.querySelector("#pref-quality-select");

  // 1. Populate camera list based on active Channel
  const renderCameras = (channel) => {
    camGrid.innerHTML = channel.cameras.map(cam => {
      const activeCam = store.getState("activeCamera");
      const isSelected = activeCam.id === cam.id;
      return `
        <button class="camera-card ${isSelected ? 'active' : ''}" data-cam-id="${cam.id}">
          <div class="cam-lens">📹</div>
          <div class="cam-info">
            <span class="cam-name">${cam.name}</span>
            <span class="cam-type">${cam.feedType.toUpperCase()} MODE</span>
          </div>
          <span class="cam-active-dot"></span>
        </button>
      `;
    }).join("");

    // Camera selector clicks
    const camButtons = camGrid.querySelectorAll(".camera-card");
    camButtons.forEach(btn => {
      btn.addEventListener("click", () => {
        const camId = btn.getAttribute("data-cam-id");
        const foundCam = channel.cameras.find(c => c.id === camId);
        if (foundCam) {
          store.setState("activeCamera", foundCam);
        }
      });
    });
  };

  // PiP secondary camera select dropdown populator
  const updatePipDropdown = (channel) => {
    if (!selectPipCamera) return;
    const activeCam = store.getState("activeCamera") || {};

    selectPipCamera.innerHTML = channel.cameras.map(cam => {
      const isPrimary = cam.id === activeCam.id;
      return `<option value="${cam.id}" ${isPrimary ? 'disabled style="color: rgba(255,255,255,0.25)"' : ''}>${cam.name} (${cam.feedType.toUpperCase()}) ${isPrimary ? '[PRIMARY]' : ''}</option>`;
    }).join("");

    const currentPipId = store.getState("pipCameraId");
    if (currentPipId === activeCam.id) {
      const nonPrimary = channel.cameras.find(c => c.id !== activeCam.id);
      if (nonPrimary) {
        store.setState("pipCameraId", nonPrimary.id);
        selectPipCamera.value = nonPrimary.id;
      }
    } else {
      selectPipCamera.value = currentPipId || channel.cameras[1]?.id || channel.cameras[0].id;
    }
  };

  // Listen to activeChannel and activeCamera updates
  store.subscribe("activeChannel", (ch) => {
    renderCameras(ch);
    updatePipDropdown(ch);
  });

  store.subscribe("activeCamera", () => {
    // Re-render to update the active class
    const activeCh = store.getState("activeChannel");
    renderCameras(activeCh);
    updatePipDropdown(activeCh);
  });

  // FX controls event handlers
  fxBtns.forEach(btn => {
    btn.addEventListener("click", () => {
      const filter = btn.getAttribute("data-fx-filter");
      store.setState("chromaKeyFilter", filter);

      fxBtns.forEach(b => {
        if (b.getAttribute("data-fx-filter") === filter) {
          b.classList.add("active");
          b.style.borderColor = "var(--brand-primary)";
          b.style.background = "rgba(255, 42, 75, 0.08)";
          b.style.color = "var(--brand-primary)";
          b.style.boxShadow = "0 0 10px rgba(255, 42, 75, 0.1)";
        } else {
          b.classList.remove("active");
          b.style.borderColor = "rgba(255,255,255,0.08)";
          b.style.background = "rgba(255,255,255,0.02)";
          b.style.color = "#ffffff";
          b.style.boxShadow = "none";
        }
      });
    });
  });

  checkPipActive.addEventListener("change", (e) => {
    store.setState("pipActive", e.target.checked);
  });

  selectPipCamera.addEventListener("change", (e) => {
    store.setState("pipCameraId", e.target.value);
  });

  checkScrollActive.addEventListener("change", (e) => {
    store.setState("canvasScrollActive", e.target.checked);
  });

  const applyCrawlText = () => {
    const text = inputScrollText.value.trim();
    if (text) {
      store.setState("canvasScrollText", text);
      alert(`Success: Lower-third caption updated to: "${text}"`);
    }
  };
  btnUpdateScroll.addEventListener("click", applyCrawlText);
  inputScrollText.addEventListener("keypress", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      applyCrawlText();
    }
  });

  // Sync initial state of new FX elements
  const syncFxPanelState = () => {
    const filter = store.getState("chromaKeyFilter") || "none";
    fxBtns.forEach(b => {
      if (b.getAttribute("data-fx-filter") === filter) {
        b.classList.add("active");
        b.style.borderColor = "var(--brand-primary)";
        b.style.background = "rgba(255, 42, 75, 0.08)";
        b.style.color = "var(--brand-primary)";
        b.style.boxShadow = "0 0 10px rgba(255, 42, 75, 0.1)";
      } else {
        b.classList.remove("active");
        b.style.borderColor = "rgba(255,255,255,0.08)";
        b.style.background = "rgba(255,255,255,0.02)";
        b.style.color = "#ffffff";
        b.style.boxShadow = "none";
      }
    });

    checkPipActive.checked = store.getState("pipActive");
    checkScrollActive.checked = store.getState("canvasScrollActive");
    inputScrollText.value = store.getState("canvasScrollText") || "";

    const activeCh = store.getState("activeChannel");
    updatePipDropdown(activeCh);
  };
  syncFxPanelState();

  // 3b. Preferences controls event handlers
  themeBtns.forEach(btn => {
    btn.addEventListener("click", () => {
      const themeId = btn.getAttribute("data-theme-id");
      store.savePreference("prefTheme", themeId);

      themeBtns.forEach(b => {
        if (b.getAttribute("data-theme-id") === themeId) {
          b.classList.add("active");
          b.style.borderColor = "var(--brand-primary)";
          b.style.background = "rgba(255, 42, 75, 0.08)";
          b.style.color = "var(--brand-primary)";
          b.style.boxShadow = "0 0 10px rgba(255, 42, 75, 0.1)";
        } else {
          b.classList.remove("active");
          b.style.borderColor = "rgba(255,255,255,0.08)";
          b.style.background = "rgba(255,255,255,0.02)";
          b.style.color = "#ffffff";
          b.style.boxShadow = "none";
        }
      });
    });
  });

  prefVolumeSlider.addEventListener("input", (e) => {
    const val = parseInt(e.target.value, 10);
    prefVolumeVal.textContent = val;
    store.savePreference("prefVolume", val);
  });

  prefQualitySelect.addEventListener("change", (e) => {
    const val = e.target.value;
    store.savePreference("prefQuality", val);
  });

  // Sync initial state of Preferences
  const syncPreferencesPanelState = () => {
    const themeId = store.getState("prefTheme") || "red";
    themeBtns.forEach(b => {
      if (b.getAttribute("data-theme-id") === themeId) {
        b.classList.add("active");
        b.style.borderColor = "var(--brand-primary)";
        b.style.background = "rgba(255, 42, 75, 0.08)";
        b.style.color = "var(--brand-primary)";
        b.style.boxShadow = "0 0 10px rgba(255, 42, 75, 0.1)";
      } else {
        b.classList.remove("active");
        b.style.borderColor = "rgba(255,255,255,0.08)";
        b.style.background = "rgba(255,255,255,0.02)";
        b.style.color = "#ffffff";
        b.style.boxShadow = "none";
      }
    });

    const vol = store.getState("prefVolume") || 80;
    prefVolumeSlider.value = vol;
    prefVolumeVal.textContent = vol;

    prefQualitySelect.value = store.getState("prefQuality") || "1080p";
  };
  syncPreferencesPanelState();

  // 2. Emergency Alert Broadcast System (EABS) Toggle
  alertBtn.addEventListener("click", () => {
    const isAlerting = store.getState("emergencyAlert").active;
    if (isAlerting) {
      // Turn Off
      audioAlert.stop();
      store.clearEmergencyAlert();
    } else {
      // Turn On
      const msg = alertInput.value.trim() || "CRITICAL EMERGENCY BROADCAST OVERRIDE";
      audioAlert.start(); // synthesizes audio dual-tone
      store.triggerEmergencyAlert(msg);
    }
  });

  store.subscribe("emergencyAlert", (alertState) => {
    if (alertState.active) {
      alertBtn.textContent = "SILENCE EMERGENCY ALARM";
      alertBtn.classList.add("danger-pulsing");
    } else {
      alertBtn.textContent = "TRIGGER BROADCAST ALARM";
      alertBtn.classList.remove("danger-pulsing");
    }
  });

  // 3. EPG Program Injector Form submit
  formEpg.addEventListener("submit", (e) => {
    e.preventDefault();
    const chId = container.querySelector("#sched-channel").value;
    const title = container.querySelector("#sched-title").value;
    const start = container.querySelector("#sched-start").value;
    const duration = parseInt(container.querySelector("#sched-duration").value, 10);
    const genre = container.querySelector("#sched-genre").value;
    const description = container.querySelector("#sched-desc").value;

    const newProgram = { title, start, duration, genre, description };
    store.addScheduledProgram(chId, newProgram);

    // Toast Alert feedback
    alert(`Success: Scheduled "${title}" at ${start} on ${chId}!`);
    formEpg.reset();
  });

  // 4. Bandwidth / Viewership Canvas Real-time Graphing
  const dataPoints = Array(20).fill(8.2); // seed
  let animId = null;

  const drawTelemetryChart = () => {
    const w = analyticsCanvas.width;
    const h = analyticsCanvas.height;

    analyticsCtx.clearRect(0, 0, w, h);

    // Draw Gridlines
    analyticsCtx.strokeStyle = "rgba(255, 255, 255, 0.05)";
    analyticsCtx.lineWidth = 1;
    for (let x = 0; x < w; x += 40) {
      analyticsCtx.beginPath();
      analyticsCtx.moveTo(x, 0);
      analyticsCtx.lineTo(x, h);
      analyticsCtx.stroke();
    }
    for (let y = 0; y < h; y += 30) {
      analyticsCtx.beginPath();
      analyticsCtx.moveTo(0, y);
      analyticsCtx.lineTo(w, y);
      analyticsCtx.stroke();
    }

    // Capture latest bitrate value
    const rawBitrate = parseFloat(store.getState("bitrate"));
    dataPoints.push(rawBitrate);
    if (dataPoints.length > 22) dataPoints.shift();

    // Plot Bezier path
    analyticsCtx.strokeStyle = "rgba(255, 42, 75, 0.85)";
    analyticsCtx.lineWidth = 3;

    // Create subtle glow below line
    analyticsCtx.shadowColor = "rgba(255, 42, 75, 0.5)";
    analyticsCtx.shadowBlur = 8;

    analyticsCtx.beginPath();
    const mapY = (val) => h - ((val - 4) / 6) * h; // map 4Mbps - 10Mbps to height

    analyticsCtx.moveTo(0, mapY(dataPoints[0]));

    for (let i = 1; i < dataPoints.length; i++) {
      const x1 = ((i - 1) / (dataPoints.length - 1)) * w;
      const y1 = mapY(dataPoints[i - 1]);
      const x2 = (i / (dataPoints.length - 1)) * w;
      const y2 = mapY(dataPoints[i]);

      const xc = (x1 + x2) / 2;
      analyticsCtx.quadraticCurveTo(x1, y1, xc, (y1 + y2) / 2);
    }

    analyticsCtx.stroke();

    // Reset shadow
    analyticsCtx.shadowColor = "transparent";
    analyticsCtx.shadowBlur = 0;

    // Fill area below graph
    analyticsCtx.fillStyle = "rgba(255, 42, 75, 0.08)";
    analyticsCtx.beginPath();
    analyticsCtx.moveTo(0, h);
    analyticsCtx.lineTo(0, mapY(dataPoints[0]));
    for (let i = 1; i < dataPoints.length; i++) {
      const x1 = ((i - 1) / (dataPoints.length - 1)) * w;
      const y2 = mapY(dataPoints[i]);
      analyticsCtx.lineTo(x1, y2);
    }
    analyticsCtx.lineTo(w, h);
    analyticsCtx.closePath();
    analyticsCtx.fill();

    // Draw active dot at the end
    const lastX = w;
    const lastY = mapY(dataPoints[dataPoints.length - 1]);
    analyticsCtx.fillStyle = "#ff2a4b";
    analyticsCtx.beginPath();
    analyticsCtx.arc(lastX - 5, lastY, 5, 0, 2 * Math.PI);
    analyticsCtx.fill();

    // Label highest point
    analyticsCtx.fillStyle = "rgba(255, 255, 255, 0.6)";
    analyticsCtx.font = "9px monospace";
    analyticsCtx.fillText(`${rawBitrate.toFixed(1)} Mbps`, w - 70, lastY - 8);

    // Refresh Viewer Count
    statViewerCount.textContent = store.getState("viewerCount").toLocaleString();

    animId = setTimeout(drawTelemetryChart, 300);
  };

  // ==========================================================================
  // GNTV DIGITAL, ALL EVERYWHERE MULTI-DESTINATION STREAM SPLITTER LOGIC & EVENT CONTROLLERS
  // ==========================================================================

  let activeIngestMode = "relay"; // "relay" or "playlist"
  let splitterIsSimulating = false;
  let splitterLogInterval = null;
  let splitterTelemetryInterval = null;
  let splitterDestActive = [true, true, true]; // Target 1, Target 2, Target 3 active states

  // HTML Elements Queries
  const btnModeRelay = container.querySelector("#btn-mode-relay");
  const btnModePlaylist = container.querySelector("#btn-mode-playlist");

  const groupSourceUrl = container.querySelector("#group-source-url");
  const groupPlaylistFile = container.querySelector("#group-playlist-file");
  const groupRemoteHosts = container.querySelector("#group-remote-hosts");

  const inputSourceUrl = container.querySelector("#split-source-url");
  const inputPlaylistPath = container.querySelector("#split-playlist-path");
  const inputRemoteHosts = container.querySelector("#split-remote-hosts");

  const selectPlatform = container.querySelector("#split-platform");
  const inputDestUrl = container.querySelector("#split-dest-url");
  const labelDestUrl = container.querySelector("#label-dest-url");

  const labelKey1 = container.querySelector("#label-key-1");
  const labelKey2 = container.querySelector("#label-key-2");
  const labelKey3 = container.querySelector("#label-key-3");

  const inputKey1 = container.querySelector("#split-key-1");
  const inputKey2 = container.querySelector("#split-key-2");
  const inputKey3 = container.querySelector("#split-key-3");

  const shellScriptBody = container.querySelector("#shell-script-body");

  const btnToggleSim = container.querySelector("#btn-toggle-splitter-sim");
  const simBtnText = container.querySelector("#sim-btn-text");
  const simBtnIcon = container.querySelector("#sim-btn-icon");
  const btnCopyScript = container.querySelector("#btn-copy-splitter-script");
  const btnDownloadScript = container.querySelector("#btn-download-splitter-script");

  const logsContainer = container.querySelector("#splitter-terminal-logs");

  // SVG paths & Diagram elements
  const pathStudioCloud = container.querySelector("#path-studio-cloud");
  const pathCloudSplitter = container.querySelector("#path-cloud-splitter");
  const pathSplitterYt1 = container.querySelector("#path-splitter-yt1");
  const pathSplitterYt2 = container.querySelector("#path-splitter-yt2");
  const pathSplitterYt3 = container.querySelector("#path-splitter-yt3");

  const nodeStudio = container.querySelector("#node-studio");
  const nodeStudioIcon = container.querySelector("#node-studio-icon");
  const nodeStudioLabel = container.querySelector("#node-studio-label");
  const nodeCloud = container.querySelector("#node-cloud");
  const nodeCloudIcon = container.querySelector("#node-cloud-icon");
  const nodeCloudLabel = container.querySelector("#node-cloud-label");
  const nodeEngine = container.querySelector("#node-engine");
  const nodeOutputs = container.querySelector("#node-outputs");

  // Channels status
  const destDot1 = container.querySelector("#dest-dot-1");
  const destDot2 = container.querySelector("#dest-dot-2");
  const destDot3 = container.querySelector("#dest-dot-3");

  const destTitle1 = container.querySelector("#dest-title-1");
  const destTitle2 = container.querySelector("#dest-title-2");
  const destTitle3 = container.querySelector("#dest-title-3");

  const destSub1 = container.querySelector("#dest-sub-1");
  const destSub2 = container.querySelector("#dest-sub-2");
  const destSub3 = container.querySelector("#dest-sub-3");

  const destBitrate1 = container.querySelector("#dest-bitrate-1");
  const destBitrate2 = container.querySelector("#dest-bitrate-2");
  const destBitrate3 = container.querySelector("#dest-bitrate-3");

  const destLatency1 = container.querySelector("#dest-latency-1");
  const destLatency2 = container.querySelector("#dest-latency-2");
  const destLatency3 = container.querySelector("#dest-latency-3");

  const btnToggleDest1 = container.querySelector("#btn-toggle-dest-1");
  const btnToggleDest2 = container.querySelector("#btn-toggle-dest-2");
  const btnToggleDest3 = container.querySelector("#btn-toggle-dest-3");

  const destCard1 = container.querySelector("#dest-card-1");
  const destCard2 = container.querySelector("#dest-card-2");
  const destCard3 = container.querySelector("#dest-card-3");

  // Ingest Mode Toggle Event Listeners
  btnModeRelay.addEventListener("click", () => {
    activeIngestMode = "relay";
    btnModeRelay.classList.add("active");
    btnModeRelay.style.background = "var(--brand-primary)";
    btnModeRelay.style.color = "#ffffff";
    btnModePlaylist.classList.remove("active");
    btnModePlaylist.style.background = "transparent";
    btnModePlaylist.style.color = "rgba(255,255,255,0.6)";

    groupSourceUrl.style.display = "flex";
    groupPlaylistFile.style.display = "none";
    groupRemoteHosts.style.display = "none";

    nodeStudioIcon.textContent = "🎙️";
    nodeStudioLabel.textContent = "Live Ingest";
    nodeCloudIcon.textContent = "☁️";
    nodeCloudLabel.textContent = "Alibaba Cloud";

    updateShellScript();
    if (splitterIsSimulating) stopSplitterSimulation();
  });

  btnModePlaylist.addEventListener("click", () => {
    activeIngestMode = "playlist";
    btnModePlaylist.classList.add("active");
    btnModePlaylist.style.background = "var(--brand-primary)";
    btnModePlaylist.style.color = "#ffffff";
    btnModeRelay.classList.remove("active");
    btnModeRelay.style.background = "transparent";
    btnModeRelay.style.color = "rgba(255,255,255,0.6)";

    groupSourceUrl.style.display = "none";
    groupPlaylistFile.style.display = "flex";
    groupRemoteHosts.style.display = "flex";

    nodeStudioIcon.textContent = "📂";
    nodeStudioLabel.textContent = "playlist.txt";
    nodeCloudIcon.textContent = "☁️";
    nodeCloudLabel.textContent = "Alibaba OSS";

    updateShellScript();
    if (splitterIsSimulating) stopSplitterSimulation();
  });

  // Platform Selector Event Listener
  selectPlatform.addEventListener("change", () => {
    const val = selectPlatform.value;
    if (val === "youtube") {
      inputDestUrl.value = "rtmp://a.rtmp.youtube.com/live2";
      labelDestUrl.textContent = "Platform Ingest Server URL";

      labelKey1.textContent = "YT Somali Core Stream Key";
      labelKey2.textContent = "YT Kiswahili Stream Key";
      labelKey3.textContent = "YT Sports & Culture Stream Key";

      destTitle1.textContent = "Somali Channel";
      destTitle2.textContent = "Kiswahili Channel";
      destTitle3.textContent = "Sports Channel";

      destSub1.textContent = "YouTube Live";
      destSub2.textContent = "YouTube Live";
      destSub3.textContent = "YouTube Live";
    } else if (val === "facebook") {
      inputDestUrl.value = "rtmps://live-api-s.facebook.com:443/rtmp/";
      labelDestUrl.textContent = "Facebook Live Ingestion Server URL";

      labelKey1.textContent = "FB Somali Core Stream Key";
      labelKey2.textContent = "FB Kiswahili Stream Key";
      labelKey3.textContent = "FB Sports & Culture Stream Key";

      destTitle1.textContent = "Somali Core";
      destTitle2.textContent = "Kiswahili Core";
      destTitle3.textContent = "Sports Core";

      destSub1.textContent = "Facebook Live";
      destSub2.textContent = "Facebook Live";
      destSub3.textContent = "Facebook Live";
    } else {
      inputDestUrl.value = "rtmp://your-custom-ingest-domain/live/";
      labelDestUrl.textContent = "Custom Ingest Ingestion Server URL";

      labelKey1.textContent = "Destination 1 Stream Key";
      labelKey2.textContent = "Destination 2 Stream Key";
      labelKey3.textContent = "Destination 3 Stream Key";

      destTitle1.textContent = "Destination 1";
      destTitle2.textContent = "Destination 2";
      destTitle3.textContent = "Destination 3";

      destSub1.textContent = "Custom RTMP";
      destSub2.textContent = "Custom RTMP";
      destSub3.textContent = "Custom RTMP";
    }
    updateShellScript();
  });

  // Live bindings for inputs to update the shell script view
  [inputSourceUrl, inputPlaylistPath, inputRemoteHosts, inputDestUrl, inputKey1, inputKey2, inputKey3].forEach(input => {
    input.addEventListener("input", updateShellScript);
  });

  // Dynamic Shell Script Generation with HTML Syntax Coloring
  function updateShellScript() {
    const sourceUrl = inputSourceUrl.value.trim();
    const playlistPath = inputPlaylistPath.value.trim();
    const whitelist = inputRemoteHosts.value.trim();
    const destServer = inputDestUrl.value.trim();

    const key1 = inputKey1.value.trim();
    const key2 = inputKey2.value.trim();
    const key3 = inputKey3.value.trim();

    let htmlContent = "";

    // Header block
    htmlContent += `<span class="term-comm">#!/bin/bash</span>\n\n`;
    htmlContent += `<span class="term-comm"># =========================================================================</span>\n`;
    htmlContent += `<span class="term-comm"># GNTV DIGITAL, ALL EVERYWHERE Media Group - Multi-Destination Failover Broadcast Splitter Engine</span>\n`;
    htmlContent += `<span class="term-comm"># Generated on 2026-05-28 by Broadcaster Console Hub</span>\n`;
    htmlContent += `<span class="term-comm"># Mode: ${activeIngestMode === "relay" ? "Studio Live RTMP Relay" : "Playlist Concat Infinite Loop"}</span>\n`;
    htmlContent += `<span class="term-comm"># =========================================================================</span>\n\n`;

    if (activeIngestMode === "relay") {
      htmlContent += `<span class="term-comm"># 1. Ingest Ingress Signal (Studio Live RTMP Stream)</span>\n`;
      htmlContent += `<span class="term-var">INPUT_STREAM</span>=<span class="term-str">"${sourceUrl}"</span>\n\n`;
    } else {
      htmlContent += `<span class="term-comm"># 1. Concat Ingress Signal (Local Playlist + Alibaba Cloud OSS Whitelist)</span>\n`;
      htmlContent += `<span class="term-var">PLAYLIST_FILE</span>=<span class="term-str">"${playlistPath}"</span>\n`;
      htmlContent += `<span class="term-var">WHITELIST</span>=<span class="term-str">"${whitelist}"</span>\n\n`;
    }

    htmlContent += `<span class="term-comm"># 2. Output Platform Egress Server (RTMP/RTMPS)</span>\n`;
    htmlContent += `<span class="term-var">INGEST_SERVER</span>=<span class="term-str">"${destServer}"</span>\n\n`;

    htmlContent += `<span class="term-comm"># 3. Stream Destinations Keys</span>\n`;
    htmlContent += `<span class="term-var">KEY_1</span>=<span class="term-str">"${key1}"</span> <span class="term-comm"># Destination 1 Stream Key</span>\n`;
    htmlContent += `<span class="term-var">KEY_2</span>=<span class="term-str">"${key2}"</span> <span class="term-comm"># Destination 2 Stream Key</span>\n`;
    htmlContent += `<span class="term-var">KEY_3</span>=<span class="term-str">"${key3}"</span> <span class="term-comm"># Destination 3 Stream Key</span>\n\n`;

    htmlContent += `<span class="term-comm"># 4. Assembled Multi-Cast Outputs</span>\n`;
    htmlContent += `<span class="term-var">TARGET_1</span>=<span class="term-str">"\${INGEST_SERVER}/\${KEY_1}"</span>\n`;
    htmlContent += `<span class="term-var">TARGET_2</span>=<span class="term-str">"\${INGEST_SERVER}/\${KEY_2}"</span>\n`;
    htmlContent += `<span class="term-var">TARGET_3</span>=<span class="term-str">"\${INGEST_SERVER}/\${KEY_3}"</span>\n\n`;

    htmlContent += `<span class="term-cmd">echo</span> <span class="term-str">"==========================================================="</span>\n`;
    htmlContent += `<span class="term-cmd">echo</span> <span class="term-str">"   GNTV DIGITAL, ALL EVERYWHERE AUTOMATED BROADCAST SPLITTER HUB ACTIVE"</span>\n`;
    htmlContent += `<span class="term-cmd">echo</span> <span class="term-str">"==========================================================="</span>\n`;
    if (activeIngestMode === "relay") {
      htmlContent += `<span class="term-cmd">echo</span> <span class="term-str">"Ingest Stream: \${INPUT_STREAM}"</span>\n`;
    } else {
      htmlContent += `<span class="term-cmd">echo</span> <span class="term-str">"Ingest Playlist: \${PLAYLIST_FILE}"</span>\n`;
    }
    htmlContent += `<span class="term-cmd">echo</span> <span class="term-str">"Splitting to 3 targets simultaneously via RTMP Tee Multiplexer..."</span>\n`;
    htmlContent += `<span class="term-cmd">echo</span> <span class="term-str">"Press [CTRL+C] to close splitter links."</span>\n`;
    htmlContent += `<span class="term-cmd">echo</span> <span class="term-str">"-----------------------------------------------------------"</span>\n\n`;

    htmlContent += `<span class="term-comm"># Fail-safe infinite loop: If network or stream key stalls, sleep and restart splitters</span>\n`;
    htmlContent += `<span class="term-kw">while</span> <span class="term-cmd">true</span>; <span class="term-kw">do</span>\n`;
    htmlContent += `  <span class="term-cmd">echo</span> <span class="term-str">"[\$(date '+%Y-%m-%d %H:%M:%S')] Starting FFmpeg pipeline..."</span>\n\n`;

    if (activeIngestMode === "relay") {
      htmlContent += `  <span class="term-comm">  # Optimized Zero-Transcode Relay Protocol (Ultra low latency and minimal CPU overhead)</span>\n`;
      htmlContent += `  <span class="term-cmd">  ffmpeg</span> -i <span class="term-str">"\$INPUT_STREAM"</span> \\\n`;
      htmlContent += `    -c:v copy -c:a copy -f tee \\\n`;
      htmlContent += `    <span class="term-str">"[f=flv:onfail=ignore]\$TARGET_1|[f=flv:onfail=ignore]\$TARGET_2|[f=flv:onfail=ignore]\$TARGET_3"</span>\n`;
    } else {
      htmlContent += `  <span class="term-comm">  # Concat Playlist Real-Time Ingest (Decodes Alibaba Assets and re-encodes to compliant YouTube H.264/AAC feeds)</span>\n`;
      htmlContent += `  <span class="term-cmd">  ffmpeg</span> -f concat -safe <span class="term-str">0</span> -protocol_whitelist <span class="term-str">"\$WHITELIST"</span> -i <span class="term-str">"\$PLAYLIST_FILE"</span> \\\n`;
      htmlContent += `    -vcodec libx264 -pix_fmt yuv420p -preset fast -r <span class="term-str">30</span> -g <span class="term-str">60</span> \\\n`;
      htmlContent += `    -b:v <span class="term-str">3000k</span> -maxrate <span class="term-str">3000k</span> -bufsize <span class="term-str">6000k</span> \\\n`;
      htmlContent += `    -acodec aac -b:a <span class="term-str">128k</span> -ar <span class="term-str">44100</span> \\\n`;
      htmlContent += `    -f tee <span class="term-str">"[f=flv:onfail=ignore]\$TARGET_1|[f=flv:onfail=ignore]\$TARGET_2|[f=flv:onfail=ignore]\$TARGET_3"</span>\n`;
    }

    htmlContent += `\n  <span class="term-cmd">  echo</span> <span class="term-str">"[\$(date '+%Y-%m-%d %H:%M:%S')] Ingest connection closed. Retrying pipeline in 5 seconds..."</span>\n`;
    htmlContent += `  <span class="term-cmd">  sleep</span> <span class="term-str">5</span>\n`;
    htmlContent += `<span class="term-kw">done</span>\n`;

    shellScriptBody.innerHTML = htmlContent;
  }

  // Get raw unformatted text of shell script for copy/download
  function getRawShellScriptText() {
    const sourceUrl = inputSourceUrl.value.trim();
    const playlistPath = inputPlaylistPath.value.trim();
    const whitelist = inputRemoteHosts.value.trim();
    const destServer = inputDestUrl.value.trim();
    const key1 = inputKey1.value.trim();
    const key2 = inputKey2.value.trim();
    const key3 = inputKey3.value.trim();

    let text = "#!/bin/bash\n\n";
    text += "# =========================================================================\n";
    text += "# GNTV DIGITAL, ALL EVERYWHERE Media Group - Multi-Destination Failover Broadcast Splitter Engine\n";
    text += "# Generated on 2026-05-28 by Broadcaster Console Hub\n";
    text += `# Mode: ${activeIngestMode === "relay" ? "Studio Live RTMP Relay" : "Playlist Concat Infinite Loop"}\n`;
    text += "# =========================================================================\n\n";

    if (activeIngestMode === "relay") {
      text += "# 1. Ingest Ingress Signal (Studio Live RTMP Stream)\n";
      text += `INPUT_STREAM="${sourceUrl}"\n\n`;
    } else {
      text += "# 1. Concat Ingress Signal (Local Playlist + Alibaba Cloud OSS Whitelist)\n";
      text += `PLAYLIST_FILE="${playlistPath}"\n`;
      text += `WHITELIST="${whitelist}"\n\n`;
    }

    text += "# 2. Output Platform Egress Server (RTMP/RTMPS)\n";
    text += `INGEST_SERVER="${destServer}"\n\n`;

    text += "# 3. Stream Destinations Keys\n";
    text += `KEY_1="${key1}" # Destination 1 Stream Key\n`;
    text += `KEY_2="${key2}" # Destination 2 Stream Key\n`;
    text += `KEY_3="${key3}" # Destination 3 Stream Key\n\n`;

    text += "# 4. Assembled Multi-Cast Outputs\n";
    text += "TARGET_1=\"${INGEST_SERVER}/${KEY_1}\"\n";
    text += "TARGET_2=\"${INGEST_SERVER}/${KEY_2}\"\n";
    text += "TARGET_3=\"${INGEST_SERVER}/${KEY_3}\"\n\n";

    text += "echo \"===========================================================\"\n";
    text += "echo \"   GNTV DIGITAL, ALL EVERYWHERE AUTOMATED BROADCAST SPLITTER HUB ACTIVE\"\n";
    text += "echo \"===========================================================\"\n";
    if (activeIngestMode === "relay") {
      text += "echo \"Ingest Stream: ${INPUT_STREAM}\"\n";
    } else {
      text += "echo \"Ingest Playlist: ${PLAYLIST_FILE}\"\n";
    }
    text += "echo \"Splitting to 3 targets simultaneously via RTMP Tee Multiplexer...\"\n";
    text += "echo \"Press [CTRL+C] to close splitter links.\"\n";
    text += "echo \"-----------------------------------------------------------\"\n\n";

    text += "# Fail-safe infinite loop: If network or stream key stalls, sleep and restart splitters\n";
    text += "while true; do\n";
    text += "  echo \"[$(date '+%Y-%m-%d %H:%M:%S')] Starting FFmpeg pipeline...\"\n\n";

    if (activeIngestMode === "relay") {
      text += "    # Optimized Zero-Transcode Relay Protocol (Ultra low latency and minimal CPU overhead)\n";
      text += "    ffmpeg -i \"$INPUT_STREAM\" \\\n";
      text += "      -c:v copy -c:a copy -f tee \\\n";
      text += "      \"[f=flv:onfail=ignore]$TARGET_1|[f=flv:onfail=ignore]$TARGET_2|[f=flv:onfail=ignore]$TARGET_3\"\n";
    } else {
      text += "    # Concat Playlist Real-Time Ingest (Decodes Alibaba Assets and re-encodes to compliant YouTube H.264/AAC feeds)\n";
      text += "    ffmpeg -f concat -safe 0 -protocol_whitelist \"$WHITELIST\" -i \"$PLAYLIST_FILE\" \\\n";
      text += "      -vcodec libx264 -pix_fmt yuv420p -preset fast -r 30 -g 60 \\\n";
      text += "      -b:v 3000k -maxrate 3000k -bufsize 6000k \\\n";
      text += "      -acodec aac -b:a 128k -ar 44100 \\\n";
      text += "      -f tee \"[f=flv:onfail=ignore]$TARGET_1|[f=flv:onfail=ignore]$TARGET_2|[f=flv:onfail=ignore]$TARGET_3\"\n";
    }

    text += "\n  echo \"[$(date '+%Y-%m-%d %H:%M:%S')] Ingest connection closed. Retrying pipeline in 5 seconds...\"\n";
    text += "  sleep 5\n";
    text += "done\n";

    return text;
  }

  // Copy Script Click Handler
  btnCopyScript.addEventListener("click", () => {
    const plainText = getRawShellScriptText();
    navigator.clipboard.writeText(plainText).then(() => {
      alert("Success: Optimized GNTV DIGITAL, ALL EVERYWHERE restreaming shell script copied to clipboard!");
    }).catch(err => {
      console.error("Clipboard copy failed: ", err);
      alert("Error: Clipboard write blocked. Please select the script in the terminal and copy manually.");
    });
  });

  // Download Script Click Handler
  btnDownloadScript.addEventListener("click", () => {
    const plainText = getRawShellScriptText();
    const blob = new Blob([plainText], { type: "text/x-shellscript" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "restream.sh";
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  });

  // Initial update of code block
  updateShellScript();

  // ----------------------------------------------------
  // BROADCASTER SIMULATION AND FAILOVER LOGIC
  // ----------------------------------------------------

  function addLogLine(text, type = "info") {
    const dateStr = new Date().toLocaleTimeString();
    const line = document.createElement("div");
    line.className = `log-line ${type}`;
    line.innerHTML = `<span style="color: rgba(255,255,255,0.3); font-weight: 500;">[${dateStr}]</span> ${text}`;
    logsContainer.appendChild(line);
    logsContainer.scrollTop = logsContainer.scrollHeight;
  }

  function startSplitterSimulation() {
    splitterIsSimulating = true;
    splitterDestActive = [true, true, true];

    // Toggle main simulation button styling
    simBtnText.textContent = "Stop Simulated Splitter";
    simBtnIcon.textContent = "⏹️";
    btnToggleSim.classList.add("active");

    // Add glowing active classes to diagram nodes & paths
    nodeStudio.classList.add("active");
    nodeCloud.classList.add("active");
    nodeEngine.classList.add("active");
    nodeOutputs.classList.add("active");

    pathStudioCloud.classList.add("active");
    pathCloudSplitter.classList.add("active");

    pathSplitterYt1.classList.add("active");
    pathSplitterYt1.classList.remove("pipeline-path-offline");
    pathSplitterYt2.classList.add("active");
    pathSplitterYt2.classList.remove("pipeline-path-offline");
    pathSplitterYt3.classList.add("active");
    pathSplitterYt3.classList.remove("pipeline-path-offline");

    // Enable Drop Buttons
    [btnToggleDest1, btnToggleDest2, btnToggleDest3].forEach(btn => {
      btn.disabled = false;
      btn.textContent = "🚫 Drop Stream";
      btn.classList.remove("active");
    });

    logsContainer.innerHTML = ""; // Clear log board
    addLogLine(`GNTV DIGITAL, ALL EVERYWHERE BROADCASTER SPLITTER CONSOLE V4.2 INITIATED.`, "info");
    addLogLine(`Encoding Ingress Pipeline: ${activeIngestMode === "relay" ? "Zero-Transcode Passthrough Relay Mode" : "Concat H.264 Real-time Transcoding Mode"}.`, "info");

    // Sequence Ingest connection handshake simulation
    setTimeout(() => {
      if (!splitterIsSimulating) return;
      if (activeIngestMode === "relay") {
        addLogLine(`Connecting to Alibaba Ingress Live Stream: ${inputSourceUrl.value.trim()}...`, "info");
      } else {
        addLogLine(`Reading Concat Playlist: ${inputPlaylistPath.value.trim()}...`, "info");
        addLogLine(`Loading remote assets from Alibaba Cloud OSS CDN server...`, "info");
        addLogLine(`Whitelisted secure transport layer protocols: [${inputRemoteHosts.value.trim()}].`, "info");
      }

      setTimeout(() => {
        if (!splitterIsSimulating) return;
        if (activeIngestMode === "relay") {
          addLogLine(`[SUCCESS] Downlink handshake established. Video Stream detected: H.264 High (1080p, 60fps), Audio: AAC (Stereo, 44.1kHz).`, "success");
        } else {
          addLogLine(`[SUCCESS] Playlist concat demuxer established. Decoding files: 'video1.mp4', 'video2.mp4', 'video3.mp4'. Encoding: libx264 H.264 encoder (3000kbps, 30fps), AAC audio (128kbps, 44.1kHz).`, "success");
        }

        setTimeout(() => {
          if (!splitterIsSimulating) return;
          addLogLine(`Initializing multiplexer. Connecting to target endpoints:`, "info");

          // Connect destinations sequentially
          [1, 2, 3].forEach(idx => {
            setTimeout(() => {
              if (!splitterIsSimulating) return;
              const chName = idx === 1 ? destTitle1.textContent : idx === 2 ? destTitle2.textContent : destTitle3.textContent;
              addLogLine(`[SUCCESS] Ingest connection accepted on Destination ${idx}: ${chName} [COMPLIANT].`, "success");

              const dot = idx === 1 ? destDot1 : idx === 2 ? destDot2 : destDot3;
              dot.className = "status-indicator-dot active";

              const card = idx === 1 ? destCard1 : idx === 2 ? destCard2 : destCard3;
              card.classList.remove("offline");
            }, idx * 400);
          });

          // Start Telemetry and running FFmpeg log scroll loops after all connections are established
          setTimeout(() => {
            if (!splitterIsSimulating) return;
            addLogLine(`FFmpeg tee multiplexer active. Real-time splitter splitting active and safe.`, "success");
            startTelemetryAndLogLoops();
          }, 1500);

        }, 800);
      }, 1000);
    }, 400);
  }

  function startTelemetryAndLogLoops() {
    let frameCount = 120;

    // FFmpeg CLI stats log line simulation
    splitterLogInterval = setInterval(() => {
      frameCount += 90;
      const uptimeSec = Math.floor(frameCount / 30);
      const timeStr = `00:00:${uptimeSec.toString().padStart(2, "0")}.00`;

      const activeOutCount = splitterDestActive.filter(x => x).length;
      let bitrate = 0;
      if (activeIngestMode === "relay") {
        bitrate = activeOutCount * 4.2; // ~4.2 Mbps per stream copy
      } else {
        bitrate = activeOutCount * 3.1; // ~3.1 Mbps per transcode stream
      }

      const speed = "1.00x";
      const q = "-1.0";

      if (activeOutCount > 0) {
        addLogLine(`frame= ${frameCount.toString().padStart(5, " ")} fps= 30 q=${q} size= ${(frameCount * 15).toString().padStart(5, " ")}kB time=${timeStr} bitrate= ${bitrate.toFixed(1)}Mbps speed=${speed}`, "stat");
      }
    }, 3000);

    // Telemetry updates
    splitterTelemetryInterval = setInterval(() => {
      [1, 2, 3].forEach(idx => {
        const isActive = splitterDestActive[idx - 1];
        const bitrateSpan = idx === 1 ? destBitrate1 : idx === 2 ? destBitrate2 : destBitrate3;
        const latencySpan = idx === 1 ? destLatency1 : idx === 2 ? destLatency2 : destLatency3;

        if (isActive) {
          const base = activeIngestMode === "relay" ? 4.2 : 3.0;
          const val = base + (Math.random() - 0.5) * 0.3;
          bitrateSpan.textContent = `${val.toFixed(1)} Mbps`;
          bitrateSpan.className = "dest-tel-value success";

          const lat = activeIngestMode === "relay" ? 1.2 : 1.6;
          const latVal = lat + (Math.random() - 0.5) * 0.1;
          latencySpan.textContent = `${latVal.toFixed(1)}s`;
        } else {
          bitrateSpan.textContent = "0.0 Mbps";
          bitrateSpan.className = "dest-tel-value error";
          latencySpan.textContent = "0ms";
        }
      });
    }, 2000);
  }

  function stopSplitterSimulation() {
    splitterIsSimulating = false;

    // Clear simulation intervals
    if (splitterLogInterval) clearInterval(splitterLogInterval);
    if (splitterTelemetryInterval) clearInterval(splitterTelemetryInterval);

    // Reset main simulation button styling
    simBtnText.textContent = "Start Simulated Splitter";
    simBtnIcon.textContent = "⚡";
    btnToggleSim.classList.remove("active");

    // Remove active glowing nodes & paths
    nodeStudio.classList.remove("active");
    nodeCloud.classList.remove("active");
    nodeEngine.classList.remove("active");
    nodeOutputs.classList.remove("active");

    pathStudioCloud.classList.remove("active");
    pathCloudSplitter.classList.remove("active");

    pathSplitterYt1.classList.remove("active");
    pathSplitterYt1.classList.remove("pipeline-path-offline");
    pathSplitterYt2.classList.remove("active");
    pathSplitterYt2.classList.remove("pipeline-path-offline");
    pathSplitterYt3.classList.remove("active");
    pathSplitterYt3.classList.remove("pipeline-path-offline");

    // Disable drop buttons & reset indicators to Red
    [btnToggleDest1, btnToggleDest2, btnToggleDest3].forEach(btn => {
      btn.disabled = true;
      btn.textContent = "🚫 Drop Stream";
      btn.classList.remove("active");
    });

    [destDot1, destDot2, destDot3].forEach(dot => {
      dot.className = "status-indicator-dot offline";
    });

    [destBitrate1, destBitrate2, destBitrate3].forEach(span => {
      span.textContent = "0.0 Mbps";
      span.className = "dest-tel-value";
    });

    [destLatency1, destLatency2, destLatency3].forEach(span => {
      span.textContent = "0ms";
    });

    [destCard1, destCard2, destCard3].forEach(card => {
      card.classList.remove("offline");
    });

    addLogLine(`[INFO] Restreamer Splitter Engine process terminated. Pipeline IDLE.`, "info");
  }

  // Bind Main Simulation Toggle Button Click
  btnToggleSim.addEventListener("click", () => {
    if (splitterIsSimulating) {
      stopSplitterSimulation();
    } else {
      startSplitterSimulation();
    }
  });

  // Bind individual Drop target buttons to simulate output drops
  function handleDropToggle(idx) {
    if (!splitterIsSimulating) return;

    const isCurrentlyActive = splitterDestActive[idx - 1];
    const newActiveState = !isCurrentlyActive;
    splitterDestActive[idx - 1] = newActiveState;

    const btn = idx === 1 ? btnToggleDest1 : idx === 2 ? btnToggleDest2 : btnToggleDest3;
    const dot = idx === 1 ? destDot1 : idx === 2 ? destDot2 : destDot3;
    const path = idx === 1 ? pathSplitterYt1 : idx === 2 ? pathSplitterYt2 : idx === 3 ? pathSplitterYt3 : null;
    const card = idx === 1 ? destCard1 : idx === 2 ? destCard2 : destCard3;
    const chName = idx === 1 ? destTitle1.textContent : idx === 2 ? destTitle2.textContent : destTitle3.textContent;

    if (newActiveState) {
      btn.textContent = "🚫 Drop Stream";
      btn.classList.remove("active");

      dot.className = "status-indicator-dot reconnecting";
      addLogLine(`[INFO] Attempting failover handshake on Destination ${idx}: ${chName}...`, "warning");

      setTimeout(() => {
        if (!splitterIsSimulating || !splitterDestActive[idx - 1]) return;
        dot.className = "status-indicator-dot active";
        card.classList.remove("offline");

        if (path) {
          path.classList.add("active");
          path.classList.remove("pipeline-path-offline");
        }
        addLogLine(`[SUCCESS] Re-connected to Ingest Node Destination ${idx} (${chName}). Active relay restored.`, "success");
      }, 2000);

    } else {
      btn.textContent = "⚡ Restore Stream";
      btn.classList.add("active");

      dot.className = "status-indicator-dot offline";
      card.classList.add("offline");

      if (path) {
        path.classList.remove("active");
        path.classList.add("pipeline-path-offline");
      }

      addLogLine(`[WARNING] Destination ${idx} (${chName}) lost ingest handshakes. Network socket closed.`, "error");
      addLogLine(`[TEE protocol active] Failover mechanism 'onfail=ignore' bypasses drop. Other streams unaffected.`, "info");
    }
  }

  btnToggleDest1.addEventListener("click", () => handleDropToggle(1));
  btnToggleDest2.addEventListener("click", () => handleDropToggle(2));
  btnToggleDest3.addEventListener("click", () => handleDropToggle(3));

  // Initialize Shell Script View on load
  updateShellScript();

  // Primary live telemetric graphing and EPG setups
  drawTelemetryChart();

  // Clean up animation on destruction simulator if needed
  return () => {
    clearTimeout(animId);
    if (splitterLogInterval) clearInterval(splitterLogInterval);
    if (splitterTelemetryInterval) clearInterval(splitterTelemetryInterval);
  };
}
