import { store } from "../../../shared/src/state.js";
import { VODS, CHANNELS } from "../../../shared/src/utils/mockData.js";

// Multi-region city database
const CITY_DATA = {
  muqdisho: {
    name: "Muqdisho",
    country: "Somalia",
    coord: { x: 74, y: 72 },
    chId: "gntv-global",
    streamColor: "hsl(205, 100%, 55%)",
    streamName: "GNTV DIGITAL, ALL EVERYWHERE News Muqdisho Live",
    news: [
      "Dekadda Muqdisho oo la ballaariyey si loogu adeego maraakiibta waawayn ee container-ka.",
      "Kulan heer caalami ah oo looga hadlayo maalgashiga tamarta oo ka furmay caasimadda.",
      "Tartanka tiknoolajiyadda ee dhalinyarada oo maanta lagu soo gabagabeeyay magaalada."
    ],
    events: [
      "🇸🇴 Mogadishu Tech Summit (Oct 12-14)",
      "🇸🇴 Bandhigga Buugaagta Caalamiga ah ee Muqdisho"
    ],
    reporters: [
      { name: "Cabdiweli Cali", role: "Wariye Sare (Mogadishu)", bio: "Khibrad 10 sano ah u leh soo tabinta wararka siyaasadda iyo horumarka caasimadda.", emoji: "🎤" }
    ]
  },
  hargeisa: {
    name: "Hargeysa",
    country: "Somaliland",
    coord: { x: 70, y: 55 },
    chId: "garissa-tv",
    streamColor: "hsl(142, 76%, 45%)",
    streamName: "Hargeysa Cultural Stream",
    news: [
      "Bandhigga Hiddaha iyo Dhaqanka oo ka furmay Hargeysa, soona jiitay kumanaan qof.",
      "Warshado cusub oo soo saara agabka dhismaha oo laga furay duleedka magaalada.",
      "Mashaariic biyo-galin ah oo laga bilaabay deegaanada miyiga ah ee ku xeeran caasimada."
    ],
    events: [
      "🇸🇴 Hargeysa International Book Fair (Jul 20-25)",
      "Tartanka Orodka Gaabna ee Gobolada Waqooyi"
    ],
    reporters: [
      { name: "Sahra Cumar", role: "Correspondent (Hargeysa Desk)", bio: "Waxay si gaar ah u tabisaa arrimaha bulshada, dhaqanka, iyo ganacsiga gaarka loo leeyahay.", emoji: "🎙️" }
    ]
  },
  nairobi: {
    name: "Nairobi",
    country: "Kenya",
    coord: { x: 67, y: 80 },
    chId: "eastleigh-tv",
    streamColor: "hsl(348, 100%, 58%)",
    streamName: "Eastleigh Council TV Relay",
    news: [
      "Shirwaynaha Dhaqaalaha ee Eastleigh oo laysku raacay fududaynta canshuuraha ganacsiyada.",
      "Tartanka Kubadda Cagta dhalinyarada Eastleigh oo si rasmi ah u bilaabmay asbuucan.",
      "Wadooyin cusub oo dib u habayn lagu sameeyay oo laga furay dhexda xaafada Eastleigh."
    ],
    events: [
      "🇰🇪 Eastleigh Trade Fair (Oct 5-7)",
      "Nairobi Cultural Integration Festival"
    ],
    reporters: [
      { name: "Axmed Yaasiin", role: "East Africa Bureau Chief", bio: "Hogaamiyaha wariyeyaasha Bariga Afrika, isagoo xaruntiisu tahay caasimadda Nairobi.", emoji: "🎥" }
    ]
  },
  "addis-ababa": {
    name: "Addis Ababa",
    country: "Ethiopia",
    coord: { x: 62, y: 64 },
    chId: "gntv-global",
    streamColor: "hsl(45, 95%, 55%)",
    streamName: "AU Bureau Broadcast",
    news: [
      "Midowga Afrika oo shir jaraa'id ku qabtay xaruntooda caasimadda oo looga hadlay nabada.",
      "Mashruuca jidka tareenka ee cusub oo loo hirgeliyay si loo fududeeyo isu-socodka bulshada.",
      "Kulan ganacsi oo u dhexeeya shirkadaha Itoobiya iyo Soomaaliya oo ka dhacay Addis."
    ],
    events: [
      "🇪🇹 African Union Summit Panel Discussions",
      "Addis Trade Expo (Nov 10-15)"
    ],
    reporters: [
      { name: "Dawit Bekele", role: "Horn of Africa Analyst", bio: "Waxay ku takhasustay tabinta wararka midowga afrika iyo siyaasadda gobolka Geeska.", emoji: "📺" }
    ]
  },
  jigjiga: {
    name: "Jigjiga",
    country: "Somali Region",
    coord: { x: 68, y: 62 },
    chId: "wajir-tv",
    streamColor: "hsl(190, 100%, 50%)",
    streamName: "Jigjiga Newsroom Live",
    news: [
      "Jaamacadda Jigjiga oo soo bandhigtay cilmi-baaris ku saabsan beeraha iyo daaqa.",
      "Mashruuc biyo sifayn ah oo laga hirgeliyay xaafado cusub oo ka tirsan magaalada.",
      "Tababar ku saabsan kobcinta tayada macalimiinta dugsiyada oo ka furmay Jigjiga."
    ],
    events: [
      "🇪🇹 Jigjiga University Regional Science Fair",
      "Dhaanto Traditional Heritage Festival (Aug)"
    ],
    reporters: [
      { name: "Khadra Yaasiin", role: "Regional Field Reporter", bio: "Khadra waxay si toos ah u soo tabisaa wararka gobolka, gaar ahaan nolosha reer miyiga.", emoji: "🎤" }
    ]
  },
  djibouti: {
    name: "Djibouti",
    country: "Djibouti",
    coord: { x: 68, y: 50 },
    chId: "gntv-global",
    streamColor: "hsl(280, 80%, 60%)",
    streamName: "Djibouti Port Telemetries",
    news: [
      "Dekadda Jabuuti oo heshiis cusub oo dhanka gaadiidka ah la saxiixatay shirkado caalami ah.",
      "Mashruuca Tamarta Cadceedda (Solar energy) oo laga hirgeliyay deegaanka roobka yar.",
      "Madaxweynaha Jabuuti oo dhagax-dhigay dugsi sare oo cusub oo laga dhisayo caasimada."
    ],
    events: [
      "🇩🇯 Red Sea Logistics and Trade Forum",
      "Djibouti Cultural Expo & Music Week"
    ],
    reporters: [
      { name: "Mustafe Cilmi", role: "Maritime Correspondent", bio: "Khabiir ku takhasusay tabinta wararka ganacsiga badaha, dekadaha iyo xiriirka caalamiga ah.", emoji: "📡" }
    ]
  },
  kampala: {
    name: "Kampala",
    country: "Uganda",
    coord: { x: 55, y: 78 },
    chId: "eastleigh-tv",
    streamColor: "hsl(15, 90%, 55%)",
    streamName: "Kampala Somali Community",
    news: [
      "Jaaliyadda Soomaaliyeed ee Kampala oo qabtay kulan weyn oo looga hadlayo isdhexgalka.",
      "Kampala Tech Hub oo deeq waxbarasho u fidiyay ardayda jaaliyadda Soomaaliyeed.",
      "Tartanka ciyaaraha fudud ee dhalinyarada Kampala oo bilowday maanta."
    ],
    events: [
      "🇺🇬 Somali Diaspora Business & Career Forum",
      "Kampala Youth Sports League Tournament"
    ],
    reporters: [
      { name: "Yuusuf Abdi", role: "Uganda Desk Officer", bio: "Wuxuu daboolaa arrimaha waxbarashada, ganacsiga, iyo jaaliyadaha ku nool caasimadda Kampala.", emoji: "🎙️" }
    ]
  },
  london: {
    name: "London",
    country: "United Kingdom",
    coord: { x: 25, y: 20 },
    chId: "gntv-global",
    streamColor: "hsl(310, 80%, 55%)",
    streamName: "London Euro Bureau Relay",
    news: [
      "Shirka Jaaliyada ee London oo looga dooday sidii loo kordhin lahaa maalgashiga dhulka hooyo.",
      "Bandhig faneed ballaaran oo lagu soo bandhigay suugaanta iyo maansada Soomaaliyeed.",
      "Magaalada London oo martiqaaday dhalinyarada Soomaaliyeed ee ku guuleystay abaalmarinta hal-abuurka."
    ],
    events: [
      "🇬🇧 London Somali Week Festival (Oct)",
      "UK Diaspora Investor Summit Gala"
    ],
    reporters: [
      { name: "Zamzam Axmed", role: "Europe Correspondent", bio: "Zamzam waxay falanqaysaa wararka Yurub iyo nolosha qurbajoogta ku nool UK.", emoji: "🎥" }
    ]
  }
};

const CITY_KEYS = Object.keys(CITY_DATA);

export function initMobileApp(container) {
  let activeDevice = "iphone"; // iphone, samsung, android-tv, smart-tv
  let selectedCityKey = "muqdisho"; // default selected city
  let activeMobileTab = "map"; // map, vod, shorts
  let canvasAnimFrame = null;
  let simulatedSignalOffset = 0;

  // TV specific state
  let tvActiveTab = "map"; // map, vod, settings
  let tvFocusedCityIndex = 0; // Focus index on cities map
  let tvFocusedVodIndex = 0; // Focus index on VOD library

  const render = () => {
    // Clear active animation frames
    if (canvasAnimFrame) {
      cancelAnimationFrame(canvasAnimFrame);
      canvasAnimFrame = null;
    }

    const currentCity = CITY_DATA[selectedCityKey];

    container.innerHTML = `
      <div class="mobile-app-simulator-container">
        <!-- Sidebar Simulator Controls (Left Panel) -->
        <div class="sim-sidebar glass-card">
          <h2 class="sim-title"><span style="color: var(--brand-primary);">Device</span> Simulator</h2>
          <p class="sim-desc">Click a device profile to render the simulated GNTV DIGITAL, ALL EVERYWHERE app environment.</p>

          <div class="sim-device-selector-list">
            <button class="btn-device-select ${activeDevice === 'iphone' ? 'active' : ''}" data-device="iphone">
              <span class="device-icon">📱</span>
              <div class="device-meta">
                <span class="device-name">iPhone 15 Pro</span>
                <span class="device-os">Apple iOS (Portrait)</span>
              </div>
            </button>
            <button class="btn-device-select ${activeDevice === 'samsung' ? 'active' : ''}" data-device="samsung">
              <span class="device-icon">📱</span>
              <div class="device-meta">
                <span class="device-name">Galaxy S24 Ultra</span>
                <span class="device-os">Android (Portrait)</span>
              </div>
            </button>
            <button class="btn-device-select ${activeDevice === 'android-tv' ? 'active' : ''}" data-device="android-tv">
              <span class="device-icon">📺</span>
              <div class="device-meta">
                <span class="device-name">Android TV</span>
                <span class="device-os">16:9 Landscape (TV OS)</span>
              </div>
            </button>
            <button class="btn-device-select ${activeDevice === 'smart-tv' ? 'active' : ''}" data-device="smart-tv">
              <span class="device-icon">📺</span>
              <div class="device-meta">
                <span class="device-name">Apple Smart TV</span>
                <span class="device-os">16:9 Widescreen (tvOS)</span>
              </div>
            </button>
          </div>

          <div class="sim-tip-box" style="margin-top: auto; padding: 12px; border-radius: 8px; background: rgba(255,255,255,0.02); border: 1px solid rgba(255,255,255,0.05);">
            <h4 style="font-size: 11px; text-transform: uppercase; color: var(--brand-primary); font-weight: 800; margin-bottom: 4px;">Pro Tip</h4>
            <p style="font-size: 11px; color: rgba(255,255,255,0.6); line-height: 1.4;">When TV layout is active, use the interactive Remote Control on the right side to navigate using the D-Pad buttons.</p>
          </div>
        </div>

        <!-- Central Display Area -->
        <div class="sim-display-workspace">
          ${renderDeviceShell(currentCity)}
        </div>

        <!-- Right Side: Interactive TV Remote Control (Only visible/active when TV devices are selected) -->
        <div class="sim-remote-container" style="display: ${activeDevice.includes('tv') ? 'flex' : 'none'};">
          <div class="tv-remote-shell">
            <div class="remote-header">
              <span class="remote-brand">GN<span style="color: var(--brand-primary)">TV</span> REMOTE</span>
              <span class="remote-led"></span>
            </div>

            <div class="remote-power-row">
              <button class="remote-power-btn" id="btn-remote-power" title="Restart Simulator">⟳</button>
              <button class="remote-menu-btn" id="btn-remote-menu" title="Menu Header">MENU</button>
            </div>

            <div class="dpad-container">
              <button class="dpad-btn dpad-up" id="btn-remote-up" title="Navigate Up">▲</button>
              <button class="dpad-btn dpad-left" id="btn-remote-left" title="Navigate Left">◀</button>
              <button class="dpad-btn dpad-ok" id="btn-remote-ok" title="Select / OK">OK</button>
              <button class="dpad-btn dpad-right" id="btn-remote-right" title="Navigate Right">▶</button>
              <button class="dpad-btn dpad-down" id="btn-remote-down" title="Navigate Down">▼</button>
            </div>

            <div class="remote-nav-row">
              <button class="remote-pill-btn" id="btn-remote-back" style="font-size: 10px; font-weight: 800;">BACK</button>
              <button class="remote-pill-btn" id="btn-remote-home" style="font-size: 10px; font-weight: 800;">HOME</button>
            </div>

            <div class="remote-vol-ch-row">
              <div class="remote-rocker">
                <button class="btn-rocker-up" id="btn-remote-vol-up">+</button>
                <span style="font-size: 8px; color: rgba(255,255,255,0.4); font-weight: 700; margin: 4px 0;">VOL</span>
                <button class="btn-rocker-down" id="btn-remote-vol-down">-</button>
              </div>
              <div class="remote-rocker">
                <button class="btn-rocker-up" id="btn-remote-ch-up">▲</button>
                <span style="font-size: 8px; color: rgba(255,255,255,0.4); font-weight: 700; margin: 4px 0;">CH</span>
                <button class="btn-rocker-down" id="btn-remote-ch-down">▼</button>
              </div>
            </div>
          </div>
        </div>
      </div>
    `;

    // Wire events
    setupListeners();
    // Fire canvas loop
    initCanvasLoop();
  };

  const renderDeviceShell = (city) => {
    if (activeDevice === "iphone" || activeDevice === "samsung") {
      const isApple = activeDevice === "iphone";
      return `
        <!-- Smartphone Container -->
        <div class="smartphone-frame ${isApple ? 'apple-bezel' : 'android-bezel'}">
          <!-- Screen Glass -->
          <div class="smartphone-screen-content">
            <!-- Top Status Bar overlay -->
            <div class="phone-status-bar">
              <span class="status-time">20:49</span>
              ${isApple ? '<div class="phone-dynamic-island"></div>' : '<div class="phone-camera-hole"></div>'}
              <div class="status-icons">
                <span>📶</span>
                <span>5G</span>
                <span>🔋 92%</span>
              </div>
            </div>

            <!-- Dynamic Sub-Tab Content -->
            <div class="phone-app-body">
              ${renderMobileAppBody(city)}
            </div>

            <!-- Bottom Navigation Bar inside smartphone app -->
            <div class="phone-app-nav">
              <button class="mobile-nav-btn ${activeMobileTab === 'map' ? 'active' : ''}" data-mobtab="map">
                <span class="icon">🗺️</span>
                <span class="label">Africa Live</span>
              </button>
              <button class="mobile-nav-btn ${activeMobileTab === 'vod' ? 'active' : ''}" data-mobtab="vod">
                <span class="icon">📼</span>
                <span class="label">VOD Library</span>
              </button>
              <button class="mobile-nav-btn ${activeMobileTab === 'shorts' ? 'active' : ''}" data-mobtab="shorts">
                <span class="icon">⚡</span>
                <span class="label">Shorts</span>
              </button>
            </div>
          </div>
        </div>
      `;
    } else {
      // Television UI (Android TV / Smart TV)
      const isAndroidTV = activeDevice === "android-tv";
      return `
        <!-- Widescreen Television frame -->
        <div class="tv-device-frame">
          <div class="tv-glass-screen">
            <!-- TV OS Navigation Shell -->
            <div class="tv-os-shell">
              <!-- Left Sidebar Navigation -->
              <div class="tv-os-sidebar">
                <div class="tv-brand">GN<span style="color: var(--brand-primary);">TV</span> <span class="tv-pill-badge">${isAndroidTV ? 'ATV' : 'tvOS'}</span></div>
                <div class="tv-sidebar-menu">
                  <button class="tv-side-btn ${tvActiveTab === 'map' ? 'focused' : ''}" data-tvtab="map">
                    🗺️ Africa Live
                  </button>
                  <button class="tv-side-btn ${tvActiveTab === 'vod' ? 'focused' : ''}" data-tvtab="vod">
                    📼 VOD Library
                  </button>
                  <button class="tv-side-btn ${tvActiveTab === 'settings' ? 'focused' : ''}" data-tvtab="settings">
                    ⚙️ Settings
                  </button>
                </div>

                <div class="tv-sidebar-footer" style="margin-top: auto; padding: 12px; font-size: 9px; opacity: 0.6;">
                  User: ${store.getState("user")?.name || "Guest"}
                </div>
              </div>

              <!-- Right Main Content Panel -->
              <div class="tv-os-content">
                ${renderTVAppBody(city)}
              </div>
            </div>
          </div>
          <!-- TV Stand -->
          <div class="tv-stand-base"></div>
        </div>
      `;
    };
  };

  const renderMobileAppBody = (city) => {
    if (activeMobileTab === "map") {
      return `
        <div class="mobile-header-brand">
          <span class="gntv-logo">GNTV DIGITAL, ALL EVERYWHERE</span>
          <span style="font-size: 10px; color: var(--brand-primary); font-weight: 800;">AFRICA LIVE</span>
        </div>

        <div class="mobile-map-scrollzone">
          <div class="mobile-svg-map-wrapper">
            <!-- SVG Map of Africa (Simulated with key coordinates) -->
            <svg viewBox="0 0 100 100" class="africa-svg-map">
              <!-- Outline shape representing East Africa/Horn of Africa & London -->
              <path d="M 20,10 L 40,20 L 50,40 L 45,50 L 60,65 L 75,60 L 85,75 L 70,90 L 50,85 L 35,70 L 25,45 Z" fill="rgba(255,255,255,0.02)" stroke="rgba(255,255,255,0.08)" stroke-width="0.75" />

              <!-- Dotted Lines from London to Africa -->
              <line x1="25" y1="20" x2="74" y2="72" stroke="rgba(255,42,75,0.15)" stroke-dasharray="1,1" stroke-width="0.5" />
              <line x1="25" y1="20" x2="70" y2="55" stroke="rgba(255,42,75,0.15)" stroke-dasharray="1,1" stroke-width="0.5" />
              <line x1="25" y1="20" x2="67" y2="80" stroke="rgba(255,42,75,0.15)" stroke-dasharray="1,1" stroke-width="0.5" />

              <!-- Map Points / City Nodes -->
              ${Object.entries(CITY_DATA).map(([key, item]) => {
                const isSelected = selectedCityKey === key;
                return `
                  <circle cx="${item.coord.x}" cy="${item.coord.y}" r="${isSelected ? '2.5' : '1.8'}"
                    class="map-svg-dot ${isSelected ? 'selected' : ''}"
                    data-city-key="${key}"
                    style="fill: ${isSelected ? 'var(--brand-primary)' : 'rgba(255,255,255,0.5)'}; cursor: pointer; transition: all 0.3s;" />

                  <text x="${item.coord.x + 3}" y="${item.coord.y + 1}" class="map-svg-label ${isSelected ? 'selected' : ''}" style="font-size: 3px; font-weight: bold; fill: #ffffff; pointer-events: none;">
                    ${item.name}
                  </text>
                `;
              }).join("")}
            </svg>
          </div>

          <!-- Selected City Dashboard inside mobile view -->
          <div class="mobile-city-details-panel">
            <div class="city-title-row">
              <h3>${city.name}</h3>
              <span class="country-badge" style="background: ${city.streamColor};">${city.country}</span>
            </div>

            <!-- Canvas livestream viewport -->
            <div class="mobile-stream-container">
              <canvas id="mobile-live-canvas" class="simulated-canvas-player" width="320" height="180"></canvas>
              <div class="live-stream-overlay">
                <span class="live-dot-blink">●</span>
                <span class="live-overlay-title">LIVE RELAY</span>
              </div>
            </div>

            <!-- News Shelf -->
            <div class="mobile-content-box">
              <h4>📰 Local News</h4>
              <ul class="mobile-news-list">
                ${city.news.map(story => `<li>${story}</li>`).join("")}
              </ul>
            </div>

            <!-- Events Shelf -->
            <div class="mobile-content-box">
              <h4>📅 Local Events</h4>
              <ul class="mobile-events-list">
                ${city.events.map(ev => `<li>${ev}</li>`).join("")}
              </ul>
            </div>

            <!-- Correspondent Desk -->
            <div class="mobile-content-box">
              <h4>🎙️ Station Reporter</h4>
              ${city.reporters.map(rep => `
                <div class="mobile-reporter-card">
                  <div class="reporter-avatar">${rep.emoji}</div>
                  <div class="reporter-details">
                    <h5>${rep.name}</h5>
                    <span class="rep-role">${rep.role}</span>
                    <p class="rep-bio">${rep.bio}</p>
                  </div>
                </div>
              `).join("")}
            </div>
          </div>
        </div>
      `;
    } else if (activeMobileTab === "vod") {
      return `
        <div class="mobile-header-brand">
          <span class="gntv-logo">GNTV DIGITAL, ALL EVERYWHERE VOD</span>
          <span style="font-size: 10px; color: var(--brand-primary); font-weight: 800;">ON DEMAND</span>
        </div>

        <div class="mobile-vod-scrollzone">
          <div style="padding: 12px; display: flex; flex-direction: column; gap: 12px;">
            ${VODS.map(vod => `
              <div class="mobile-vod-card glass-card" data-vod-id="${vod.id}">
                <div class="vod-banner" style="background: ${vod.bg || '#1e293b'}; height: 80px; display: flex; align-items: center; justify-content: center; position: relative;">
                  <span style="font-size: 24px;">📼</span>
                  ${vod.premium ? '<span class="premium-tag">PREMIUM</span>' : ''}
                </div>
                <div class="vod-info" style="padding: 10px;">
                  <h4 style="font-size: 13px; font-weight: 700; color: #fff; margin-bottom: 2px;">${vod.title}</h4>
                  <span style="font-size: 10px; color: rgba(255,255,255,0.6);">${vod.category} | ${vod.duration}</span>
                  <p style="font-size: 10px; color: rgba(255,255,255,0.5); margin-top: 6px; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;">${vod.description}</p>
                </div>
              </div>
            `).join("")}
          </div>
        </div>
      `;
    } else {
      // Shorts Tab inside phone
      return `
        <div class="mobile-shorts-fullscreen">
          <canvas id="mobile-shorts-canvas" class="fullscreen-canvas-shorts" width="360" height="640" style="position: absolute; top:0; left:0; width:100%; height:100%;"></canvas>

          <div class="shorts-ui-overlay">
            <div class="shorts-left-info">
              <h4>@gntv_africa</h4>
              <p>Special documentary dispatch live from the streets of Eastleigh. #Somali #Nairobi</p>
              <div class="sound-tag">🎵 GNTV DIGITAL, ALL EVERYWHERE Original Sound</div>
            </div>

            <div class="shorts-right-actions">
              <button class="short-act-btn"><span>❤️</span><label>12.4K</label></button>
              <button class="short-act-btn"><span>💬</span><label>890</label></button>
              <button class="short-act-btn"><span>⭐</span><label>4.5K</label></button>
              <button class="short-act-btn"><span>🔗</span><label>Share</label></button>
            </div>
          </div>
        </div>
      `;
    }
  };

  const renderTVAppBody = (city) => {
    if (tvActiveTab === "map") {
      return `
        <div class="tv-split-layout">
          <!-- Left side: TV Interactive Map -->
          <div class="tv-map-pane">
            <h3 class="tv-content-title">🗺️ GNTV DIGITAL, ALL EVERYWHERE Africa Live Map</h3>
            <span class="tv-content-subtitle">Interact using the side-panel remote D-pad to change coverage cities.</span>

            <div class="tv-svg-map-wrapper">
              <svg viewBox="0 0 100 100" class="africa-svg-map">
                <path d="M 20,10 L 40,20 L 50,40 L 45,50 L 60,65 L 75,60 L 85,75 L 70,90 L 50,85 L 35,70 L 25,45 Z" fill="rgba(255,255,255,0.02)" stroke="rgba(255,255,255,0.08)" stroke-width="0.75" />

                <line x1="25" y1="20" x2="74" y2="72" stroke="rgba(255,42,75,0.1)" stroke-dasharray="1,1" stroke-width="0.5" />
                <line x1="25" y1="20" x2="70" y2="55" stroke="rgba(255,42,75,0.1)" stroke-dasharray="1,1" stroke-width="0.5" />

                ${Object.entries(CITY_DATA).map(([key, item], idx) => {
                  const isSelected = selectedCityKey === key;
                  const isFocused = tvFocusedCityIndex === idx;
                  return `
                    <circle cx="${item.coord.x}" cy="${item.coord.y}" r="${isSelected ? '2.5' : '1.8'}"
                      class="map-svg-dot ${isSelected ? 'selected' : ''} ${isFocused ? 'tv-focused-node' : ''}"
                      data-city-key="${key}"
                      style="fill: ${isFocused ? 'var(--brand-secondary)' : (isSelected ? 'var(--brand-primary)' : 'rgba(255,255,255,0.4)')}; transition: all 0.3s;" />

                    <text x="${item.coord.x + 3}" y="${item.coord.y + 1}" class="map-svg-label ${isSelected ? 'selected' : ''}" style="font-size: 3px; font-weight: bold; fill: #ffffff;">
                      ${item.name}
                    </text>
                  `;
                }).join("")}
              </svg>
            </div>
          </div>

          <!-- Right side: TV Selected City Dashboard -->
          <div class="tv-details-pane scrollable-tv-pane">
            <div class="tv-city-header">
              <h2>${city.name}</h2>
              <span class="tv-country-badge" style="background: ${city.streamColor};">${city.country}</span>
            </div>

            <!-- TV Livestream view -->
            <div class="tv-video-container">
              <canvas id="tv-live-canvas" width="480" height="270" class="simulated-canvas-player"></canvas>
              <div class="tv-live-badge">● LIVE TRANSMISSION</div>
              <div class="tv-overlay-watermark">${city.streamName.toUpperCase()}</div>
            </div>

            <div class="tv-city-grid-details" style="margin-top: 15px; display: grid; grid-template-columns: 1.2fr 0.8fr; gap: 15px;">
              <!-- News & Events -->
              <div>
                <h4 style="font-size: 13px; color: var(--brand-primary); margin-bottom: 8px;">📰 Local News Headlines</h4>
                <ul style="font-size: 11px; color: rgba(255,255,255,0.7); display: flex; flex-direction: column; gap: 6px; padding-left: 14px;">
                  ${city.news.map(s => `<li>${s}</li>`).join("")}
                </ul>

                <h4 style="font-size: 13px; color: var(--brand-primary); margin-top: 15px; margin-bottom: 8px;">📅 Regional Events</h4>
                <ul style="font-size: 11px; color: rgba(255,255,255,0.7); display: flex; flex-direction: column; gap: 6px; padding-left: 14px;">
                  ${city.events.map(e => `<li>${e}</li>`).join("")}
                </ul>
              </div>

              <!-- Reporter Card -->
              <div class="glass-card" style="padding: 12px; border: 1px solid rgba(255,255,255,0.06); border-radius: 8px; background: rgba(255,255,255,0.01);">
                <h4 style="font-size: 12px; color: var(--brand-primary); margin-bottom: 8px;">🎙️ Assigned Reporter</h4>
                ${city.reporters.map(rep => `
                  <div style="display: flex; gap: 10px; align-items: flex-start;">
                    <span style="font-size: 24px;">${rep.emoji}</span>
                    <div>
                      <h5 style="font-size: 12px; color: #fff; font-weight: 700; margin: 0;">${rep.name}</h5>
                      <span style="font-size: 9px; color: rgba(255,255,255,0.5); font-weight: 700; text-transform: uppercase;">${rep.role}</span>
                      <p style="font-size: 10px; color: rgba(255,255,255,0.6); margin-top: 6px; line-height: 1.4;">${rep.bio}</p>
                    </div>
                  </div>
                `).join("")}
              </div>
            </div>
          </div>
        </div>
      `;
    } else if (tvActiveTab === "vod") {
      return `
        <h3 class="tv-content-title">📼 TV VOD Library Shelf</h3>
        <span class="tv-content-subtitle">Select card using D-Pad and hit OK to simulate playback.</span>

        <div class="tv-vod-grid">
          ${VODS.map((vod, idx) => {
            const isFocused = tvFocusedVodIndex === idx;
            return `
              <div class="tv-vod-card glass-card ${isFocused ? 'tv-focused-card' : ''}" data-vod-id="${vod.id}">
                <div class="tv-vod-poster" style="background: ${vod.bg || '#1e293b'}; height: 130px; display: flex; align-items: center; justify-content: center; position: relative;">
                  <span style="font-size: 48px;">📼</span>
                  ${vod.premium ? '<span class="premium-tag" style="position: absolute; top:10px; right:10px;">PREMIUM</span>' : ''}
                </div>
                <div class="tv-vod-meta" style="padding: 12px;">
                  <h4 style="font-size: 13px; color: #fff; font-weight: 800; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">${vod.title}</h4>
                  <span style="font-size: 10px; color: rgba(255,255,255,0.5); font-weight: 700;">${vod.category.toUpperCase()}</span>
                </div>
              </div>
            `;
          }).join("")}
        </div>
      `;
    } else {
      // Settings tab
      return `
        <h3 class="tv-content-title">⚙️ TV Display Settings</h3>
        <span class="tv-content-subtitle">Simulated receiver configuration settings.</span>

        <div class="glass-card" style="padding: 24px; border: 1px solid rgba(255,255,255,0.06); border-radius: 12px; background: rgba(255,255,255,0.01); max-width: 500px; display: flex; flex-direction: column; gap: 16px; margin-top: 15px;">
          <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid rgba(255,255,255,0.04); padding-bottom: 12px;">
            <span>Simulated Quality Standard</span>
            <span style="font-weight: 800; color: var(--brand-primary);">4K UHD 2160p</span>
          </div>
          <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid rgba(255,255,255,0.04); padding-bottom: 12px;">
            <span>Broadcasting Region Node</span>
            <span>Mogadishu Gateway Hub 01</span>
          </div>
          <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid rgba(255,255,255,0.04); padding-bottom: 12px;">
            <span>Audio Stream Output</span>
            <span>Dolby Atmos Digital Passthrough</span>
          </div>
          <div style="display: flex; justify-content: space-between; align-items: center;">
            <span>Satellite Downlink Frequency</span>
            <span style="font-family: var(--font-mono); color: var(--brand-secondary);">11.472 GHz H</span>
          </div>
        </div>
      `;
    }
  };

  const setupListeners = () => {
    // Device Select buttons
    const deviceButtons = container.querySelectorAll(".btn-device-select");
    deviceButtons.forEach(btn => {
      btn.addEventListener("click", () => {
        activeDevice = btn.getAttribute("data-device");
        render();
      });
    });

    // Mobile Navigation Tab buttons
    const mobTabButtons = container.querySelectorAll(".mobile-nav-btn");
    mobTabButtons.forEach(btn => {
      btn.addEventListener("click", () => {
        activeMobileTab = btn.getAttribute("data-mobtab");
        render();
      });
    });

    // Map city dot clicks inside SVG (for mobile and TV)
    const mapDots = container.querySelectorAll(".map-svg-dot");
    mapDots.forEach(dot => {
      dot.addEventListener("click", (e) => {
        const key = dot.getAttribute("data-city-key");
        selectedCityKey = key;
        // Also update the index so TV remote and dot selection stays aligned
        const idx = CITY_KEYS.indexOf(key);
        if (idx !== -1) {
          tvFocusedCityIndex = idx;
        }
        render();
      });
    });

    // TV Remote D-Pad and volume rocker listeners
    const remoteUp = container.querySelector("#btn-remote-up");
    const remoteDown = container.querySelector("#btn-remote-down");
    const remoteLeft = container.querySelector("#btn-remote-left");
    const remoteRight = container.querySelector("#btn-remote-right");
    const remoteOk = container.querySelector("#btn-remote-ok");
    const remoteBack = container.querySelector("#btn-remote-back");
    const remoteHome = container.querySelector("#btn-remote-home");
    const remotePower = container.querySelector("#btn-remote-power");
    const remoteVolUp = container.querySelector("#btn-remote-vol-up");
    const remoteVolDown = container.querySelector("#btn-remote-vol-down");

    if (remoteUp) {
      remoteUp.addEventListener("click", () => {
        if (tvActiveTab === "map") {
          // Navigating up on sidebar tabs or cities list
          tvActiveTab = "vod";
        } else if (tvActiveTab === "vod") {
          tvActiveTab = "map";
        } else if (tvActiveTab === "settings") {
          tvActiveTab = "vod";
        }
        render();
      });
    }

    if (remoteDown) {
      remoteDown.addEventListener("click", () => {
        if (tvActiveTab === "map") {
          tvActiveTab = "vod";
        } else if (tvActiveTab === "vod") {
          tvActiveTab = "settings";
        } else if (tvActiveTab === "settings") {
          tvActiveTab = "map";
        }
        render();
      });
    }

    if (remoteLeft) {
      remoteLeft.addEventListener("click", () => {
        if (tvActiveTab === "map") {
          // cycle city left
          tvFocusedCityIndex = (tvFocusedCityIndex - 1 + CITY_KEYS.length) % CITY_KEYS.length;
          selectedCityKey = CITY_KEYS[tvFocusedCityIndex];
        } else if (tvActiveTab === "vod") {
          // cycle VOD items
          tvFocusedVodIndex = (tvFocusedVodIndex - 1 + VODS.length) % VODS.length;
        }
        render();
      });
    }

    if (remoteRight) {
      remoteRight.addEventListener("click", () => {
        if (tvActiveTab === "map") {
          // cycle city right
          tvFocusedCityIndex = (tvFocusedCityIndex + 1) % CITY_KEYS.length;
          selectedCityKey = CITY_KEYS[tvFocusedCityIndex];
        } else if (tvActiveTab === "vod") {
          tvFocusedVodIndex = (tvFocusedVodIndex + 1) % VODS.length;
        }
        render();
      });
    }

    if (remoteOk) {
      remoteOk.addEventListener("click", () => {
        if (tvActiveTab === "map") {
          alert(`Simulated TV OK: Tune live feed for ${CITY_DATA[selectedCityKey].name}!`);
        } else if (tvActiveTab === "vod") {
          const focusedVod = VODS[tvFocusedVodIndex];
          alert(`Simulated TV OK: Play VOD: "${focusedVod.title}"!`);
        }
      });
    }

    if (remoteBack) {
      remoteBack.addEventListener("click", () => {
        tvActiveTab = "map";
        render();
      });
    }

    if (remoteHome) {
      remoteHome.addEventListener("click", () => {
        tvActiveTab = "map";
        selectedCityKey = "muqdisho";
        tvFocusedCityIndex = 0;
        render();
      });
    }

    if (remotePower) {
      remotePower.addEventListener("click", () => {
        alert("Simulator Rebooting...");
        render();
      });
    }

    if (remoteVolUp) {
      remoteVolUp.addEventListener("click", () => {
        const curVol = store.getState("prefVolume") || 80;
        const nextVol = Math.min(100, curVol + 5);
        store.setState("prefVolume", nextVol);
        alert(`Volume: ${nextVol}%`);
      });
    }

    if (remoteVolDown) {
      remoteVolDown.addEventListener("click", () => {
        const curVol = store.getState("prefVolume") || 80;
        const nextVol = Math.max(0, curVol - 5);
        store.setState("prefVolume", nextVol);
        alert(`Volume: ${nextVol}%`);
      });
    }
  };

  const initCanvasLoop = () => {
    // Determine which canvas to animate
    const mobileCanvas = container.querySelector("#mobile-live-canvas");
    const tvCanvas = container.querySelector("#tv-live-canvas");
    const shortsCanvas = container.querySelector("#mobile-shorts-canvas");

    const canvas = mobileCanvas || tvCanvas;
    const currentCity = CITY_DATA[selectedCityKey];

    if (canvas && currentCity) {
      const ctx = canvas.getContext("2d");
      const streamColor = currentCity.streamColor;
      const cityName = currentCity.name;

      const drawFrame = () => {
        simulatedSignalOffset += 0.05;
        const w = canvas.width;
        const h = canvas.height;

        ctx.fillStyle = "#0c0c12";
        ctx.fillRect(0, 0, w, h);

        // Draw animated waves matching streamColor theme
        ctx.strokeStyle = streamColor;
        ctx.lineWidth = 2;

        ctx.beginPath();
        for (let x = 0; x < w; x++) {
          const y = h / 2 + Math.sin(x * 0.03 + simulatedSignalOffset) * 25 * Math.cos(x * 0.005);
          if (x === 0) ctx.moveTo(x, y);
          else ctx.lineTo(x, y);
        }
        ctx.stroke();

        ctx.strokeStyle = "rgba(255,255,255,0.06)";
        ctx.lineWidth = 1;
        ctx.beginPath();
        for (let x = 0; x < w; x++) {
          const y = h / 2 + Math.cos(x * 0.04 + simulatedSignalOffset * 1.5) * 15;
          if (x === 0) ctx.moveTo(x, y);
          else ctx.lineTo(x, y);
        }
        ctx.stroke();

        // Draw HUD overlay text
        ctx.fillStyle = "rgba(255, 255, 255, 0.4)";
        ctx.font = "8px monospace";
        ctx.fillText("REC DOWNLINK: SECURED", 10, 20);
        ctx.fillText(`RESOL: 1080p@60FPS | ACCENT: ${streamColor}`, 10, 32);

        // Watermark name
        ctx.fillStyle = "#ffffff";
        ctx.font = "bold 11px sans-serif";
        ctx.fillText(`GNTV DIGITAL, ALL EVERYWHERE ${cityName.toUpperCase()}`, 10, h - 15);

        // Blink live dot
        const blink = Math.floor(Date.now() / 500) % 2 === 0;
        ctx.fillStyle = blink ? "red" : "gray";
        ctx.beginPath();
        ctx.arc(w - 20, 18, 4, 0, Math.PI * 2);
        ctx.fill();

        ctx.fillStyle = "#ffffff";
        ctx.font = "bold 8px sans-serif";
        ctx.fillText("LIVE", w - 42, 21);

        canvasAnimFrame = requestAnimationFrame(drawFrame);
      };

      drawFrame();
    } else if (shortsCanvas) {
      // Shorts full viewport draw loop
      const ctx = shortsCanvas.getContext("2d");

      const drawShortsFrame = () => {
        simulatedSignalOffset += 0.03;
        const w = shortsCanvas.width;
        const h = shortsCanvas.height;

        // Draw a slow vertical color gradient to represent vertical shorts video content
        const grad = ctx.createLinearGradient(0, 0, 0, h);
        grad.addColorStop(0, "hsl(240, 10%, 4%)");
        grad.addColorStop(0.5, "hsl(348, 45%, 15%)");
        grad.addColorStop(1, "hsl(205, 50%, 10%)");

        ctx.fillStyle = grad;
        ctx.fillRect(0, 0, w, h);

        // draw color dots
        ctx.fillStyle = "rgba(255, 255, 255, 0.1)";
        for (let i = 0; i < 5; i++) {
          const dotY = (h / 4) * i + Math.sin(simulatedSignalOffset + i) * 30;
          ctx.beginPath();
          ctx.arc(w / 2 + Math.cos(simulatedSignalOffset * 0.5 + i) * 80, dotY, 40, 0, Math.PI * 2);
          ctx.fill();
        }

        // Draw simulated anchor outline or text overlays
        ctx.fillStyle = "rgba(255,255,255,0.3)";
        ctx.font = "10px sans-serif";
        ctx.fillText("SIMULATED SHORTS STREAM", 20, 40);
        ctx.fillText("SWIPE UP/DOWN TO NEXT CLIP", 20, 55);

        canvasAnimFrame = requestAnimationFrame(drawShortsFrame);
      };
      drawShortsFrame();
    }
  };

  // Initial draw
  render();

  // Return destructor
  return () => {
    if (canvasAnimFrame) {
      cancelAnimationFrame(canvasAnimFrame);
    }
  };
}
