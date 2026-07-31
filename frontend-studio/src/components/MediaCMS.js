import { store } from "../../../shared/src/state.js";
import { CHANNELS, VODS } from "../../../shared/src/utils/mockData.js";

export function initMediaCMS(container) {

  store.syncCmsWithBackend().catch(error => console.error("CMS synchronization failed", error));

  const renderCMS = () => {
    const user = store.getState("user") || { name: "Guest Viewer", email: "guest@gntv.com", role: "free" };
    const userRole = user.role || "free";

    // Build lists of items dynamically from the shared arrays
    const allItems = [
      ...CHANNELS.map(c => ({ id: c.id, type: "channel", title: c.name, category: "Live Feed", premium: false, presenter: "GNTV DIGITAL, ALL EVERYWHERE Team" })),
      ...VODS.map(v => ({ id: v.id, type: "vod", title: v.title, category: v.category, premium: v.premium, presenter: v.host }))
    ];

    container.innerHTML = `
      <div class="cms-wrapper glass-card">
        <div class="cms-header">
          <div style="display:flex; justify-content:space-between; align-items:center;">
            <div>
              <h2 class="section-title"><span class="icon">📁</span> GNTV DIGITAL, ALL EVERYWHERE Enterprise Content Management System (CMS)</h2>
              <p class="section-desc">Add, edit, or remove linear channels, on-demand archives, news articles, and shorts.</p>
            </div>
            <div class="cms-role-badge" style="background: var(--brand-primary); color: white; padding: 6px 12px; border-radius: 20px; font-size: 11px; font-weight: 850; letter-spacing: 0.5px;">
              ACTIVE ROLE: ${userRole.toUpperCase()}
            </div>
          </div>
        </div>

        <div class="cms-grid">
          <!-- Left: Drag-and-Drop + Add Item Form -->
          <div style="display: flex; flex-direction: column; gap: 20px;">

            <!-- Drag and Drop upload visual simulator -->
            <div class="cms-section-card">
              <h3>⚡ Express Media Asset Ingest</h3>
              <p class="section-desc">Drag and drop raw video files (.mp4, .mov, .mkv) to parse metadata and trigger auto-fill inputs.</p>

              <div class="cms-drop-zone" id="cms-drop-zone">
                <span class="drop-icon">📤</span>
                <span class="drop-text">Drag & Drop Media Files Here or Click to Browse</span>
                <span class="drop-subtext">Supports MP4, MOV, FLV up to 4 GB</span>

                <!-- Simulated Upload Progress Bar -->
                <div class="upload-progress-box" id="upload-progress-box" style="display: none; width: 85%; margin-top: 14px;">
                  <div style="display:flex; justify-content:space-between; font-size:10px; margin-bottom:4px; font-family:var(--font-mono); color:var(--brand-primary);">
                    <span id="upload-status-lbl">UPLOADING TRANSCODE SLICES...</span>
                    <span id="upload-pct-val">0%</span>
                  </div>
                  <div style="width:100%; height:4px; background:rgba(255,255,255,0.1); border-radius:2px; overflow:hidden;">
                    <div id="upload-progress-fill" style="width: 0%; height:100%; background:var(--brand-primary); transition: width 0.1s;"></div>
                  </div>
                </div>
              </div>
            </div>

            <!-- Ingest Form -->
            <div class="cms-section-card">
              <h3>📝 Asset Ingest Metadata Form</h3>

              <form class="cms-ingest-form" id="form-cms-add">
                <div class="form-row" style="display: grid; grid-template-columns: 1fr 1fr; gap: 14px;">
                  <div class="form-group">
                    <label for="cms-item-title">Title / Name</label>
                    <input type="text" id="cms-item-title" placeholder="e.g. Somali History Part 3" required>
                  </div>
                  <div class="form-group">
                    <label for="cms-item-type">Asset Type</label>
                    <select id="cms-item-type" required>
                      <option value="vod">Movie / Series (VOD)</option>
                      <option value="channel">Live Broadcast Channel</option>
                      <option value="news">News Article</option>
                      <option value="podcast">Podcast Audio Feed</option>
                      <option value="short">Short Video Clip</option>
                    </select>
                  </div>
                </div>

                <div class="form-row" style="display: grid; grid-template-columns: 1fr 1fr; gap: 14px; margin-top: 12px;">
                  <div class="form-group">
                    <label for="cms-item-category">Category / Genre</label>
                    <select id="cms-item-category" required>
                      <option value="News">News</option>
                      <option value="Sports">Sports</option>
                      <option value="Documentaries">Documentaries</option>
                      <option value="Entertainment">Entertainment</option>
                    </select>
                  </div>
                  <div class="form-group">
                    <label for="cms-item-presenter">Host / Presenter</label>
                    <input type="text" id="cms-item-presenter" placeholder="e.g. Layla Warsame" required value="GNTV DIGITAL, ALL EVERYWHERE Host">
                  </div>
                </div>

                <div class="form-row" style="display: grid; grid-template-columns: 1fr 1fr; gap: 14px; margin-top: 12px; align-items: center;">
                  <div class="form-group">
                    <label for="cms-item-duration">Duration</label>
                    <input type="text" id="cms-item-duration" placeholder="e.g. 45:10" value="45:00">
                  </div>
                  <div class="form-group" style="flex-direction: row; gap: 8px; margin-bottom: 0;">
                    <input type="checkbox" id="cms-item-premium" style="width:16px; height:16px; accent-color: var(--brand-primary);">
                    <label for="cms-item-premium" style="margin-bottom:0; font-weight:700;">Require Premium Access</label>
                  </div>
                </div>

                <div class="form-group" style="margin-top: 12px;">
                  <label for="cms-item-desc">Asset Outline / Description</label>
                  <textarea id="cms-item-desc" rows="3" placeholder="Enter full summary description for EPG guides and catalogue info..." required></textarea>
                </div>

                <button type="submit" class="cms-submit-btn">INGEST AND SAVE ASSET</button>
              </form>
            </div>

          </div>

          <!-- Right: Catalogue List -->
          <div class="cms-section-card catalogue-table-card">
            <h3>📂 Platform Media Catalogue (${allItems.length} items)</h3>
            <p class="section-desc">Active items broadcasted to users. Deleting an item removes it from home, EPG, and VOD lists.</p>

            <div class="cms-table-wrapper" style="overflow-x: auto; margin-top: 14px;">
              <table class="cms-table">
                <thead>
                  <tr>
                    <th>Type</th>
                    <th>Title</th>
                    <th>Genre</th>
                    <th>Presenter</th>
                    <th>Access</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  ${allItems.map(item => `
                    <tr>
                      <td>
                        <span class="type-icon">${item.type === 'channel' ? '📡' : '📼'}</span>
                        <span class="type-lbl" style="font-size:10px; font-weight:700; color:rgba(255,255,255,0.45); text-transform:uppercase;">${item.type}</span>
                      </td>
                      <td class="table-bold-title" style="max-width: 140px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${item.title}</td>
                      <td><span style="font-size: 10px; font-weight:700;">${item.category}</span></td>
                      <td style="color:rgba(255,255,255,0.6);">${item.presenter}</td>
                      <td>
                        <span style="font-size:9px; font-weight:850; padding:2px 6px; border-radius:4px; background:${item.premium ? 'rgba(245,158,11,0.15)' : 'rgba(255,255,255,0.06)'}; color:${item.premium ? '#f59e0b' : 'rgba(255,255,255,0.6)'};">
                          ${item.premium ? 'PREMIUM' : 'FREE'}
                        </span>
                      </td>
                      <td>
                        <button class="cms-delete-btn" data-id="${item.id}" data-type="${item.type}">✕ Delete</button>
                      </td>
                    </tr>
                  `).join("")}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </div>
    `;

    // Hook Form Ingestion
    const form = container.querySelector("#form-cms-add");
    form.addEventListener("submit", async (e) => {
      e.preventDefault();

      const title = container.querySelector("#cms-item-title").value.trim();
      const type = container.querySelector("#cms-item-type").value;
      const category = container.querySelector("#cms-item-category").value;
      const presenter = container.querySelector("#cms-item-presenter").value.trim();
      const duration = container.querySelector("#cms-item-duration").value.trim();
      const premium = container.querySelector("#cms-item-premium").checked;
      const description = container.querySelector("#cms-item-desc").value.trim();

      // Check role permissions:
      // Admin: everything.
      // Editor: everything.
      // Reporter: only "news" assets.
      // Producer: only "channel", "podcast", "short".
      let isPermitted = false;
      if (userRole === "admin" || userRole === "editor") {
        isPermitted = true;
      } else if (userRole === "reporter" && type === "news") {
        isPermitted = true;
      } else if (userRole === "producer" && (type === "channel" || type === "podcast" || type === "short")) {
        isPermitted = true;
      }

      if (!isPermitted) {
        alert(`❌ Permission Denied: Your role (${userRole.toUpperCase()}) does not have permission to ingest asset type "${type.toUpperCase()}".`);
        return;
      }

      const item = {
        title, type, category, presenter, duration, premium, description
      };

      try {
        await store.addCatalogItem(item);
        alert(`Success: "${title}" successfully ingested and saved into the content catalogue.`);
        form.reset();
        renderCMS();
      } catch (error) {
        alert(`CMS ingest failed: ${error.message}`);
      }
    });

    // Hook Delete Buttons
    container.querySelectorAll(".cms-delete-btn").forEach(btn => {
      btn.addEventListener("click", async () => {
        const id = btn.getAttribute("data-id");
        const type = btn.getAttribute("data-type");

        if (userRole !== "admin" && userRole !== "editor") {
          alert(`❌ Permission Denied: Your role (${userRole.toUpperCase()}) does not have permission to delete assets.`);
          return;
        }

        if (confirm("Are you sure you want to permanently delete this media asset?")) {
          try {
            await store.deleteCatalogItem(id, type);
            alert("✔️ Asset deleted from catalogue.");
            renderCMS();
          } catch (error) {
            alert(`CMS deletion failed: ${error.message}`);
          }
        }
      });
    });

    // Hook Drag and Drop upload visual simulator
    const dropZone = container.querySelector("#cms-drop-zone");
    const progressBox = container.querySelector("#upload-progress-box");
    const progressBar = container.querySelector("#upload-progress-fill");
    const progressPct = container.querySelector("#upload-pct-val");
    const progressStatus = container.querySelector("#upload-status-lbl");

    if (dropZone) {
      dropZone.addEventListener("dragover", (e) => {
        e.preventDefault();
        dropZone.classList.add("hover");
      });

      dropZone.addEventListener("dragleave", () => {
        dropZone.classList.remove("hover");
      });

      dropZone.addEventListener("drop", (e) => {
        e.preventDefault();
        dropZone.classList.remove("hover");

        const files = e.dataTransfer.files;
        if (files && files.length > 0) {
          const file = files[0];

          // Show progress bar
          progressBox.style.display = "block";
          let pct = 0;

          const interval = setInterval(() => {
            pct += 5;
            if (pct >= 100) {
              pct = 100;
              clearInterval(interval);
              progressStatus.textContent = "TRANSCODE COMPLETE // METADATA PARSED";

              // Auto fill form
              container.querySelector("#cms-item-title").value = file.name.substring(0, file.name.lastIndexOf('.')) || file.name;
              container.querySelector("#cms-item-desc").value = `Simulated automated upload of file "${file.name}". Size: ${(file.size / 1024 / 1024).toFixed(1)} MB. Type: ${file.type || 'video/mp4'}. Uploaded on ${new Date().toLocaleDateString()}.`;

              setTimeout(() => {
                progressBox.style.display = "none";
                progressBar.style.width = "0%";
                progressPct.textContent = "0%";
                progressStatus.textContent = "UPLOADING TRANSCODE SLICES...";
              }, 1200);
            }
            progressBar.style.width = `${pct}%`;
            progressPct.textContent = `${pct}%`;
          }, 80);
        }
      });
    }
  };

  renderCMS();

  // Listen to catalog updates
  const unsubCatalog = store.subscribe("catalogVods", renderCMS);

  return () => {
    unsubCatalog();
  };
}
