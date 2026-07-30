import { store } from "../../../shared/src/state.js";

export function initCreateWorkflow(container) {
  let step = 1;
  let uploadProgress = 0;
  let uploadInterval = null;
  let aiLogs = [];
  let aiLogIndex = 0;
  let aiTimeout = null;
  let videoFileName = "";

  const platforms = [
    { id: "youtube", name: "YouTube", icon: "🔴", connected: true },
    { id: "facebook", name: "Facebook", icon: "🔵", connected: true },
    { id: "tiktok", name: "TikTok", icon: "🎵", connected: true },
    { id: "instagram", name: "Instagram", icon: "📸", connected: true },
    { id: "ott", name: "GNTV DIGITAL, ALL EVERYWHERE OTT", icon: "🌐", connected: true },
    { id: "iptv", name: "IPTV Channel", icon: "📡", connected: true }
  ];

  const aiProcessingSteps = [
    "Initializing GNTV DIGITAL, ALL EVERYWHERE AI Ingestion Core...",
    "Scanning audio track for Somali dialogue transcription...",
    "Applying loudness normalization (EBU R128 compliance checks)...",
    "Generating multi-lingual sub-rip tracks (Somali, Arabic, English)...",
    "Optimizing video bandwidth (HEVC/H.265 compression for mobile networks)...",
    "Securing edge CDN endpoints for live synchronization...",
    "Ingestion and analysis complete! Content verified safe for broadcast."
  ];

  const render = () => {
    container.innerHTML = `
      <div class="create-workflow-container glass-card" style="padding: 40px; border-radius: 20px; max-width: 800px; margin: 40px auto; background: rgba(10, 10, 15, 0.7); border: 1px solid rgba(255, 255, 255, 0.08); box-shadow: 0 20px 50px rgba(0, 0, 0, 0.5); font-family: var(--font-sans); color: #fff;">

        <!-- Header -->
        <div style="text-align: center; margin-bottom: 40px;">
          <span style="font-size: 40px;">📤</span>
          <h2 style="font-size: 28px; font-weight: 850; letter-spacing: -1px; margin: 10px 0 6px 0; background: linear-gradient(135deg, #ffffff 0%, #a1a1aa 100%); -webkit-background-clip: text; -webkit-text-fill-color: transparent;">Redeen Muuqaalkaaga / Upload & Distribute</h2>
          <p style="color: rgba(255, 255, 255, 0.5); font-size: 14px; max-width: 500px; margin: 0 auto; line-height: 1.5;">
            Redeen hal mar, ka dibna u dir dhammaan baraha bulshada iyo satelite-ka caalamiga ah ee GNTV DIGITAL, ALL EVERYWHERE.
          </p>
        </div>

        <!-- Stepper Indicator -->
        <div style="display: flex; justify-content: space-between; align-items: center; position: relative; margin-bottom: 40px; padding: 0 20px;">
          <div style="position: absolute; top: 15px; left: 40px; right: 40px; height: 2px; background: rgba(255,255,255,0.08); z-index: 1;">
            <div style="width: ${((step - 1) / 3) * 100}%; height: 100%; background: var(--brand-primary); transition: width 0.4s ease; box-shadow: 0 0 10px var(--brand-primary-glow);"></div>
          </div>

          ${[1, 2, 3, 4].map(s => {
            const isActive = s <= step;
            const isCurrent = s === step;
            const stepTitles = ["Dheji", "AI Processing", "Faafi", "Daabacan"];
            return `
              <div style="z-index: 2; display: flex; flex-direction: column; align-items: center; gap: 8px;">
                <div style="width: 32px; height: 32px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 13px; font-weight: 800; border: 2px solid ${isCurrent ? 'var(--brand-primary)' : isActive ? 'var(--brand-primary)' : 'rgba(255,255,255,0.1)'}; background: ${isActive ? 'var(--brand-primary)' : '#0c0c12'}; color: ${isActive ? '#fff' : 'rgba(255,255,255,0.4)'}; transition: all 0.3s; box-shadow: ${isCurrent ? '0 0 15px var(--brand-primary-glow)' : 'none'};">
                  ${s < step ? '✓' : s}
                </div>
                <span style="font-size: 11px; font-weight: 700; color: ${isActive ? '#fff' : 'rgba(255,255,255,0.4)'}; text-transform: uppercase; letter-spacing: 0.5px;">${stepTitles[s-1]}</span>
              </div>
            `;
          }).join('')}
        </div>

        <!-- Step Content Wrapper -->
        <div class="step-content-area" style="min-height: 260px;">
          ${renderStepContent()}
        </div>

        <!-- Action Footer -->
        <div style="display: flex; justify-content: flex-end; gap: 12px; margin-top: 32px; padding-top: 20px; border-top: 1px solid rgba(255,255,255,0.06);">
          ${renderActionButtons()}
        </div>
      </div>
    `;

    bindEvents();
  };

  const renderStepContent = () => {
    if (step === 1) {
      return `
        <!-- Step 1: File Ingestion -->
        <div id="drop-zone" style="border: 2px dashed rgba(255, 255, 255, 0.15); border-radius: 12px; padding: 40px 20px; text-align: center; background: rgba(255,255,255,0.02); cursor: pointer; transition: all 0.3s;" onmouseover="this.style.borderColor='var(--brand-primary)';this.style.background='rgba(255,255,255,0.04)'" onmouseout="this.style.borderColor='rgba(255,255,255,0.15)';this.style.background='rgba(255,255,255,0.02)'">
          <input type="file" id="file-input" accept="video/*" style="display: none;" />
          <span style="font-size: 48px; display: block; margin-bottom: 12px; filter: drop-shadow(0 0 10px rgba(255,255,255,0.1));">🎬</span>
          <h3 style="font-size: 18px; font-weight: 800; margin-bottom: 4px;">Jiid oo halkan dhig faylka muuqaalka</h3>
          <p style="color: rgba(255,255,255,0.4); font-size: 13px; margin-bottom: 16px;">Ama riix si aad u hesho faylkaaga (MP4, MKV, MOV - ilaa 4GB)</p>
          <span style="font-family: var(--font-mono); font-size: 11px; background: rgba(255,255,255,0.08); padding: 4px 10px; border-radius: 4px; color: rgba(255,255,255,0.6);">Automatic AI metadata generation is enabled</span>
        </div>
      `;
    }

    if (step === 2) {
      return `
        <!-- Step 2: Upload & AI Processing -->
        <div style="display: flex; flex-direction: column; gap: 20px;">

          <!-- Upload Status bar -->
          <div class="glass-card" style="padding: 16px; border-radius: 12px; background: rgba(255,255,255,0.02); border: 1px solid rgba(255,255,255,0.05);">
            <div style="display: flex; justify-content: space-between; font-size: 13px; font-weight: 700; margin-bottom: 8px;">
              <span style="color: rgba(255,255,255,0.7); display: flex; align-items: center; gap: 8px;">
                <span class="upload-pulse-dot" style="width: 8px; height: 8px; border-radius: 50%; background: #0088ff; display: inline-block;"></span>
                Waxaa la soo dhejinayaa: ${videoFileName || 'video_stream.mp4'}
              </span>
              <span style="color: #0088ff;">${uploadProgress}%</span>
            </div>
            <div style="width: 100%; height: 6px; background: rgba(255,255,255,0.08); border-radius: 3px; overflow: hidden;">
              <div style="width: ${uploadProgress}%; height: 100%; background: linear-gradient(90deg, #0088ff 0%, #00d2ff 100%); transition: width 0.1s ease;"></div>
            </div>
          </div>

          <!-- AI Ingestion Logs Terminal -->
          <div>
            <h4 style="font-size: 12px; font-weight: 800; color: var(--brand-primary); text-transform: uppercase; margin-bottom: 8px; letter-spacing: 0.5px;">📡 AI Processing Logs</h4>
            <div style="background: rgba(0, 0, 0, 0.4); border: 1px solid rgba(255,255,255,0.08); border-radius: 8px; padding: 16px; font-family: var(--font-mono); font-size: 12px; height: 160px; overflow-y: auto; color: #a1a1aa; line-height: 1.6; display: flex; flex-direction: column; gap: 6px;">
              ${aiLogs.map((log, i) => `
                <div style="display: flex; gap: 8px;">
                  <span style="color: ${i === aiLogs.length - 1 ? 'var(--brand-primary)' : 'rgba(255,255,255,0.3)'}; font-weight: 800;">[${new Date().toLocaleTimeString()}]</span>
                  <span style="color: ${i === aiLogs.length - 1 ? '#ffffff' : '#a1a1aa'};">${log}</span>
                </div>
              `).join('')}
              ${uploadProgress < 100 || aiLogIndex < aiProcessingSteps.length ? `
                <div style="display: flex; align-items: center; gap: 8px; color: var(--brand-primary);" class="animate-pulse">
                  <span>➜</span>
                  <span style="font-weight: 700;">Processing stream telemetry chunks...</span>
                </div>
              ` : ''}
            </div>
          </div>
        </div>
      `;
    }

    if (step === 3) {
      return `
        <!-- Step 3: Choose Distribution -->
        <div>
          <h3 style="font-size: 16px; font-weight: 800; margin-bottom: 16px;">Dooro Halka Aad Rabto In Lagu Faafiyo / Distribution Channels</h3>

          <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 16px;">
            ${platforms.map(p => {
              const isSelected = p.connected;
              return `
                <div class="platform-card ${isSelected ? 'active' : ''}" data-platform-id="${p.id}" style="padding: 16px; border-radius: 12px; background: ${isSelected ? 'rgba(255, 42, 75, 0.05)' : 'rgba(255,255,255,0.02)'}; border: 1px solid ${isSelected ? 'var(--brand-primary)' : 'rgba(255,255,255,0.06)'}; cursor: pointer; transition: all 0.2s; display: flex; flex-direction: column; justify-content: space-between; height: 110px; position: relative;">
                  <div style="display: flex; justify-content: space-between; align-items: flex-start;">
                    <span style="font-size: 28px;">${p.icon}</span>
                    <span style="font-size: 12px; font-weight: 800; background: ${isSelected ? 'var(--brand-primary)' : 'rgba(255,255,255,0.05)'}; padding: 2px 8px; border-radius: 10px; color: #fff;">
                      ${isSelected ? 'Dhegay' : 'Ka xiran'}
                    </span>
                  </div>

                  <div>
                    <h4 style="font-size: 14px; font-weight: 800; margin: 0 0 2px 0;">${p.name}</h4>
                    <span style="font-size: 11px; color: rgba(255,255,255,0.4);">
                      ${p.id === 'iptv' ? 'Satelite relay' : p.id === 'ott' ? 'Global app VOD' : 'Social feed syncer'}
                    </span>
                  </div>
                </div>
              `;
            }).join('')}
          </div>
        </div>
      `;
    }

    if (step === 4) {
      return `
        <!-- Step 4: Published Success! -->
        <div style="text-align: center; padding: 20px 0;">
          <div style="width: 80px; height: 80px; border-radius: 50%; background: rgba(16, 185, 129, 0.1); border: 2px solid #10b981; display: flex; align-items: center; justify-content: center; margin: 0 auto 20px auto; font-size: 36px; box-shadow: 0 0 20px rgba(16, 185, 129, 0.3); animation: scaleUp 0.4s ease-out;">
            ✓
          </div>
          <h3 style="font-size: 22px; font-weight: 850; color: #ffffff; margin-bottom: 8px;">Muuqaalkaaga Si Fudud Ayaa Loo Daabacay!</h3>
          <p style="color: rgba(255,255,255,0.5); font-size: 14px; max-width: 500px; margin: 0 auto 24px auto; line-height: 1.5;">
            Ingestion complete. Your content is now actively streaming across connected platforms: YouTube, Facebook, TikTok, Instagram, GNTV DIGITAL, ALL EVERYWHERE OTT, and IPTV Satellite streams.
          </p>

          <div style="display: inline-flex; align-items: center; gap: 8px; background: rgba(255, 255, 255, 0.03); border: 1px solid rgba(255, 255, 255, 0.05); padding: 12px 24px; border-radius: 12px; text-align: left; font-size: 13px;">
            <span>📈</span>
            <div>
              <div style="font-weight: 700; color: #fff;">Performance Telemetry Ready</div>
              <div style="font-size: 11px; color: rgba(255,255,255,0.4); margin-top: 2px;">Track views and viewer retention in real-time.</div>
            </div>
          </div>
        </div>
      `;
    }
  };

  const renderActionButtons = () => {
    if (step === 1) {
      return `<button id="btn-next-step" disabled style="background: rgba(255,255,255,0.05); color: rgba(255,255,255,0.3); border: none; padding: 10px 24px; border-radius: 8px; font-weight: 700; font-size: 13px; cursor: not-allowed; transition: all 0.2s;">Guji Xiga (Next) ➔</button>`;
    }
    if (step === 2) {
      const isDone = uploadProgress === 100 && aiLogIndex >= aiProcessingSteps.length;
      return `
        <button id="btn-cancel-processing" style="background: transparent; border: 1px solid rgba(255,255,255,0.12); color: rgba(255,255,255,0.6); padding: 10px 20px; border-radius: 8px; font-weight: 700; font-size: 13px; cursor: pointer; transition: all 0.2s;">Jooji / Cancel</button>
        <button id="btn-next-step" ${!isDone ? 'disabled' : ''} style="background: ${isDone ? 'var(--brand-primary)' : 'rgba(255,255,255,0.05)'}; color: ${isDone ? '#fff' : 'rgba(255,255,255,0.3)'}; border: none; padding: 10px 24px; border-radius: 8px; font-weight: 700; font-size: 13px; cursor: ${isDone ? 'pointer' : 'not-allowed'}; transition: all 0.2s; box-shadow: ${isDone ? '0 4px 15px var(--brand-primary-glow)' : 'none'};">Guji Xiga (Next) ➔</button>
      `;
    }
    if (step === 3) {
      return `
        <button id="btn-prev-step" style="background: transparent; border: 1px solid rgba(255,255,255,0.12); color: rgba(255,255,255,0.6); padding: 10px 20px; border-radius: 8px; font-weight: 700; font-size: 13px; cursor: pointer; transition: all 0.2s;">◀ Dib U Noqo</button>
        <button id="btn-next-step" style="background: var(--brand-primary); color: #fff; border: none; padding: 10px 24px; border-radius: 8px; font-weight: 700; font-size: 13px; cursor: pointer; transition: all 0.2s; box-shadow: 0 4px 15px var(--brand-primary-glow);">Faafi / Publish 🚀</button>
      `;
    }
    if (step === 4) {
      return `
        <button id="btn-upload-more" style="background: transparent; border: 1px solid rgba(255,255,255,0.12); color: rgba(255,255,255,0.6); padding: 10px 20px; border-radius: 8px; font-weight: 700; font-size: 13px; cursor: pointer; transition: all 0.2s;">Soo Dheji Mid Kale</button>
        <button id="btn-go-analytics" style="background: var(--brand-primary); color: #fff; border: none; padding: 10px 24px; border-radius: 8px; font-weight: 700; font-size: 13px; cursor: pointer; transition: all 0.2s; box-shadow: 0 4px 15px var(--brand-primary-glow);">Eeg Analytics 📊</button>
      `;
    }
  };

  const startUploadSimulation = () => {
    uploadProgress = 0;
    aiLogs = ["Starting secure uplink session..."];
    aiLogIndex = 0;

    uploadInterval = setInterval(() => {
      uploadProgress += Math.floor(Math.random() * 8) + 3;
      if (uploadProgress >= 100) {
        uploadProgress = 100;
        clearInterval(uploadInterval);
      }
      render();
    }, 200);

    const triggerNextLog = () => {
      if (aiLogIndex < aiProcessingSteps.length) {
        aiLogs.push(aiProcessingSteps[aiLogIndex]);
        aiLogIndex++;
        render();
        aiTimeout = setTimeout(triggerNextLog, 1200 + Math.random() * 800);
      }
    };
    aiTimeout = setTimeout(triggerNextLog, 500);
  };

  const bindEvents = () => {
    // Step 1: Input events
    const dropZone = container.querySelector("#drop-zone");
    const fileInput = container.querySelector("#file-input");

    if (dropZone && fileInput) {
      dropZone.addEventListener("click", () => fileInput.click());

      fileInput.addEventListener("change", (e) => {
        if (e.target.files && e.target.files[0]) {
          videoFileName = e.target.files[0].name;
          step = 2;
          render();
          startUploadSimulation();
        }
      });

      // Drag and drop support
      dropZone.addEventListener("dragover", (e) => {
        e.preventDefault();
        dropZone.style.borderColor = "var(--brand-primary)";
      });
      dropZone.addEventListener("dragleave", () => {
        dropZone.style.borderColor = "rgba(255,255,255,0.15)";
      });
      dropZone.addEventListener("drop", (e) => {
        e.preventDefault();
        if (e.dataTransfer.files && e.dataTransfer.files[0]) {
          videoFileName = e.dataTransfer.files[0].name;
          step = 2;
          render();
          startUploadSimulation();
        }
      });
    }

    // Step 3: Platform card toggles
    const platformCards = container.querySelectorAll(".platform-card");
    platformCards.forEach(card => {
      card.addEventListener("click", () => {
        const id = card.getAttribute("data-platform-id");
        const match = platforms.find(p => p.id === id);
        if (match) {
          match.connected = !match.connected;
          render();
        }
      });
    });

    // Step Navigation buttons
    const nextBtn = container.querySelector("#btn-next-step");
    if (nextBtn) {
      nextBtn.addEventListener("click", () => {
        if (step < 4) {
          step++;
          render();
        }
      });
    }

    const prevBtn = container.querySelector("#btn-prev-step");
    if (prevBtn) {
      prevBtn.addEventListener("click", () => {
        if (step > 1) {
          step--;
          render();
        }
      });
    }

    const cancelBtn = container.querySelector("#btn-cancel-processing");
    if (cancelBtn) {
      cancelBtn.addEventListener("click", () => {
        clearInterval(uploadInterval);
        clearTimeout(aiTimeout);
        step = 1;
        uploadProgress = 0;
        aiLogs = [];
        aiLogIndex = 0;
        render();
      });
    }

    const uploadMoreBtn = container.querySelector("#btn-upload-more");
    if (uploadMoreBtn) {
      uploadMoreBtn.addEventListener("click", () => {
        step = 1;
        uploadProgress = 0;
        aiLogs = [];
        aiLogIndex = 0;
        videoFileName = "";
        render();
      });
    }

    const goAnalyticsBtn = container.querySelector("#btn-go-analytics");
    if (goAnalyticsBtn) {
      goAnalyticsBtn.addEventListener("click", () => {
        store.setState("activeTab", "analytics");
      });
    }
  };

  render();

  // Destructor/Cleanup handler
  return () => {
    clearInterval(uploadInterval);
    clearTimeout(aiTimeout);
  };
}
