import { store } from "../../../shared/src/state.js";
import { VODS, CHANNELS } from "../../../shared/src/utils/mockData.js";
import { initProcessingCenter } from "./ProcessingCenter.js";
import { initSheekoXariiroVoiceStudio } from "./SheekoXariiroVoiceStudio.jsx";
import { initChatModerationConsole } from "./ChatModerationConsole.js";
import { initExecutiveAnalyticsDashboard } from "./ExecutiveAnalyticsDashboard.js";
import { initPartnerSyndicationDashboard } from "./PartnerSyndicationDashboard.js";

export function initStudioDashboard(container) {
  let activeSubTab = "upload"; // default module tab
  let activeTabCleanup = null;

  // Pipeline transcoding state
  const pipelineJobs = [
    { id: "pipe1", file: "dhacdooyinka_dunida_2026.mp4", progress: 100, status: "Completed", rate: "4.2x", format: "HLS + DASH" },
    { id: "pipe2", file: "somali_league_match_day.mp4", progress: 68, status: "Transcoding", rate: "2.8x", format: "HLS Only" },
    { id: "pipe3", file: "xogta_gntv_investigative.mov", progress: 0, status: "Queued", rate: "0.0x", format: "HLS + DASH" }
  ];

  // Ingest stream details
  let streamKey = "live_gntv_hub_" + Math.random().toString(36).substring(2, 10);
  let primaryIngest = "rtmp://ingest.gntv.net/live2";
  let fallbackIngest = "srt://srt-ingest.gntv.net:9000?streamid=" + streamKey;

  // Distribution channels state
  const distChannels = [
    { id: "yt", name: "YouTube Live Sync", icon: "📺", status: "Connected", syncActive: true },
    { id: "fb", name: "Facebook Live Feed", icon: "👥", status: "Offline", syncActive: false },
    { id: "tt", name: "TikTok Stream Relay", icon: "🎵", status: "Connected", syncActive: true },
    { id: "ott", name: "AppleTV / FireTV OTT", icon: "🍏", status: "Synced", syncActive: true },
    { id: "iptv", name: "IPTV Satellite Ingress", icon: "🛰️", status: "Broadcasting", syncActive: true }
  ];

  // Monetization rates state
  const monSettings = {
    premiumPrice: "9.99",
    familyPrice: "14.99",
    businessPrice: "49.99",
    adFrequency: "15",
    ppvActive: true
  };

  let pipelineInterval = null;

  const render = () => {
    const user = store.getState("user") || { role: "free" };
    const userRole = user.role;

    let sidebarTitle = "GNTV DIGITAL, ALL EVERYWHERE Media OS";
    let sidebarSubtitle = "v4.2.1-SECURE-INGRESS";
    let allowedTabs = [];

    if (userRole === "admin") {
      sidebarTitle = "GNTV DIGITAL, ALL EVERYWHERE System Control";
      sidebarSubtitle = "SYSTEM ADMINISTRATOR";
      allowedTabs = [
        { id: "upload", label: "Upload Video", icon: "📤" },
        { id: "library", label: "Media Library", icon: "📁" },
        { id: "categories", label: "Categories", icon: "🏷️" },
        { id: "shows", label: "Shows & Episodes", icon: "📺" },
        { id: "sheeko-voice", label: "Sheeko Xariiro Voice Studio", icon: "🎙️" },
        { id: "channels", label: "Channels", icon: "📡" },
        { id: "scheduling", label: "Scheduling", icon: "📅" },
        { id: "publish", label: "Publish", icon: "🚀" },
        { id: "processing-center", label: "Processing Ops Center", icon: "⚙️" },
        { id: "analytics", label: "Analytics Hub", icon: "📊" },
        { id: "executive-analytics", label: "Executive Analytics", icon: "📈" },
        { id: "partner-syndication", label: "Partner Syndication", icon: "🔗" },
        { id: "monetization", label: "Monetization Panel", icon: "💰" },
        { id: "moderation", label: "Chat Moderation", icon: "🛡️" }
      ];
    } else if (userRole === "operator") {
      sidebarTitle = "GNTV DIGITAL, ALL EVERYWHERE Back Office";
      sidebarSubtitle = "TERMINAL OPERATOR";
      allowedTabs = [
        { id: "upload", label: "Upload Video", icon: "📤" },
        { id: "library", label: "Media Library", icon: "📁" },
        { id: "categories", label: "Categories", icon: "🏷️" },
        { id: "shows", label: "Shows & Episodes", icon: "📺" },
        { id: "sheeko-voice", label: "Sheeko Xariiro Voice Studio", icon: "🎙️" },
        { id: "channels", label: "Channels", icon: "📡" },
        { id: "scheduling", label: "Scheduling", icon: "📅" },
        { id: "publish", label: "Publish", icon: "🚀" },
        { id: "processing-center", label: "Processing Ops Center", icon: "⚙️" },
        { id: "executive-analytics", label: "Executive Analytics", icon: "📈" },
        { id: "partner-syndication", label: "Partner Syndication", icon: "🔗" },
        { id: "moderation", label: "Chat Moderation", icon: "🛡️" }
      ];
    } else {
      sidebarTitle = "GNTV DIGITAL, ALL EVERYWHERE Creator Studio";
      sidebarSubtitle = "CONTENT CREATOR WORKSPACE";
      allowedTabs = [
        { id: "upload", label: "Upload Video", icon: "📤" },
        { id: "library", label: "Media Library", icon: "📁" },
        { id: "categories", label: "Categories", icon: "🏷️" },
        { id: "shows", label: "Shows & Episodes", icon: "📺" }
      ];
    }

    if (!allowedTabs.some(t => t.id === activeSubTab)) {
      activeSubTab = allowedTabs[0]?.id || "upload";
    }

    container.innerHTML = `
      <style>
        .studio-os-wrapper {
          display: flex;
          height: calc(100vh - 60px);
          background: #06060c;
          font-family: var(--font-sans), system-ui, sans-serif;
          color: #e5e7eb;
          overflow: hidden;
        }

        /* Sidebar Navigation */
        .studio-sidebar {
          width: 260px;
          background: rgba(10, 10, 15, 0.95);
          border-right: 1px solid rgba(255, 255, 255, 0.05);
          display: flex;
          flex-direction: column;
          padding: 20px 0;
          box-sizing: border-box;
          flex-shrink: 0;
        }
        .studio-sidebar-header {
          padding: 0 24px 16px 24px;
          border-bottom: 1px solid rgba(255, 255, 255, 0.04);
          margin-bottom: 16px;
        }
        .studio-sidebar-header h2 {
          font-size: 14px;
          font-weight: 850;
          letter-spacing: 1px;
          text-transform: uppercase;
          color: var(--brand-primary);
          margin: 0;
        }
        .studio-sidebar-header p {
          font-size: 10px;
          color: rgba(255, 255, 255, 0.4);
          margin: 4px 0 0 0;
          font-family: var(--font-mono);
        }
        .studio-tab-btn {
          display: flex;
          align-items: center;
          gap: 12px;
          padding: 12px 24px;
          background: transparent;
          border: none;
          color: rgba(255, 255, 255, 0.6);
          font-size: 13px;
          font-weight: 700;
          text-align: left;
          cursor: pointer;
          transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1);
          position: relative;
          width: 100%;
        }
        .studio-tab-btn:hover {
          color: #ffffff;
          background: rgba(255, 255, 255, 0.02);
        }
        .studio-tab-btn.active {
          color: #ffffff;
          background: rgba(255, 42, 75, 0.06);
        }
        .studio-tab-btn.active::before {
          content: "";
          position: absolute;
          left: 0;
          top: 0;
          bottom: 0;
          width: 3px;
          background: var(--brand-primary);
          box-shadow: 0 0 10px var(--brand-primary-glow);
        }
        .studio-tab-btn span.icon {
          font-size: 16px;
        }

        /* Content Area */
        .studio-content-pane {
          flex: 1;
          display: flex;
          flex-direction: column;
          overflow-y: auto;
          padding: 32px;
          box-sizing: border-box;
        }

        .pane-header {
          margin-bottom: 24px;
          border-bottom: 1px solid rgba(255, 255, 255, 0.05);
          padding-bottom: 16px;
        }
        .pane-header h3 {
          font-size: 20px;
          font-weight: 850;
          letter-spacing: -0.5px;
          margin: 0;
          text-transform: uppercase;
        }
        .pane-header p {
          font-size: 12px;
          color: rgba(255, 255, 255, 0.45);
          margin: 4px 0 0 0;
        }

        /* UI elements */
        .os-grid-2 {
          display: grid;
          grid-template-columns: 1fr 1fr;
          gap: 24px;
        }
        @media(max-width: 900px) {
          .os-grid-2 {
            grid-template-columns: 1fr;
          }
        }
        .os-card {
          background: rgba(255, 255, 255, 0.02);
          border: 1px solid rgba(255, 255, 255, 0.06);
          border-radius: 12px;
          padding: 20px;
          box-sizing: border-box;
        }
        .os-card-title {
          font-size: 12px;
          font-weight: 800;
          color: var(--brand-primary);
          text-transform: uppercase;
          margin: 0 0 16px 0;
          letter-spacing: 0.5px;
        }

        /* Forms */
        .form-group {
          display: flex;
          flex-direction: column;
          gap: 6px;
          margin-bottom: 16px;
        }
        .form-group label {
          font-size: 11px;
          font-weight: 700;
          color: rgba(255, 255, 255, 0.5);
          text-transform: uppercase;
        }
        .form-group input, .form-group select, .form-group textarea {
          background: rgba(255, 255, 255, 0.05);
          border: 1px solid rgba(255, 255, 255, 0.08);
          border-radius: 8px;
          padding: 10px 14px;
          color: #ffffff;
          font-size: 13px;
          outline: none;
          transition: border-color 0.2s;
        }
        .form-group input:focus, .form-group select:focus, .form-group textarea:focus {
          border-color: var(--brand-primary);
        }

        /* Buttons */
        .os-btn {
          background: var(--brand-primary);
          border: none;
          color: #ffffff;
          font-weight: 700;
          padding: 10px 20px;
          border-radius: 8px;
          cursor: pointer;
          font-size: 13px;
          transition: all 0.2s;
          box-shadow: 0 4px 10px var(--brand-primary-glow);
          display: inline-flex;
          align-items: center;
          justify-content: center;
          gap: 8px;
        }
        .os-btn:hover {
          opacity: 0.9;
        }
        .os-btn-secondary {
          background: rgba(255, 255, 255, 0.05);
          border: 1px solid rgba(255, 255, 255, 0.1);
          color: #fff;
          box-shadow: none;
        }
        .os-btn-secondary:hover {
          background: rgba(255, 255, 255, 0.08);
        }

        /* Tables */
        .os-table {
          width: 100%;
          border-collapse: collapse;
          text-align: left;
        }
        .os-table th {
          padding: 12px 16px;
          border-bottom: 2px solid rgba(255, 255, 255, 0.08);
          font-size: 11px;
          font-weight: 700;
          color: rgba(255,255,255,0.4);
          text-transform: uppercase;
        }
        .os-table td {
          padding: 14px 16px;
          border-bottom: 1px solid rgba(255, 255, 255, 0.04);
          font-size: 13px;
        }
        .os-table tr:hover td {
          background: rgba(255, 255, 255, 0.01);
        }

        /* Badges */
        .os-badge {
          font-size: 9px;
          font-weight: 800;
          padding: 2px 8px;
          border-radius: 4px;
          text-transform: uppercase;
          display: inline-block;
        }
        .os-badge-green { background: rgba(16, 185, 129, 0.15); color: #10b981; border: 1px solid rgba(16, 185, 129, 0.2); }
        .os-badge-yellow { background: rgba(245, 158, 11, 0.15); color: #f59e0b; border: 1px solid rgba(245, 158, 11, 0.2); }
        .os-badge-red { background: rgba(239, 68, 68, 0.15); color: #ef4444; border: 1px solid rgba(239, 68, 68, 0.2); }
        .os-badge-blue { background: rgba(59, 130, 246, 0.15); color: #3b82f6; border: 1px solid rgba(59, 130, 246, 0.2); }

        /* Steppers */
        .stepper {
          display: flex;
          justify-content: space-between;
          margin-bottom: 24px;
          position: relative;
        }
        .stepper::before {
          content: "";
          position: absolute;
          top: 14px;
          left: 10px;
          right: 10px;
          height: 2px;
          background: rgba(255,255,255,0.08);
          z-index: 1;
        }
        .step {
          display: flex;
          flex-direction: column;
          align-items: center;
          z-index: 2;
          width: 60px;
        }
        .step-circle {
          width: 30px;
          height: 30px;
          border-radius: 50%;
          background: #111827;
          border: 2px solid rgba(255,255,255,0.15);
          display: flex;
          align-items: center;
          justify-content: center;
          font-weight: 800;
          font-size: 11px;
          color: rgba(255,255,255,0.4);
          transition: all 0.3s;
        }
        .step.active .step-circle {
          background: var(--brand-primary);
          border-color: var(--brand-primary);
          color: #fff;
          box-shadow: 0 0 10px var(--brand-primary-glow);
        }
        .step-lbl {
          font-size: 9px;
          font-weight: 700;
          margin-top: 6px;
          text-transform: uppercase;
          color: rgba(255,255,255,0.4);
        }
        .step.active .step-lbl {
          color: #fff;
        }

        /* KPIs */
        .kpi-row {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
          gap: 16px;
          margin-bottom: 24px;
        }
        .kpi-card {
          background: rgba(255,255,255,0.02);
          border: 1px solid rgba(255,255,255,0.05);
          padding: 16px;
          border-radius: 10px;
        }
        .kpi-title {
          font-size: 10px;
          font-weight: 700;
          color: rgba(255,255,255,0.4);
          text-transform: uppercase;
          margin-bottom: 4px;
        }
        .kpi-val {
          font-size: 20px;
          font-weight: 850;
          color: #fff;
        }
      </style>

      <div class="studio-os-wrapper">
        <!-- Left Sidebar Navigation -->
        <aside class="studio-sidebar" role="navigation" aria-label="GNTV DIGITAL, ALL EVERYWHERE Studio OS Navigation">
          <div class="studio-sidebar-header">
            <h2>\${sidebarTitle}</h2>
            <p>\${sidebarSubtitle}</p>
          </div>

          \${allowedTabs.map(t => \`
            <button class="studio-tab-btn \${activeSubTab === t.id ? 'active' : ''}" data-target="\${t.id}">
              <span class="icon">\${t.icon}</span> \${t.label}
            </button>
          \`).join('')}
        </aside>

        <!-- Right Content Pane -->
        <main class="studio-content-pane" id="studio-pane-viewport">
          <!-- Rendered dynamically -->
        </main>
      </div>
    `;

    renderSubTab();
    bindSidebarEvents();
  };

  // Ingest upload progress state variables
  let uploadProgress = 0;
  let uploadStateText = "[SYSTEM IDLE] Ready for media upload...";
  let isUploading = false;
  let activeUploadingTitle = "";

  // Temporary memory state lists to support CMS mapping
  const localCategories = [
    { name: "News", slug: "news", description: "World, National, and Local Broadcast News feeds." },
    { name: "Sports", slug: "sports", description: "Match playbacks and local athletic tournaments." },
    { name: "Entertainment", slug: "entertainment", description: "Somali drama series and culture plays." },
    { name: "Documentaries", slug: "documentaries", description: "Historical research and educational programs." }
  ];

  const localShows = [
    { title: "Visionary Voices", category: "Entertainment", seasons: 1, episodesCount: 8 },
    { title: "Taariikhda Geeska Afrika", category: "Documentaries", seasons: 1, episodesCount: 5 },
    { title: "Dhalinyarada Eastleigh", category: "Entertainment", seasons: 2, episodesCount: 12 },
    { title: "GNTV DIGITAL, ALL EVERYWHERE Originals", category: "Entertainment", seasons: 1, episodesCount: 6 }
  ];

  const renderSubTab = () => {
    const pane = container.querySelector("#studio-pane-viewport");
    if (!pane) return;

    if (activeTabCleanup) {
      activeTabCleanup();
      activeTabCleanup = null;
    }

    if (activeSubTab === "upload") {
      // Color helper for flowchart nodes based on current upload stage
      const getNodeStyle = (min, max) => {
        const active = isUploading && uploadProgress >= min && uploadProgress <= max;
        const completed = isUploading && uploadProgress > max;
        if (active) {
          return `background: var(--brand-primary); border-color: var(--brand-primary); color: #fff; box-shadow: 0 0 15px var(--brand-primary-glow);`;
        } else if (completed) {
          return `background: rgba(16, 185, 129, 0.2); border-color: #10b981; color: #10b981;`;
        }
        return `background: #111827; border-color: rgba(255,255,255,0.1); color: rgba(255,255,255,0.4);`;
      };

      const getArrowStyle = (min) => {
        const active = isUploading && uploadProgress >= min;
        return active ? `color: #10b981; text-shadow: 0 0 8px rgba(16,185,129,0.5);` : `color: rgba(255,255,255,0.15);`;
      };

      pane.innerHTML = `
        <div class="pane-header">
          <h3>Upload Video & Ingestion Workflow</h3>
          <p>Ingest raw video files into the GNTV DIGITAL, ALL EVERYWHERE CMS. Video is processed, segmented into HLS/DASH, and published to the Front Door App.</p>
        </div>

        <div class="os-grid-2">
          <!-- Left Ingestion Form -->
          <div class="os-card">
            <h4 class="os-card-title">CMS Ingest Form</h4>
            <form id="ingest-video-form">
              <div class="form-group">
                <label for="ingest-title">Muuqaalka Title (Video Title)</label>
                <input type="text" id="ingest-title" required placeholder="e.g. Sheeko Soomaaliyeed Episode 1" ${isUploading ? 'disabled' : ''}>
              </div>
              <div class="form-group" style="display: grid; grid-template-columns: 1fr 1fr; gap: 14px; margin-bottom: 0;">
                <div class="form-group">
                  <label for="ingest-category">Qaybta (Category)</label>
                  <select id="ingest-category" ${isUploading ? 'disabled' : ''}>
                    <option value="Entertainment">Entertainment (Riwaayadaha)</option>
                    <option value="Documentaries">Documentaries (Taariikhda)</option>
                    <option value="News">News</option>
                    <option value="Sports">Sports</option>
                  </select>
                </div>
                <div class="form-group">
                  <label for="ingest-show">Show / Original Series</label>
                  <select id="ingest-show" ${isUploading ? 'disabled' : ''}>
                    ${localShows.map(s => `<option value="${s.title}">${s.title}</option>`).join('')}
                    <option value="New Show">+ Add New Show</option>
                  </select>
                </div>
              </div>
              <div class="form-group" style="display: grid; grid-template-columns: 1fr 1fr; gap: 14px; margin-bottom: 0;">
                <div class="form-group">
                  <label for="ingest-duration">Muddada (Duration - MM:SS)</label>
                  <input type="text" id="ingest-duration" value="45:00" required placeholder="e.g. 24:15" ${isUploading ? 'disabled' : ''}>
                </div>
                <div class="form-group">
                  <label for="ingest-episode">Episode Number</label>
                  <input type="number" id="ingest-episode" value="1" min="1" required ${isUploading ? 'disabled' : ''}>
                </div>
              </div>
              <div class="form-group" style="display: grid; grid-template-columns: 1fr 1fr; gap: 14px; margin-bottom: 0;">
                <div class="form-group">
                  <label for="ingest-host">Host / Presenter</label>
                  <input type="text" id="ingest-host" value="Layla Warsame" required placeholder="Presenter name" ${isUploading ? 'disabled' : ''}>
                </div>
                <div class="form-group">
                  <label for="ingest-rating">Age Rating</label>
                  <select id="ingest-rating" ${isUploading ? 'disabled' : ''}>
                    <option value="G">G - General Audience</option>
                    <option value="PG">PG - Parental Guidance</option>
                    <option value="PG-13">PG-13</option>
                    <option value="TV-MA">TV-MA (PIN Restricted)</option>
                  </select>
                </div>
              </div>
              <div class="form-group" style="flex-direction: row; align-items: center; gap: 10px; margin-bottom: 16px;">
                <input type="checkbox" id="ingest-premium" style="width: auto; cursor: pointer;" ${isUploading ? 'disabled' : ''}>
                <label for="ingest-premium" style="margin: 0; cursor: pointer;">Require Premium Access</label>
              </div>
              <div class="form-group">
                <label for="ingest-description">Description</label>
                <textarea id="ingest-description" rows="2" required placeholder="Gali fahfaahin kooban oo ku saabsan barnaamijkan..." ${isUploading ? 'disabled' : ''}>Riwaayad cusub oo ka tirsan sheekooyinka GNTV DIGITAL, ALL EVERYWHERE Originals.</textarea>
              </div>
              <button type="submit" class="os-btn" style="width: 100%;" ${isUploading ? 'disabled' : ''}>
                <span>${isUploading ? '⏳ Processing...' : '➕ Ingest & Start Video Ingest'}</span>
              </button>
            </form>
          </div>

          <!-- Right Processing Pipeline Flow & Logs -->
          <div class="os-card" style="display: flex; flex-direction: column; justify-content: space-between;">
            <div>
              <h4 class="os-card-title">Real-time Processing Pipeline</h4>

              <!-- Transcode Pipeline Visual Node flowchart diagram -->
              <div style="display: flex; flex-direction: column; gap: 16px; margin: 10px 0;">
                <!-- Row 1: Source to CMS to Storage -->
                <div style="display: flex; align-items: center; justify-content: space-between; gap: 4px;">
                  <div style="display: flex; flex-direction: column; align-items: center; gap: 4px; flex: 1;">
                    <div style="width: 38px; height: 38px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 14px; border: 2px solid; transition: all 0.3s; ${getNodeStyle(1, 15)}">📤</div>
                    <span style="font-size: 8px; font-weight: 800; text-transform: uppercase;">1. Source File</span>
                  </div>
                  <div style="font-size: 12px; transition: all 0.3s; ${getArrowStyle(15)}">➔</div>
                  <div style="display: flex; flex-direction: column; align-items: center; gap: 4px; flex: 1;">
                    <div style="width: 38px; height: 38px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 14px; border: 2px solid; transition: all 0.3s; ${getNodeStyle(16, 30)}">📝</div>
                    <span style="font-size: 8px; font-weight: 800; text-transform: uppercase;">2. GNTV DIGITAL, ALL EVERYWHERE CMS</span>
                  </div>
                  <div style="font-size: 12px; transition: all 0.3s; ${getArrowStyle(30)}">➔</div>
                  <div style="display: flex; flex-direction: column; align-items: center; gap: 4px; flex: 1;">
                    <div style="width: 38px; height: 38px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 14px; border: 2px solid; transition: all 0.3s; ${getNodeStyle(31, 50)}">💽</div>
                    <span style="font-size: 8px; font-weight: 800; text-transform: uppercase;">3. OSS Storage</span>
                  </div>
                </div>

                <!-- Vertical Down connector -->
                <div style="display: flex; justify-content: flex-end; padding-right: 36px;">
                  <div style="font-size: 12px; transform: rotate(90deg); transition: all 0.3s; ${getArrowStyle(50)}">➔</div>
                </div>

                <!-- Row 2: FFmpeg to HLS/DASH to CDN -->
                <div style="display: flex; align-items: center; justify-content: space-between; gap: 4px;">
                  <div style="display: flex; flex-direction: column; align-items: center; gap: 4px; flex: 1;">
                    <div style="width: 38px; height: 38px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 14px; border: 2px solid; transition: all 0.3s; ${getNodeStyle(51, 68)}">⚙️</div>
                    <span style="font-size: 8px; font-weight: 800; text-transform: uppercase;">4. FFmpeg Tool</span>
                  </div>
                  <div style="font-size: 12px; transition: all 0.3s; ${getArrowStyle(68)}">➔</div>
                  <div style="display: flex; flex-direction: column; align-items: center; gap: 4px; flex: 1;">
                    <div style="width: 38px; height: 38px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 14px; border: 2px solid; transition: all 0.3s; ${getNodeStyle(69, 85)}">📼</div>
                    <span style="font-size: 8px; font-weight: 800; text-transform: uppercase;">5. HLS / DASH</span>
                  </div>
                  <div style="font-size: 12px; transition: all 0.3s; ${getArrowStyle(85)}">➔</div>
                  <div style="display: flex; flex-direction: column; align-items: center; gap: 4px; flex: 1;">
                    <div style="width: 38px; height: 38px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 14px; border: 2px solid; transition: all 0.3s; ${getNodeStyle(86, 95)}">⚡</div>
                    <span style="font-size: 8px; font-weight: 800; text-transform: uppercase;">6. Alibaba CDN</span>
                  </div>
                </div>

                <!-- Vertical Down connector -->
                <div style="display: flex; justify-content: flex-start; padding-left: 36px;">
                  <div style="font-size: 12px; transform: rotate(90deg); transition: all 0.3s; ${getArrowStyle(95)}">➔</div>
                </div>

                <!-- Row 3: Front Door App Target -->
                <div style="display: flex; align-items: center; justify-content: center;">
                  <div style="display: flex; flex-direction: column; align-items: center; gap: 4px; width: 140px; background: rgba(255,255,255,0.02); padding: 8px; border-radius: 8px; border: 1px solid rgba(255,255,255,0.05);">
                    <div style="width: 38px; height: 38px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 14px; border: 2px solid; transition: all 0.3s; ${getNodeStyle(96, 100)}">📱</div>
                    <span style="font-size: 8px; font-weight: 800; text-transform: uppercase; text-align: center; color: #fff;">7. Front Door App</span>
                  </div>
                </div>
              </div>

              <!-- Progress bar -->
              <div style="margin-top: 15px;">
                <div style="display:flex; justify-content:space-between; font-size:10px; margin-bottom:4px; font-family:var(--font-mono); color:var(--brand-primary); font-weight:700;">
                  <span>INGESTION PROGRESS</span>
                  <span>${uploadProgress}%</span>
                </div>
                <div style="width:100%; height:4px; background:rgba(255,255,255,0.1); border-radius:2px; overflow:hidden;">
                  <div style="width: ${uploadProgress}%; height:100%; background:var(--brand-primary); transition: width 0.1s;"></div>
                </div>
              </div>
            </div>

            <!-- Simulation Logger Console -->
            <div id="upload-simulation-log" style="margin-top: 15px; font-family: var(--font-mono); font-size: 10px; padding: 12px; background: #000; border-radius: 6px; min-height: 105px; max-height: 120px; overflow-y: auto; color: #10b981; border: 1px solid rgba(16, 185, 129, 0.2);">
              ${uploadStateText}
            </div>
          </div>
        </div>
      `;

      bindUploadEvents();

    } else if (activeSubTab === "library") {
      const activeVODS = store.getState("catalogVods") || VODS;
      pane.innerHTML = `
        <div class="pane-header">
          <h3>GNTV DIGITAL, ALL EVERYWHERE Media Catalog Library</h3>
          <p>Full database list of registered live streams and video-on-demand assets. Actions update catalog list reactively.</p>
        </div>

        <div class="os-card" style="overflow-x: auto;">
          <h4 class="os-card-title">Registered VOD Assets (${activeVODS.length} items)</h4>
          <table class="os-table">
            <thead>
              <tr>
                <th>Title</th>
                <th>Category</th>
                <th>Duration</th>
                <th>Host</th>
                <th>Rating</th>
                <th>Access</th>
                <th>Views</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              ${activeVODS.map(v => `
                <tr id="row-media-${v.id}">
                  <td style="font-weight: 700; color: #fff;">${v.title}</td>
                  <td><span class="os-badge os-badge-blue">${v.category}</span></td>
                  <td style="font-family: var(--font-mono);">${v.duration}</td>
                  <td>${v.host || "AI Host"}</td>
                  <td><span class="os-badge os-badge-yellow">${v.rating || "G"}</span></td>
                  <td>
                    ${v.premium ? '<span class="os-badge os-badge-red">🔒 PREMIUM</span>' : '<span class="os-badge os-badge-green">🔓 FREE</span>'}
                  </td>
                  <td style="font-family: var(--font-mono);">${(v.views || 0).toLocaleString()}</td>
                  <td>
                    <button class="os-btn os-btn-secondary btn-delete-catalog-item" data-id="${v.id}" style="padding: 6px 12px; font-size: 11px; border-color: rgba(239, 68, 68, 0.3); color: #ef4444;">
                      Delete
                    </button>
                  </td>
                </tr>
              `).join('')}
            </tbody>
          </table>
        </div>
      `;
      bindLibraryEvents();

    } else if (activeSubTab === "categories") {
      pane.innerHTML = `
        <div class="pane-header">
          <h3>Category Database Manager</h3>
          <p>Configure dynamic content genres, category tags, and localized Somali classification codes.</p>
        </div>

        <div class="os-grid-2">
          <div class="os-card">
            <h4 class="os-card-title">Active Categories</h4>
            <div style="display: flex; flex-direction: column; gap: 10px;">
              ${localCategories.map(cat => `
                <div style="background: rgba(255,255,255,0.02); border: 1px solid rgba(255,255,255,0.05); padding: 12px 16px; border-radius: 8px; display: flex; justify-content: space-between; align-items: center;">
                  <div>
                    <h5 style="margin: 0; font-size: 13px; font-weight: 700; color: #fff;">${cat.name}</h5>
                    <span style="font-size: 10px; color: rgba(255,255,255,0.4);">${cat.description}</span>
                  </div>
                  <span class="os-badge os-badge-blue" style="font-family: var(--font-mono);">${cat.slug}</span>
                </div>
              `).join('')}
            </div>
          </div>

          <div class="os-card">
            <h4 class="os-card-title">Create New Category</h4>
            <form id="create-category-form">
              <div class="form-group">
                <label for="cat-name">Category Name</label>
                <input type="text" id="cat-name" required placeholder="e.g. Music / Heeso">
              </div>
              <div class="form-group">
                <label for="cat-slug">Unique Slug</label>
                <input type="text" id="cat-slug" required placeholder="e.g. music">
              </div>
              <div class="form-group">
                <label for="cat-desc">Description</label>
                <textarea id="cat-desc" rows="3" required placeholder="Enter description for catalog navigation guides..."></textarea>
              </div>
              <button type="submit" class="os-btn" style="width: 100%;">Create Category</button>
            </form>
          </div>
        </div>
      `;
      bindCategoriesEvents();

    } else if (activeSubTab === "shows") {
      pane.innerHTML = `
        <div class="pane-header">
          <h3>Original Shows & Seasonal Series</h3>
          <p>Group individual episodes under registered shows. Shows dynamically render as featured shelves on Front Door.</p>
        </div>

        <div class="os-grid-2">
          <div class="os-card">
            <h4 class="os-card-title">Registered Original Series</h4>
            <div style="display: flex; flex-direction: column; gap: 10px;">
              ${localShows.map(show => `
                <div style="background: rgba(255,255,255,0.02); border: 1px solid rgba(255,255,255,0.05); padding: 12px 16px; border-radius: 8px; display: flex; justify-content: space-between; align-items: center;">
                  <div>
                    <h5 style="margin: 0; font-size: 13px; font-weight: 700; color: #fff;">${show.title}</h5>
                    <span style="font-size: 10px; color: rgba(255,255,255,0.45);">Category: ${show.category} | ${show.seasons} Seasons</span>
                  </div>
                  <span class="os-badge os-badge-green">${show.episodesCount} Episodes</span>
                </div>
              `).join('')}
            </div>
          </div>

          <div class="os-card">
            <h4 class="os-card-title">Register New Series</h4>
            <form id="create-show-form">
              <div class="form-group">
                <label for="show-title">Series Title</label>
                <input type="text" id="show-title" required placeholder="e.g. Sheeko Soomaaliyeed">
              </div>
              <div class="form-group">
                <label for="show-category">Primary Category</label>
                <select id="show-category">
                  <option value="Entertainment">Entertainment</option>
                  <option value="Documentaries">Documentaries</option>
                  <option value="News">News</option>
                </select>
              </div>
              <div class="form-group" style="display: grid; grid-template-columns: 1fr 1fr; gap: 14px;">
                <div class="form-group">
                  <label for="show-seasons">Total Seasons</label>
                  <input type="number" id="show-seasons" value="1" min="1">
                </div>
                <div class="form-group">
                  <label for="show-episodes">Initial Episodes</label>
                  <input type="number" id="show-episodes" value="0" min="0">
                </div>
              </div>
              <button type="submit" class="os-btn" style="width: 100%;">Register Series</button>
            </form>
          </div>
        </div>
      `;
      bindShowsEvents();

    } else if (activeSubTab === "channels") {
      pane.innerHTML = `
        <div class="pane-header">
          <h3>Linear Satellite Channels Ingress</h3>
          <p>Manage television stream nodes, encoder ingress keys (RTMP/SRT), and live camera feed angles.</p>
        </div>

        <div class="os-grid-2">
          <!-- Ingest keys -->
          <div class="os-card">
            <h4 class="os-card-title">Ingest Control & Keys</h4>

            <div class="form-group">
              <label>RTMP Ingest Server URL</label>
              <div style="display: flex; gap: 8px;">
                <input type="text" readonly value="${primaryIngest}" style="flex: 1; font-family: var(--font-mono); font-size: 11px; background: rgba(0,0,0,0.35); border: 1px solid rgba(255,255,255,0.08); padding: 8px 12px; color: #fff; border-radius: 6px;">
                <button class="os-btn os-btn-secondary btn-copy" data-val="${primaryIngest}">Copy</button>
              </div>
            </div>

            <div class="form-group">
              <label>SRT Caller Ingest Server URL</label>
              <div style="display: flex; gap: 8px;">
                <input type="text" readonly value="${fallbackIngest}" style="flex: 1; font-family: var(--font-mono); font-size: 11px; background: rgba(0,0,0,0.35); border: 1px solid rgba(255,255,255,0.08); padding: 8px 12px; color: #fff; border-radius: 6px;">
                <button class="os-btn os-btn-secondary btn-copy" data-val="${fallbackIngest}">Copy</button>
              </div>
            </div>

            <div class="form-group">
              <label>RTMP Stream Key (Secret)</label>
              <div style="display: flex; gap: 8px;">
                <input type="password" readonly value="${streamKey}" id="stream-key-input" style="flex: 1; font-family: var(--font-mono); font-size: 11px; background: rgba(0,0,0,0.35); border: 1px solid rgba(255,255,255,0.08); padding: 8px 12px; color: #fff; border-radius: 6px;">
                <button class="os-btn os-btn-secondary" id="btn-reveal-key">Reveal</button>
              </div>
            </div>
            <button class="os-btn" id="btn-refresh-stream-key" style="width: 100%; margin-top: 10px;">
              🔄 Regenerate Stream Ingest Key
            </button>
          </div>

          <!-- Channel List -->
          <div class="os-card">
            <h4 class="os-card-title">Active Satellite Feeds</h4>
            <div style="display: flex; flex-direction: column; gap: 10px;">
              ${CHANNELS.map(ch => `
                <div style="background: rgba(255,255,255,0.02); border: 1px solid rgba(255,255,255,0.05); padding: 12px 16px; border-radius: 8px; display: flex; justify-content: space-between; align-items: center;">
                  <div style="display: flex; align-items: center; gap: 12px;">
                    <span style="font-size: 24px;">${ch.logo}</span>
                    <div>
                      <h5 style="margin: 0; font-size: 13px; font-weight: 700; color: #fff;">${ch.name}</h5>
                      <span style="font-size: 9px; color: rgba(255,255,255,0.45); font-family: var(--font-mono);">${ch.id}</span>
                    </div>
                  </div>
                  <span class="os-badge os-badge-green">ACTIVE</span>
                </div>
              `).join('')}
            </div>
          </div>
        </div>
      `;
      bindChannelsEvents();

    } else if (activeSubTab === "scheduling") {
      pane.innerHTML = `
        <div class="pane-header">
          <h3>EPG Program Guide Scheduling</h3>
          <p>Schedule episodes, talks, and bulletins on linear TV guides. Changes synchronize live to the viewer program timeline.</p>
        </div>

        <div class="os-grid-2">
          <!-- Schedule Injection -->
          <div class="os-card">
            <h4 class="os-card-title">Inject Program into EPG</h4>
            <form id="epg-inject-form">
              <div class="form-group">
                <label for="epg-channel">Select Channel</label>
                <select id="epg-channel">
                  ${CHANNELS.map(c => `<option value="${c.id}">${c.name}</option>`).join('')}
                </select>
              </div>
              <div class="form-group">
                <label for="epg-title">Program Title</label>
                <input type="text" id="epg-title" required placeholder="e.g. Dood-Wadaag: Maxaa Cusub?">
              </div>
              <div class="form-group" style="display: grid; grid-template-columns: 1fr 1fr; gap: 14px;">
                <div class="form-group">
                  <label for="epg-start">Start Time (HH:MM)</label>
                  <input type="text" id="epg-start" value="14:00" required placeholder="e.g. 19:30">
                </div>
                <div class="form-group">
                  <label for="epg-duration">Duration (Minutes)</label>
                  <input type="number" id="epg-duration" value="60" required placeholder="e.g. 45">
                </div>
              </div>
              <div class="form-group">
                <label for="epg-genre">Genre / Category</label>
                <input type="text" id="epg-genre" value="Talk Show" required placeholder="e.g. Sports, News">
              </div>
              <button type="submit" class="os-btn" style="width: 100%;">
                <span>📅</span> Inject Scheduled Program
              </button>
            </form>
          </div>

          <!-- Schedule preview logs -->
          <div class="os-card">
            <h4 class="os-card-title">Upcoming Scheduled Program Logs</h4>
            <div style="background: rgba(0,0,0,0.3); border: 1px solid rgba(255,255,255,0.06); padding: 16px; border-radius: 8px; height: 300px; overflow-y: auto;">
              ${CHANNELS.map(ch => `
                <div style="margin-bottom: 16px; border-bottom: 1px solid rgba(255,255,255,0.04); padding-bottom: 10px;">
                  <h5 style="font-size: 11px; font-weight: 850; color: var(--brand-primary); margin: 0 0 6px 0; text-transform: uppercase;">${ch.name} Schedule</h5>
                  ${ch.programs.slice(0, 3).map(p => `
                    <div style="font-size: 11px; display: flex; justify-content: space-between; margin-bottom: 4px; color: rgba(255,255,255,0.75);">
                      <span>🕒 ${p.start} - <strong>${p.title}</strong></span>
                      <span style="font-size: 9px; color: rgba(255,255,255,0.4);">${p.genre} (${p.duration}m)</span>
                    </div>
                  `).join('')}
                </div>
              `).join('')}
            </div>
          </div>
        </div>
      `;
      bindSchedulingEvents();

    } else if (activeSubTab === "publish") {
      pane.innerHTML = `
        <div class="pane-header">
          <h3>Edge Distribution & Publish Controls</h3>
          <p>Sync linear TV feeds to external social networks and clear edge server caches dynamically on Alibaba Cloud CDN.</p>
        </div>

        <div class="os-grid-2">
          <!-- CDN invalidations -->
          <div class="os-card">
            <h4 class="os-card-title">Alibaba Cloud CDN Purge Tool</h4>
            <p class="section-desc" style="margin-bottom: 16px;">Purge edge caches to invalidate stale metadata or stream configurations instantly across regional nodes.</p>
            <div class="form-group">
              <label for="cdn-purge-url">Target Ingress Path (Pattern)</label>
              <input type="text" id="cdn-purge-url" value="/assets/hls/live_gntv_*.m3u8" style="font-family: var(--font-mono); font-size: 12px;">
            </div>
            <button class="os-btn" id="btn-purge-cdn" style="width: 100%;">
              🚀 Invalidate CDN Edge Cache
            </button>
            <div id="cdn-purge-status" style="margin-top: 15px; font-family: var(--font-mono); font-size: 11px; padding: 10px; background: rgba(0,0,0,0.3); border-radius: 6px; display: none;"></div>
          </div>

          <!-- Social feeds sync -->
          <div class="os-card" style="display: flex; flex-direction: column; gap: 16px;">
            <h4 class="os-card-title">Live Egress Platform Sync</h4>
            ${distChannels.map(ch => `
              <div style="background: rgba(255,255,255,0.02); border: 1px solid rgba(255,255,255,0.05); border-radius: 8px; padding: 12px 16px; display: flex; align-items: center; justify-content: space-between;">
                <div style="display: flex; align-items: center; gap: 12px;">
                  <span style="font-size: 24px;">${ch.icon}</span>
                  <div>
                    <h5 style="font-size: 13px; font-weight: 700; color: #fff; margin: 0;">${ch.name}</h5>
                    <span class="os-badge ${ch.status === 'Connected' || ch.status === 'Broadcasting' || ch.status === 'Synced' ? 'os-badge-green' : 'os-badge-red'}" style="margin-top: 4px; font-size: 8px;">${ch.status}</span>
                  </div>
                </div>
                <div>
                  <button class="os-btn os-btn-secondary btn-toggle-dist" data-id="${ch.id}" style="padding: 6px 12px; font-size: 11px;">
                    ${ch.status === 'Offline' ? 'Connect' : 'Disconnect'}
                  </button>
                </div>
              </div>
            `).join('')}
          </div>
        </div>
      `;
      bindPublishEvents();

    } else if (activeSubTab === "analytics") {
      pane.innerHTML = `
        <div class="pane-header">
          <h3>Audience Analytics Hub</h3>
          <p>Real-time telemetry measuring client connections, content retention curves, and concurrent streaming performance.</p>
        </div>

        <div class="kpi-row">
          <div class="kpi-card">
            <div class="kpi-title">Current Global Viewers</div>
            <div class="kpi-val">${store.getState("viewerCount").toLocaleString()}</div>
          </div>
          <div class="kpi-card">
            <div class="kpi-title">Avg Bitrate Ingress</div>
            <div class="kpi-val">${store.getState("bitrate")}</div>
          </div>
          <div class="kpi-card">
            <div class="kpi-title">NOC Stream Frame Rate</div>
            <div class="kpi-val">${store.getState("fps")} FPS</div>
          </div>
          <div class="kpi-card">
            <div class="kpi-title">NOC Ingress Status</div>
            <div class="kpi-val" style="color: #10b981; font-weight: 800;">ACTIVE</div>
          </div>
        </div>

        <div class="os-grid-2">
          <!-- Viewer Retention SVG chart -->
          <div class="os-card">
            <h4 class="os-card-title">Viewer Retention Spline (Live Stream)</h4>
            <div style="display: flex; align-items: center; justify-content: center; height: 200px;">
              <svg viewBox="0 0 400 200" style="width: 100%; height: 100%;">
                <line x1="10" y1="20" x2="390" y2="20" stroke="rgba(255,255,255,0.05)" stroke-width="1" />
                <line x1="10" y1="60" x2="390" y2="60" stroke="rgba(255,255,255,0.05)" stroke-width="1" />
                <line x1="10" y1="100" x2="390" y2="100" stroke="rgba(255,255,255,0.05)" stroke-width="1" />
                <line x1="10" y1="140" x2="390" y2="140" stroke="rgba(255,255,255,0.05)" stroke-width="1" />
                <line x1="10" y1="180" x2="390" y2="180" stroke="rgba(255,255,255,0.05)" stroke-width="1" />
                <path d="M 10 180 Q 70 120 130 90 T 250 60 T 390 30 L 390 180 Z" fill="rgba(255, 42, 75, 0.08)" />
                <path d="M 10 180 Q 70 120 130 90 T 250 60 T 390 30" fill="none" stroke="var(--brand-primary)" stroke-width="3" />
                <circle cx="130" cy="90" r="5" fill="var(--brand-primary)" />
                <circle cx="250" cy="60" r="5" fill="var(--brand-primary)" />
                <text x="135" y="85" fill="#fff" font-size="8" font-family="monospace">Ingress Peak</text>
                <text x="255" y="55" fill="#fff" font-size="8" font-family="monospace">Satellite Handshake</text>
              </svg>
            </div>
          </div>

          <!-- Concurrent Viewers Hourly bar chart -->
          <div class="os-card">
            <h4 class="os-card-title">Concurrent Viewers Hourly Distribution (Past 6 hours)</h4>
            <div style="display: flex; align-items: flex-end; justify-content: space-around; height: 180px; padding: 10px 0;">
              <div style="display: flex; flex-direction: column; align-items: center; gap: 8px;">
                <span style="font-size: 10px; font-family: monospace;">12K</span>
                <div style="width: 28px; height: 60px; background: rgba(255,255,255,0.06); border-radius: 4px; border: 1px solid rgba(255,255,255,0.1);"></div>
                <span style="font-size: 9px; color: rgba(255,255,255,0.4);">18:00</span>
              </div>
              <div style="display: flex; flex-direction: column; align-items: center; gap: 8px;">
                <span style="font-size: 10px; font-family: monospace;">16K</span>
                <div style="width: 28px; height: 80px; background: rgba(255,255,255,0.06); border-radius: 4px; border: 1px solid rgba(255,255,255,0.1);"></div>
                <span style="font-size: 9px; color: rgba(255,255,255,0.4);">19:00</span>
              </div>
              <div style="display: flex; flex-direction: column; align-items: center; gap: 8px;">
                <span style="font-size: 10px; font-family: monospace;">22K</span>
                <div style="width: 28px; height: 110px; background: rgba(255,255,255,0.06); border-radius: 4px; border: 1px solid rgba(255,255,255,0.1);"></div>
                <span style="font-size: 9px; color: rgba(255,255,255,0.4);">20:00</span>
              </div>
              <div style="display: flex; flex-direction: column; align-items: center; gap: 8px;">
                <span style="font-size: 10px; font-family: monospace;">28K</span>
                <div style="width: 28px; height: 140px; background: var(--brand-primary); border-radius: 4px; box-shadow: 0 0 10px var(--brand-primary-glow);"></div>
                <span style="font-size: 9px; color: #fff; font-weight: 700;">21:00</span>
              </div>
              <div style="display: flex; flex-direction: column; align-items: center; gap: 8px;">
                <span style="font-size: 10px; font-family: monospace;">24K</span>
                <div style="width: 28px; height: 120px; background: rgba(255,255,255,0.06); border-radius: 4px; border: 1px solid rgba(255,255,255,0.1);"></div>
                <span style="font-size: 9px; color: rgba(255,255,255,0.4);">22:00</span>
              </div>
              <div style="display: flex; flex-direction: column; align-items: center; gap: 8px;">
                <span style="font-size: 10px; font-family: monospace;">18K</span>
                <div style="width: 28px; height: 90px; background: rgba(255,255,255,0.06); border-radius: 4px; border: 1px solid rgba(255,255,255,0.1);"></div>
                <span style="font-size: 9px; color: rgba(255,255,255,0.4);">23:00</span>
              </div>
            </div>
          </div>
        </div>
      `;

    } else if (activeSubTab === "monetization") {
      pane.innerHTML = `
        <div class="pane-header">
          <h3>GNTV DIGITAL, ALL EVERYWHERE Monetization Control Panel</h3>
          <p>Configure subscription tier pricing rates, pay-per-view match licenses, and set Google Ad Manager insertion intervals.</p>
        </div>

        <div class="os-grid-2">
          <!-- Prices Setup -->
          <div class="os-card">
            <h4 class="os-card-title">Configure Plan Rates</h4>

            <div class="form-group">
              <label for="mon-price-premium">Premium Plan Rate ($ USD / Month)</label>
              <input type="number" step="0.01" id="mon-price-premium" value="${monSettings.premiumPrice}">
            </div>

            <div class="form-group">
              <label for="mon-price-family">Family Plan Rate ($ USD / Month)</label>
              <input type="number" step="0.01" id="mon-price-family" value="${monSettings.familyPrice}">
            </div>

            <div class="form-group">
              <label for="mon-price-business">Business Plan Rate ($ USD / Month)</label>
              <input type="number" step="0.01" id="mon-price-business" value="${monSettings.businessPrice}">
            </div>

            <button class="os-btn" id="btn-save-mon-prices" style="width: 100%;">
              💾 Update Subscription Pricing
            </button>
          </div>

          <!-- Ad insertion -->
          <div class="os-card">
            <h4 class="os-card-title">Ad Insertion Rules</h4>

            <div class="form-group">
              <label for="mon-ad-freq">Pre-roll/Mid-roll Frequency (Seconds of delay)</label>
              <div style="display: flex; align-items: center; gap: 12px;">
                <input type="range" id="mon-ad-freq" min="5" max="60" value="${monSettings.adFrequency}" style="flex: 1;">
                <span id="mon-ad-freq-val" style="font-family: var(--font-mono); font-size: 13px; font-weight: 700; width: 40px; text-align: right;">${monSettings.adFrequency}s</span>
              </div>
            </div>

            <div class="form-group" style="flex-direction: row; align-items: center; gap: 10px;">
              <input type="checkbox" id="mon-ppv-active" ${monSettings.ppvActive ? 'checked' : ''} style="width: auto; cursor: pointer;">
              <label for="mon-ppv-active" style="margin: 0; cursor: pointer;">Pay-Per-View Match Licensing Active</label>
            </div>

            <div style="background: rgba(255,255,255,0.02); border: 1px solid rgba(255,255,255,0.05); padding: 16px; border-radius: 8px; font-size: 11px; color: rgba(255,255,255,0.5); line-height: 1.5; margin-top: 24px;">
              <strong>Monetization Guard:</strong> Changes applied here affect ad network configuration scripts and paywall trigger amounts globally. Ad networks default to Somali Telecom AdNet.
            </div>
          </div>
        </div>
      `;
      bindMonEvents();
    } else if (activeSubTab === "processing-center") {
      pane.innerHTML = `<div id="proc-noc-root"></div>`;
      const mountNode = pane.querySelector("#proc-noc-root");
      activeTabCleanup = initProcessingCenter(mountNode);
    } else if (activeSubTab === "executive-analytics") {
      pane.innerHTML = `<div id="executive-analytics-root"></div>`;
      const mountNode = pane.querySelector("#executive-analytics-root");
      activeTabCleanup = initExecutiveAnalyticsDashboard(mountNode);
    } else if (activeSubTab === "partner-syndication") {
      pane.innerHTML = `<div id="partner-syndication-root"></div>`;
      const mountNode = pane.querySelector("#partner-syndication-root");
      activeTabCleanup = initPartnerSyndicationDashboard(mountNode);
    } else if (activeSubTab === "sheeko-voice") {
      pane.innerHTML = `<div id="sheeko-xariiro-root"></div>`;
      const mountNode = pane.querySelector("#sheeko-xariiro-root");
      activeTabCleanup = initSheekoXariiroVoiceStudio(mountNode);
    } else if (activeSubTab === "moderation") {
      pane.innerHTML = `<div id="chat-moderation-root"></div>`;
      const mountNode = pane.querySelector("#chat-moderation-root");
      activeTabCleanup = initChatModerationConsole(mountNode, { roomId: "default-room" });
    }
  };

  const bindSidebarEvents = () => {
    container.querySelectorAll(".studio-tab-btn").forEach(btn => {
      btn.addEventListener("click", () => {
        container.querySelectorAll(".studio-tab-btn").forEach(b => b.classList.remove("active"));
        btn.classList.add("active");
        activeSubTab = btn.getAttribute("data-target");
        renderSubTab();
      });
    });
  };

  const bindUploadEvents = () => {
    const form = container.querySelector("#ingest-video-form");
    if (!form) return;

    form.addEventListener("submit", (e) => {
      e.preventDefault();
      if (isUploading) return;

      const title = container.querySelector("#ingest-title").value;
      const categorySel = container.querySelector("#ingest-category").value;
      const show = container.querySelector("#ingest-show").value;
      const duration = container.querySelector("#ingest-duration").value;
      const episode = container.querySelector("#ingest-episode").value;
      const host = container.querySelector("#ingest-host").value;
      const rating = container.querySelector("#ingest-rating").value;
      const premium = container.querySelector("#ingest-premium").checked;
      const description = container.querySelector("#ingest-description").value;

      isUploading = true;
      uploadProgress = 0;
      activeUploadingTitle = title;
      uploadStateText = `[${new Date().toLocaleTimeString()}] CMS Ingestion initiated for: "${title}"...`;
      renderSubTab();

      if (pipelineInterval) clearInterval(pipelineInterval);

      pipelineInterval = setInterval(() => {
        uploadProgress += 5;

        // Log statuses at different progress steps
        if (uploadProgress === 15) {
          uploadStateText += `\n[${new Date().toLocaleTimeString()}] Source File upload completed. Size: 2.4 GB. Connection rate: 450 Mbps.`;
        } else if (uploadProgress === 30) {
          uploadStateText += `\n[${new Date().toLocaleTimeString()}] Ingested metadata verified in GNTV DIGITAL, ALL EVERYWHERE CMS. Schema checks passed.`;
        } else if (uploadProgress === 50) {
          uploadStateText += `\n[${new Date().toLocaleTimeString()}] Chunked write to Alibaba OSS bucket 'gntv-vod-storage' successfully completed.`;
        } else if (uploadProgress === 65) {
          uploadStateText += `\n[${new Date().toLocaleTimeString()}] Launching FFmpeg Transcoder. Slicing into 1080p, 720p, 480p low-bandwidth profiles...`;
        } else if (uploadProgress === 80) {
          uploadStateText += `\n[${new Date().toLocaleTimeString()}] HLS & DASH manifest generation completed (.m3u8 index output verified).`;
        } else if (uploadProgress === 95) {
          uploadStateText += `\n[${new Date().toLocaleTimeString()}] Distributing files to Alibaba Cloud CDN edge nodes. Regional invalidations complete.`;
        } else if (uploadProgress >= 100) {
          uploadProgress = 100;
          uploadStateText += `\n[${new Date().toLocaleTimeString()}] [SUCCESS] Video successfully published! Broadcast notification dispatched to Front Door feed.`;
          clearInterval(pipelineInterval);
          isUploading = false;

          // Category mapping helper
          let mappedCategory = "News";
          if (categorySel === "Entertainment") mappedCategory = "Riwaayadaha";
          else if (categorySel === "Documentaries") mappedCategory = "Taariikhda";
          else if (categorySel === "Sports") mappedCategory = "Cayaaraha";

          // Add item to active catalog store
          store.addCatalogItem({
            title: show !== "New Show" ? `${show} - Episode ${episode}: ${title}` : title,
            category: mappedCategory,
            duration,
            host,
            rating,
            premium,
            description
          });

          alert(`Successfully Ingested and Published:\n${title}\nIt is now playable in the Front Door!`);
        }

        // Keep console scrolled down
        renderSubTab();
        const consoleLog = container.querySelector("#upload-simulation-log");
        if (consoleLog) {
          consoleLog.scrollTop = consoleLog.scrollHeight;
        }
      }, 350);
    });
  };

  const bindLibraryEvents = () => {
    container.querySelectorAll(".btn-delete-catalog-item").forEach(btn => {
      btn.addEventListener("click", () => {
        const id = btn.getAttribute("data-id");
        const row = container.querySelector(`#row-media-${id}`);
        if (confirm("Are you sure you want to delete this asset from the catalog?")) {
          store.deleteCatalogItem(id, "vod");
          if (row) row.remove();
          alert("Asset deleted from catalog.");
        }
      });
    });
  };

  const bindCategoriesEvents = () => {
    const form = container.querySelector("#create-category-form");
    if (!form) return;

    form.addEventListener("submit", (e) => {
      e.preventDefault();
      const name = container.querySelector("#cat-name").value;
      const slug = container.querySelector("#cat-slug").value;
      const description = container.querySelector("#cat-desc").value;

      localCategories.push({ name, slug, description });
      alert(`Category "${name}" successfully registered.`);
      renderSubTab();
    });
  };

  const bindShowsEvents = () => {
    const form = container.querySelector("#create-show-form");
    if (!form) return;

    form.addEventListener("submit", (e) => {
      e.preventDefault();
      const title = container.querySelector("#show-title").value;
      const category = container.querySelector("#show-category").value;
      const seasons = parseInt(container.querySelector("#show-seasons").value, 10) || 1;
      const initialEpisodes = parseInt(container.querySelector("#show-episodes").value, 10) || 0;

      localShows.push({ title, category, seasons, episodesCount: initialEpisodes });
      alert(`Show Series "${title}" successfully registered.`);
      renderSubTab();
    });
  };

  const bindChannelsEvents = () => {
    container.querySelectorAll(".btn-copy").forEach(btn => {
      btn.addEventListener("click", () => {
        const val = btn.getAttribute("data-val");
        navigator.clipboard.writeText(val);
        const originalText = btn.textContent;
        btn.textContent = "Copied!";
        btn.style.borderColor = "var(--brand-primary)";
        setTimeout(() => {
          btn.textContent = originalText;
          btn.style.borderColor = "";
        }, 1500);
      });
    });

    const revealBtn = container.querySelector("#btn-reveal-key");
    const keyInput = container.querySelector("#stream-key-input");
    if (revealBtn && keyInput) {
      revealBtn.addEventListener("click", () => {
        if (keyInput.type === "password") {
          keyInput.type = "text";
          revealBtn.textContent = "Hide";
        } else {
          keyInput.type = "password";
          revealBtn.textContent = "Reveal";
        }
      });
    }

    const refreshBtn = container.querySelector("#btn-refresh-stream-key");
    if (refreshBtn) {
      refreshBtn.addEventListener("click", () => {
        if (confirm("Regenerating ingest keys will terminate all active RTMP stream relays immediately. Proceed?")) {
          streamKey = "live_gntv_hub_" + Math.random().toString(36).substring(2, 10);
          fallbackIngest = "srt://srt-ingest.gntv.net:9000?streamid=" + streamKey;
          renderSubTab();
        }
      });
    }
  };

  const bindSchedulingEvents = () => {
    const epgForm = container.querySelector("#epg-inject-form");
    if (epgForm) {
      epgForm.addEventListener("submit", (e) => {
        e.preventDefault();
        const channelId = container.querySelector("#epg-channel").value;
        const title = container.querySelector("#epg-title").value;
        const start = container.querySelector("#epg-start").value;
        const duration = parseInt(container.querySelector("#epg-duration").value, 10) || 60;
        const genre = container.querySelector("#epg-genre").value;

        store.addScheduledProgram(channelId, {
          title,
          start,
          duration,
          genre,
          description: "Ingested from EPG injection module inside GNTV DIGITAL, ALL EVERYWHERE Media OS Console."
        });

        alert(`Successfully injected program "${title}" into EPG schedule.`);
        epgForm.reset();
      });
    }
  };

  const bindPublishEvents = () => {
    const purgeBtn = container.querySelector("#btn-purge-cdn");
    const statusDiv = container.querySelector("#cdn-purge-status");
    const purgeUrl = container.querySelector("#cdn-purge-url");

    if (purgeBtn && statusDiv) {
      purgeBtn.addEventListener("click", () => {
        purgeBtn.disabled = true;
        statusDiv.style.display = "block";
        statusDiv.style.color = "#f59e0b";
        statusDiv.textContent = `[Alibaba Cloud CDN] Purge requested for pattern: ${purgeUrl.value}...`;

        setTimeout(() => {
          statusDiv.style.color = "#10b981";
          statusDiv.textContent = `[SUCCESS] Cache cleared successfully for all edge nodes in East Africa and Somali Region.`;
          purgeBtn.disabled = false;
        }, 1500);
      });
    }

    container.querySelectorAll(".btn-toggle-dist").forEach(btn => {
      btn.addEventListener("click", () => {
        const id = btn.getAttribute("data-id");
        const ch = distChannels.find(c => c.id === id);
        if (ch) {
          if (ch.status === "Offline") {
            ch.status = "Connected";
          } else {
            ch.status = "Offline";
          }
          renderSubTab();
        }
      });
    });
  };

  const bindMonEvents = () => {
    const saveBtn = container.querySelector("#btn-save-mon-prices");
    const freqInput = container.querySelector("#mon-ad-freq");
    const freqVal = container.querySelector("#mon-ad-freq-val");

    if (freqInput && freqVal) {
      freqInput.addEventListener("input", (e) => {
        freqVal.textContent = e.target.value + "s";
      });
    }

    if (saveBtn) {
      saveBtn.addEventListener("click", () => {
        monSettings.premiumPrice = container.querySelector("#mon-price-premium").value;
        monSettings.familyPrice = container.querySelector("#mon-price-family").value;
        monSettings.businessPrice = container.querySelector("#mon-price-business").value;
        monSettings.adFrequency = freqInput.value;
        monSettings.ppvActive = container.querySelector("#mon-ppv-active").checked;

        alert(`Settings saved! Pricing updated:\nPremium: $${monSettings.premiumPrice}\nFamily: $${monSettings.familyPrice}\nBusiness: $${monSettings.businessPrice}\nAd frequency: ${monSettings.adFrequency}s`);
      });
    }
  };

  render();

  return () => {
    if (pipelineInterval) clearInterval(pipelineInterval);
    if (activeTabCleanup) activeTabCleanup();
    container.innerHTML = '';
  };
}
