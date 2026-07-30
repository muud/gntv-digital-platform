import { store } from "../../../shared/src/state.js";

export function initQREngine(container) {
  // Local state for the simulator
  const simState = {
    activeSubTab: "architecture", // architecture or simulator
    activeFlow: "registration", // registration, payment, pairing, login
    countdownTime: 90, // seconds for registration/login tokens
    countdownTimer: null,
    selectedPaymentPlan: "gold", // standard ($9.99) or gold ($19.99)
    phoneStep: "start", // start, scanning, input, pin, processing, success
    pairingCode: "GN-948X",
    userInputs: {
      name: "Cumar Cabdi",
      email: "cumar@gntv.com",
      mpesaPin: "",
      cardNumber: "",
      cardExpiry: "",
      cardCvv: "",
      cardholderName: "CUMAR CABDI"
    },
    telemetryLogs: [],
    isTVLoggedIn: false,
    loggedInUser: null,
    tvState: "idle", // idle, counting, scanning, processing, success
    isUpgraded: false,
    activeNode: "firebase-db" // default highlighted node in arch diagram
  };

  const addTelemetry = (tag, msg) => {
    const time = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    simState.telemetryLogs.push({ time, tag, msg });
    if (simState.telemetryLogs.length > 30) {
      simState.telemetryLogs.shift();
    }

    const logBody = container.querySelector("#telemetry-logs-body");
    if (logBody) {
      // Clear placeholder if it's the first log
      if (simState.telemetryLogs.length === 1 || logBody.innerHTML.includes("handshake initialization")) {
        logBody.innerHTML = "";
      }

      const line = document.createElement("div");
      line.className = "telemetry-line";
      let tagClass = "";
      const lowerTag = tag.toLowerCase();
      if (lowerTag.includes("stripe") || lowerTag.includes("card")) tagClass = "stripe";
      else if (lowerTag.includes("m-pesa") || lowerTag.includes("safaricom") || lowerTag.includes("stk")) tagClass = "mpesa";
      else if (lowerTag.includes("firebase") || lowerTag.includes("db") || lowerTag.includes("auth")) tagClass = "firebase";

      line.innerHTML = `
        <span class="telemetry-time">[${time}]</span>
        <span class="telemetry-event-tag ${tagClass}">${tag}</span>
        <span class="telemetry-msg">${msg}</span>
      `;
      logBody.appendChild(line);
      logBody.scrollTop = logBody.scrollHeight;
    }
  };

  // Static Details for the interactive architecture nodes
  const nodeDetails = {
    "tv-client": {
      title: "Smart TV / IPTV Client",
      somaliTitle: "Client-ka TV-ga Casriga Ah",
      desc: "The viewer's large-screen interface. It runs on a low-overhead web wrapper (Vanilla JS / Tizen / WebOS). Instead of typing card numbers or passwords, it polls Firebase Realtime Database for connection confirmations.",
      somaliDesc: "Interface-ka shaashadda weyn ee daawadaha. Waxay ku shaqaysaa nidaamyada Tizen, WebOS, ama Android TV. Halkii laga qori lahaa kaarar ama erey sir ah, waxay si joogto ah u dhagaysataa xogta Firebase DB si ay u xaqiijiso xidhiidhka.",
      tech: "HTML5 Canvas, SSE Polling, WebSockets",
      latency: "< 150ms",
      security: "SSL / TLS 1.3 Encryption"
    },
    "mobile-client": {
      title: "Viewer's Mobile Device",
      somaliTitle: "Telefoonka Gacanta ee Daawadaha",
      desc: "The interactive remote input. Standard camera QR-scans deliver signed JWT activation payloads. Captures payments (Stripe/M-Pesa) and handles registration inputs without requiring standard remote typing.",
      somaliDesc: "Qalabka fog ee wax lagu qoro. Sawiridda QR code ee kamaradda waxay dirtaa xogta JWT ee saxeexan. Waxay maamushaa lacag-bixinta (Stripe/M-Pesa) iyo diiwaangelinta iyadoo ka baajinaysa isticmaalaha qorista TV-ga.",
      tech: "iOS Safari / Android Chrome, Camera API, JWT",
      latency: "< 200ms",
      security: "Signed JWT Tokens, AES-256"
    },
    "firebase-functions": {
      title: "Firebase Cloud Functions (Token Engine)",
      somaliTitle: "Mashiinka Tokens-ka (Cloud Functions)",
      desc: "The brains behind the QR engine. It generates cryptographically signed, short-lived tokens (90s expiration) and validates JWT signatures sent from the mobile client upon scan events.",
      somaliDesc: "Maskaxda ka dambaysa mashiinka QR-ka. Waxay soo saartaa tokens si amni ah loo saxeexay oo dhacaya 90 ilbiriqsi gudahood, waxayna hubisaa saxnaanta saxeexa JWT ee ka yimaada telefoonka gacanta.",
      tech: "Node.js (Serverless), Google Cloud KMS",
      latency: "80ms - 120ms",
      security: "SHA-256 HMAC Signatures, Token TTL (90s)"
    },
    "firebase-db": {
      title: "Firebase Realtime Database (Sync Hub)",
      somaliTitle: "Xarunta Isku-xidhka (Realtime DB)",
      desc: "The low-latency communication layer. The TV establishes a secure listener on `/sessions/{token_id}`. The moment the mobile phone successfully processes an action, it writes to this node, pushing updates instantly.",
      somaliDesc: "Muuqaalka isgaadhsiinta ee xawliga sare leh. TV-ga wuxuu dhagaystaa galka `/sessions/{token_id}`. Marka telefoonku dhammeeyo hawsha, wuxuu u qoraa halkan, taas oo TV-ga u cusboonaysiisa isla ilbiriqsigaas.",
      tech: "Firebase Realtime DB Protocol, WebSockets",
      latency: "< 50ms",
      security: "Firebase Security Rules, Fine-grained IAM"
    },
    "stripe-api": {
      title: "Stripe API & Billing Gateway",
      somaliTitle: "Albaabka Lacagaha ee Stripe",
      desc: "Processes international card payments and Apple Pay. Emits secure webhooks back to GNTV DIGITAL, ALL EVERYWHERE Cloud Functions immediately upon successful card auth, unlocking dynamic premium tiers.",
      somaliDesc: "Wuxuu maamulaa kaararka caalamiga ah iyo Apple Pay. Wuxuu u soo diraa webhooks ammaan ah GNTV DIGITAL, ALL EVERYWHERE Cloud Functions marka lacagta la bixiyo, si loo furo kanaalada premium-ka.",
      tech: "Stripe Webhooks, Stripe Elements, Apple Pay API",
      latency: "1.2s - 2.5s (Checkout)",
      security: "PCI-DSS Level 1 Compliance, Webhook HMAC"
    },
    "mpesa-api": {
      title: "M-Pesa API & Mobile Money",
      somaliTitle: "Lacagta Gacanta ee M-Pesa",
      desc: "Handles East African mobile money wallets. Uses STK Push (Lipa Na M-Pesa) to trigger a direct PIN prompt on the subscriber's phone. Instantly communicates transaction state via secure callbacks.",
      somaliDesc: "Waxay maamushaa lacagta gacanta ee Bariga Afrika. Waxay isticmaashaa STK Push si ay toos ugu soo tuurto daaqada sirta ah (PIN) ee telefoonka. Xogta lacag-bixinta waxaa lala wadaagaa TV-ga si degdeg ah.",
      tech: "Safaricom Daraja API, STK Push, USSD Callback",
      latency: "1.5s - 3s (PIN processing)",
      security: "OAuth 2.0, API Key Credentials"
    },
    "alibaba-cdn": {
      title: "Alibaba CDN & Media Pipeline",
      somaliTitle: "Qaybiyaha Muuqaalka ee Alibaba CDN",
      desc: "The primary high-performance content delivery network. Delivers the GNTV DIGITAL, ALL EVERYWHERE live stream with multi-camera relays. The stream is token-locked, authorizing playback only when Firebase confirms a valid paired session.",
      somaliDesc: "Shabakada qaybinta muuqaalka ee xawliga sare leh. Waxay soo gudbisaa tooska GNTV DIGITAL, ALL EVERYWHERE iyo kamaradaha kala duwan. Stream-ku wuxuu ku xidhanyahay token gaar ah oo la ogolaado kaliya marka session-ku saxmo.",
      tech: "RTMP / HLS, Dynamic Key Authorization",
      latency: "0.8s - 2.0s (Edge Latency)",
      security: "Dynamic URL Signing, Token Authentication"
    },
    "aws-failover": {
      title: "AWS DynamoDB & Failover DB",
      somaliTitle: "AWS DB oo ah Badbaadada labaad",
      desc: "The geo-redundant secondary cluster. In case of primary Firebase Cloud service disruption, the QR system gracefully fails over to AWS API Gateway, routing database updates through regional DynamoDB instances.",
      somaliDesc: "Kaydka labaad ee u diyaarsan haddii Firebase uu cilad ku yimaado. QR system-ku wuxuu si otomaatig ah u adeegsanayaa AWS API Gateway iyo DynamoDB si uu u hubiyo in daawashadu aysan kala go'in.",
      tech: "DynamoDB Global Tables, AWS Route 53 Failover",
      latency: "< 80ms (Replication)",
      security: "AWS IAM Roles, KMS encryption-at-rest"
    },
    "google-stt": {
      title: "Google Speech-to-Text & Subtitles",
      somaliTitle: "Mashiinka Tarjumaada Google AI",
      desc: "Background real-time audio analysis engine. Translates live Somali broadcasting commentary into high-quality English and Arabic subtitles dynamically, delivered on-screen simultaneously with the broadcast feed.",
      somaliDesc: "Mashiinka falanqeeya codka tooska ah ee gadaal ka shaqeeya. Wuxuu u beddelaa hadalka tooska ah ee Soomaaliga subtitles Ingiriisi iyo Carabi ah oo si toos ah uga muuqanaya shaashadda TV-ga.",
      tech: "Google Speech-to-Text API, Cloud Translation",
      latency: "200ms - 400ms (Stream Overlay)",
      security: "API Key Restrictions, Secure gRPC downlinks"
    }
  };

  // Renders the baseline skeleton
  const renderLayout = () => {
    container.innerHTML = `
      <style>
        .qr-dashboard-wrapper {
          padding: 94px 32px 48px 32px;
          max-width: 1400px;
          margin: 0 auto;
          font-family: var(--font-sans);
          display: flex;
          flex-direction: column;
          gap: 24px;
        }

        /* Nav and Tabs */
        .qr-nav-container {
          display: flex;
          justify-content: space-between;
          align-items: center;
          border-bottom: 1px solid rgba(255, 255, 255, 0.06);
          padding-bottom: 16px;
        }

        .qr-tab-buttons {
          display: flex;
          gap: 12px;
        }

        .qr-tab-btn {
          background: rgba(255, 255, 255, 0.03);
          border: 1px solid rgba(255, 255, 255, 0.06);
          padding: 10px 20px;
          border-radius: 30px;
          color: rgba(255, 255, 255, 0.7);
          font-weight: 600;
          font-size: 14px;
          cursor: pointer;
          transition: all 0.3s cubic-bezier(0.16, 1, 0.3, 1);
        }

        .qr-tab-btn:hover {
          color: #ffffff;
          background: rgba(255, 255, 255, 0.08);
          border-color: rgba(255, 255, 255, 0.15);
        }

        .qr-tab-btn.active {
          color: var(--brand-primary);
          background: rgba(255, 42, 75, 0.12);
          border-color: var(--brand-primary);
          box-shadow: 0 0 15px rgba(255, 42, 75, 0.15);
        }

        /* Architecture Panel */
        .arch-panel-grid {
          display: grid;
          grid-template-columns: 1.6fr 1fr;
          gap: 24px;
          align-items: start;
        }

        @media (max-width: 1024px) {
          .arch-panel-grid {
            grid-template-columns: 1fr;
          }
        }

        .svg-container-card {
          background: rgba(10, 10, 15, 0.5);
          border: 1px solid rgba(255, 255, 255, 0.05);
          border-radius: 16px;
          padding: 24px;
          display: flex;
          align-items: center;
          justify-content: center;
          backdrop-filter: blur(20px);
          overflow: hidden;
          position: relative;
        }

        /* SVG Glow Styles */
        .glow-node {
          cursor: pointer;
          transition: filter 0.3s, transform 0.3s;
        }
        .glow-node:hover {
          transform: scale(1.03);
          filter: drop-shadow(0 0 8px var(--brand-primary-glow));
        }
        .glow-node.active-node {
          filter: drop-shadow(0 0 12px var(--brand-primary-glow)) drop-shadow(0 0 4px var(--brand-secondary));
        }

        .pulse-path {
          stroke-dasharray: 10, 15;
          animation: path-flow 25s linear infinite;
        }

        @keyframes path-flow {
          to {
            stroke-dashoffset: -1000;
          }
        }

        .node-inspect-card {
          display: flex;
          flex-direction: column;
          gap: 16px;
        }

        .tech-spec-badge {
          display: inline-flex;
          align-items: center;
          padding: 4px 10px;
          border-radius: 4px;
          background: rgba(255, 255, 255, 0.05);
          border: 1px solid rgba(255, 255, 255, 0.08);
          font-family: var(--font-mono);
          font-size: 11px;
          color: rgba(255, 255, 255, 0.85);
        }

        /* Simulator Grid */
        .sim-panel-grid {
          display: grid;
          grid-template-columns: 1fr 1fr;
          gap: 32px;
          max-width: 1100px;
          margin: 0 auto;
          width: 100%;
          align-items: start;
        }

        @media (max-width: 850px) {
          .sim-panel-grid {
            grid-template-columns: 1fr;
          }
        }

        /* Flow selectors */
        .flow-selector-bar {
          display: grid;
          grid-template-columns: repeat(4, 1fr);
          gap: 8px;
          background: rgba(255, 255, 255, 0.02);
          border: 1px solid rgba(255, 255, 255, 0.04);
          padding: 6px;
          border-radius: 12px;
        }

        .flow-btn {
          background: transparent;
          border: none;
          padding: 10px;
          border-radius: 8px;
          color: rgba(255, 255, 255, 0.6);
          font-size: 12px;
          font-weight: 700;
          cursor: pointer;
          transition: all 0.25s ease;
        }

        .flow-btn:hover {
          color: #ffffff;
          background: rgba(255, 255, 255, 0.04);
        }

        .flow-btn.active {
          color: #ffffff;
          background: var(--brand-primary);
          box-shadow: 0 4px 12px var(--brand-primary-glow);
        }

        /* Smart TV Mockup */
        .tv-bezel-frame {
          background: #0f0f15;
          border: 12px solid #23232f;
          border-bottom-width: 18px;
          border-radius: 20px;
          box-shadow: 0 25px 60px rgba(0,0,0,0.8), 0 0 100px rgba(255, 42, 75, 0.05);
          position: relative;
          aspect-ratio: 16/9;
          width: 100%;
          overflow: hidden;
          display: flex;
          flex-direction: column;
        }

        .tv-screen-content {
          background: radial-gradient(circle at center, #1b131a 0%, #07070a 100%);
          width: 100%;
          height: 100%;
          position: relative;
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          padding: 24px;
          box-sizing: border-box;
        }

        /* TV Active state overlay */
        .tv-success-overlay {
          position: absolute;
          inset: 0;
          background: rgba(8, 8, 12, 0.95);
          backdrop-filter: blur(10px);
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          gap: 16px;
          z-index: 10;
          opacity: 0;
          pointer-events: none;
          transition: opacity 0.4s ease;
        }

        .tv-success-overlay.active {
          opacity: 1;
          pointer-events: auto;
        }

        /* Mobile Phone Mockup */
        .phone-case {
          background: #111116;
          border: 10px solid #1a1a24;
          border-radius: 40px;
          box-shadow: 0 20px 50px rgba(0,0,0,0.6);
          width: 320px;
          height: 600px;
          margin: 0 auto;
          overflow: hidden;
          position: relative;
          display: flex;
          flex-direction: column;
          border-top-width: 14px;
          border-bottom-width: 14px;
        }

        /* Speaker Notch */
        .phone-notch {
          position: absolute;
          top: 0;
          left: 50%;
          transform: translateX(-50%);
          width: 120px;
          height: 20px;
          background: #1a1a24;
          border-bottom-left-radius: 12px;
          border-bottom-right-radius: 12px;
          z-index: 20;
        }

        .phone-screen {
          flex-grow: 1;
          background: #08080d;
          position: relative;
          padding: 30px 16px 16px 16px;
          display: flex;
          flex-direction: column;
          justify-content: space-between;
          overflow-y: auto;
        }

        /* Phone Keyboard Key styles */
        .phone-keyboard-grid {
          display: grid;
          grid-template-columns: repeat(3, 1fr);
          gap: 8px;
          margin-top: 12px;
        }

        .key-btn {
          background: rgba(255,255,255,0.06);
          border: 1px solid rgba(255,255,255,0.08);
          border-radius: 8px;
          padding: 12px;
          font-weight: 700;
          font-size: 16px;
          color: #ffffff;
          cursor: pointer;
          transition: background 0.15s;
        }

        .key-btn:hover {
          background: rgba(255,255,255,0.12);
        }

        .key-btn:active {
          background: var(--brand-primary);
        }

        /* Progress bars and pulsing markers */
        .countdown-progress-bar {
          width: 100%;
          height: 4px;
          background: rgba(255,255,255,0.1);
          border-radius: 2px;
          overflow: hidden;
          margin-top: 12px;
        }

        .countdown-fill {
          height: 100%;
          background: var(--brand-primary);
          transition: width 1s linear;
        }

        .pulsing-scanner-glow {
          position: absolute;
          top: 0;
          left: 0;
          width: 100%;
          height: 3px;
          background: linear-gradient(to right, transparent, var(--brand-secondary), transparent);
          box-shadow: 0 0 12px var(--brand-secondary);
          animation: scan-vertical 2s infinite ease-in-out;
        }

        @keyframes scan-vertical {
          0% { top: 10%; }
          50% { top: 90%; }
          100% { top: 10%; }
        }
      </style>

      <div class="qr-dashboard-wrapper">

        <!-- Tab Navigation and Header -->
        <div class="qr-nav-container">
          <div>
            <h2 style="font-size: 26px; font-weight: 850; letter-spacing: -1px; display: flex; align-items: center; gap: 10px;">
              📡 QR Engine & Cloud Architecture
            </h2>
            <p style="font-size: 13px; color: rgba(255,255,255,0.5); margin-top: 4px;">
              Experience Apple TV-style cross-screen activation powered by highly redundant distributed networks.
            </p>
          </div>

          <div class="qr-tab-buttons">
            <button class="qr-tab-btn active" id="tab-btn-architecture" data-tab="architecture">Cloud Architecture Diagram</button>
            <button class="qr-tab-btn" id="tab-btn-simulator" data-tab="simulator">Interactive Flow Stepper</button>
          </div>
        </div>

        <!-- 1. Cloud Architecture View -->
        <div class="qr-content-tab-pane" id="pane-architecture">
          <div class="arch-panel-grid">

            <!-- SVG Interactive Diagram -->
            <div class="svg-container-card glass-card">
              <svg viewBox="0 0 760 500" width="100%" height="100%" id="architecture-svg" style="display: block;">
                <!-- Define Neon Gradients -->
                <defs>
                  <linearGradient id="primary-grad" x1="0%" y1="0%" x2="100%" y2="100%">
                    <stop offset="0%" stop-color="hsl(348, 100%, 58%)" />
                    <stop offset="100%" stop-color="#b91c1c" />
                  </linearGradient>
                  <linearGradient id="secondary-grad" x1="0%" y1="0%" x2="100%" y2="100%">
                    <stop offset="0%" stop-color="hsl(190, 100%, 50%)" />
                    <stop offset="100%" stop-color="#0891b2" />
                  </linearGradient>
                  <linearGradient id="gold-grad" x1="0%" y1="0%" x2="100%" y2="100%">
                    <stop offset="0%" stop-color="hsl(40, 95%, 55%)" />
                    <stop offset="100%" stop-color="#d97706" />
                  </linearGradient>
                  <linearGradient id="purple-grad" x1="0%" y1="0%" x2="100%" y2="100%">
                    <stop offset="0%" stop-color="#c084fc" />
                    <stop offset="100%" stop-color="#7c3aed" />
                  </linearGradient>

                  <!-- Drop Shadows -->
                  <filter id="glow" x="-20%" y="-20%" width="140%" height="140%">
                    <feGaussianBlur stdDeviation="6" result="blur" />
                    <feMerge>
                      <feMergeNode in="blur" />
                      <feMergeNode in="SourceGraphic" />
                    </feMerge>
                  </filter>
                </defs>

                <!-- Grid Background -->
                <g stroke="rgba(255,255,255,0.03)" stroke-width="1">
                  <path d="M 0,50 L 760,50 M 0,100 L 760,100 M 0,150 L 760,150 M 0,200 L 760,200 M 0,250 L 760,250 M 0,300 L 760,300 M 0,350 L 760,350 M 0,400 L 760,400 M 0,450 L 760,450" />
                  <path d="M 50,0 L 50,500 M 100,0 L 100,500 M 150,0 L 150,500 M 200,0 L 200,500 M 250,0 L 250,500 M 300,0 L 300,500 M 350,0 L 350,500 M 400,0 L 400,500 M 450,0 L 450,500 M 500,0 L 500,500 M 550,0 L 550,500 M 600,0 L 600,500 M 650,0 L 650,500 M 700,0 L 700,500" />
                </g>

                <!-- Connection Lines (Data Pathways) -->
                <!-- TV to Firebase Realtime DB (Bi-directional Polling) -->
                <path d="M 160,180 Q 250,180 340,230" fill="none" stroke="rgba(6, 182, 212, 0.4)" stroke-width="2" stroke-dasharray="5 5" />
                <path d="M 160,180 Q 250,180 340,230" fill="none" stroke="url(#secondary-grad)" stroke-width="2.5" class="pulse-path" />

                <!-- Mobile to Firebase Cloud Functions (Signed Tokens Scan Post) -->
                <path d="M 160,320 Q 250,320 340,270" fill="none" stroke="rgba(255, 42, 75, 0.4)" stroke-width="2" stroke-dasharray="5 5" />
                <path d="M 160,320 Q 250,320 340,270" fill="none" stroke="url(#primary-grad)" stroke-width="2.5" class="pulse-path" />

                <!-- Firebase Functions to Firebase DB (Write state) -->
                <line x1="380" y1="240" x2="380" y2="260" stroke="rgba(255, 255, 255, 0.3)" stroke-width="2" stroke-dasharray="4 4" />

                <!-- Firebase Functions to Stripe / M-Pesa -->
                <path d="M 420,250 Q 510,210 600,180" fill="none" stroke="rgba(255,255,255,0.2)" stroke-width="2" stroke-dasharray="6 6" />
                <path d="M 420,250 Q 510,210 600,180" fill="none" stroke="url(#primary-grad)" stroke-width="2" class="pulse-path" style="animation-duration: 12s;" />

                <path d="M 420,250 Q 510,270 600,320" fill="none" stroke="rgba(255,255,255,0.2)" stroke-width="2" stroke-dasharray="6 6" />
                <path d="M 420,250 Q 510,270 600,320" fill="none" stroke="url(#gold-grad)" stroke-width="2" class="pulse-path" style="animation-duration: 12s;" />

                <!-- DB/Functions back downlinks to dynamic media CDN, subtitles & failover -->
                <path d="M 380,290 L 220,410" fill="none" stroke="rgba(255,255,255,0.15)" stroke-width="1.5" stroke-dasharray="5 5" />
                <path d="M 380,290 L 380,410" fill="none" stroke="rgba(255,255,255,0.15)" stroke-width="1.5" stroke-dasharray="5 5" />
                <path d="M 380,290 L 540,410" fill="none" stroke="rgba(255,255,255,0.15)" stroke-width="1.5" stroke-dasharray="5 5" />

                <!-- Interactive Node Circles & Label Boxes -->
                <!-- 1. TV Screen Node -->
                <g id="node-tv-client" class="glow-node active-node" transform="translate(110, 180)">
                  <circle r="36" fill="#181825" stroke="url(#secondary-grad)" stroke-width="3" filter="url(#glow)" />
                  <text y="-4" fill="#ffffff" font-size="20" text-anchor="middle" pointer-events="none">📺</text>
                  <text y="16" fill="#06b6d4" font-family="var(--font-mono)" font-size="9" font-weight="700" text-anchor="middle" pointer-events="none">Smart TV</text>
                </g>

                <!-- 2. Mobile Scanner Node -->
                <g id="node-mobile-client" class="glow-node" transform="translate(110, 320)">
                  <circle r="36" fill="#181825" stroke="url(#primary-grad)" stroke-width="3" filter="url(#glow)" />
                  <text y="-4" fill="#ffffff" font-size="20" text-anchor="middle" pointer-events="none">📱</text>
                  <text y="16" fill="#ff2a4b" font-family="var(--font-mono)" font-size="9" font-weight="700" text-anchor="middle" pointer-events="none">Mobile Scan</text>
                </g>

                <!-- 3. Firebase Functions (Token Generator) -->
                <g id="node-firebase-functions" class="glow-node" transform="translate(380, 250)">
                  <rect x="-42" y="-42" width="84" height="84" rx="12" fill="#181825" stroke="url(#primary-grad)" stroke-width="3" filter="url(#glow)" />
                  <text y="-10" fill="#ffffff" font-size="22" text-anchor="middle" pointer-events="none">⚙️</text>
                  <text y="15" fill="#ffffff" font-size="10" font-weight="800" text-anchor="middle" pointer-events="none">Cloud Engine</text>
                  <text y="28" fill="#ff2a4b" font-family="var(--font-mono)" font-size="7" font-weight="700" text-anchor="middle" pointer-events="none">Firebase API</text>
                </g>

                <!-- 4. Firebase Database (Sync Socket) -->
                <g id="node-firebase-db" class="glow-node" transform="translate(380, 100)">
                  <circle r="32" fill="#181825" stroke="url(#secondary-grad)" stroke-width="2.5" filter="url(#glow)" />
                  <text y="-4" fill="#ffffff" font-size="18" text-anchor="middle" pointer-events="none">🗄️</text>
                  <text y="14" fill="#06b6d4" font-family="var(--font-mono)" font-size="8" font-weight="700" text-anchor="middle" pointer-events="none">Realtime DB</text>
                </g>

                <!-- 5. Stripe Billing Gateway -->
                <g id="node-stripe-api" class="glow-node" transform="translate(640, 180)">
                  <circle r="34" fill="#181825" stroke="url(#purple-grad)" stroke-width="2.5" filter="url(#glow)" />
                  <text y="-4" fill="#ffffff" font-size="18" text-anchor="middle" pointer-events="none">💳</text>
                  <text y="14" fill="#c084fc" font-family="var(--font-mono)" font-size="8" font-weight="700" text-anchor="middle" pointer-events="none">Stripe Webhook</text>
                </g>

                <!-- 6. M-Pesa Mobile Wallet -->
                <g id="node-mpesa-api" class="glow-node" transform="translate(640, 320)">
                  <circle r="34" fill="#181825" stroke="url(#gold-grad)" stroke-width="2.5" filter="url(#glow)" />
                  <text y="-4" fill="#ffffff" font-size="18" text-anchor="middle" pointer-events="none">💸</text>
                  <text y="14" fill="#f59e0b" font-family="var(--font-mono)" font-size="8" font-weight="700" text-anchor="middle" pointer-events="none">M-Pesa API</text>
                </g>

                <!-- Bottom Tier: Auxiliary cloud infrastructure -->
                <!-- 7. Alibaba CDN (Media feed) -->
                <g id="node-alibaba-cdn" class="glow-node" transform="translate(220, 430)">
                  <rect x="-35" y="-20" width="70" height="40" rx="6" fill="#14141e" stroke="rgba(255,255,255,0.2)" stroke-width="1.5" />
                  <text y="-2" fill="#ffffff" font-size="11" font-weight="700" text-anchor="middle" pointer-events="none">Alibaba CDN</text>
                  <text y="10" fill="rgba(255,255,255,0.4)" font-family="var(--font-mono)" font-size="6.5" text-anchor="middle" pointer-events="none">Live Stream</text>
                </g>

                <!-- 8. AWS Failover -->
                <g id="node-aws-failover" class="glow-node" transform="translate(380, 430)">
                  <rect x="-35" y="-20" width="70" height="40" rx="6" fill="#14141e" stroke="rgba(255,255,255,0.2)" stroke-width="1.5" />
                  <text y="-2" fill="#ffffff" font-size="11" font-weight="700" text-anchor="middle" pointer-events="none">AWS Backup</text>
                  <text y="10" fill="rgba(255,255,255,0.4)" font-family="var(--font-mono)" font-size="6.5" text-anchor="middle" pointer-events="none">Failover DB</text>
                </g>

                <!-- 9. Google Speech subtitles -->
                <g id="node-google-stt" class="glow-node" transform="translate(540, 430)">
                  <rect x="-35" y="-20" width="70" height="40" rx="6" fill="#14141e" stroke="rgba(255,255,255,0.2)" stroke-width="1.5" />
                  <text y="-2" fill="#ffffff" font-size="11" font-weight="700" text-anchor="middle" pointer-events="none">Google AI</text>
                  <text y="10" fill="rgba(255,255,255,0.4)" font-family="var(--font-mono)" font-size="6.5" text-anchor="middle" pointer-events="none">Subtitles (STT)</text>
                </g>
              </svg>
            </div>

            <!-- Inspect Panel Details -->
            <div class="node-inspect-card glass-card">
              <div style="border-bottom: 1px solid rgba(255,255,255,0.08); padding-bottom: 12px; margin-bottom: 4px;">
                <span style="font-size: 10px; font-weight: 800; color: var(--brand-primary); text-transform: uppercase; letter-spacing: 1px;">
                  INSPECTING NETWORK NODE // QAABKA SHAQADA NOODE-KA
                </span>
                <h3 id="inspect-title" style="font-size: 20px; font-weight: 800; color: #ffffff; margin-top: 6px;">
                  Firebase Realtime Database (Sync Hub)
                </h3>
                <span id="inspect-somali-title" style="font-size: 13px; font-weight: 600; color: var(--brand-secondary); display: block; margin-top: 2px;">
                  Xarunta Isku-xidhka (Realtime DB)
                </span>
              </div>

              <div>
                <span style="font-size: 11px; font-weight: 700; color: rgba(255,255,255,0.4); text-transform: uppercase; display: block; margin-bottom: 6px;">
                  Operational Overview (English)
                </span>
                <p id="inspect-desc" style="font-size: 13px; line-height: 1.5; color: rgba(255,255,255,0.8);">
                  The low-latency communication layer. The TV establishes a secure listener on '/sessions/{token_id}'. The moment the mobile phone successfully processes an action, it writes to this database node, pushing updates instantly to the TV.
                </p>
              </div>

              <div>
                <span style="font-size: 11px; font-weight: 700; color: rgba(255,255,255,0.4); text-transform: uppercase; display: block; margin-bottom: 6px;">
                  Sharaxaada Luuqada Soomaaliga (Somali)
                </span>
                <p id="inspect-somali-desc" style="font-size: 13px; line-height: 1.5; color: rgba(255,255,255,0.65);">
                  Muuqaalka isgaadhsiinta ee xawliga sare leh. TV-ga wuxuu dhagaystaa galka '/sessions/{token_id}'. Marka telefoonku dhammeeyo hawsha, wuxuu u qoraa halkan, taas oo TV-ga u cusboonaysiisa isla ilbiriqsigaas.
                </p>
              </div>

              <div style="border-top: 1px solid rgba(255,255,255,0.06); padding-top: 16px; margin-top: 4px; display: grid; grid-template-columns: 1fr 1fr; gap: 12px;">
                <div>
                  <span style="font-size: 9px; font-weight: 700; color: rgba(255,255,255,0.4); text-transform: uppercase; display: block; margin-bottom: 4px;">
                    Underlying Technology
                  </span>
                  <span id="inspect-tech" class="tech-spec-badge">Firebase Protocol, WebSockets</span>
                </div>
                <div>
                  <span style="font-size: 9px; font-weight: 700; color: rgba(255,255,255,0.4); text-transform: uppercase; display: block; margin-bottom: 4px;">
                    Average Network Latency
                  </span>
                  <span id="inspect-latency" class="tech-spec-badge" style="color: var(--brand-secondary); border-color: rgba(6,182,212,0.2);">&lt; 50ms</span>
                </div>
                <div style="grid-column: span 2;">
                  <span style="font-size: 9px; font-weight: 700; color: rgba(255,255,255,0.4); text-transform: uppercase; display: block; margin-bottom: 4px;">
                    Security Configuration
                  </span>
                  <span id="inspect-security" class="tech-spec-badge" style="color: var(--brand-primary); border-color: rgba(255,42,75,0.2);">Firebase Security Rules, Fine-grained IAM</span>
                </div>
              </div>
            </div>

          </div>
        </div>

        <!-- 2. Interactive Flow Stepper Simulator View -->
        <div class="qr-content-tab-pane" id="pane-simulator" style="display: none;">
          <div style="display: flex; flex-direction: column; gap: 24px;">

            <!-- Flow selector top bar -->
            <div class="flow-selector-bar">
              <button class="flow-btn active" id="btn-flow-registration" data-flow="registration">1. Registration QR</button>
              <button class="flow-btn" id="btn-flow-payment" data-flow="payment">2. Payment QR</button>
              <button class="flow-btn" id="btn-flow-pairing" data-flow="pairing">3. Device Pairing</button>
              <button class="flow-btn" id="btn-flow-login" data-flow="login">4. Password-Free Login</button>
            </div>

            <div class="sim-panel-grid">

              <!-- LEFT COLUMN: SMART TV MOCKUP -->
              <div style="display: flex; flex-direction: column; gap: 12px;">
                <span style="font-size: 11px; font-weight: 800; color: rgba(255,255,255,0.4); text-transform: uppercase; letter-spacing: 1px;">
                  Smart TV Screen // Shaashadda TV-ga
                </span>

                <div class="tv-bezel-frame">
                  <div class="tv-screen-content" id="tv-screen">

                    <!-- Dynamic screen states inside javascript render -->

                  </div>

                  <!-- TV Success checkmark overlay -->
                  <div class="tv-success-overlay" id="tv-success-layer">
                    <span style="font-size: 52px; animation: heart-beat 1.5s infinite alternate;">✅</span>
                    <h3 style="font-size: 20px; font-weight: 800; color: #ffffff;" id="tv-success-title">
                      WAAD FURTAY / UNLOCKED SUCCESSFUL
                    </h3>
                    <p style="font-size: 12px; color: rgba(255,255,255,0.6); text-align: center; max-width: 280px;" id="tv-success-desc">
                      Firebase cloud database synchronized! Access granted without standard remote typing.
                    </p>
                  </div>
                </div>
              </div>

              <!-- RIGHT COLUMN: MOBILE PHONE MOCKUP -->
              <div style="display: flex; flex-direction: column; gap: 12px; align-items: center;">
                <div style="width: 100%; display: flex; justify-content: space-between; align-items: center; max-width: 320px;">
                  <span style="font-size: 11px; font-weight: 800; color: rgba(255,255,255,0.4); text-transform: uppercase; letter-spacing: 1px;">
                    Viewer's Phone // Telefoonka Gacanta
                  </span>
                  <button id="btn-reset-simulator" style="background: transparent; border: none; color: var(--brand-primary); font-size: 11px; font-weight: 700; cursor: pointer; text-decoration: underline;">
                    Reset Flow
                  </button>
                </div>

                <div class="phone-case">
                  <div class="phone-notch"></div>
                  <div class="phone-screen" id="phone-screen-container">

                    <!-- Dynamic mobile interface screen -->

                  </div>
                </div>
              </div>

            </div>

          </div>
        </div>

      </div>
    `;

    bindTabEvents();
    bindArchEvents();
    initSimulators();
  };

  // Sub-Tab triggers switching
  const bindTabEvents = () => {
    const btnArch = container.querySelector("#tab-btn-architecture");
    const btnSim = container.querySelector("#tab-btn-simulator");
    const paneArch = container.querySelector("#pane-architecture");
    const paneSim = container.querySelector("#pane-simulator");

    btnArch.addEventListener("click", () => {
      simState.activeSubTab = "architecture";
      btnArch.classList.add("active");
      btnSim.classList.remove("active");
      paneArch.style.display = "block";
      paneSim.style.display = "none";
    });

    btnSim.addEventListener("click", () => {
      simState.activeSubTab = "simulator";
      btnSim.classList.add("active");
      btnArch.classList.remove("active");
      paneSim.style.display = "block";
      paneArch.style.display = "none";
      renderSimulator();
    });
  };

  // Architecture SVG Click handler
  const bindArchEvents = () => {
    const nodes = container.querySelectorAll(".glow-node");
    nodes.forEach(node => {
      node.addEventListener("click", () => {
        // Toggle active visual states
        nodes.forEach(n => n.classList.remove("active-node"));
        node.classList.add("active-node");

        const nodeId = node.id.replace("node-", "");
        simState.activeNode = nodeId;

        // Render Node inspect details
        const info = nodeDetails[nodeId];
        if (info) {
          container.querySelector("#inspect-title").textContent = info.title;
          container.querySelector("#inspect-somali-title").textContent = info.somaliTitle;
          container.querySelector("#inspect-desc").textContent = info.desc;
          container.querySelector("#inspect-somali-desc").textContent = info.somaliDesc;
          container.querySelector("#inspect-tech").textContent = info.tech;
          container.querySelector("#inspect-latency").textContent = info.latency;
          container.querySelector("#inspect-security").textContent = info.security;
        }
      });
    });
  };

  // Interactive Stepper Engine logic
  const initSimulators = () => {
    // Flow Selection Buttons
    const flowButtons = {
      registration: container.querySelector("#btn-flow-registration"),
      payment: container.querySelector("#btn-flow-payment"),
      pairing: container.querySelector("#btn-flow-pairing"),
      login: container.querySelector("#btn-flow-login")
    };

    const handleFlowSwitch = (flowId) => {
      // Clear timers
      if (simState.countdownTimer) {
        clearInterval(simState.countdownTimer);
        simState.countdownTimer = null;
      }

      simState.activeFlow = flowId;
      simState.tvState = "idle";
      simState.phoneStep = "start";
      simState.isTVLoggedIn = false;
      simState.isUpgraded = false;

      // Deactivate other tabs
      Object.keys(flowButtons).forEach(key => {
        if (key === flowId) {
          flowButtons[key].classList.add("active");
        } else {
          flowButtons[key].classList.remove("active");
        }
      });

      // Clear success screen immediately
      container.querySelector("#tv-success-layer").classList.remove("active");

      // Set up specific timers or parameters
      if (flowId === "registration" || flowId === "login") {
        simState.countdownTime = 90;
        simState.tvState = "counting";
        startTokenTimer();
      } else if (flowId === "pairing") {
        // Alphanumeric pairing code fallback setup
        simState.pairingCode = `GN-${Math.floor(1000 + Math.random() * 9000)}`;
      }

      // Initialize logs for current flow
      simState.telemetryLogs = [];
      setTimeout(() => {
        addTelemetry("SYSTEM", `Establish secure dynamic WebSocket connection at wss://api.gntv.com/v2/handshake...`);
        addTelemetry("FIREBASE", `Listening on database socket /sessions/${flowId === 'pairing' ? simState.pairingCode : 'token'}...`);
      }, 0);

      renderSimulator();
    };

    Object.keys(flowButtons).forEach(key => {
      flowButtons[key].addEventListener("click", () => handleFlowSwitch(key));
    });

    container.querySelector("#btn-reset-simulator").addEventListener("click", () => {
      handleFlowSwitch(simState.activeFlow);
    });

    // Initial load
    handleFlowSwitch("registration");
  };

  // 90s countdown bar
  const startTokenTimer = () => {
    simState.countdownTimer = setInterval(() => {
      if (simState.countdownTime > 0) {
        simState.countdownTime--;

        // Update countdown text on TV Screen reactively
        const timeEl = container.querySelector("#tv-countdown-val");
        const fillEl = container.querySelector("#tv-timer-fill");
        if (timeEl) timeEl.textContent = `${simState.countdownTime}s`;
        if (fillEl) fillEl.style.width = `${(simState.countdownTime / 90) * 100}%`;
      } else {
        // Token expired
        clearInterval(simState.countdownTimer);
        simState.countdownTimer = null;
        simState.tvState = "expired";
        renderSimulator();
      }
    }, 1000);
  };

  // Draws dynamic QR simulation code on target canvas
  const drawQR = (canvas, contentText) => {
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    const size = canvas.width;
    ctx.fillStyle = "#ffffff";
    ctx.fillRect(0, 0, size, size);

    ctx.fillStyle = "#09090e";

    // Draw corner anchor blocks (standard QR pattern)
    ctx.fillRect(4, 4, 18, 18);
    ctx.fillStyle = "#ffffff";
    ctx.fillRect(7, 7, 12, 12);
    ctx.fillStyle = "#09090e";
    ctx.fillRect(9, 9, 8, 8);

    ctx.fillRect(size - 22, 4, 18, 18);
    ctx.fillStyle = "#ffffff";
    ctx.fillRect(size - 19, 7, 12, 12);
    ctx.fillStyle = "#09090e";
    ctx.fillRect(size - 17, 9, 8, 8);

    ctx.fillRect(4, size - 22, 18, 18);
    ctx.fillStyle = "#ffffff";
    ctx.fillRect(7, size - 19, 12, 12);
    ctx.fillStyle = "#09090e";
    ctx.fillRect(9, 9, 8, 8);

    // Dynamic blocks depending on token strings
    ctx.fillStyle = "#09090e";
    let seed = 0;
    for (let i = 0; i < contentText.length; i++) {
      seed += contentText.charCodeAt(i);
    }

    for (let x = 22; x < size - 22; x += 3) {
      for (let y = 4; y < size - 4; y += 3) {
        const pseudorandom = Math.sin(seed + x * y) > 0.1;
        if (pseudorandom) {
          ctx.fillRect(x, y, 3, 3);
        }
      }
    }
  };

  // Renders the TV side + Mobile side simulator
  const renderSimulator = () => {
    renderTVScreen();
    renderPhoneScreen();
  };

  // 1. SMART TV SCREEN MOCKUP RENDERING
  const renderTVScreen = () => {
    const tvBox = container.querySelector("#tv-screen");
    if (!tvBox) return;

    if (simState.tvState === "success") {
      // Hands over to checkmark layer animations
      return;
    }

    if (simState.activeFlow === "registration") {
      tvBox.innerHTML = `
        <div style="text-align: center; display: flex; flex-direction: column; align-items: center; gap: 10px; width: 100%;">
          <div style="font-family: var(--font-mono); font-size: 8px; border: 1px solid var(--brand-primary); padding: 2px 6px; border-radius: 4px; color: var(--brand-primary); font-weight: 700; width: fit-content; text-transform: uppercase;">
            SECURE DEVICE COUPLING ENGINE
          </div>
          <h2 style="font-size: 16px; font-weight: 800; color: #ffffff; letter-spacing: -0.5px; margin: 0;">
            Diiwaan Geli TV-gaaga / Quick Registration
          </h2>
          <p style="font-size: 10px; color: rgba(255,255,255,0.5); max-width: 290px; margin-bottom: 6px;">
            Scan code below to instantly create an account and unlock trial relays. No tedious TV remote keyboard typing.
          </p>

          <div style="display: flex; align-items: center; gap: 20px; background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.06); padding: 12px 18px; border-radius: 12px;">
            <!-- QR Canvas -->
            <div style="background: #ffffff; padding: 6px; border-radius: 8px; box-shadow: 0 5px 15px rgba(0,0,0,0.5); display: flex;">
              <canvas id="tv-qr-canvas" width="96" height="96"></canvas>
            </div>

            <!-- Polling State -->
            <div style="text-align: left; display: flex; flex-direction: column; gap: 6px;">
              <div style="display: flex; align-items: center; gap: 6px;">
                <span class="status-pulse-green" style="width: 5px; height: 5px; background: var(--brand-primary); border-radius: 50%;"></span>
                <span style="font-size: 9px; font-weight: 700; font-family: var(--font-mono); color: var(--brand-primary);">
                  LISTENING FOR PHONE SCAN
                </span>
              </div>
              <div style="font-size: 11px; font-weight: 500; color: rgba(255,255,255,0.4);">
                Token expires in: <span id="tv-countdown-val" style="color: #ffffff; font-family: var(--font-mono); font-weight: 700;">${simState.countdownTime}s</span>
              </div>
              <div class="countdown-progress-bar" style="width: 100px;">
                <div class="countdown-fill" id="tv-timer-fill" style="width: ${(simState.countdownTime / 90) * 100}%"></div>
              </div>
            </div>
          </div>

          <div style="font-family: var(--font-mono); font-size: 7.5px; color: rgba(255,255,255,0.3); margin-top: 4px;">
            SECURE TOKEN ID // HMAC-SHA256: [REG_AUTH_TOKEN_GNTV DIGITAL, ALL EVERYWHERE_HUB]
          </div>
        </div>
      `;
      const canvas = tvBox.querySelector("#tv-qr-canvas");
      drawQR(canvas, `gntv-reg-auth-${simState.countdownTime}`);
    }

    else if (simState.activeFlow === "payment") {
      const goldActive = simState.selectedPaymentPlan === "gold";
      tvBox.innerHTML = `
        <div style="text-align: center; display: flex; flex-direction: column; align-items: center; gap: 6px; width: 100%;">
          <div style="font-family: var(--font-mono); font-size: 8px; border: 1px solid var(--brand-warning); padding: 2px 6px; border-radius: 4px; color: var(--brand-warning); font-weight: 700; width: fit-content; text-transform: uppercase;">
            GNTV DIGITAL, ALL EVERYWHERE PREMIUM UPGRADE
          </div>

          <h2 style="font-size: 14px; font-weight: 800; color: #ffffff; letter-spacing: -0.5px; margin: 0;">
            Dalbo GNTV DIGITAL, ALL EVERYWHERE Premium / Premium Subscription
          </h2>

          <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px; width: 100%; max-width: 320px; margin-top: 2px;">
            <!-- Plan 1 -->
            <div id="plan-standard" class="glass-card" style="padding: 6px 10px; border-radius: 8px; border-color: ${!goldActive ? 'var(--brand-primary)' : 'rgba(255,255,255,0.06)'}; background: ${!goldActive ? 'rgba(255,42,75,0.04)' : 'rgba(255,255,255,0.01)'}; cursor: pointer; text-align: left; transition: all 0.2s;">
              <span style="font-size: 11px; font-weight: 800; color: #ffffff; display: block;">Standard Package</span>
              <span style="font-size: 8px; color: rgba(255,255,255,0.4); display: block;">All Local Relays</span>
              <span style="font-size: 12px; font-weight: 800; color: var(--brand-secondary); display: block; margin-top: 2px;">$9.99 / mo</span>
            </div>

            <!-- Plan 2 -->
            <div id="plan-gold" class="glass-card" style="padding: 6px 10px; border-radius: 8px; border-color: ${goldActive ? 'var(--brand-warning)' : 'rgba(255,255,255,0.06)'}; background: ${goldActive ? 'rgba(245,158,11,0.04)' : 'rgba(255,255,255,0.01)'}; cursor: pointer; text-align: left; transition: all 0.2s;">
              <span style="font-size: 11px; font-weight: 800; color: #ffffff; display: flex; align-items: center; gap: 4px;">Gold VIP 👑</span>
              <span style="font-size: 8px; color: rgba(255,255,255,0.4); display: block;">Ultra HD + Somali League</span>
              <span style="font-size: 12px; font-weight: 800; color: var(--brand-warning); display: block; margin-top: 2px;">$19.99 / mo</span>
            </div>
          </div>

          <div style="display: grid; grid-template-columns: 72px 1fr; gap: 12px; background: rgba(255,255,255,0.02); border: 1px solid rgba(255,255,255,0.05); padding: 8px 12px; border-radius: 10px; width: 100%; max-width: 390px; justify-content: center; align-items: center; margin-top: 4px;">
            <div style="background: #ffffff; padding: 4px; border-radius: 6px; display: flex; width: 72px; height: 72px;">
              <canvas id="tv-qr-canvas" width="64" height="64" style="width: 64px; height: 64px; display: block;"></canvas>
            </div>

            <!-- Live Webhook Telemetry Console -->
            <div class="telemetry-console-wrapper">
              <div class="telemetry-console-header">
                <span style="font-weight: 800; color: rgba(255,255,255,0.4); font-size: 7px; text-transform: uppercase; letter-spacing: 0.5px;">API Webhook Telemetry Log</span>
                <span class="status-pulse-green" style="width: 4px; height: 4px; background: #10b981; border-radius: 50%; display: block;"></span>
              </div>
              <div class="telemetry-console-body" id="telemetry-logs-body" style="height: 54px; font-size: 8px; text-align: left; padding: 4px 8px;">
                <!-- Filled dynamically -->
              </div>
            </div>
          </div>
        </div>
      `;
      const canvas = tvBox.querySelector("#tv-qr-canvas");
      drawQR(canvas, `gntv-pay-checkout-${simState.selectedPaymentPlan}`);

      // Render existing telemetry logs in this state
      const logBody = tvBox.querySelector("#telemetry-logs-body");
      if (logBody) {
        if (simState.telemetryLogs.length === 0) {
          logBody.innerHTML = `<div style="color: rgba(255,255,255,0.35); font-style: italic;">Awaiting network handshake initialization...</div>`;
        } else {
          logBody.innerHTML = "";
          simState.telemetryLogs.forEach(log => {
            const line = document.createElement("div");
            line.className = "telemetry-line";
            let tagClass = "";
            const lowerTag = log.tag.toLowerCase();
            if (lowerTag.includes("stripe") || lowerTag.includes("card")) tagClass = "stripe";
            else if (lowerTag.includes("m-pesa") || lowerTag.includes("safaricom") || lowerTag.includes("stk")) tagClass = "mpesa";
            else if (lowerTag.includes("firebase") || lowerTag.includes("db") || lowerTag.includes("auth")) tagClass = "firebase";

            line.innerHTML = `
              <span class="telemetry-time">[${log.time}]</span>
              <span class="telemetry-event-tag ${tagClass}">${log.tag}</span>
              <span class="telemetry-msg">${log.msg}</span>
            `;
            logBody.appendChild(line);
          });
          logBody.scrollTop = logBody.scrollHeight;
        }
      }

      // Plan click handlers inside TV screen!
      tvBox.querySelector("#plan-standard").addEventListener("click", () => {
        simState.selectedPaymentPlan = "standard";
        simState.phoneStep = "start";
        simState.telemetryLogs = [];
        addTelemetry("SYSTEM", "Selected Standard Subscription Package ($9.99/mo).");
        addTelemetry("FIREBASE", "Polling payment path /payments/sessions/GN-948X...");
        renderSimulator();
      });
      tvBox.querySelector("#plan-gold").addEventListener("click", () => {
        simState.selectedPaymentPlan = "gold";
        simState.phoneStep = "start";
        simState.telemetryLogs = [];
        addTelemetry("SYSTEM", "Selected VIP Gold Subscription Package ($19.99/mo).");
        addTelemetry("FIREBASE", "Polling payment path /payments/sessions/GN-948X...");
        renderSimulator();
      });
    }

    else if (simState.activeFlow === "pairing") {
      tvBox.innerHTML = `
        <div style="text-align: center; display: flex; flex-direction: column; align-items: center; gap: 8px; width: 100%;">
          <div style="font-family: var(--font-mono); font-size: 8px; border: 1px solid var(--brand-secondary); padding: 2px 6px; border-radius: 4px; color: var(--brand-secondary); font-weight: 700; width: fit-content; text-transform: uppercase;">
            IPTV / DECODER SYNC HUB
          </div>

          <h2 style="font-size: 15px; font-weight: 800; color: #ffffff; letter-spacing: -0.5px; margin: 0;">
            Ku Xidh Decoder-kaaga / Device Pairing
          </h2>
          <p style="font-size: 9.5px; color: rgba(255,255,255,0.45); max-width: 320px;">
            Pair your Set-Top Box, IPTV decoder, or friend's Smart TV. Scan QR code, or type the 6-character activation code at <strong style="color: var(--brand-secondary);">gntv.com/activate</strong>.
          </p>

          <div style="display: flex; align-items: center; gap: 24px; background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.06); padding: 12px 20px; border-radius: 12px; width: 100%; max-width: 350px; justify-content: center; margin-top: 4px;">
            <div style="background: #ffffff; padding: 5px; border-radius: 6px; display: flex;">
              <canvas id="tv-qr-canvas" width="76" height="76"></canvas>
            </div>

            <div style="text-align: left; display: flex; flex-direction: column; gap: 4px;">
              <span style="font-size: 9px; font-weight: 700; color: rgba(255,255,255,0.4); text-transform: uppercase;">6-CHARACTER ACTIVATION CODE</span>
              <div style="font-family: var(--font-mono); font-size: 22px; font-weight: 800; color: #ffffff; letter-spacing: 2px; text-shadow: 0 0 10px rgba(6,182,212,0.4);">
                ${simState.pairingCode}
              </div>
              <span style="font-size: 7.5px; color: rgba(255,255,255,0.4); font-family: var(--font-mono);">Awaiting active coupling handshake...</span>
            </div>
          </div>
        </div>
      `;
      const canvas = tvBox.querySelector("#tv-qr-canvas");
      drawQR(canvas, `gntv-pair-code-${simState.pairingCode}`);
    }

    else if (simState.activeFlow === "login") {
      tvBox.innerHTML = `
        <div style="text-align: center; display: flex; flex-direction: column; align-items: center; gap: 10px; width: 100%;">
          <div style="font-family: var(--font-mono); font-size: 8px; border: 1px solid var(--brand-primary); padding: 2px 6px; border-radius: 4px; color: var(--brand-primary); font-weight: 700; width: fit-content; text-transform: uppercase;">
            WHATSAPP WEB-STYLE AUTH PIPELINE
          </div>

          <h2 style="font-size: 15px; font-weight: 800; color: #ffffff; letter-spacing: -0.5px; margin: 0;">
            Gali Adigoon Isticmaalin Password / Password-Free Login
          </h2>
          <p style="font-size: 9.5px; color: rgba(255,255,255,0.45); max-width: 320px;">
            Returning subscriber? Walk up to any hotel screen or Smart TV. Scan with your GNTV DIGITAL, ALL EVERYWHERE mobile app to sign in instantly.
          </p>

          <div style="display: flex; align-items: center; gap: 20px; background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.06); padding: 12px 18px; border-radius: 12px; position: relative;">
            <div style="background: #ffffff; padding: 6px; border-radius: 8px; display: flex; position: relative; overflow: hidden;">
              <canvas id="tv-qr-canvas" width="80" height="80"></canvas>
              <!-- Scanner line animation in QR frame -->
              <div class="pulsing-scanner-glow"></div>
            </div>

            <div style="text-align: left; display: flex; flex-direction: column; gap: 4px;">
              <div style="display: flex; align-items: center; gap: 6px;">
                <span class="status-pulse-green" style="width: 5px; height: 5px; background: var(--brand-success); border-radius: 50%;"></span>
                <span style="font-size: 9px; font-weight: 800; font-family: var(--font-mono); color: var(--brand-success);">
                  FAST AUTH SYNC CHANNEL ACTIVE
                </span>
              </div>
              <span style="font-size: 11px; color: rgba(255,255,255,0.5);">
                Valid for: <span id="tv-countdown-val" style="color: #ffffff; font-family: var(--font-mono); font-weight: 700;">${simState.countdownTime}s</span>
              </span>
              <div class="countdown-progress-bar" style="width: 120px;">
                <div class="countdown-fill" id="tv-timer-fill" style="width: ${(simState.countdownTime / 90) * 100}%"></div>
              </div>
            </div>
          </div>
        </div>
      `;
      const canvas = tvBox.querySelector("#tv-qr-canvas");
      drawQR(canvas, `gntv-fast-login-auth-${simState.countdownTime}`);
    }
  };

  // 2. MOBILE PHONE SCREEN RENDERING
  const renderPhoneScreen = () => {
    const phoneBox = container.querySelector("#phone-screen-container");
    if (!phoneBox) return;

    // A. PHONE FLOW: REGISTRATION
    if (simState.activeFlow === "registration") {
      if (simState.phoneStep === "start") {
        phoneBox.innerHTML = `
          <div style="display: flex; flex-direction: column; justify-content: space-between; height: 100%;">
            <div style="display: flex; flex-direction: column; gap: 12px; flex-grow: 1;">
              <div style="display: flex; align-items: center; gap: 8px; border-bottom: 1px solid rgba(255,255,255,0.06); padding-bottom: 10px;">
                <span style="font-size: 16px;">📷</span>
                <div>
                  <h4 style="font-size: 13px; font-weight: 800; color: #ffffff; margin: 0;">GNTV DIGITAL, ALL EVERYWHERE Scan Viewfinder</h4>
                  <span style="font-size: 8.5px; color: var(--brand-primary); font-family: var(--font-mono); font-weight: 700;">AWAITING QR TARGET</span>
                </div>
              </div>

              <div class="scanner-viewfinder">
                <div class="scanner-corner top-left"></div>
                <div class="scanner-corner top-right"></div>
                <div class="scanner-corner bottom-left"></div>
                <div class="scanner-corner bottom-right"></div>
                <div class="scanner-laser-line"></div>
                <span class="scanner-status-text" id="scanner-status">READY TO SCAN</span>
              </div>

              <p style="font-size: 11px; color: rgba(255,255,255,0.5); text-align: center; margin-top: 6px; line-height: 1.4;">
                Position the TV's QR Code inside the scanner target frame.
              </p>
            </div>

            <button id="btn-simulate-scan" style="background: var(--brand-primary); border: none; padding: 14px; border-radius: 12px; color: #ffffff; font-weight: 700; font-size: 13px; cursor: pointer; box-shadow: 0 4px 15px var(--brand-primary-glow);">
              SIMULATE CAMERA SCAN ⚡
            </button>
          </div>
        `;
        phoneBox.querySelector("#btn-simulate-scan").addEventListener("click", () => {
          simState.phoneStep = "scanning";
          renderPhoneScreen();

          addTelemetry("CAMERA", "Camera viewfinder focusing on target QR registration anchors...");

          setTimeout(() => {
            const statusText = phoneBox.querySelector("#scanner-status");
            if (statusText) statusText.textContent = "DECODING QR DATA...";
            addTelemetry("DECODER", "Dynamic token signature read: gntv-reg-auth-token-90s");
          }, 600);

          setTimeout(() => {
            const statusText = phoneBox.querySelector("#scanner-status");
            if (statusText) statusText.textContent = "VALIDATING PAYLOAD...";
            addTelemetry("AUTH", "HMAC verified. JWT session authorization token match: SECURE");
          }, 1200);

          setTimeout(() => {
            simState.phoneStep = "input";
            renderPhoneScreen();
          }, 1800);
        });
      }

      else if (simState.phoneStep === "scanning") {
        phoneBox.innerHTML = `
          <div style="display: flex; flex-direction: column; justify-content: center; height: 100%;">
            <div style="display: flex; flex-direction: column; gap: 12px; flex-grow: 1;">
              <div style="display: flex; align-items: center; gap: 8px; border-bottom: 1px solid rgba(255,255,255,0.06); padding-bottom: 10px;">
                <span style="font-size: 16px;">📷</span>
                <div>
                  <h4 style="font-size: 13px; font-weight: 800; color: #ffffff; margin: 0;">GNTV DIGITAL, ALL EVERYWHERE Scan Viewfinder</h4>
                  <span style="font-size: 8.5px; color: var(--brand-primary); font-family: var(--font-mono); font-weight: 700;">SCAN IN PROGRESS</span>
                </div>
              </div>

              <div class="scanner-viewfinder">
                <div class="scanner-corner top-left"></div>
                <div class="scanner-corner top-right"></div>
                <div class="scanner-corner bottom-left"></div>
                <div class="scanner-corner bottom-right"></div>
                <div class="scanner-laser-line"></div>
                <span class="scanner-status-text" id="scanner-status">SCANNING / DECODING...</span>
              </div>

              <p style="font-size: 11px; color: rgba(255,255,255,0.5); text-align: center; margin-top: 6px; line-height: 1.4;">
                Hold steady. Aligning coordinates with WebSocket listener...
              </p>
            </div>
          </div>
        `;
      }

      else if (simState.phoneStep === "input") {
        phoneBox.innerHTML = `
          <div style="display: flex; flex-direction: column; justify-content: space-between; height: 100%;">
            <div style="display: flex; flex-direction: column; gap: 14px;">
              <div style="display: flex; align-items: center; gap: 8px; border-bottom: 1px solid rgba(255,255,255,0.06); padding-bottom: 10px;">
                <span style="font-size: 18px;">📋</span>
                <div>
                  <h4 style="font-size: 13px; font-weight: 800; color: #ffffff; margin: 0;">Device Signed Enrollment</h4>
                  <span style="font-size: 9px; color: var(--brand-primary); font-family: var(--font-mono); font-weight: 700;">TTL SECURE TOKEN CHECKED IN</span>
                </div>
              </div>

              <p style="font-size: 11px; color: rgba(255,255,255,0.5); line-height: 1.4;">
                Fill out the rapid registration form below. Submitting will sync coordinates immediately and log the TV in.
              </p>

              <div style="display: flex; flex-direction: column; gap: 12px; margin-top: 6px;">
                <div style="display: flex; flex-direction: column; gap: 5px;">
                  <label style="font-size: 9.5px; font-weight: 800; color: rgba(255,255,255,0.4); text-transform: uppercase;">Full Name // Magacaaga</label>
                  <input type="text" id="phone-reg-name" style="background: rgba(255,255,255,0.04); border: 1px solid rgba(255,255,255,0.08); padding: 10px 12px; border-radius: 8px; font-size: 13px; color: #ffffff; outline: none;" value="${simState.userInputs.name}">
                </div>

                <div style="display: flex; flex-direction: column; gap: 5px;">
                  <label style="font-size: 9.5px; font-weight: 800; color: rgba(255,255,255,0.4); text-transform: uppercase;">Email Address // E-Mail</label>
                  <input type="email" id="phone-reg-email" style="background: rgba(255,255,255,0.04); border: 1px solid rgba(255,255,255,0.08); padding: 10px 12px; border-radius: 8px; font-size: 13px; color: #ffffff; outline: none;" value="${simState.userInputs.email}">
                </div>
              </div>
            </div>

            <button id="btn-submit-reg" style="background: var(--brand-primary); border: none; padding: 14px; border-radius: 12px; color: #ffffff; font-weight: 700; font-size: 13px; cursor: pointer; box-shadow: 0 4px 15px var(--brand-primary-glow);">
              SUBMIT SECURE REGISTRATION 🚀
            </button>
          </div>
        `;
        phoneBox.querySelector("#btn-submit-reg").addEventListener("click", () => {
          const nameInput = phoneBox.querySelector("#phone-reg-name").value.trim();
          const emailInput = phoneBox.querySelector("#phone-reg-email").value.trim();

          if (!emailInput) {
            alert("Email is required!");
            return;
          }

          simState.userInputs.name = nameInput;
          simState.userInputs.email = emailInput;
          simState.phoneStep = "processing";
          renderPhoneScreen();

          // Simulate Firebase Realtime DB sync propagation
          simState.tvState = "processing";
          renderTVScreen();

          addTelemetry("FIREBASE", `Writing metadata nodes at /users/temp_reg_session...`);

          setTimeout(() => {
            // Write coordinates into state to simulate real auth
            store.signIn(emailInput, nameInput);

            simState.phoneStep = "success";
            simState.tvState = "success";
            renderSimulator();
            triggerTVCheckmark("REGISTRATION ENROLLMENT SUCCESS!", "Your GNTV DIGITAL, ALL EVERYWHERE Account has been created and synced session-wide! TV shell authorized.");
          }, 1500);
        });
      }

      else if (simState.phoneStep === "processing") {
        phoneBox.innerHTML = `
          <div style="text-align: center; display: flex; flex-direction: column; align-items: center; justify-content: center; flex-grow: 1; gap: 16px;">
            <div style="border: 3px solid rgba(255,42,75,0.15); border-top: 3px solid var(--brand-primary); border-radius: 50%; width: 40px; height: 40px; animation: banner-flash 1s infinite linear;"></div>
            <h4 style="font-size: 14px; font-weight: 800; color: #ffffff;">Firebase Write in Progress</h4>
            <p style="font-size: 11px; color: rgba(255,255,255,0.45); text-align: center; max-width: 220px; line-height: 1.4;">
              Syncing '/sessions/{token}' in Firebase Realtime Database. Secure channel authorization established.
            </p>
          </div>
        `;
      }

      else if (simState.phoneStep === "success") {
        phoneBox.innerHTML = `
          <div style="text-align: center; display: flex; flex-direction: column; align-items: center; justify-content: center; flex-grow: 1; gap: 14px;">
            <span style="font-size: 44px;">✔️</span>
            <h4 style="font-size: 16px; font-weight: 800; color: var(--brand-success);">Handshake Complete</h4>
            <p style="font-size: 11.5px; color: rgba(255,255,255,0.5); text-align: center; line-height: 1.4;">
              TV authorized as subscriber <strong>${simState.userInputs.name}</strong>. Free trial tier active session-wide!
            </p>
            <div style="background: rgba(16,185,129,0.06); border: 1px solid rgba(16,185,129,0.15); border-radius: 10px; padding: 10px 14px; width: 100%; text-align: left; font-size: 11px; color: rgba(255,255,255,0.7); display: flex; flex-direction: column; gap: 4px;">
              <div>• Session ID: <strong style="font-family: var(--font-mono); font-size: 9px; color: #ffffff;">SES_8829FBA</strong></div>
              <div>• Status: <strong style="color: var(--brand-success)">Connected</strong></div>
              <div>• Device: <strong style="color: var(--brand-secondary)">Tizen Smart TV Hub</strong></div>
            </div>
          </div>
        `;
      }
    }

    // B. PHONE FLOW: PAYMENT CHECKOUT
    else if (simState.activeFlow === "payment") {
      const planLabel = simState.selectedPaymentPlan === "gold" ? "Gold VIP Package" : "Standard Package";
      const planCost = simState.selectedPaymentPlan === "gold" ? "$19.99" : "$9.99";

      if (simState.phoneStep === "start") {
        phoneBox.innerHTML = `
          <div style="display: flex; flex-direction: column; justify-content: space-between; height: 100%;">
            <div style="display: flex; flex-direction: column; gap: 12px; flex-grow: 1;">
              <div style="display: flex; align-items: center; gap: 8px; border-bottom: 1px solid rgba(255,255,255,0.06); padding-bottom: 10px;">
                <span style="font-size: 16px;">📷</span>
                <div>
                  <h4 style="font-size: 13px; font-weight: 800; color: #ffffff; margin: 0;">Checkout Scanner</h4>
                  <span style="font-size: 8.5px; color: var(--brand-warning); font-family: var(--font-mono); font-weight: 700;">PLAN: ${planCost} USD</span>
                </div>
              </div>

              <div class="scanner-viewfinder">
                <div class="scanner-corner top-left" style="border-color:var(--brand-warning)"></div>
                <div class="scanner-corner top-right" style="border-color:var(--brand-warning)"></div>
                <div class="scanner-corner bottom-left" style="border-color:var(--brand-warning)"></div>
                <div class="scanner-corner bottom-right" style="border-color:var(--brand-warning)"></div>
                <div class="scanner-laser-line" style="background:linear-gradient(90deg, transparent, var(--brand-warning), transparent); box-shadow: 0 0 10px var(--brand-warning);"></div>
                <span class="scanner-status-text" id="scanner-status" style="color:var(--brand-warning); text-shadow: 0 0 8px rgba(245,158,11,0.6)">SCAN BILLING QR</span>
              </div>

              <p style="font-size: 11px; color: rgba(255,255,255,0.5); text-align: center; margin-top: 6px; line-height: 1.4;">
                Aim camera at TV payment checkout code for <strong>${planLabel}</strong>.
              </p>
            </div>

            <button id="btn-simulate-scan" style="background: var(--brand-warning); border: none; padding: 14px; border-radius: 12px; color: #ffffff; font-weight: 700; font-size: 13px; cursor: pointer; box-shadow: 0 4px 15px rgba(245,158,11,0.3);">
              SCAN CHECKOUT QR ⚡
            </button>
          </div>
        `;
        phoneBox.querySelector("#btn-simulate-scan").addEventListener("click", () => {
          simState.phoneStep = "scanning";
          renderPhoneScreen();

          addTelemetry("CAMERA", `Locating secure Stripe/M-Pesa payload dimensions...`);

          setTimeout(() => {
            const statusText = phoneBox.querySelector("#scanner-status");
            if (statusText) statusText.textContent = "DECODING BILLING...";
            addTelemetry("DECODER", `Identified billing session code: gntv-pay-checkout-${simState.selectedPaymentPlan}`);
          }, 600);

          setTimeout(() => {
            const statusText = phoneBox.querySelector("#scanner-status");
            if (statusText) statusText.textContent = "VALIDATING GATEWAYS...";
            addTelemetry("SYSTEM", `Secure pipeline resolved successfully for ${planCost} USD.`);
          }, 1200);

          setTimeout(() => {
            simState.phoneStep = "input";
            renderPhoneScreen();
          }, 1800);
        });
      }

      else if (simState.phoneStep === "scanning") {
        phoneBox.innerHTML = `
          <div style="display: flex; flex-direction: column; justify-content: center; height: 100%;">
            <div style="display: flex; flex-direction: column; gap: 12px; flex-grow: 1;">
              <div style="display: flex; align-items: center; gap: 8px; border-bottom: 1px solid rgba(255,255,255,0.06); padding-bottom: 10px;">
                <span style="font-size: 16px;">📷</span>
                <div>
                  <h4 style="font-size: 13px; font-weight: 800; color: #ffffff; margin: 0;">Checkout Scanner</h4>
                  <span style="font-size: 8.5px; color: var(--brand-warning); font-family: var(--font-mono); font-weight: 700;">SCAN IN PROGRESS</span>
                </div>
              </div>

              <div class="scanner-viewfinder">
                <div class="scanner-corner top-left" style="border-color:var(--brand-warning)"></div>
                <div class="scanner-corner top-right" style="border-color:var(--brand-warning)"></div>
                <div class="scanner-corner bottom-left" style="border-color:var(--brand-warning)"></div>
                <div class="scanner-corner bottom-right" style="border-color:var(--brand-warning)"></div>
                <div class="scanner-laser-line" style="background:linear-gradient(90deg, transparent, var(--brand-warning), transparent); box-shadow: 0 0 10px var(--brand-warning);"></div>
                <span class="scanner-status-text" id="scanner-status" style="color:var(--brand-warning); text-shadow: 0 0 8px rgba(245,158,11,0.6)">DECODING MERCHANDISE...</span>
              </div>

              <p style="font-size: 11px; color: rgba(255,255,255,0.5); text-align: center; margin-top: 6px; line-height: 1.4;">
                Establishing encrypted handshake session with GNTV DIGITAL, ALL EVERYWHERE billing server...
              </p>
            </div>
          </div>
        `;
      }

      else if (simState.phoneStep === "input") {
        phoneBox.innerHTML = `
          <div style="display: flex; flex-direction: column; justify-content: space-between; height: 100%;">
            <div style="display: flex; flex-direction: column; gap: 12px;">
              <div style="display: flex; align-items: center; gap: 8px; border-bottom: 1px solid rgba(255,255,255,0.06); padding-bottom: 10px;">
                <span style="font-size: 18px;">🛒</span>
                <div>
                  <h4 style="font-size: 13px; font-weight: 800; color: #ffffff; margin: 0;">GNTV DIGITAL, ALL EVERYWHERE Express Checkout</h4>
                  <span style="font-size: 9.5px; color: var(--brand-warning); font-weight: 700;">PLAN: ${planLabel.toUpperCase()}</span>
                </div>
              </div>

              <div style="background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.06); padding: 10px; border-radius: 8px; display: flex; justify-content: space-between; align-items: center;">
                <span style="font-size: 11px; color: rgba(255,255,255,0.5);">Subtotal Due:</span>
                <strong style="font-size: 15px; color: #ffffff;">${planCost} USD</strong>
              </div>

              <span style="font-size: 10px; font-weight: 800; color: rgba(255,255,255,0.4); text-transform: uppercase; margin-top: 8px;">Select Payment Gateway</span>

              <div style="display: flex; flex-direction: column; gap: 8px;">
                <!-- Stripe Card / Apple Pay option -->
                <button id="btn-pay-stripe" class="glass-card" style="padding: 12px; border-radius: 8px; cursor: pointer; text-align: left; background: rgba(255,255,255,0.02); display: flex; align-items: center; gap: 10px; width: 100%;">
                  <span style="font-size: 18px;">💳</span>
                  <div style="flex: 1;">
                    <strong style="font-size: 12px; color: #ffffff; display: block;">Credit Card / Stripe</strong>
                    <span style="font-size: 9px; color: rgba(255,255,255,0.4);">Visa, MasterCard, Apple Pay</span>
                  </div>
                  <span style="font-size: 10px; color: var(--brand-secondary);">➔</span>
                </button>

                <!-- M-Pesa Mobile money option -->
                <button id="btn-pay-mpesa" class="glass-card" style="padding: 12px; border-radius: 8px; cursor: pointer; text-align: left; background: rgba(255,255,255,0.02); display: flex; align-items: center; gap: 10px; width: 100%;">
                  <span style="font-size: 18px;">💸</span>
                  <div style="flex: 1;">
                    <strong style="font-size: 12px; color: #ffffff; display: block;">M-Pesa Express (STK)</strong>
                    <span style="font-size: 9px; color: rgba(255,255,255,0.4);">Direct PIN Push Prompt</span>
                  </div>
                  <span style="font-size: 10px; color: var(--brand-warning);">➔</span>
                </button>
              </div>
            </div>

            <span style="font-size: 8px; color: rgba(255,255,255,0.3); text-align: center;">Secure payments managed under AES-256 tokens.</span>
          </div>
        `;

        phoneBox.querySelector("#btn-pay-stripe").addEventListener("click", () => {
          simState.phoneStep = "card";
          simState.userInputs.cardNumber = "";
          simState.userInputs.cardExpiry = "";
          simState.userInputs.cardCvv = "";
          renderPhoneScreen();
        });

        phoneBox.querySelector("#btn-pay-mpesa").addEventListener("click", () => {
          simState.phoneStep = "pin";
          simState.userInputs.mpesaPin = "";
          renderPhoneScreen();

          addTelemetry("Safaricom API", "OAuth 2.0 generated token (Scope: Daraja_STK_Push)...");
          setTimeout(() => {
            addTelemetry("Safaricom API", "Triggering dynamic Lipa Na M-Pesa STK Push request...");
            addTelemetry("Safaricom Gateway", "CheckoutRequestID: ws_CO_0506. Direct user PIN prompt dispatched.");
          }, 600);
        });
      }

      else if (simState.phoneStep === "card") {
        phoneBox.innerHTML = `
          <div style="display: flex; flex-direction: column; justify-content: space-between; height: 100%;">
            <div style="display: flex; flex-direction: column; gap: 10px;">
              <div style="display: flex; align-items: center; gap: 8px; border-bottom: 1px solid rgba(255,255,255,0.06); padding-bottom: 8px;">
                <span style="font-size: 16px;">💳</span>
                <div>
                  <h4 style="font-size: 12px; font-weight: 800; color: #ffffff; margin: 0;">Card Verification</h4>
                  <span style="font-size: 8px; color: var(--brand-secondary); font-weight: 700;">STRIPE DYNAMIC EMBED</span>
                </div>
              </div>

              <!-- Interactive Visual Credit Card Mockup -->
              <div class="visual-credit-card">
                <div class="visual-card-glow"></div>
                <div class="card-preview-header">
                  <span class="card-preview-logo">GNTV DIGITAL, ALL EVERYWHERE <span style="color:var(--brand-primary); font-weight:800;">PAY</span></span>
                  <span class="card-preview-type" id="card-type-logo">💳</span>
                </div>
                <div class="card-preview-chip"></div>
                <div class="card-preview-number" id="card-preview-num-val">•••• •••• •••• ••••</div>
                <div class="card-preview-meta">
                  <div>
                    <span class="card-preview-label">Cardholder</span>
                    <div class="card-preview-val" id="card-preview-name-val">CUMAR CABDI</div>
                  </div>
                  <div>
                    <span class="card-preview-label">Expires</span>
                    <div class="card-preview-val" id="card-preview-expiry-val">MM/YY</div>
                  </div>
                </div>
              </div>

              <!-- Card form inputs -->
              <div style="display: flex; flex-direction: column; gap: 8px; margin-top: 4px;">
                <div style="display: flex; flex-direction: column; gap: 3px;">
                  <label style="font-size: 8px; font-weight: 800; color: rgba(255,255,255,0.4); text-transform: uppercase;">Card Number</label>
                  <input type="text" id="cc-num" placeholder="4111 1111 1111 1111" style="background: rgba(255,255,255,0.04); border: 1px solid rgba(255,255,255,0.08); padding: 8px 10px; border-radius: 6px; font-size: 12px; font-family: var(--font-mono); color: #ffffff; outline: none;" value="${simState.userInputs.cardNumber}">
                </div>

                <div style="display: flex; flex-direction: column; gap: 3px;">
                  <label style="font-size: 8px; font-weight: 800; color: rgba(255,255,255,0.4); text-transform: uppercase;">Cardholder Name</label>
                  <input type="text" id="cc-name" placeholder="Cumar Cabdi" style="background: rgba(255,255,255,0.04); border: 1px solid rgba(255,255,255,0.08); padding: 8px 10px; border-radius: 6px; font-size: 12px; color: #ffffff; outline: none;" value="${simState.userInputs.name}">
                </div>

                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px;">
                  <div style="display: flex; flex-direction: column; gap: 3px;">
                    <label style="font-size: 8px; font-weight: 800; color: rgba(255,255,255,0.4); text-transform: uppercase;">Expiration</label>
                    <input type="text" id="cc-expiry" placeholder="MM/YY" style="background: rgba(255,255,255,0.04); border: 1px solid rgba(255,255,255,0.08); padding: 8px 10px; border-radius: 6px; font-size: 12px; font-family: var(--font-mono); color: #ffffff; outline: none;" value="${simState.userInputs.cardExpiry}">
                  </div>
                  <div style="display: flex; flex-direction: column; gap: 3px;">
                    <label style="font-size: 8px; font-weight: 800; color: rgba(255,255,255,0.4); text-transform: uppercase;">CVV</label>
                    <input type="password" id="cc-cvv" placeholder="•••" style="background: rgba(255,255,255,0.04); border: 1px solid rgba(255,255,255,0.08); padding: 8px 10px; border-radius: 6px; font-size: 12px; font-family: var(--font-mono); color: #ffffff; outline: none;" value="${simState.userInputs.cardCvv}">
                  </div>
                </div>
              </div>
            </div>

            <button id="btn-submit-stripe" style="background: var(--brand-primary); border: none; padding: 12px; border-radius: 10px; color: #ffffff; font-weight: 700; font-size: 13px; cursor: pointer; box-shadow: 0 4px 15px var(--brand-primary-glow);">
              PAY ${planCost} USD SECURELY
            </button>
          </div>
        `;

        // Card format logic
        const ccNum = phoneBox.querySelector("#cc-num");
        const ccName = phoneBox.querySelector("#cc-name");
        const ccExpiry = phoneBox.querySelector("#cc-expiry");
        const ccCvv = phoneBox.querySelector("#cc-cvv");
        const ccBtn = phoneBox.querySelector("#btn-submit-stripe");

        if (ccNum) {
          ccNum.addEventListener("focus", () => addTelemetry("Stripe SDK", "Encrypting target credential fields dynamically..."));
          ccNum.addEventListener("input", (e) => {
            let val = e.target.value.replace(/\D/g, "");
            let formatted = "";
            for (let i = 0; i < val.length && i < 16; i++) {
              if (i > 0 && i % 4 === 0) formatted += " ";
              formatted += val[i];
            }
            e.target.value = formatted;
            simState.userInputs.cardNumber = formatted;

            // Sync to preview card
            const cardNumVal = phoneBox.querySelector("#card-preview-num-val");
            if (cardNumVal) cardNumVal.textContent = formatted || "•••• •••• •••• ••••";

            // Detect card brand
            const typeLogo = phoneBox.querySelector("#card-type-logo");
            if (typeLogo) {
              if (val.startsWith("4")) {
                typeLogo.textContent = "VISA";
                typeLogo.style.color = "#3b82f6";
                addTelemetry("Stripe API", "Card BIN matched: VISA Network verified.");
              } else if (val.startsWith("5")) {
                typeLogo.textContent = "MC";
                typeLogo.style.color = "#f59e0b";
                addTelemetry("Stripe API", "Card BIN matched: MasterCard Network verified.");
              } else {
                typeLogo.textContent = "💳";
                typeLogo.style.color = "";
              }
            }
          });
        }

        if (ccName) {
          ccName.addEventListener("input", (e) => {
            let val = e.target.value.toUpperCase();
            simState.userInputs.cardholderName = val;
            const cardNameVal = phoneBox.querySelector("#card-preview-name-val");
            if (cardNameVal) cardNameVal.textContent = val || "CUMAR CABDI";
          });
        }

        if (ccExpiry) {
          ccExpiry.addEventListener("input", (e) => {
            let val = e.target.value.replace(/\D/g, "");
            let formatted = val;
            if (val.length > 2) {
              formatted = val.substring(0, 2) + "/" + val.substring(2, 4);
            }
            e.target.value = formatted.substring(0, 5);
            simState.userInputs.cardExpiry = e.target.value;

            const cardExpVal = phoneBox.querySelector("#card-preview-expiry-val");
            if (cardExpVal) cardExpVal.textContent = e.target.value || "MM/YY";
          });
        }

        if (ccCvv) {
          ccCvv.addEventListener("input", (e) => {
            e.target.value = e.target.value.replace(/\D/g, "").substring(0, 3);
            simState.userInputs.cardCvv = e.target.value;
          });
        }

        if (ccBtn) {
          ccBtn.addEventListener("click", () => {
            const numDigits = ccNum.value.replace(/\s/g, "");
            if (numDigits.length < 16) {
              alert("Please enter a valid 16-digit credit card number.");
              return;
            }
            if (ccExpiry.value.length < 5) {
              alert("Please enter card expiration date.");
              return;
            }
            if (ccCvv.value.length < 3) {
              alert("Please enter CVV.");
              return;
            }

            simState.phoneStep = "processing";
            simState.tvState = "processing";
            renderSimulator();

            addTelemetry("Stripe API", "Initiating secure card verification checkout handshake...");
            setTimeout(() => {
              addTelemetry("Stripe API", "POST /v1/tokens ~ Exchanging fields for secure token tok_1N5bYx...");
              addTelemetry("Stripe API", "Token generated: tok_8873hF (Status: ACTIVE)");
            }, 400);

            setTimeout(() => {
              addTelemetry("Stripe Webhook", "payment_intent.created ~ Received status pi_3N4bYx...");
              addTelemetry("Stripe Webhook", "charge.succeeded ~ Customer captured funds successfully.");
            }, 900);

            setTimeout(() => {
              addTelemetry("Stripe Webhook", "checkout.session.completed ~ Broadcasting payload back to client socket.");
              addTelemetry("FIREBASE DB", "Write session status: 'premium' (upgraded active subscription).");
            }, 1400);

            setTimeout(() => {
              store.activateFreeTrial(); // Upgrade user tier locally
              simState.phoneStep = "success";
              simState.tvState = "success";
              renderSimulator();
              triggerTVCheckmark("STRIPE PAYMENTS UNLOCKED SUCCESSFUL!", `Stripe Webhook authorization captured! TV upgraded to active ${planLabel} tier immediately.`);
            }, 1900);
          });
        }
      }

      else if (simState.phoneStep === "pin") {
        phoneBox.innerHTML = `
          <div style="display: flex; flex-direction: column; justify-content: space-between; height: 100%;">
            <div style="display: flex; flex-direction: column; gap: 12px;">
              <div style="display: flex; align-items: center; justify-content: space-between; border-bottom: 1px solid rgba(255,255,255,0.06); padding-bottom: 10px;">
                <h4 style="font-size: 13px; font-weight: 800; color: #ffffff; margin: 0;">Safaricom M-Pesa PIN</h4>
                <span style="font-size: 9px; color: var(--brand-warning); font-family: var(--font-mono); font-weight: 700;">LIPA NA M-PESA STK</span>
              </div>

              <p style="font-size: 11px; color: rgba(255,255,255,0.5); line-height: 1.4;">
                Enter your 4-digit M-Pesa Wallet PIN code to authorize checkout payment for <strong>${planCost}</strong>.
              </p>

              <!-- Star visual PIN placeholder -->
              <div style="display: flex; justify-content: center; gap: 16px; margin: 16px 0;">
                <div style="width: 14px; height: 14px; border-radius: 50%; border: 2px solid rgba(255,255,255,0.2); background: ${simState.userInputs.mpesaPin.length >= 1 ? 'var(--brand-warning)' : 'transparent'};"></div>
                <div style="width: 14px; height: 14px; border-radius: 50%; border: 2px solid rgba(255,255,255,0.2); background: ${simState.userInputs.mpesaPin.length >= 2 ? 'var(--brand-warning)' : 'transparent'};"></div>
                <div style="width: 14px; height: 14px; border-radius: 50%; border: 2px solid rgba(255,255,255,0.2); background: ${simState.userInputs.mpesaPin.length >= 3 ? 'var(--brand-warning)' : 'transparent'};"></div>
                <div style="width: 14px; height: 14px; border-radius: 50%; border: 2px solid rgba(255,255,255,0.2); background: ${simState.userInputs.mpesaPin.length >= 4 ? 'var(--brand-warning)' : 'transparent'};"></div>
              </div>

              <!-- Phone Keyboard numeric UI -->
              <div class="phone-keyboard-grid">
                <button class="key-btn" data-val="1">1</button>
                <button class="key-btn" data-val="2">2</button>
                <button class="key-btn" data-val="3">3</button>
                <button class="key-btn" data-val="4">4</button>
                <button class="key-btn" data-val="5">5</button>
                <button class="key-btn" data-val="6">6</button>
                <button class="key-btn" data-val="7">7</button>
                <button class="key-btn" data-val="8">8</button>
                <button class="key-btn" data-val="9">9</button>
                <button class="key-btn" style="background: rgba(255,42,75,0.1); color: var(--brand-primary);" id="btn-pin-clear">C</button>
                <button class="key-btn" data-val="0">0</button>
                <button class="key-btn" style="background: rgba(16,185,129,0.1); color: var(--brand-success);" id="btn-pin-submit">OK</button>
              </div>
            </div>
          </div>
        `;

        // PIN Button Click handling
        phoneBox.querySelectorAll(".phone-keyboard-grid .key-btn[data-val]").forEach(btn => {
          btn.addEventListener("click", () => {
            const digit = btn.getAttribute("data-val");
            if (simState.userInputs.mpesaPin.length < 4) {
              simState.userInputs.mpesaPin += digit;
              renderPhoneScreen();
            }
          });
        });

        phoneBox.querySelector("#btn-pin-clear").addEventListener("click", () => {
          simState.userInputs.mpesaPin = "";
          renderPhoneScreen();
        });

        phoneBox.querySelector("#btn-pin-submit").addEventListener("click", () => {
          if (simState.userInputs.mpesaPin.length < 4) {
            alert("Please enter full 4-digit PIN.");
            return;
          }

          simState.phoneStep = "processing";
          renderPhoneScreen();
          simState.tvState = "processing";
          renderTVScreen();

          addTelemetry("Safaricom API", "Customer entered secure PIN key on handset...");

          // Mocking M-Pesa Safaricom callback push
          setTimeout(() => {
            addTelemetry("Safaricom Webhook", "Lipa Na M-Pesa callback processed.");
            addTelemetry("Safaricom Webhook", "ResultCode: 0 (Transaction Successful). Ref: MP_REF_99882X.");
            addTelemetry("FIREBASE DB", "Write session status: 'premium' (upgraded active subscription).");
          }, 900);

          setTimeout(() => {
            store.activateFreeTrial(); // Upgrade user tier locally
            simState.phoneStep = "success";
            simState.tvState = "success";
            renderSimulator();
            triggerTVCheckmark("M-PESA WALLET PAYMENT AUTHORIZED!", `M-Pesa callback handshake processed. Lipa Na M-Pesa reference: MP_REF_99882X. TV upgraded to VIP Gold.`);
          }, 1800);
        });
      }

      else if (simState.phoneStep === "processing") {
        phoneBox.innerHTML = `
          <div style="text-align: center; display: flex; flex-direction: column; align-items: center; justify-content: center; flex-grow: 1; gap: 16px;">
            <div style="border: 3px solid rgba(245,158,11,0.15); border-top: 3px solid var(--brand-warning); border-radius: 50%; width: 40px; height: 40px; animation: banner-flash 1s infinite linear;"></div>
            <h4 style="font-size: 14px; font-weight: 800; color: #ffffff;">Processing Checkout Pipeline</h4>
            <p style="font-size: 11px; color: rgba(255,255,255,0.45); text-align: center; max-width: 220px; line-height: 1.4;">
              Syncing payment details with server gateway. Polling database for secure state upgrades.
            </p>
          </div>
        `;
      }

      else if (simState.phoneStep === "success") {
        phoneBox.innerHTML = `
          <div style="text-align: center; display: flex; flex-direction: column; align-items: center; justify-content: center; flex-grow: 1; gap: 14px;">
            <span style="font-size: 44px;">👑</span>
            <h4 style="font-size: 16px; font-weight: 800; color: var(--brand-warning);">VIP Gold Active</h4>
            <p style="font-size: 11.5px; color: rgba(255,255,255,0.5); text-align: center; line-height: 1.4;">
              Billing validation completed! TV subscriber session upgraded to VIP Gold instantly.
            </p>
            <div style="background: rgba(245,158,11,0.06); border: 1px solid rgba(245,158,11,0.15); border-radius: 10px; padding: 10px 14px; width: 100%; text-align: left; font-size: 11px; color: rgba(255,255,255,0.7); display: flex; flex-direction: column; gap: 4px;">
              <div>• Gateway: <strong style="color: #ffffff;">Safaricom Daraja STK</strong></div>
              <div>• Amount: <strong style="color: var(--brand-warning)">${planCost} USD</strong></div>
              <div>• Sync status: <strong style="color: var(--brand-success)">Active / Live</strong></div>
            </div>
          </div>
        `;
      }
    }

    // C. PHONE FLOW: DEVICE PAIRING
    else if (simState.activeFlow === "pairing") {
      if (simState.phoneStep === "start") {
        phoneBox.innerHTML = `
          <div style="display: flex; flex-direction: column; justify-content: space-between; height: 100%;">
            <div style="display: flex; flex-direction: column; gap: 14px;">
              <div style="display: flex; align-items: center; gap: 8px; border-bottom: 1px solid rgba(255,255,255,0.06); padding-bottom: 10px;">
                <span style="font-size: 18px;">🔌</span>
                <div>
                  <h4 style="font-size: 13px; font-weight: 800; color: #ffffff; margin: 0;">Coupling Integration</h4>
                  <span style="font-size: 9px; color: var(--brand-secondary); font-family: var(--font-mono); font-weight: 700;">IPTV DECODER / APPLE TV SYNC</span>
                </div>
              </div>

              <p style="font-size: 11.5px; color: rgba(255,255,255,0.5); line-height: 1.4;">
                Select activation method to pair the TV. IPTV box or IPTV decoders without a camera can type the 6-character code fallback at <strong>gntv.com/activate</strong> instead.
              </p>

              <div style="display: flex; flex-direction: column; gap: 10px; margin-top: 10px;">
                <!-- Choice 1: Camera Scan -->
                <button id="btn-pair-scan" class="glass-card" style="padding: 12px; border-radius: 8px; cursor: pointer; text-align: left; background: rgba(255,255,255,0.02); display: flex; align-items: center; gap: 12px; width: 100%;">
                  <span style="font-size: 20px;">📷</span>
                  <div style="flex: 1;">
                    <strong style="font-size: 12px; color: #ffffff; display: block;">Simulate Camera QR Scan</strong>
                    <span style="font-size: 9px; color: rgba(255,255,255,0.4);">Instantly pair with dynamic codes</span>
                  </div>
                </button>

                <!-- Choice 2: Code activation -->
                <button id="btn-pair-code" class="glass-card" style="padding: 12px; border-radius: 8px; cursor: pointer; text-align: left; background: rgba(255,255,255,0.02); display: flex; align-items: center; gap: 12px; width: 100%;">
                  <span style="font-size: 20px;">⌨️</span>
                  <div style="flex: 1;">
                    <strong style="font-size: 12px; color: #ffffff; display: block;">Enter 6-Character Fallback Code</strong>
                    <span style="font-size: 9px; color: rgba(255,255,255,0.4);">gntv.com/activate manual coupling</span>
                  </div>
                </button>
              </div>
            </div>
          </div>
        `;

        phoneBox.querySelector("#btn-pair-scan").addEventListener("click", () => {
          simState.phoneStep = "scanning";
          renderPhoneScreen();

          addTelemetry("CAMERA", "Camera scan initializing for set-top box activation...");

          setTimeout(() => {
            const statusText = phoneBox.querySelector("#scanner-status");
            if (statusText) statusText.textContent = "PAIRING CODE FOUND...";
            addTelemetry("DECODER", `Found dynamic pair string: ${simState.pairingCode}`);
          }, 600);

          setTimeout(() => {
            simState.phoneStep = "processing";
            simState.tvState = "processing";
            renderSimulator();
            addTelemetry("FIREBASE", "Pairing session matched. Upstream server authorization validated.");
          }, 1200);

          setTimeout(() => {
            simState.phoneStep = "success";
            simState.tvState = "success";
            renderSimulator();
            triggerTVCheckmark("IPTV DEVICE PAIRED SUCCESSFUL!", "Decoders synchronized successfully via QR scan! Standard streaming downstream feed secured.");
          }, 2400);
        });

        phoneBox.querySelector("#btn-pair-code").addEventListener("click", () => {
          simState.phoneStep = "input";
          renderPhoneScreen();
        });
      }

      else if (simState.phoneStep === "scanning") {
        phoneBox.innerHTML = `
          <div style="display: flex; flex-direction: column; justify-content: center; height: 100%;">
            <div style="display: flex; flex-direction: column; gap: 12px; flex-grow: 1;">
              <div style="display: flex; align-items: center; gap: 8px; border-bottom: 1px solid rgba(255,255,255,0.06); padding-bottom: 10px;">
                <span style="font-size: 16px;">📷</span>
                <div>
                  <h4 style="font-size: 13px; font-weight: 800; color: #ffffff; margin: 0;">Coupling Integration</h4>
                  <span style="font-size: 8.5px; color: var(--brand-secondary); font-family: var(--font-mono); font-weight: 700;">SCAN IN PROGRESS</span>
                </div>
              </div>

              <div class="scanner-viewfinder">
                <div class="scanner-corner top-left" style="border-color:var(--brand-secondary)"></div>
                <div class="scanner-corner top-right" style="border-color:var(--brand-secondary)"></div>
                <div class="scanner-corner bottom-left" style="border-color:var(--brand-secondary)"></div>
                <div class="scanner-corner bottom-right" style="border-color:var(--brand-secondary)"></div>
                <div class="scanner-laser-line" style="background:linear-gradient(90deg, transparent, var(--brand-secondary), transparent); box-shadow: 0 0 10px var(--brand-secondary);"></div>
                <span class="scanner-status-text" id="scanner-status" style="color:var(--brand-secondary); text-shadow: 0 0 8px rgba(6,182,212,0.6)">SYNCING RECEIVER...</span>
              </div>

              <p style="font-size: 11px; color: rgba(255,255,255,0.5); text-align: center; margin-top: 6px; line-height: 1.4;">
                Resolving dynamic decoder sync targets...
              </p>
            </div>
          </div>
        `;
      }

      else if (simState.phoneStep === "input") {
        phoneBox.innerHTML = `
          <div style="display: flex; flex-direction: column; justify-content: space-between; height: 100%;">
            <div style="display: flex; flex-direction: column; gap: 12px;">
              <div style="display: flex; align-items: center; gap: 8px; border-bottom: 1px solid rgba(255,255,255,0.06); padding-bottom: 10px;">
                <span style="font-size: 18px;">⌨️</span>
                <div>
                  <h4 style="font-size: 13px; font-weight: 800; color: #ffffff; margin: 0;">gntv.com/activate Manual Auth</h4>
                  <span style="font-size: 9px; color: var(--brand-secondary); font-family: var(--font-mono); font-weight: 700;">ALPHANUMERIC PAIRING GRID</span>
                </div>
              </div>

              <p style="font-size: 11.5px; color: rgba(255,255,255,0.5); line-height: 1.4;">
                Enter the 6-character activation code showing on your Smart TV screen (e.g. <strong>${simState.pairingCode}</strong>).
              </p>

              <div style="display: flex; flex-direction: column; gap: 6px; margin-top: 10px;">
                <label style="font-size: 9.5px; font-weight: 800; color: rgba(255,255,255,0.4); text-transform: uppercase;">6-Character Code</label>
                <input type="text" id="phone-pair-input-code" placeholder="GN-XXXX" style="background: rgba(255,255,255,0.04); border: 1px solid rgba(255,255,255,0.08); padding: 12px 14px; border-radius: 8px; font-size: 18px; font-family: var(--font-mono); font-weight: 800; letter-spacing: 2px; text-transform: uppercase; color: #ffffff; text-align: center; outline: none;" value="${simState.pairingCode}">
              </div>
            </div>

            <button id="btn-submit-pair-code" style="background: var(--brand-primary); border: none; padding: 14px; border-radius: 12px; color: #ffffff; font-weight: 700; font-size: 13px; cursor: pointer; box-shadow: 0 4px 15px var(--brand-primary-glow);">
              ACTIVATE IPTV SCREEN 🚀
            </button>
          </div>
        `;

        phoneBox.querySelector("#btn-submit-pair-code").addEventListener("click", () => {
          const typed = phoneBox.querySelector("#phone-pair-input-code").value.trim().toUpperCase();
          if (typed !== simState.pairingCode) {
            alert(`Code does not match TV! Please type: ${simState.pairingCode}`);
            return;
          }

          simState.phoneStep = "processing";
          renderPhoneScreen();
          simState.tvState = "processing";
          renderTVScreen();

          addTelemetry("SYSTEM", `User entered pairing code GN-${simState.pairingCode}...`);

          setTimeout(() => {
            addTelemetry("FIREBASE", `Verified manual code alignment. Establishing device token session ID SES_5521...`);
            simState.phoneStep = "success";
            simState.tvState = "success";
            renderSimulator();
            triggerTVCheckmark("MANUAL CODE PAIRING SECURED!", `Activation code matches server record [${simState.pairingCode}]. TV decoder unlocked.`);
          }, 1500);
        });
      }

      else if (simState.phoneStep === "processing") {
        phoneBox.innerHTML = `
          <div style="text-align: center; display: flex; flex-direction: column; align-items: center; justify-content: center; flex-grow: 1; gap: 16px;">
            <div style="border: 3px solid rgba(6,182,212,0.15); border-top: 3px solid var(--brand-secondary); border-radius: 50%; width: 40px; height: 40px; animation: banner-flash 1s infinite linear;"></div>
            <h4 style="font-size: 14px; font-weight: 800; color: #ffffff;">Decoder Handshake Active</h4>
            <p style="font-size: 11px; color: rgba(255,255,255,0.45); text-align: center; max-width: 220px; line-height: 1.4;">
              Syncing dynamic socket values between Mobile remote and Set-Top Box.
            </p>
          </div>
        `;
      }

      else if (simState.phoneStep === "success") {
        phoneBox.innerHTML = `
          <div style="text-align: center; display: flex; flex-direction: column; align-items: center; justify-content: center; flex-grow: 1; gap: 14px;">
            <span style="font-size: 44px;">🔌</span>
            <h4 style="font-size: 16px; font-weight: 800; color: var(--brand-success);">IPTV Device Synced</h4>
            <p style="font-size: 11.5px; color: rgba(255,255,255,0.5); text-align: center; line-height: 1.4;">
              Decoder pairing complete. Set-top box and phone profile matched with ID <strong>${simState.pairingCode}</strong>.
            </p>
            <div style="background: rgba(6,182,212,0.06); border: 1px solid rgba(6,182,212,0.15); border-radius: 10px; padding: 10px 14px; width: 100%; text-align: left; font-size: 11px; color: rgba(255,255,255,0.7); display: flex; flex-direction: column; gap: 4px;">
              <div>• Active device: <strong style="color: #ffffff;">Set-Top Box (IPTV-BOX)</strong></div>
              <div>• Sync Code: <strong style="color: var(--brand-secondary)">${simState.pairingCode}</strong></div>
              <div>• Channel: <strong style="color: var(--brand-success)">GNTV DIGITAL, ALL EVERYWHERE Downlink Feed</strong></div>
            </div>
          </div>
        `;
      }
    }

    // D. PHONE FLOW: PASSWORD-FREE LOGIN
    else if (simState.activeFlow === "login") {
      if (simState.phoneStep === "start") {
        phoneBox.innerHTML = `
          <div style="display: flex; flex-direction: column; justify-content: space-between; height: 100%;">
            <div style="display: flex; flex-direction: column; gap: 12px; flex-grow: 1;">
              <div style="display: flex; align-items: center; gap: 8px; border-bottom: 1px solid rgba(255,255,255,0.06); padding-bottom: 10px;">
                <span style="font-size: 16px;">📷</span>
                <div>
                  <h4 style="font-size: 13px; font-weight: 800; color: #ffffff; margin: 0;">WhatsApp-style Login</h4>
                  <span style="font-size: 8.5px; color: var(--brand-primary); font-family: var(--font-mono); font-weight: 700;">AWAITING SCAN</span>
                </div>
              </div>

              <div class="scanner-viewfinder">
                <div class="scanner-corner top-left"></div>
                <div class="scanner-corner top-right"></div>
                <div class="scanner-corner bottom-left"></div>
                <div class="scanner-corner bottom-right"></div>
                <div class="scanner-laser-line"></div>
                <span class="scanner-status-text" id="scanner-status">READY TO SCAN</span>
              </div>

              <p style="font-size: 11px; color: rgba(255,255,255,0.5); text-align: center; margin-top: 6px; line-height: 1.4;">
                Aim camera at TV login code.
              </p>
            </div>

            <button id="btn-simulate-scan" style="background: var(--brand-primary); border: none; padding: 14px; border-radius: 12px; color: #ffffff; font-weight: 700; font-size: 13px; cursor: pointer; box-shadow: 0 4px 15px var(--brand-primary-glow);">
              SCAN LOGIN QR ⚡
            </button>
          </div>
        `;
        phoneBox.querySelector("#btn-simulate-scan").addEventListener("click", () => {
          simState.phoneStep = "scanning";
          renderPhoneScreen();

          addTelemetry("CAMERA", "Camera scan triggered. Seeking login matrix session...");

          setTimeout(() => {
            const statusText = phoneBox.querySelector("#scanner-status");
            if (statusText) statusText.textContent = "DECODING CREDENTIALS...";
            addTelemetry("DECODER", "Read login verification token successfully.");
          }, 600);

          setTimeout(() => {
            simState.phoneStep = "input";
            renderPhoneScreen();
            addTelemetry("SYSTEM", "Requesting profile verification from registered user database...");
          }, 1200);
        });
      }

      else if (simState.phoneStep === "scanning") {
        phoneBox.innerHTML = `
          <div style="display: flex; flex-direction: column; justify-content: center; height: 100%;">
            <div style="display: flex; flex-direction: column; gap: 12px; flex-grow: 1;">
              <div style="display: flex; align-items: center; gap: 8px; border-bottom: 1px solid rgba(255,255,255,0.06); padding-bottom: 10px;">
                <span style="font-size: 16px;">📷</span>
                <div>
                  <h4 style="font-size: 13px; font-weight: 800; color: #ffffff; margin: 0;">WhatsApp-style Login</h4>
                  <span style="font-size: 8.5px; color: var(--brand-primary); font-family: var(--font-mono); font-weight: 700;">SCAN IN PROGRESS</span>
                </div>
              </div>

              <div class="scanner-viewfinder">
                <div class="scanner-corner top-left"></div>
                <div class="scanner-corner top-right"></div>
                <div class="scanner-corner bottom-left"></div>
                <div class="scanner-corner bottom-right"></div>
                <div class="scanner-laser-line"></div>
                <span class="scanner-status-text" id="scanner-status">VALIDATING QR SEED...</span>
              </div>

              <p style="font-size: 11px; color: rgba(255,255,255,0.5); text-align: center; margin-top: 6px; line-height: 1.4;">
                Hold steady. Handshaking credentials with core database...
              </p>
            </div>
          </div>
        `;
      }

      else if (simState.phoneStep === "input") {
        // Find existing authenticated user or fallback
        const existingUser = store.getState("user") || { name: "Cumar Cabdi", email: "cumar@gntv.com" };
        phoneBox.innerHTML = `
          <div style="display: flex; flex-direction: column; justify-content: space-between; height: 100%;">
            <div style="display: flex; flex-direction: column; gap: 12px;">
              <div style="display: flex; align-items: center; gap: 8px; border-bottom: 1px solid rgba(255,255,255,0.06); padding-bottom: 10px;">
                <span style="font-size: 18px;">🔐</span>
                <div>
                  <h4 style="font-size: 13px; font-weight: 800; color: #ffffff; margin: 0;">Smart TV Auth Request</h4>
                  <span style="font-size: 9px; color: var(--brand-primary); font-family: var(--font-mono); font-weight: 700;">WHATSAPP STYLE TOKEN MATCHUP</span>
                </div>
              </div>

              <p style="font-size: 11.5px; color: rgba(255,255,255,0.5); line-height: 1.4;">
                We detected a request to log in on a Smart TV from IP <strong>192.168.1.105</strong>. Click Authorize to synchronize credentials.
              </p>

              <div style="background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.06); padding: 12px; border-radius: 10px; display: flex; align-items: center; gap: 10px; margin-top: 10px;">
                <span style="font-size: 24px;">👤</span>
                <div>
                  <strong style="font-size: 13px; color: #ffffff; display: block;">${existingUser.name}</strong>
                  <span style="font-size: 10px; color: rgba(255,255,255,0.5);">${existingUser.email}</span>
                </div>
              </div>
            </div>

            <button id="btn-submit-authorize" style="background: var(--brand-primary); border: none; padding: 14px; border-radius: 12px; color: #ffffff; font-weight: 700; font-size: 13px; cursor: pointer; box-shadow: 0 4px 15px var(--brand-primary-glow);">
              AUTHORIZE SMART TV LOGIN 🔑
            </button>
          </div>
        `;

        phoneBox.querySelector("#btn-submit-authorize").addEventListener("click", () => {
          simState.phoneStep = "processing";
          renderPhoneScreen();
          simState.tvState = "processing";
          renderTVScreen();

          addTelemetry("AUTH", `Broadcasting signed authentication payload for user ${existingUser.name}...`);

          setTimeout(() => {
            // Write coordinates into state to authorize TV
            store.signIn(existingUser.email, existingUser.name);

            simState.phoneStep = "success";
            simState.tvState = "success";
            renderSimulator();
            triggerTVCheckmark("PASSWORD-FREE AUTH SECURED!", `Smart TV authorized as subscriber ${existingUser.name} within 2 seconds. No keyboard password typing needed.`);
          }, 1400);
        });
      }

      else if (simState.phoneStep === "processing") {
        phoneBox.innerHTML = `
          <div style="text-align: center; display: flex; flex-direction: column; align-items: center; justify-content: center; flex-grow: 1; gap: 16px;">
            <div style="border: 3px solid rgba(255,42,75,0.15); border-top: 3px solid var(--brand-primary); border-radius: 50%; width: 40px; height: 40px; animation: banner-flash 1s infinite linear;"></div>
            <h4 style="font-size: 14px; font-weight: 800; color: #ffffff;">Pushing Signed Session</h4>
            <p style="font-size: 11px; color: rgba(255,255,255,0.45); text-align: center; max-width: 220px; line-height: 1.4;">
              Syncing profile credentials via WebSockets socket. Authorizing secure key exchange.
            </p>
          </div>
        `;
      }

      else if (simState.phoneStep === "success") {
        phoneBox.innerHTML = `
          <div style="text-align: center; display: flex; flex-direction: column; align-items: center; justify-content: center; flex-grow: 1; gap: 14px;">
            <span style="font-size: 44px;">🔐</span>
            <h4 style="font-size: 16px; font-weight: 800; color: var(--brand-success);">Smart TV Authorized</h4>
            <p style="font-size: 11.5px; color: rgba(255,255,255,0.5); text-align: center; line-height: 1.4;">
              Credentials synchronized! Smart TV shell logged in. Enjoy your streaming dashboard.
            </p>
            <div style="background: rgba(16,185,129,0.06); border: 1px solid rgba(16,185,129,0.15); border-radius: 10px; padding: 10px 14px; width: 100%; text-align: left; font-size: 11px; color: rgba(255,255,255,0.7); display: flex; flex-direction: column; gap: 4px;">
              <div>• Handshake: <strong style="color: #ffffff;">WhatsApp Web Pattern</strong></div>
              <div>• Sync time: <strong style="color: var(--brand-secondary)">&lt; 2.0s</strong></div>
              <div>• Status: <strong style="color: var(--brand-success)">Authorized</strong></div>
            </div>
          </div>
        `;
      }
    }
  }

  // Triggers the Apple TV style overlay checkout success checkmark
  const triggerTVCheckmark = (title, desc) => {
    const layer = container.querySelector("#tv-success-layer");
    const titleEl = container.querySelector("#tv-success-title");
    const descEl = container.querySelector("#tv-success-desc");

    if (layer && titleEl && descEl) {
      titleEl.textContent = title;
      descEl.textContent = desc;
      layer.classList.add("active");

      // Stop active timer
      if (simState.countdownTimer) {
        clearInterval(simState.countdownTimer);
        simState.countdownTimer = null;
      }
    }
  };

  // Boot UI layout
  renderLayout();

  // Return Destructor Hook to clean up active timers and interval triggers
  return () => {
    if (simState.countdownTimer) {
      clearInterval(simState.countdownTimer);
      simState.countdownTimer = null;
    }
  };
}
