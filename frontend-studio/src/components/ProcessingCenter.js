import { store } from "../../../shared/src/state.js";

export function initProcessingCenter(container) {
  let activeTab = "dashboard"; // dashboard, active, fleet, utilization, queues, manifests, thumbnails, timeline, retries, failures, performance
  let simulationInterval = null;
  let systemClockInterval = null;
  let apiConnected = false;
  let isRefreshing = false;
  let reconnectTick = 0;
  const apiBase = import.meta.env.VITE_API_URL || "http://localhost:8000";

  const processingRequest = async (path, options = {}) => {
    const token = localStorage.getItem("gntv_auth_token");
    if (!token) throw new Error("Operator authentication is required");
    const response = await fetch(`${apiBase}/api/v1/processing${path}`, {
      ...options,
      headers: {
        "Content-Type": "application/json",
        "Authorization": `Bearer ${token}`,
        ...(options.headers || {})
      }
    });
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      throw new Error(body?.detail?.message || `Processing API returned ${response.status}`);
    }
    return response.json();
  };

  // Real-time telemetry metrics
  let dashboardStats = {
    activeTranscodes: 3,
    queuedJobs: 2,
    fleetOnline: 12,
    fleetTotal: 12,
    avgSpeed: 3.1,
    recoveryRate: 98.6,
    incomingBps: "4.2 Gbps",
    egressBps: "12.8 Gbps"
  };

  // Live Transcoding Jobs
  let jobs = [
    {
      id: "job-e77c88b9-4a12",
      file: "somalia_independence_day_parade_1080p.mp4",
      queue: "transcode-accelerated",
      resolutions: ["1080p", "720p", "480p"],
      progress: 62.5,
      speed: 4.2,
      fps: 120,
      elapsed: 45,
      status: "PROCESSING",
      worker: "worker-accel-02",
      error: null
    },
    {
      id: "job-fb11a2d3-9c88",
      file: "weekly_news_recap_east_africa.mov",
      queue: "transcode-cpu",
      resolutions: ["720p", "480p"],
      progress: 18.0,
      speed: 1.8,
      fps: 54,
      elapsed: 12,
      status: "PROCESSING",
      worker: "worker-cpu-01",
      error: null
    },
    {
      id: "job-ad09c8f2-3e4b",
      file: "somali_league_football_derby.mkv",
      queue: "transcode-accelerated",
      resolutions: ["1080p", "720p"],
      progress: 0,
      speed: 0,
      fps: 0,
      elapsed: 0,
      status: "QUEUED",
      worker: "Unassigned",
      error: null
    }
  ];

  // Worker Fleet
  let workers = [
    { id: "worker-cpu-01", host: "transcode-cpu-node-01", queue: "transcode-cpu", status: "PROCESSING", cpu: 82.5, gpu: 0.0, vram: 0, temp: 42, heartbeat: 0 },
    { id: "worker-cpu-02", host: "transcode-cpu-node-02", queue: "transcode-cpu", status: "IDLE", cpu: 2.1, gpu: 0.0, vram: 0, temp: 35, heartbeat: 1 },
    { id: "worker-accel-01", host: "transcode-gpu-node-01", queue: "transcode-accelerated", status: "IDLE", cpu: 5.4, gpu: 0.0, vram: 256, temp: 45, heartbeat: 0 },
    { id: "worker-accel-02", host: "transcode-gpu-node-02", queue: "transcode-accelerated", status: "PROCESSING", cpu: 45.1, gpu: 72.8, vram: 4096, temp: 64, heartbeat: 2 },
    { id: "worker-io-01", host: "manifest-io-node-01", queue: "manifest", status: "IDLE", cpu: 12.0, gpu: 0.0, vram: 0, temp: 38, heartbeat: 0 },
    { id: "worker-thumb-01", host: "thumbnail-node-01", queue: "thumbnail", status: "IDLE", cpu: 1.5, gpu: 0.0, vram: 0, temp: 34, heartbeat: 3 },
    { id: "worker-rec-01", host: "recording-node-01", queue: "recording", status: "PROCESSING", cpu: 24.8, gpu: 0.0, vram: 0, temp: 40, heartbeat: 0 }
  ];

  // Queues status
  let queueStats = {
    "transcode-cpu": { queued: 1, leased: 1, activeWorkers: 2, dleq: 0 },
    "transcode-accelerated": { queued: 1, leased: 1, activeWorkers: 2, dleq: 0 },
    "manifest": { queued: 0, leased: 0, activeWorkers: 1, dleq: 0 },
    "thumbnail": { queued: 0, leased: 0, activeWorkers: 1, dleq: 0 },
    "recording": { queued: 0, leased: 1, activeWorkers: 1, dleq: 0 },
    "maintenance": { queued: 0, leased: 0, activeWorkers: 1, dleq: 0 }
  };

  // Failed / Cancelled Registry
  let failedJobs = [
    {
      id: "job-dead0001-9f9f",
      file: "corrupt_stream_file_bad_header.mp4",
      queue: "transcode-cpu",
      error_code: "ERR_PROBING_FAILED",
      error_message: "FFprobe scan failed: Invalid pixel format or corrupt GOP metadata headers",
      timestamp: "2026-07-24T17:15:32.400Z"
    },
    {
      id: "job-dead0002-3c3c",
      file: "somali_chef_culinary_guide_raw.mov",
      queue: "transcode-accelerated",
      error_code: "ERR_WRITE_TIMEOUT",
      error_message: "OSS Storage upload pipeline disconnected: Write timeout during fragment upload to tenant_gntv/vod/channels/",
      timestamp: "2026-07-24T16:42:01.000Z"
    }
  ];

  // Retry Queue
  let retryJobs = [
    {
      id: "job-retry01-7c7c",
      file: "diaspora_talk_show_part_2.mp4",
      queue: "transcode-cpu",
      attempt: 2,
      max_attempts: 3,
      backoff_delay: 45,
      seconds_remaining: 18,
      error_message: "Redis lock lease conflict (lease_expires_at exceeded worker refresh tick)"
    }
  ];

  // Log terminal rows
  let logs = [
    "[17:39:05] [NOC ENGINE] Media Processing Service Initialized Successfully.",
    "[17:39:05] [BROKER] Connected to Redis Broker Core Node 01.",
    "[17:39:06] [FLEET] 12 / 12 workers registered with healthy heartbeat.",
    "[17:39:06] [STORAGE] Private OSS streaming bucket validated: Ready."
  ];

  // Selected job for manifest inspector / timeline
  let selectedJobForInspector = jobs[0].id;
  let selectedJobForTimeline = jobs[0].id;

  // Manifest explorer paths
  let manifests = {
    "tenant_gntv/channels/ch_global/sessions/sess_20260724/master.m3u8": `#EXTM3U
#EXT-X-VERSION:6
#EXT-X-INDEPENDENT-SEGMENTS

#EXT-X-STREAM-INF:BANDWIDTH=4500000,AVERAGE-BANDWIDTH=4200000,RESOLUTION=1920x1080,FRAME-RATE=29.97,CODECS="avc1.64002a,mp4a.40.2"
stream_1080p/index.m3u8

#EXT-X-STREAM-INF:BANDWIDTH=2200000,AVERAGE-BANDWIDTH=2000000,RESOLUTION=1280x720,FRAME-RATE=29.97,CODECS="avc1.4d401f,mp4a.40.2"
stream_720p/index.m3u8

#EXT-X-STREAM-INF:BANDWIDTH=800000,AVERAGE-BANDWIDTH=750000,RESOLUTION=854x480,FRAME-RATE=29.97,CODECS="avc1.42c01e,mp4a.40.2"
stream_480p/index.m3u8`,

    "tenant_gntv/channels/ch_global/sessions/sess_20260724/stream_1080p/index.m3u8": `#EXTM3U
#EXT-X-VERSION:6
#EXT-X-TARGETDURATION:6
#EXT-X-MEDIA-SEQUENCE:1042
#EXT-X-PLAYLIST-TYPE:EVENT
#EXT-X-KEY:METHOD=AES-128,URI="https://api.gntv.tv/api/v1/streaming/playback/key/ch_global",IV=0x000102030405060708090a0b0c0d0e0f
#EXTINF:6.006,
data_1042.ts
#EXTINF:6.006,
data_1043.ts
#EXTINF:6.006,
data_1044.ts`,

    "tenant_gntv/channels/ch_global/sessions/sess_20260724/manifest.mpd": `<?xml version="1.0" encoding="utf-8"?>
<MPD xmlns="urn:mpeg:dash:schema:mpd:2011" minBufferTime="PT1.5S" type="dynamic" profiles="urn:mpeg:dash:profile:isoff-live:2011">
  <Period id="1" start="PT0S">
    <AdaptationSet id="0" mimeType="video/mp4" codecs="avc1.64002a" segmentAlignment="true">
      <Representation id="1080p" bandwidth="4500000" width="1920" height="1080" frameRate="30000/1001">
        <SegmentTemplate timescale="30000" media="$RepresentationID$/media-$Number$.m4s" startNumber="1042" duration="180180" />
      </Representation>
    </AdaptationSet>
  </Period>
</MPD>`
  };

  let activeInspectorPath = Object.keys(manifests)[0];

  // Thumbnail Assets
  let thumbnailGallery = [
    {
      title: "Somali Independence Day Parade 2026",
      path: "tenant_gntv/vod/channels/ch_global/sessions/sess_e77c88b9/",
      keyframes: ["keyframe_01.jpg", "keyframe_02.jpg", "keyframe_03.jpg", "keyframe_04.jpg"],
      sprite: "sprite.webp",
      vtt: "sprite.vtt"
    },
    {
      title: "Weekly News Recap East Africa",
      path: "tenant_gntv/vod/channels/ch_news/sessions/sess_fb11a2d3/",
      keyframes: ["keyframe_01.jpg", "keyframe_02.jpg", "keyframe_03.jpg"],
      sprite: "sprite.webp",
      vtt: "sprite.vtt"
    }
  ];

  const refreshProcessingApi = async () => {
    if (isRefreshing) return;
    isRefreshing = true;
    try {
      const [jobPage, workerRows, queueData, manifestPage, thumbnailPage, metricsPage] = await Promise.all([
        processingRequest("/jobs?limit=100"),
        processingRequest("/workers"),
        processingRequest("/queues"),
        processingRequest("/manifests?limit=100"),
        processingRequest("/thumbnails?limit=100"),
        processingRequest("/metrics")
      ]);

      jobs = jobPage.items
        .filter(job => !["COMPLETED", "FAILED", "CANCELLED"].includes(job.status))
        .map(job => ({
          id: job.job_id,
          file: job.job_type.replaceAll("_", " "),
          queue: job.queue,
          resolutions: [],
          progress: job.progress,
          speed: job.metrics?.encoding_speed_factor || 0,
          fps: job.metrics?.encoding_fps || 0,
          elapsed: job.metrics?.processing_duration_seconds || 0,
          status: job.status,
          worker: job.worker_id || "Unassigned",
          error: job.error_detail
        }));
      failedJobs = jobPage.items
        .filter(job => ["FAILED", "CANCELLED"].includes(job.status))
        .map(job => ({
          id: job.job_id,
          file: job.job_type.replaceAll("_", " "),
          queue: job.queue,
          error_code: job.error_code || `ERR_${job.status}`,
          error_message: job.error_detail || `Processing job ${job.status.toLowerCase()}`,
          timestamp: job.completed_at || job.created_at
        }));
      retryJobs = jobPage.items
        .filter(job => job.status === "RETRYING")
        .map(job => ({
          id: job.job_id,
          file: job.job_type.replaceAll("_", " "),
          queue: job.queue,
          attempt: job.attempt,
          max_attempts: job.max_attempts,
          backoff_delay: 0,
          seconds_remaining: 0,
          error_message: job.error_detail || "Worker retry scheduled"
        }));

      workers = workerRows.map(worker => ({
        id: worker.worker_id,
        host: worker.hostname || worker.worker_id,
        queue: worker.queue,
        status: worker.status,
        cpu: worker.hardware.cpu_usage_pct || 0,
        gpu: worker.hardware.gpu_usage_pct || 0,
        vram: worker.hardware.vram_allocated_mb || 0,
        temp: worker.hardware.temperature_celsius || 0,
        heartbeat: Math.max(0, Math.floor((Date.now() - Date.parse(worker.last_heartbeat)) / 1000))
      }));

      queueStats = Object.fromEntries(Object.entries(queueData.queues).map(([name, item]) => [
        name,
        {
          queued: item.messages_queued,
          leased: item.messages_leased + item.messages_running,
          activeWorkers: item.active_workers,
          dleq: 0
        }
      ]));

      manifests = Object.fromEntries(manifestPage.items.map(item => [
        item.manifest_path,
        `Manifest ${item.format.toUpperCase()} • ${item.status.toUpperCase()} • generation ${item.generation}`
      ]));
      if (Object.keys(manifests).length === 0) {
        manifests = { "No manifests published": "No processing manifests are currently registered." };
      }
      if (!manifests[activeInspectorPath]) activeInspectorPath = Object.keys(manifests)[0];

      thumbnailGallery = thumbnailPage.items.map(item => ({
        title: `${item.kind} • ${item.status}`,
        path: item.asset_path,
        keyframes: item.kind === "keyframe" ? [item.asset_path.split("/").pop()] : [],
        sprite: item.kind === "sprite" ? item.asset_path.split("/").pop() : "—",
        vtt: "—"
      }));

      dashboardStats.activeTranscodes = jobs.filter(job => job.status === "PROCESSING").length;
      dashboardStats.queuedJobs = jobs.filter(job => job.status === "QUEUED").length;
      dashboardStats.fleetOnline = workers.filter(worker => worker.status !== "OFFLINE").length;
      dashboardStats.fleetTotal = workers.length;
      const measuredSpeeds = metricsPage.items
        .map(item => item.encoding_speed_factor)
        .filter(value => typeof value === "number");
      dashboardStats.avgSpeed = measuredSpeeds.length
        ? Number((measuredSpeeds.reduce((sum, value) => sum + value, 0) / measuredSpeeds.length).toFixed(1))
        : 0;

      if (!apiConnected) addLog("[API] Processing Operations Center connected to live control-plane data.");
      apiConnected = true;
      renderActiveTab();
      drawDashboardTraffic();
      drawPerformanceCharts();
    } catch (error) {
      if (apiConnected) addLog(`[API] Processing telemetry unavailable: ${error.message}`);
      apiConnected = false;
    } finally {
      isRefreshing = false;
    }
  };

  // Helper: Append a line to NOC console logs
  const addLog = (msg) => {
    const time = new Date().toLocaleTimeString('en-US', { hour12: false });
    logs.unshift(`[${time}] ${msg}`);
    if (logs.length > 30) logs.pop();
    const logBox = container.querySelector("#proc-terminal-box");
    if (logBox) {
      logBox.innerHTML = logs.map(l => `<div class="log-line">> ${l}</div>`).join('');
    }
  };

  // Draw Performance Charts (Direct Canvas 2D)
  const drawPerformanceCharts = () => {
    const canvasSpeed = container.querySelector("#canvas-perf-speed");
    const canvasLatency = container.querySelector("#canvas-perf-latency");

    if (canvasSpeed) {
      const ctx = canvasSpeed.getContext("2d");
      const w = canvasSpeed.width;
      const h = canvasSpeed.height;
      ctx.clearRect(0, 0, w, h);

      // Grid Lines
      ctx.strokeStyle = "rgba(255, 255, 255, 0.05)";
      ctx.lineWidth = 1;
      for (let i = 20; i < h; i += 30) {
        ctx.beginPath(); ctx.moveTo(0, i); ctx.lineTo(w, i); ctx.stroke();
      }

      // Spline data (mock speed factors)
      const data = [2.2, 2.5, 2.4, 2.8, 3.2, 3.0, 3.1, 3.5, 3.4, 3.8, 4.1, 3.9, 4.2];
      const spacing = w / (data.length - 1);

      // Gradient Fill
      const grad = ctx.createLinearGradient(0, 0, 0, h);
      grad.addColorStop(0, "rgba(0, 102, 255, 0.2)");
      grad.addColorStop(1, "rgba(0, 0, 0, 0.0)");

      ctx.beginPath();
      ctx.moveTo(0, h);
      data.forEach((val, idx) => {
        const x = idx * spacing;
        const y = h - (val / 5.0) * (h - 20);
        ctx.lineTo(x, y);
      });
      ctx.lineTo(w, h);
      ctx.closePath();
      ctx.fillStyle = grad;
      ctx.fill();

      // Stroke Line
      ctx.beginPath();
      data.forEach((val, idx) => {
        const x = idx * spacing;
        const y = h - (val / 5.0) * (h - 20);
        if (idx === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      });
      ctx.strokeStyle = "#0066ff";
      ctx.lineWidth = 2.5;
      ctx.shadowColor = "rgba(0, 102, 255, 0.5)";
      ctx.shadowBlur = 10;
      ctx.stroke();
      ctx.shadowBlur = 0; // Reset
    }

    if (canvasLatency) {
      const ctx = canvasLatency.getContext("2d");
      const w = canvasLatency.width;
      const h = canvasLatency.height;
      ctx.clearRect(0, 0, w, h);

      // Grid
      ctx.strokeStyle = "rgba(255, 255, 255, 0.05)";
      for (let i = 20; i < h; i += 30) {
        ctx.beginPath(); ctx.moveTo(0, i); ctx.lineTo(w, i); ctx.stroke();
      }

      // Latency in seconds (ideal target < 2s)
      const data = [1.8, 2.2, 2.5, 1.9, 1.6, 1.5, 1.4, 1.8, 2.1, 1.9, 1.5, 1.3, 1.2];
      const spacing = w / (data.length - 1);

      const grad = ctx.createLinearGradient(0, 0, 0, h);
      grad.addColorStop(0, "rgba(255, 102, 0, 0.2)");
      grad.addColorStop(1, "rgba(0, 0, 0, 0.0)");

      ctx.beginPath();
      ctx.moveTo(0, h);
      data.forEach((val, idx) => {
        const x = idx * spacing;
        const y = h - (val / 3.0) * (h - 20);
        ctx.lineTo(x, y);
      });
      ctx.lineTo(w, h);
      ctx.closePath();
      ctx.fillStyle = grad;
      ctx.fill();

      ctx.beginPath();
      data.forEach((val, idx) => {
        const x = idx * spacing;
        const y = h - (val / 3.0) * (h - 20);
        if (idx === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      });
      ctx.strokeStyle = "#ff6600";
      ctx.lineWidth = 2.5;
      ctx.shadowColor = "rgba(255, 102, 0, 0.5)";
      ctx.shadowBlur = 10;
      ctx.stroke();
      ctx.shadowBlur = 0;
    }
  };

  // Draw Ingress/Egress Load Area Plot in Dashboard
  const drawDashboardTraffic = () => {
    const canvas = container.querySelector("#canvas-dash-traffic");
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    const w = canvas.width;
    const h = canvas.height;
    ctx.clearRect(0, 0, w, h);

    // Grids
    ctx.strokeStyle = "rgba(255, 255, 255, 0.03)";
    ctx.lineWidth = 1;
    for (let i = 10; i < h; i += 20) {
      ctx.beginPath(); ctx.moveTo(0, i); ctx.lineTo(w, i); ctx.stroke();
    }

    // Ingress data spline (blue)
    const ingress = [40, 45, 42, 48, 55, 58, 62, 60, 68, 70, 72, 68, 75, 80, 85];
    const egress = [120, 130, 125, 140, 155, 168, 180, 195, 210, 205, 220, 240, 235, 250, 256];
    const spacing = w / (ingress.length - 1);

    // Egress Spline Area (Blue Glow)
    const egGrad = ctx.createLinearGradient(0, 0, 0, h);
    egGrad.addColorStop(0, "rgba(0, 102, 255, 0.15)");
    egGrad.addColorStop(1, "rgba(0, 0, 0, 0.0)");

    ctx.beginPath();
    ctx.moveTo(0, h);
    egress.forEach((val, idx) => {
      const x = idx * spacing;
      const y = h - (val / 300) * (h - 20);
      ctx.lineTo(x, y);
    });
    ctx.lineTo(w, h);
    ctx.closePath();
    ctx.fillStyle = egGrad;
    ctx.fill();

    ctx.beginPath();
    egress.forEach((val, idx) => {
      const x = idx * spacing;
      const y = h - (val / 300) * (h - 20);
      if (idx === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.strokeStyle = "#0066ff";
    ctx.lineWidth = 2.0;
    ctx.stroke();

    // Ingress Spline (Orange Line)
    ctx.beginPath();
    ingress.forEach((val, idx) => {
      const x = idx * spacing;
      const y = h - (val / 300) * (h - 20);
      if (idx === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.strokeStyle = "#ff6600";
    ctx.lineWidth = 1.8;
    ctx.stroke();
  };

  // Real-time Simulation Engine
  const startSimulator = () => {
    simulationInterval = setInterval(() => {
      if (apiConnected) {
        refreshProcessingApi();
        return;
      }

      // Periodic reconnection check when offline (every 5 ticks = 10s)
      reconnectTick++;
      if (reconnectTick >= 5) {
        reconnectTick = 0;
        refreshProcessingApi();
      }

      let activeCount = 0;
      let queuedCount = 0;

      // 1. Progress active jobs
      jobs.forEach(job => {
        if (job.status === "PROCESSING") {
          activeCount++;
          job.progress += parseFloat((Math.random() * 2.5 + 0.5).toFixed(1));
          job.elapsed += 2;
          if (job.progress >= 100) {
            job.progress = 100;
            job.status = "PACKAGING";
            addLog(`Job ${job.id.substring(0, 8)}: Video encoding finished. Packaging segments (HLS/DASH)...`);
          }
        } else if (job.status === "PACKAGING") {
          activeCount++;
          job.elapsed += 2;
          job.progress = 100; // Keep at 100%
          // Simulate packaging state timer
          if (Math.random() < 0.4) {
            job.status = "VALIDATING";
            addLog(`Job ${job.id.substring(0, 8)}: Segments constructed. Running manifest validation...`);
          }
        } else if (job.status === "VALIDATING") {
          activeCount++;
          job.elapsed += 2;
          if (Math.random() < 0.4) {
            job.status = "PUBLISHING";
            addLog(`Job ${job.id.substring(0, 8)}: Manifest validated successfully. Syncing atomically to private OSS...`);
          }
        } else if (job.status === "PUBLISHING") {
          activeCount++;
          job.elapsed += 2;
          if (Math.random() < 0.4) {
            job.status = "COMPLETED";
            addLog(`[SUCCESS] Job ${job.id.substring(0, 8)} completed. Asset published to streaming endpoint.`);

            // Auto add to VOD database catalog locally!
            const newVod = {
              title: job.file.replace(/\.[^/.]+$/, "").replace(/_/g, " "),
              category: "Entertainment",
              duration: `${Math.floor(job.elapsed / 60)}:${(job.elapsed % 60).toString().padStart(2, '0')}`,
              presenter: "NOC Automated Output",
              premium: false,
              description: `Automated transcode of input source file "${job.file}". Transcode completed in ${job.elapsed}s using ${job.queue} queue.`
            };
            store.addCatalogItem(newVod).catch(err => console.error("Auto catalog write failed", err));
          }
        } else if (job.status === "QUEUED") {
          queuedCount++;
          // Simulate queue leasing by worker
          if (Math.random() < 0.25) {
            job.status = "CLAIMED";
            job.worker = job.queue === "transcode-cpu" ? "worker-cpu-02" : "worker-accel-01";
            addLog(`Worker ${job.worker} claimed job ${job.id.substring(0, 8)}. Initializing lease lock...`);

            // Phase shift to probing
            setTimeout(() => {
              if (job.status === "CLAIMED") {
                job.status = "PROBING";
                addLog(`Job ${job.id.substring(0, 8)}: Probing stream codecs using ffprobe...`);

                // Shift to processing
                setTimeout(() => {
                  if (job.status === "PROBING") {
                    job.status = "PROCESSING";
                    job.speed = job.queue === "transcode-cpu" ? 1.8 : 4.1;
                    job.fps = job.queue === "transcode-cpu" ? 60 : 120;
                    addLog(`Job ${job.id.substring(0, 8)}: Transcode started. Presets configured. Pipeline active.`);
                  }
                }, 4000);
              }
            }, 3000);
          }
        }
      });

      // Remove completed VODs after 6 seconds to keep layout clean
      jobs = jobs.filter(j => {
        if (j.status === "COMPLETED") {
          // Add to thumbnail gallery before deleting from active queue
          if (!thumbnailGallery.some(tg => tg.title.toLowerCase() === j.file.replace(/\.[^/.]+$/, "").replace(/_/g, " ").toLowerCase())) {
            thumbnailGallery.push({
              title: j.file.replace(/\.[^/.]+$/, "").replace(/_/g, " "),
              path: `tenant_gntv/vod/channels/ch_global/sessions/sess_${j.id.substring(0,8)}/`,
              keyframes: ["keyframe_01.jpg", "keyframe_02.jpg"],
              sprite: "sprite.webp",
              vtt: "sprite.vtt"
            });
          }
          return false;
        }
        return true;
      });

      // 2. Fluctuate worker usage
      workers.forEach(w => {
        if (w.status === "PROCESSING") {
          w.cpu = Math.min(100, Math.max(40, w.cpu + (Math.random() - 0.5) * 8)).toFixed(1);
          if (w.gpu > 0) {
            w.gpu = Math.min(100, Math.max(30, w.gpu + (Math.random() - 0.5) * 10)).toFixed(1);
            w.temp = Math.min(80, Math.max(50, w.temp + Math.round((Math.random() - 0.5) * 4)));
          } else {
            w.temp = Math.min(60, Math.max(38, w.temp + Math.round((Math.random() - 0.5) * 2)));
          }
          w.heartbeat = 0;
        } else {
          w.cpu = Math.min(10, Math.max(1, w.cpu + (Math.random() - 0.5) * 1)).toFixed(1);
          w.gpu = 0.0;
          w.temp = Math.min(40, Math.max(30, w.temp + Math.round((Math.random() - 0.5) * 1)));
          w.heartbeat += 2;
          if (w.heartbeat > 10) w.heartbeat = 0; // Simulate regular ping
        }
      });

      // 3. Queue statistics updates
      let cpuQueued = jobs.filter(j => j.status === "QUEUED" && j.queue === "transcode-cpu").length;
      let cpuLeased = jobs.filter(j => j.status !== "QUEUED" && j.status !== "COMPLETED" && j.queue === "transcode-cpu").length;
      let gpuQueued = jobs.filter(j => j.status === "QUEUED" && j.queue === "transcode-accelerated").length;
      let gpuLeased = jobs.filter(j => j.status !== "QUEUED" && j.status !== "COMPLETED" && j.queue === "transcode-accelerated").length;

      queueStats["transcode-cpu"].queued = cpuQueued + retryJobs.filter(j => j.queue === "transcode-cpu").length;
      queueStats["transcode-cpu"].leased = cpuLeased;
      queueStats["transcode-accelerated"].queued = gpuQueued + retryJobs.filter(j => j.queue === "transcode-accelerated").length;
      queueStats["transcode-accelerated"].leased = gpuLeased;

      // 4. Retry updates
      retryJobs.forEach((rj, idx) => {
        rj.seconds_remaining -= 2;
        if (rj.seconds_remaining <= 0) {
          addLog(`Retry timer expired. Re-enqueuing job ${rj.id.substring(0, 8)} into queue broker...`);
          // Re-enqueue
          jobs.push({
            id: rj.id,
            file: rj.file,
            queue: rj.queue,
            resolutions: ["1080p", "720p", "480p"],
            progress: 0,
            speed: 0,
            fps: 0,
            elapsed: 0,
            status: "QUEUED",
            worker: "Unassigned",
            error: null
          });
          retryJobs.splice(idx, 1);
        }
      });

      // 5. Update overall telemetry stats
      dashboardStats.activeTranscodes = activeCount;
      dashboardStats.queuedJobs = queuedCount + retryJobs.length;
      dashboardStats.avgSpeed = activeCount > 0
        ? parseFloat((jobs.reduce((acc, curr) => acc + (curr.speed || 0), 0) / activeCount).toFixed(1))
        : 0;

      // Render Active Tab Content dynamically
      renderActiveTab();
      drawDashboardTraffic();
      drawPerformanceCharts();
    }, 2000);
  };

  const render = () => {
    container.innerHTML = `
      <style>
        .proc-noc-container {
          --proc-black: #020206;
          --proc-blue: #0066ff;
          --proc-blue-glow: rgba(0, 102, 255, 0.4);
          --proc-orange: #ff6600;
          --proc-orange-glow: rgba(255, 102, 0, 0.35);
          --proc-cyan: #00d2ff;
          --proc-border: rgba(255, 255, 255, 0.07);
          --proc-border-blue: rgba(0, 102, 255, 0.25);
          --proc-border-orange: rgba(255, 102, 0, 0.25);
          --proc-glass-bg: rgba(8, 8, 16, 0.8);
          --proc-bg-card: rgba(255, 255, 255, 0.02);

          display: flex;
          flex-direction: column;
          height: calc(100vh - 120px);
          width: 100%;
          background: var(--proc-black);
          color: #e2e8f0;
          font-family: var(--font-sans), sans-serif;
          position: relative;
          overflow: hidden;
          border-radius: 12px;
          border: 1px solid var(--proc-border);
        }

        .proc-noc-header {
          background: rgba(4, 4, 8, 0.95);
          border-bottom: 1px solid var(--proc-border);
          padding: 14px 24px;
          display: flex;
          justify-content: space-between;
          align-items: center;
          flex-shrink: 0;
        }

        .proc-logo-area {
          display: flex;
          align-items: center;
          gap: 10px;
        }

        .proc-logo-text {
          font-size: 20px;
          font-weight: 850;
          letter-spacing: -1px;
          color: #ffffff;
        }

        .proc-logo-tag {
          font-family: var(--font-mono);
          font-size: 8px;
          font-weight: 700;
          border: 1px solid var(--proc-blue);
          padding: 2px 6px;
          border-radius: 4px;
          color: var(--proc-blue);
          letter-spacing: 0.5px;
          box-shadow: 0 0 5px var(--proc-blue-glow);
        }

        .proc-header-time {
          font-family: var(--font-mono);
          font-size: 11px;
          color: rgba(255, 255, 255, 0.5);
          background: rgba(255,255,255,0.03);
          border: 1px solid rgba(255,255,255,0.06);
          padding: 4px 10px;
          border-radius: 4px;
        }

        .proc-noc-layout {
          display: flex;
          flex: 1;
          overflow: hidden;
        }

        /* Sidebar Navigation */
        .proc-noc-sidebar {
          width: 210px;
          background: rgba(4, 4, 8, 0.95);
          border-right: 1px solid var(--proc-border);
          display: flex;
          flex-direction: column;
          padding: 16px 8px;
          gap: 4px;
          flex-shrink: 0;
          overflow-y: auto;
        }

        .proc-noc-nav-item {
          display: flex;
          align-items: center;
          gap: 10px;
          padding: 10px 14px;
          background: transparent;
          border: none;
          border-radius: 6px;
          color: rgba(255, 255, 255, 0.55);
          font-size: 12px;
          font-weight: 700;
          text-align: left;
          cursor: pointer;
          transition: all 0.2s;
          position: relative;
        }

        .proc-noc-nav-item:hover {
          color: #ffffff;
          background: rgba(255, 255, 255, 0.02);
        }

        .proc-noc-nav-item.active {
          color: #ffffff;
          background: rgba(0, 102, 255, 0.1);
          border: 1px solid var(--proc-border-blue);
        }

        .proc-noc-nav-item.active::before {
          content: "";
          position: absolute;
          left: 4px;
          top: 10px;
          bottom: 10px;
          width: 3px;
          background: var(--proc-blue);
          border-radius: 2px;
          box-shadow: 0 0 8px var(--proc-blue-glow);
        }

        /* Content pane */
        .proc-noc-content {
          flex: 1;
          padding: 24px;
          overflow-y: auto;
          box-sizing: border-box;
          display: flex;
          flex-direction: column;
          gap: 20px;
          background: radial-gradient(at 0% 0%, rgba(0, 102, 255, 0.05) 0px, transparent 40%),
                      radial-gradient(at 100% 100%, rgba(255, 102, 0, 0.03) 0px, transparent 50%);
        }

        /* Glassmorphic Grid items */
        .proc-glass-card {
          background: var(--proc-glass-bg);
          backdrop-filter: blur(20px);
          border: 1px solid var(--proc-border);
          border-radius: 8px;
          padding: 16px;
          box-sizing: border-box;
          transition: all 0.25s cubic-bezier(0.16, 1, 0.3, 1);
        }

        .proc-glass-card:hover {
          border-color: rgba(255, 255, 255, 0.12);
        }

        .proc-glass-card.blue-glow:hover {
          border-color: var(--proc-blue);
          box-shadow: 0 0 12px var(--proc-blue-glow);
        }

        .proc-glass-card.orange-glow:hover {
          border-color: var(--proc-orange);
          box-shadow: 0 0 12px var(--proc-orange-glow);
        }

        /* KPIs */
        .proc-kpis-grid {
          display: grid;
          grid-template-columns: repeat(4, 1fr);
          gap: 16px;
        }

        @media(max-width: 1100px) {
          .proc-kpis-grid {
            grid-template-columns: repeat(2, 1fr);
          }
        }

        @media(max-width: 600px) {
          .proc-kpis-grid {
            grid-template-columns: 1fr;
          }
        }

        .proc-kpi-card {
          display: flex;
          align-items: center;
          gap: 14px;
        }

        .proc-kpi-icon {
          width: 42px;
          height: 42px;
          border-radius: 8px;
          display: flex;
          align-items: center;
          justify-content: center;
          font-size: 20px;
          background: rgba(255,255,255,0.03);
          border: 1px solid rgba(255,255,255,0.06);
          flex-shrink: 0;
        }

        .proc-kpi-info {
          display: flex;
          flex-direction: column;
          gap: 2px;
        }

        .proc-kpi-title {
          font-size: 10px;
          font-weight: 700;
          color: rgba(255, 255, 255, 0.45);
          text-transform: uppercase;
          letter-spacing: 0.5px;
        }

        .proc-kpi-value {
          font-size: 20px;
          font-weight: 850;
          font-family: var(--font-mono);
          color: #ffffff;
        }

        /* Table design */
        .proc-table {
          width: 100%;
          border-collapse: collapse;
          text-align: left;
        }

        .proc-table th {
          padding: 10px 14px;
          border-bottom: 2px solid rgba(255, 255, 255, 0.08);
          font-size: 10px;
          font-weight: 700;
          color: rgba(255,255,255,0.4);
          text-transform: uppercase;
          letter-spacing: 0.5px;
        }

        .proc-table td {
          padding: 12px 14px;
          border-bottom: 1px solid rgba(255, 255, 255, 0.04);
          font-size: 12px;
        }

        .proc-table tr:hover td {
          background: rgba(255, 255, 255, 0.01);
        }

        /* Progress bars */
        .proc-progress-bg {
          width: 100%;
          height: 6px;
          background: rgba(255,255,255,0.08);
          border-radius: 3px;
          overflow: hidden;
          position: relative;
        }

        .proc-progress-fill {
          height: 100%;
          background: var(--proc-blue);
          box-shadow: 0 0 8px var(--proc-blue-glow);
          transition: width 0.3s ease;
        }

        .proc-progress-fill.orange {
          background: var(--proc-orange);
          box-shadow: 0 0 8px var(--proc-orange-glow);
        }

        /* Badges */
        .proc-badge {
          font-size: 9px;
          font-weight: 800;
          padding: 2px 6px;
          border-radius: 4px;
          text-transform: uppercase;
          font-family: var(--font-mono);
          display: inline-block;
          border: 1px solid transparent;
        }

        .proc-badge-blue { background: rgba(0, 102, 255, 0.12); color: var(--proc-cyan); border-color: var(--proc-border-blue); }
        .proc-badge-orange { background: rgba(255, 102, 0, 0.12); color: var(--proc-orange); border-color: var(--proc-border-orange); }
        .proc-badge-green { background: rgba(16, 185, 129, 0.12); color: #10b981; border-color: rgba(16, 185, 129, 0.2); }
        .proc-badge-red { background: rgba(239, 68, 68, 0.12); color: #ef4444; border-color: rgba(239, 68, 68, 0.2); }
        .proc-badge-gray { background: rgba(255, 255, 255, 0.05); color: rgba(255,255,255,0.6); border-color: rgba(255,255,255,0.1); }

        /* Logger console */
        .proc-console {
          background: #000000;
          border: 1px solid rgba(0, 102, 255, 0.15);
          border-radius: 6px;
          font-family: var(--font-mono);
          font-size: 11px;
          color: var(--proc-cyan);
          padding: 12px;
          height: 140px;
          overflow-y: auto;
          box-sizing: border-box;
          box-shadow: inset 0 0 10px rgba(0, 102, 255, 0.1);
        }

        .proc-console .log-line {
          margin-bottom: 4px;
          line-height: 1.4;
          white-space: pre-wrap;
        }

        /* Forms */
        .proc-form-group {
          display: flex;
          flex-direction: column;
          gap: 6px;
          margin-bottom: 12px;
        }
        .proc-form-group label {
          font-size: 10px;
          font-weight: 700;
          color: rgba(255,255,255,0.4);
          text-transform: uppercase;
        }
        .proc-form-group input, .proc-form-group select, .proc-form-group textarea {
          background: rgba(255, 255, 255, 0.04);
          border: 1px solid rgba(255,255,255,0.08);
          border-radius: 6px;
          padding: 8px 12px;
          color: #fff;
          font-size: 12px;
          outline: none;
          transition: all 0.2s;
        }
        .proc-form-group input:focus, .proc-form-group select:focus, .proc-form-group textarea:focus {
          border-color: var(--proc-blue);
          box-shadow: 0 0 8px var(--proc-blue-glow);
        }

        .proc-btn {
          background: var(--proc-blue);
          border: 1px solid var(--proc-border-blue);
          color: #fff;
          font-weight: 700;
          font-size: 12px;
          padding: 8px 16px;
          border-radius: 6px;
          cursor: pointer;
          transition: all 0.2s;
          display: inline-flex;
          align-items: center;
          justify-content: center;
          gap: 8px;
        }
        .proc-btn:hover {
          background: #0052cc;
          box-shadow: 0 0 10px var(--proc-blue-glow);
        }
        .proc-btn-orange {
          background: var(--proc-orange);
          border-color: var(--proc-border-orange);
        }
        .proc-btn-orange:hover {
          background: #cc5200;
          box-shadow: 0 0 10px var(--proc-orange-glow);
        }
        .proc-btn-secondary {
          background: rgba(255,255,255,0.03);
          border-color: rgba(255,255,255,0.1);
        }
        .proc-btn-secondary:hover {
          background: rgba(255,255,255,0.06);
          box-shadow: none;
        }
      </style>

      <div class="proc-noc-container">
        <!-- Top NOC Header -->
        <header class="proc-noc-header">
          <div class="proc-logo-area">
            <span class="proc-logo-text">GN<span style="color: var(--proc-orange);">TV</span></span>
            <span class="proc-logo-tag">PROCESSING OPERATIONS NOC</span>
          </div>

          <div style="display: flex; align-items: center; gap: 14px;">
            <div class="proc-badge proc-badge-green" style="font-size: 9px; letter-spacing: 0.5px;">
              ● NOC LIVE TELEMETRY ONLINE
            </div>
            <div class="proc-header-time" id="proc-system-clock">00:00:00 LCT</div>
          </div>
        </header>

        <!-- NOC Body Layout -->
        <div class="proc-noc-layout">
          <!-- Sidebar tabs -->
          <aside class="proc-noc-sidebar" role="navigation" aria-label="NOC Subpages">
            <button class="proc-noc-nav-item active" data-tab="dashboard">📊 NOC Dashboard</button>
            <button class="proc-noc-nav-item" data-tab="active">⚡ Active Transcodes</button>
            <button class="proc-noc-nav-item" data-tab="fleet">🖥️ Worker Fleet</button>
            <button class="proc-noc-nav-item" data-tab="utilization">🎛️ CPU/GPU Load</button>
            <button class="proc-noc-nav-item" data-tab="queues">📥 Celery Queues</button>
            <button class="proc-noc-nav-item" data-tab="manifests">🔍 Manifest Inspector</button>
            <button class="proc-noc-nav-item" data-tab="thumbnails">🖼️ Keyframe sprites</button>
            <button class="proc-noc-nav-item" data-tab="timeline">🕒 Processing Timeline</button>
            <button class="proc-noc-nav-item" data-tab="retries">🔄 Retry Center</button>
            <button class="proc-noc-nav-item" data-tab="failures">🚫 Failed & Dead-Letter</button>
            <button class="proc-noc-nav-item" data-tab="performance">📈 Historical Analytics</button>
          </aside>

          <!-- Dynamic Panel Content -->
          <main class="proc-noc-content" id="proc-noc-viewport">
            <!-- Rendered in sub-method -->
          </main>
        </div>
      </div>
    `;

    // Local system clock
    const clock = container.querySelector("#proc-system-clock");
    systemClockInterval = setInterval(() => {
      if (clock) {
        clock.textContent = new Date().toLocaleTimeString('en-US', { hour12: false }) + " LCT";
      }
    }, 1000);

    bindSidebarEvents();
    renderActiveTab();
    drawDashboardTraffic();
    drawPerformanceCharts();
    startSimulator();
  };

  const bindSidebarEvents = () => {
    container.querySelectorAll(".proc-noc-nav-item").forEach(btn => {
      btn.addEventListener("click", () => {
        container.querySelectorAll(".proc-noc-nav-item").forEach(b => b.classList.remove("active"));
        btn.classList.add("active");
        activeTab = btn.getAttribute("data-tab");
        renderActiveTab();
        drawDashboardTraffic();
        drawPerformanceCharts();
      });
    });
  };

  const renderActiveTab = () => {
    const viewport = container.querySelector("#proc-noc-viewport");
    if (!viewport) return;

    if (activeTab === "dashboard") {
      // 1. NOC Dashboard (Overview)
      viewport.innerHTML = `
        <div class="proc-kpis-grid">
          <div class="proc-glass-card proc-kpi-card blue-glow">
            <div class="proc-kpi-icon" style="color: var(--proc-blue);">⚡</div>
            <div class="proc-kpi-info">
              <span class="proc-kpi-title">Active Transcodes</span>
              <span class="proc-kpi-value">${dashboardStats.activeTranscodes}</span>
            </div>
          </div>

          <div class="proc-glass-card proc-kpi-card orange-glow">
            <div class="proc-kpi-icon" style="color: var(--proc-orange);">📥</div>
            <div class="proc-kpi-info">
              <span class="proc-kpi-title">Queued Messages</span>
              <span class="proc-kpi-value">${dashboardStats.queuedJobs}</span>
            </div>
          </div>

          <div class="proc-glass-card proc-kpi-card blue-glow">
            <div class="proc-kpi-icon" style="color: var(--proc-cyan);">📈</div>
            <div class="proc-kpi-info">
              <span class="proc-kpi-title">Avg Speed Factor</span>
              <span class="proc-kpi-value">${dashboardStats.avgSpeed > 0 ? dashboardStats.avgSpeed + "x" : "--"}</span>
            </div>
          </div>

          <div class="proc-glass-card proc-kpi-card blue-glow">
            <div class="proc-kpi-icon" style="color: #10b981;">🛡️</div>
            <div class="proc-kpi-info">
              <span class="proc-kpi-title">Recovery Rate</span>
              <span class="proc-kpi-value">${dashboardStats.recoveryRate}%</span>
            </div>
          </div>
        </div>

        <div style="display: grid; grid-template-columns: 2fr 1fr; gap: 20px;">
          <!-- Left: Real-time charts -->
          <div class="proc-glass-card blue-glow" style="display:flex; flex-direction:column; gap:12px;">
            <div style="display:flex; justify-content:space-between; align-items:center;">
              <h3 style="font-size: 13px; font-weight:800; text-transform:uppercase; letter-spacing:0.5px; color:var(--proc-blue);">
                📡 Broker Queue Traffic (Mbps) & Network Loads
              </h3>
              <div style="display:flex; gap:10px; font-size:10px;">
                <span style="color:#ff6600;">● Ingress: ${dashboardStats.incomingBps}</span>
                <span style="color:#0066ff;">● Egress: ${dashboardStats.egressBps}</span>
              </div>
            </div>
            <div style="flex:1; min-height: 180px;">
              <canvas id="canvas-dash-traffic" width="560" height="190" style="width:100%; height:100%;"></canvas>
            </div>
          </div>

          <!-- Right: Summary lists -->
          <div class="proc-glass-card" style="display:flex; flex-direction:column; gap:12px;">
            <h3 style="font-size: 12px; font-weight:800; text-transform:uppercase; color:#fff;">Fleet Capacity</h3>
            <div style="display:flex; flex-direction:column; gap:8px;">
              <div style="display:flex; justify-content:space-between; font-size:11px;">
                <span>CPU transcode nodes:</span>
                <strong style="font-family:var(--font-mono);">${workers.filter(w=>w.queue === 'transcode-cpu' && w.status === 'PROCESSING').length} / ${workers.filter(w=>w.queue === 'transcode-cpu').length} Active</strong>
              </div>
              <div style="display:flex; justify-content:space-between; font-size:11px;">
                <span>GPU accelerated nodes:</span>
                <strong style="color:var(--proc-orange); font-family:var(--font-mono);">${workers.filter(w=>w.queue === 'transcode-accelerated' && w.status === 'PROCESSING').length} / ${workers.filter(w=>w.queue === 'transcode-accelerated').length} Active</strong>
              </div>
              <div style="display:flex; justify-content:space-between; font-size:11px;">
                <span>Average Node Temp:</span>
                <strong style="font-family:var(--font-mono);">${Math.round(workers.reduce((acc,curr)=>acc+curr.temp, 0)/workers.length)}°C</strong>
              </div>
            </div>

            <div style="border-top:1px solid rgba(255,255,255,0.06); padding-top:10px; margin-top:5px;">
              <div style="display:flex; justify-content:space-between; font-size:11px; margin-bottom:4px;">
                <span>Active celery tasks:</span>
                <span class="proc-badge proc-badge-blue">${jobs.filter(j=>j.status !== 'QUEUED').length} Leased</span>
              </div>
            </div>
          </div>
        </div>

        <!-- System Logs Console -->
        <div class="proc-glass-card">
          <h4 style="font-size: 11px; font-weight:800; text-transform:uppercase; margin-bottom:8px; color:var(--proc-cyan);">NOC System Log feed (Real-Time Redis Events)</h4>
          <div class="proc-console" id="proc-terminal-box">
            ${logs.map(l => `<div class="log-line">> ${l}</div>`).join('')}
          </div>
        </div>
      `;

    } else if (activeTab === "active") {
      // 2. Active Jobs
      const activeRunningJobs = jobs.filter(j => j.status !== "COMPLETED");
      viewport.innerHTML = `
        <div style="display:flex; justify-content:space-between; align-items:center;">
          <div>
            <h3 style="font-size:16px; font-weight:850; text-transform:uppercase; margin:0;">Active Transcoding Jobs</h3>
            <p style="font-size:11px; color:rgba(255,255,255,0.45); margin:4px 0 0 0;">Currently leased jobs executing inside Docker container namespaces.</p>
          </div>
          <!-- Quick Submit Action -->
          <button class="proc-btn proc-btn-orange" id="btn-trigger-mock-job">+ Enqueue Test VOD Job</button>
        </div>

        <div class="proc-glass-card" style="overflow-x:auto;">
          <table class="proc-table">
            <thead>
              <tr>
                <th>Job ID</th>
                <th>Input file</th>
                <th>Queue</th>
                <th>ABR Resolution</th>
                <th>Progress</th>
                <th>Metrics</th>
                <th>Worker ID</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              ${activeRunningJobs.length === 0 ? `
                <tr>
                  <td colspan="8" style="text-align:center; padding:32px; color:rgba(255,255,255,0.35);">
                    No active transcoding jobs. Submit a test job above.
                  </td>
                </tr>
              ` : activeRunningJobs.map(job => `
                <tr id="job-row-${job.id}">
                  <td style="font-family:var(--font-mono); font-weight:700; color:var(--proc-cyan);">
                    <a href="#" class="view-job-timeline-link" data-id="${job.id}" style="color:var(--proc-cyan); text-decoration:none;">${job.id.substring(0,8)}...</a>
                  </td>
                  <td style="max-width:180px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;" title="${job.file}">${job.file}</td>
                  <td><span class="proc-badge ${job.queue === 'transcode-accelerated' ? 'proc-badge-orange' : 'proc-badge-gray'}">${job.queue.replace('transcode-','')}</span></td>
                  <td>
                    ${job.resolutions.map(r => `<span class="proc-badge proc-badge-blue" style="margin-right:2px;">${r}</span>`).join('')}
                  </td>
                  <td style="width:150px;">
                    <div style="display:flex; align-items:center; gap:8px;">
                      <div class="proc-progress-bg" style="flex:1;">
                        <div class="proc-progress-fill ${job.queue === 'transcode-accelerated' ? 'orange' : ''}" style="width: ${job.progress}%;"></div>
                      </div>
                      <span style="font-family:var(--font-mono); font-size:10px; font-weight:700; width:35px; text-align:right;">${job.progress}%</span>
                    </div>
                    <div style="font-size:9px; color:rgba(255,255,255,0.45); margin-top:2px; font-family:var(--font-mono);">State: ${job.status}</div>
                  </td>
                  <td style="font-family:var(--font-mono); font-size:11px;">
                    ${job.status === 'PROCESSING' ? `<div>Speed: ${job.speed}x</div><div>FPS: ${job.fps}</div>` : `<span style="color:rgba(255,255,255,0.4);">${job.status}</span>`}
                  </td>
                  <td style="font-family:var(--font-mono); color:rgba(255,255,255,0.6);">${job.worker}</td>
                  <td>
                    ${job.status === 'COMPLETED' ? `
                      <span style="color:#10b981; font-weight:700;">Completed</span>
                    ` : `
                      <button class="proc-btn proc-btn-secondary btn-cancel-job" data-id="${job.id}" style="padding:4px 8px; font-size:10px; color:#ef4444; border-color:rgba(239,68,68,0.25);">Cancel</button>
                    `}
                  </td>
                </tr>
              `).join('')}
            </tbody>
          </table>
        </div>
      `;

      bindActiveJobsEvents();

    } else if (activeTab === "fleet") {
      // 3. Worker Fleet
      viewport.innerHTML = `
        <div>
          <h3 style="font-size:16px; font-weight:850; text-transform:uppercase; margin:0;">Docker Cluster Worker Fleet</h3>
          <p style="font-size:11px; color:rgba(255,255,255,0.45); margin:4px 0 0 0;">Active container slots listening to enqueued Celery tasks.</p>
        </div>

        <div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(260px, 1fr)); gap:16px;">
          ${workers.map(w => {
            let statusColor = "#10b981";
            if (w.status === "PROCESSING") statusColor = "var(--proc-cyan)";
            if (w.heartbeat > 5) statusColor = "var(--proc-orange)";

            return `
              <div class="proc-glass-card ${w.status === 'PROCESSING' ? 'blue-glow' : ''}">
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px;">
                  <span style="font-family:var(--font-mono); font-weight:800; font-size:12px; color:#fff;">${w.id}</span>
                  <span class="proc-badge" style="background:rgba(255,255,255,0.03); color:${statusColor}; border-color:rgba(255,255,255,0.06); font-size:8px;">● ${w.status}</span>
                </div>

                <div style="display:flex; flex-direction:column; gap:6px; font-size:11px; margin-bottom:12px;">
                  <div style="display:flex; justify-content:space-between; color:rgba(255,255,255,0.5);">
                    <span>Host Mount:</span>
                    <strong style="color:#fff; font-family:var(--font-mono);">${w.host}</strong>
                  </div>
                  <div style="display:flex; justify-content:space-between; color:rgba(255,255,255,0.5);">
                    <span>Queue Subscribed:</span>
                    <strong style="color:var(--proc-orange); font-family:var(--font-mono);">${w.queue}</strong>
                  </div>
                  <div style="display:flex; justify-content:space-between; color:rgba(255,255,255,0.5);">
                    <span>Core Temp:</span>
                    <strong style="color:${w.temp > 60 ? 'var(--proc-orange)' : '#fff'}; font-family:var(--font-mono);">${w.temp}°C</strong>
                  </div>
                  <div style="display:flex; justify-content:space-between; color:rgba(255,255,255,0.5);">
                    <span>Last Ping:</span>
                    <strong style="color:rgba(255,255,255,0.8); font-family:var(--font-mono);">${w.heartbeat}s ago</strong>
                  </div>
                </div>

                <div style="display:flex; gap:6px;">
                  <button class="proc-btn proc-btn-secondary btn-reboot-worker" data-id="${w.id}" style="flex:1; font-size:10px; padding:6px 0;">Cycle Container</button>
                  <button class="proc-btn proc-btn-secondary" style="flex:1; font-size:10px; padding:6px 0; color:#ef4444; border-color:rgba(239,68,68,0.25);">Decommission</button>
                </div>
              </div>
            `;
          }).join('')}
        </div>
      `;

      bindFleetEvents();

    } else if (activeTab === "utilization") {
      // 4. CPU/GPU Utilization
      viewport.innerHTML = `
        <div>
          <h3 style="font-size:16px; font-weight:850; text-transform:uppercase; margin:0;">Hardware Load Monitors</h3>
          <p style="font-size:11px; color:rgba(255,255,255,0.45); margin:4px 0 0 0;">Cluster metrics tracking NVENC codecs and logical compute cores.</p>
        </div>

        <div style="display:grid; grid-template-columns:1fr 1fr; gap:20px;">
          <!-- CPU Load Gauge -->
          <div class="proc-glass-card blue-glow">
            <h4 style="font-size:12px; font-weight:800; text-transform:uppercase; margin-bottom:14px; color:var(--proc-blue);">Logical CPU Core Pools (Avg Load)</h4>
            <div style="display:flex; align-items:center; justify-content:center; flex-direction:column; padding:20px;">
              <svg width="150" height="150" viewBox="0 0 100 100">
                <circle cx="50" cy="50" r="40" fill="none" stroke="rgba(255,255,255,0.04)" stroke-width="8" />
                <circle cx="50" cy="50" r="40" fill="none" stroke="#0066ff" stroke-width="8" stroke-dasharray="251.2" stroke-dashoffset="${251.2 - (251.2 * (workers.reduce((acc,curr)=>acc+parseFloat(curr.cpu),0)/workers.length))/100}" stroke-linecap="round" transform="rotate(-90 50 50)" />
                <text x="50" y="55" text-anchor="middle" fill="#fff" font-size="16" font-family="var(--font-mono)" font-weight="bold">${Math.round(workers.reduce((acc,curr)=>acc+parseFloat(curr.cpu),0)/workers.length)}%</text>
              </svg>
              <div style="font-size:11px; color:rgba(255,255,255,0.5); margin-top:14px; text-align:center;">Avg load across ${workers.filter(w=>w.queue === 'transcode-cpu').length} standard VM compute threads</div>
            </div>
          </div>

          <!-- GPU NVENC Load Gauge -->
          <div class="proc-glass-card orange-glow">
            <h4 style="font-size:12px; font-weight:800; text-transform:uppercase; margin-bottom:14px; color:var(--proc-orange);">NVIDIA NVENC Hardware Codecs</h4>
            <div style="display:flex; flex-direction:column; gap:12px; padding:10px;">
              <div>
                <div style="display:flex; justify-content:space-between; font-size:11px; margin-bottom:4px;">
                  <span>GPU Core load:</span>
                  <strong style="font-family:var(--font-mono);">${workers.find(w=>w.id === 'worker-accel-02').gpu}%</strong>
                </div>
                <div class="proc-progress-bg">
                  <div class="proc-progress-fill orange" style="width: ${workers.find(w=>w.id === 'worker-accel-02').gpu}%;"></div>
                </div>
              </div>

              <div>
                <div style="display:flex; justify-content:space-between; font-size:11px; margin-bottom:4px;">
                  <span>VRAM Allocation:</span>
                  <strong style="font-family:var(--font-mono);">${workers.find(w=>w.id === 'worker-accel-02').vram} MB / 16384 MB</strong>
                </div>
                <div class="proc-progress-bg">
                  <div class="proc-progress-fill orange" style="width: ${(workers.find(w=>w.id === 'worker-accel-02').vram/16384)*100}%;"></div>
                </div>
              </div>

              <div style="background:rgba(255, 102, 0, 0.05); border:1px dashed rgba(255,102,0,0.25); border-radius:6px; padding:10px; margin-top:10px; font-size:11px; line-height:1.4; color:rgba(255,255,255,0.7);">
                <strong>🔒 Concurrency Gate Constraint:</strong> Hardware sessions capped at <strong>3 encodes max</strong> per GPU card to protect driver queues from thread lock exhaustion. Active streams: <strong>1</strong>.
              </div>
            </div>
          </div>
        </div>
      `;

    } else if (activeTab === "queues") {
      // 5. Queue Monitor
      viewport.innerHTML = `
        <div>
          <h3 style="font-size:16px; font-weight:850; text-transform:uppercase; margin:0;">Celery Broker Queue Monitor</h3>
          <p style="font-size:11px; color:rgba(255,255,255,0.45); margin:4px 0 0 0;">Redis server queues and message delivery rates.</p>
        </div>

        <div class="proc-glass-card" style="overflow-x:auto;">
          <table class="proc-table">
            <thead>
              <tr>
                <th>Queue Channel Name</th>
                <th>Message Broker</th>
                <th>Messages Queued</th>
                <th>Active Leased Tasks</th>
                <th>Allocated Node Count</th>
                <th>Dead-Letter (DLQ) Warnings</th>
              </tr>
            </thead>
            <tbody>
              ${Object.keys(queueStats).map(qName => {
                const q = queueStats[qName];
                return `
                  <tr>
                    <td style="font-family:var(--font-mono); font-weight:700; color:#fff;">${qName}</td>
                    <td><span class="proc-badge proc-badge-green" style="font-size:8px;">Online // Redis</span></td>
                    <td style="font-family:var(--font-mono); font-weight:700; color:${q.queued > 0 ? 'var(--proc-orange)' : '#fff'};">${q.queued}</td>
                    <td style="font-family:var(--font-mono);">${q.leased}</td>
                    <td style="font-family:var(--font-mono);">${q.activeWorkers} slots</td>
                    <td>
                      ${q.dleq > 0 ? `
                        <span class="proc-badge proc-badge-red">⚠️ ${q.dleq} Poison Jobs</span>
                      ` : `
                        <span class="proc-badge proc-badge-green">0 Alerts</span>
                      `}
                    </td>
                  </tr>
                `;
              }).join('')}
            </tbody>
          </table>
        </div>
      `;

    } else if (activeTab === "manifests") {
      // 6. Manifest Inspector
      viewport.innerHTML = `
        <div>
          <h3 style="font-size:16px; font-weight:850; text-transform:uppercase; margin:0;">Atomic Manifest Inspector</h3>
          <p style="font-size:11px; color:rgba(255,255,255,0.45); margin:4px 0 0 0;">Inspect playlist tags and GOP structure of generated stream manifests.</p>
        </div>

        <div style="display:grid; grid-template-columns:1fr 2fr; gap:20px;">
          <!-- Left: selector list -->
          <div style="display:flex; flex-direction:column; gap:12px;">
            <div class="proc-glass-card">
              <h4 style="font-size:11px; font-weight:800; text-transform:uppercase; margin-bottom:12px; color:var(--proc-blue);">Select Manifest File</h4>
              <div style="display:flex; flex-direction:column; gap:8px;">
                ${Object.keys(manifests).map(path => `
                  <button class="proc-btn proc-btn-secondary btn-select-manifest-path ${activeInspectorPath === path ? 'active' : ''}" data-path="${path}" style="text-align:left; font-size:10px; font-family:var(--font-mono); padding:8px 10px; text-transform:none; border-radius:4px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; ${activeInspectorPath === path ? 'border-color:var(--proc-blue); background:rgba(0,102,255,0.08);' : ''}" title="${path}">
                    ${path.split('/').pop()}
                  </button>
                `).join('')}
              </div>
            </div>

            <!-- Run dry run validator -->
            <div class="proc-glass-card" style="display:flex; flex-direction:column; gap:10px;">
              <h4 style="font-size:11px; font-weight:800; text-transform:uppercase; color:var(--proc-cyan);">Validator diagnostics</h4>
              <button class="proc-btn proc-btn-orange" id="btn-run-manifest-val">Validate Playlist GOP Alignment</button>
              <div id="manifest-val-results" style="font-size:11px; font-family:var(--font-mono); color:rgba(255,255,255,0.5);">
                Click validate to run integrity scanner...
              </div>
            </div>
          </div>

          <!-- Right: Code Viewer -->
          <div class="proc-glass-card blue-glow" style="display:flex; flex-direction:column; gap:12px;">
            <div style="display:flex; justify-content:space-between; align-items:center;">
              <span style="font-family:var(--font-mono); font-size:10px; color:var(--proc-cyan);">${activeInspectorPath}</span>
              <span class="proc-badge proc-badge-blue">READ-ONLY</span>
            </div>
            <pre style="background:#000; border:1px solid rgba(255,255,255,0.05); padding:16px; border-radius:6px; font-family:var(--font-mono); font-size:11px; color:#fff; overflow:auto; max-height:300px; line-height:1.5; margin:0;">${escapeHtml(manifests[activeInspectorPath])}</pre>
          </div>
        </div>
      `;

      bindManifestEvents();

    } else if (activeTab === "thumbnails") {
      // 7. Thumbnail Gallery
      viewport.innerHTML = `
        <div>
          <h3 style="font-size:16px; font-weight:850; text-transform:uppercase; margin:0;">Scrub bar keyframe sprites</h3>
          <p style="font-size:11px; color:rgba(255,255,255,0.45); margin:4px 0 0 0;">Scrub spritesheets and WebVTT indices generated dynamically by the thumbnail queue.</p>
        </div>

        <div style="display:flex; flex-direction:column; gap:20px;">
          ${thumbnailGallery.map(item => `
            <div class="proc-glass-card blue-glow" style="display:grid; grid-template-columns:1fr 2fr; gap:20px;">
              <div>
                <h4 style="font-size:13px; font-weight:800; color:#fff; margin:0 0 4px 0;">${item.title}</h4>
                <div style="font-family:var(--font-mono); font-size:9px; color:var(--proc-cyan); margin-bottom:12px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">${item.path}</div>

                <div style="display:flex; flex-direction:column; gap:6px; font-size:11px; color:rgba(255,255,255,0.5);">
                  <div>Spritesheet: <strong style="color:#fff;">${item.sprite}</strong></div>
                  <div>Mapping Track: <strong style="color:#fff;">${item.vtt}</strong></div>
                </div>
              </div>

              <!-- Sprites preview grid -->
              <div>
                <div style="font-size:10px; font-weight:700; color:rgba(255,255,255,0.4); text-transform:uppercase; margin-bottom:8px;">Extracted keyframe slices</div>
                <div style="display:flex; gap:10px; flex-wrap:wrap;">
                  ${item.keyframes.map((kf, i) => `
                    <div style="position:relative; width:90px; height:50px; background:linear-gradient(135deg, #0b1530, #142a5c); border:1px solid rgba(255,255,255,0.1); border-radius:4px; display:flex; align-items:center; justify-content:center; flex-direction:column; cursor:pointer;">
                      <span style="font-size:18px;">🖼️</span>
                      <span style="font-size:8px; font-family:var(--font-mono); color:rgba(255,255,255,0.6); position:absolute; bottom:2px; right:4px;">${i * 10}s</span>
                    </div>
                  `).join('')}
                </div>
              </div>
            </div>
          `).join('')}
        </div>
      `;

    } else if (activeTab === "timeline") {
      // 8. Processing Timeline
      const activeJob = jobs.find(j => j.id === selectedJobForTimeline) || failedJobs.find(j => j.id === selectedJobForTimeline) || retryJobs.find(j => j.id === selectedJobForTimeline) || jobs[0];

      // Define lifecycle steps
      const steps = ["QUEUED", "CLAIMED", "PROBING", "PROCESSING", "PACKAGING", "VALIDATING", "PUBLISHING", "COMPLETED"];
      const currentStepIndex = steps.indexOf(activeJob ? activeJob.status : "COMPLETED");

      viewport.innerHTML = `
        <div style="display:flex; justify-content:space-between; align-items:center;">
          <div>
            <h3 style="font-size:16px; font-weight:850; text-transform:uppercase; margin:0;">Processing Lifecycle timeline</h3>
            <p style="font-size:11px; color:rgba(255,255,255,0.45); margin:4px 0 0 0;">Sequential flow chart mapping job state transitions.</p>
          </div>
          <!-- Job Selector -->
          <select class="proc-btn proc-btn-secondary" id="select-timeline-job" style="padding:6px 12px;">
            ${[...jobs, ...failedJobs, ...retryJobs].map(j => `<option value="${j.id}" ${selectedJobForTimeline === j.id ? 'selected' : ''}>${j.file.substring(0,25)}... (${j.status})</option>`).join('')}
          </select>
        </div>

        ${activeJob ? `
          <div class="proc-glass-card blue-glow" style="display:flex; flex-direction:column; gap:20px; padding:24px;">
            <div style="display:flex; justify-content:space-between; font-size:12px; font-family:var(--font-mono); border-bottom:1px solid rgba(255,255,255,0.06); padding-bottom:12px;">
              <div>Job UUID: <strong style="color:var(--proc-cyan);">${activeJob.id}</strong></div>
              <div>Queue Node: <strong>${activeJob.queue}</strong></div>
              <div>Speed Factor: <strong>${activeJob.speed ? activeJob.speed + "x" : "--"}</strong></div>
            </div>

            <!-- Horizontal Stepper -->
            <div style="display:flex; justify-content:space-between; align-items:center; position:relative; margin:20px 0; overflow-x:auto; padding:10px 0;">
              <!-- connector Line -->
              <div style="position:absolute; top:24px; left:20px; right:20px; height:2px; background:rgba(255,255,255,0.08); z-index:1;"></div>

              ${steps.map((st, i) => {
                let circleBg = "rgba(4, 4, 8, 0.9)";
                let borderCol = "rgba(255, 255, 255, 0.1)";
                let textColor = "rgba(255, 255, 255, 0.4)";
                let isPulse = false;

                if (activeJob.status === "FAILED" && st === "FAILED") {
                  circleBg = "rgba(239, 68, 68, 0.2)";
                  borderCol = "#ef4444";
                  textColor = "#ef4444";
                } else if (i < currentStepIndex) {
                  circleBg = "rgba(0, 102, 255, 0.15)";
                  borderCol = "var(--proc-blue)";
                  textColor = "var(--proc-cyan)";
                } else if (i === currentStepIndex) {
                  circleBg = "var(--proc-blue)";
                  borderCol = "var(--proc-blue)";
                  textColor = "#ffffff";
                  isPulse = true;
                }

                return `
                  <div style="display:flex; flex-direction:column; align-items:center; gap:8px; z-index:2; width:80px; flex-shrink:0;">
                    <div style="width:30px; height:30px; border-radius:50%; background:${circleBg}; border:2px solid ${borderCol}; display:flex; align-items:center; justify-content:center; font-size:10px; font-weight:800; font-family:var(--font-mono); color:${textColor}; ${isPulse ? 'box-shadow:0 0 10px var(--proc-blue-glow);' : ''}">
                      ${i + 1}
                    </div>
                    <span style="font-size:9px; font-weight:800; text-transform:uppercase; color:${textColor}; text-align:center;">${st}</span>
                  </div>
                `;
              }).join('')}
            </div>

            <!-- Diagnostics logs for this job -->
            <div style="background:#000; border:1px solid rgba(255,255,255,0.05); border-radius:6px; padding:12px; font-family:var(--font-mono); font-size:11px; color:#10b981;">
              <div>[SYSTEM INFO] Initiating diagnostic trace for job ${activeJob.id.substring(0,8)}...</div>
              <div>[QUEUED] Job pushed to Broker at 2026-07-24T17:39:00Z.</div>
              ${currentStepIndex >= 1 ? `<div>[CLAIMED] Worker lease acquired. Lock established on Redis.</div>` : ''}
              ${currentStepIndex >= 2 ? `<div>[PROBING] ffprobe validated format: h264/aac stream. GOP: 60 frames.</div>` : ''}
              ${currentStepIndex >= 3 ? `<div>[PROCESSING] Active transcoding segments at ${activeJob.speed || 3.1}x speed factor.</div>` : ''}
              ${currentStepIndex >= 4 ? `<div>[PACKAGING] Master playlists created. Atomic manifest update scheduled.</div>` : ''}
            </div>
          </div>
        ` : ''}
      `;

      bindTimelineEvents();

    } else if (activeTab === "retries") {
      // 9. Retry Center
      viewport.innerHTML = `
        <div>
          <h3 style="font-size:16px; font-weight:850; text-transform:uppercase; margin:0;">Job Retry Manager</h3>
          <p style="font-size:11px; color:rgba(255,255,255,0.45); margin:4px 0 0 0;">Recoverable exceptions governed by exponential backoff policies.</p>
        </div>

        <div class="proc-glass-card" style="overflow-x:auto;">
          <table class="proc-table">
            <thead>
              <tr>
                <th>Job ID</th>
                <th>File Name</th>
                <th>Queue</th>
                <th>Attempt</th>
                <th>Next Scheduled Retry</th>
                <th>Exception Reason</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              ${retryJobs.length === 0 ? `
                <tr>
                  <td colspan="7" style="text-align:center; padding:32px; color:rgba(255,255,255,0.35);">
                    No jobs currently undergoing retry delay timers.
                  </td>
                </tr>
              ` : retryJobs.map(job => `
                <tr>
                  <td style="font-family:var(--font-mono); font-weight:700; color:var(--proc-cyan);">${job.id.substring(0,8)}...</td>
                  <td>${job.file}</td>
                  <td><span class="proc-badge proc-badge-gray">${job.queue.replace('transcode-','')}</span></td>
                  <td style="font-family:var(--font-mono);">${job.attempt} / ${job.max_attempts}</td>
                  <td style="font-family:var(--font-mono); color:var(--proc-orange);">
                    Re-enqueue in <strong>${job.seconds_remaining}s</strong> (Backoff: ${job.backoff_delay}s)
                  </td>
                  <td style="font-size:11px; color:rgba(255,255,255,0.6); max-width:250px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;" title="${job.error_message}">${job.error_message}</td>
                  <td>
                    <button class="proc-btn btn-force-retry" data-id="${job.id}" style="padding:4px 8px; font-size:10px; background:var(--proc-orange); border-color:var(--proc-border-orange);">Force Now</button>
                  </td>
                </tr>
              `).join('')}
            </tbody>
          </table>
        </div>
      `;

      bindRetryEvents();

    } else if (activeTab === "failures") {
      // 10. Failed Jobs
      viewport.innerHTML = `
        <div>
          <h3 style="font-size:16px; font-weight:850; text-transform:uppercase; margin:0;">Failed & Dead-Letter Jobs</h3>
          <p style="font-size:11px; color:rgba(255,255,255,0.45); margin:4px 0 0 0;">Terminal failures quarantined in dead-letter queues. Alerts are dispatched to system logs.</p>
        </div>

        <div class="proc-glass-card" style="overflow-x:auto;">
          <table class="proc-table">
            <thead>
              <tr>
                <th>Job ID</th>
                <th>File Name</th>
                <th>Queue Channel</th>
                <th>Error Code</th>
                <th>Error message</th>
                <th>Quarantined Date</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              ${failedJobs.length === 0 ? `
                <tr>
                  <td colspan="7" style="text-align:center; padding:32px; color:rgba(255,255,255,0.35);">
                    Clean status. No failed or quarantined jobs registered.
                  </td>
                </tr>
              ` : failedJobs.map(job => `
                <tr style="border-left: 2px solid #ef4444;">
                  <td style="font-family:var(--font-mono); font-weight:700; color:#ef4444;">${job.id.substring(0,8)}...</td>
                  <td style="font-weight:700; color:#fff;">${job.file}</td>
                  <td><span class="proc-badge proc-badge-gray">${job.queue.replace('transcode-','')}</span></td>
                  <td><span class="proc-badge proc-badge-red">${job.error_code}</span></td>
                  <td style="font-size:11px; color:rgba(255,255,255,0.6); max-width:260px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;" title="${job.error_message}">${job.error_message}</td>
                  <td style="font-family:var(--font-mono); font-size:11px; color:rgba(255,255,255,0.45);">${new Date(job.timestamp).toLocaleString()}</td>
                  <td>
                    <button class="proc-btn btn-re-enqueue" data-id="${job.id}" style="padding:4px 8px; font-size:10px; background:#10b981; border-color:rgba(16,185,129,0.2);">Re-enqueue</button>
                  </td>
                </tr>
              `).join('')}
            </tbody>
          </table>
        </div>
      `;

      bindFailuresEvents();

    } else if (activeTab === "performance") {
      // 11. Performance Analytics
      viewport.innerHTML = `
        <div>
          <h3 style="font-size:16px; font-weight:850; text-transform:uppercase; margin:0;">NOC Historical Performance Analytics</h3>
          <p style="font-size:11px; color:rgba(255,255,255,0.45); margin:4px 0 0 0;">Historical charts tracking transcode latency and speed indices.</p>
        </div>

        <div style="display:grid; grid-template-columns:1fr 1fr; gap:20px;">
          <!-- Speed Spline -->
          <div class="proc-glass-card blue-glow" style="display:flex; flex-direction:column; gap:12px;">
            <h4 style="font-size:12px; font-weight:800; text-transform:uppercase; color:var(--proc-blue);">Avg Transcode Speed Ratio (24h)</h4>
            <div style="height:180px;">
              <canvas id="canvas-perf-speed" width="400" height="170" style="width:100%; height:100%;"></canvas>
            </div>
            <div style="font-size:10px; color:rgba(255,255,255,0.45); text-align:center;">Values mapped in speed multipliers (e.g. 4.0x real-time media duration)</div>
          </div>

          <!-- Latency Spline -->
          <div class="proc-glass-card orange-glow" style="display:flex; flex-direction:column; gap:12px;">
            <h4 style="font-size:12px; font-weight:800; text-transform:uppercase; color:var(--proc-orange);">Segment Storage Origin Latency (24h)</h4>
            <div style="height:180px;">
              <canvas id="canvas-perf-latency" width="400" height="170" style="width:100%; height:100%;"></canvas>
            </div>
            <div style="font-size:10px; color:rgba(255,255,255,0.45); text-align:center;">Publication latency in seconds (ideal target &lt; 2.0s)</div>
          </div>
        </div>
      `;

      drawPerformanceCharts();
    }
  };

  // Event binders for active view pages
  const bindActiveJobsEvents = () => {
    // 1. Submit Mock VOD Job
    const btnSubmit = container.querySelector("#btn-trigger-mock-job");
    if (btnSubmit) {
      btnSubmit.addEventListener("click", async () => {
        const randId = "job-" + Math.random().toString(36).substring(2,10) + "-4a12";
        const fileNames = [
          "somalia_economy_reconstruction_VOD.mp4",
          "mogadishu_culture_festival_4k.mov",
          "national_news_nightly_broadcast.mkv",
          "hargeisa_tech_summit_keynote.mp4"
        ];
        const selectedFile = fileNames[Math.floor(Math.random() * fileNames.length)];
        const isGPU = Math.random() < 0.6;

        if (apiConnected) {
          try {
            await processingRequest("/jobs", {
              method: "POST",
              body: JSON.stringify({
                idempotency_key: `studio-${crypto.randomUUID()}`,
                job_type: "vod_transcode",
                input_url: selectedFile,
                output_prefix: `studio/${crypto.randomUUID()}`,
                renditions: isGPU ? ["1080p", "720p", "480p"] : ["720p", "480p"],
                queue: isGPU ? "transcode-accelerated" : "transcode-cpu",
                max_attempts: 3
              })
            });
            await refreshProcessingApi();
            addLog(`New media job accepted by the Processing API: ${selectedFile}.`);
          } catch (error) {
            addLog(`[API ERROR] ${error.message}`);
          }
          return;
        }

        jobs.push({
          id: randId,
          file: selectedFile,
          queue: isGPU ? "transcode-accelerated" : "transcode-cpu",
          resolutions: isGPU ? ["1080p", "720p", "480p"] : ["720p", "480p"],
          progress: 0,
          speed: 0,
          fps: 0,
          elapsed: 0,
          status: "QUEUED",
          worker: "Unassigned",
          error: null
        });

        addLog(`New media job enqueued: ${selectedFile} placed in ${isGPU ? 'GPU' : 'CPU'} queue.`);
        renderActiveTab();
      });
    }

    // 2. Cancel Active Job
    container.querySelectorAll(".btn-cancel-job").forEach(btn => {
      btn.addEventListener("click", async () => {
        const id = btn.getAttribute("data-id");
        const idx = jobs.findIndex(j => j.id === id);
        if (idx > -1) {
          const job = jobs[idx];
          if (apiConnected) {
            try {
              await processingRequest(`/jobs/${id}`, { method: "DELETE" });
              addLog(`[API] Cancellation accepted for job ${id.substring(0,8)}.`);
              await refreshProcessingApi();
            } catch (error) {
              addLog(`[API ERROR] ${error.message}`);
            }
            return;
          }
          addLog(`[SIGTERM] operator commanded shutdown for job ${id.substring(0,8)}. Releasing container mounts...`);

          // Move to Failed/Cancelled Registry
          failedJobs.push({
            id: job.id,
            file: job.file,
            queue: job.queue,
            error_code: "ERR_OPERATOR_CANCELLED",
            error_message: "SIGKILL signal dispatched: Media transcode session cancelled by console administrator.",
            timestamp: new Date().toISOString()
          });

          jobs.splice(idx, 1);
          renderActiveTab();
        }
      });
    });

    // 3. View timeline link
    container.querySelectorAll(".view-job-timeline-link").forEach(link => {
      link.addEventListener("click", (e) => {
        e.preventDefault();
        selectedJobForTimeline = link.getAttribute("data-id");
        activeTab = "timeline";
        // Shift active link in sidebar
        container.querySelectorAll(".proc-noc-nav-item").forEach(b => b.classList.toggle("active", b.getAttribute("data-tab") === "timeline"));
        renderActiveTab();
      });
    });
  };

  const bindFleetEvents = () => {
    // Container reboot simulation
    container.querySelectorAll(".btn-reboot-worker").forEach(btn => {
      btn.addEventListener("click", () => {
        const id = btn.getAttribute("data-id");
        const worker = workers.find(w => w.id === id);
        if (worker) {
          const prevStatus = worker.status;
          worker.status = "IDLE";
          worker.cpu = 0.0;
          worker.gpu = 0.0;
          worker.heartbeat = 0;
          addLog(`[CLUSTER] cycling Docker container workspace namespace for node "${id}"...`);

          setTimeout(() => {
            worker.status = prevStatus;
            addLog(`[CLUSTER] Worker node "${id}" re-registered successfully to Celery broker.`);
            renderActiveTab();
          }, 3000);

          renderActiveTab();
        }
      });
    });
  };

  const bindManifestEvents = () => {
    // 1. Select path
    container.querySelectorAll(".btn-select-manifest-path").forEach(btn => {
      btn.addEventListener("click", () => {
        activeInspectorPath = btn.getAttribute("data-path");
        renderActiveTab();
      });
    });

    // 2. Validate manifest check
    const btnVal = container.querySelector("#btn-run-manifest-val");
    const valResults = container.querySelector("#manifest-val-results");
    if (btnVal && valResults) {
      btnVal.addEventListener("click", async () => {
        if (apiConnected) {
          valResults.innerHTML = `<span style="color:var(--proc-orange);">Validating manifest through Processing API...</span>`;
          try {
            const result = await processingRequest("/manifests/validate", {
              method: "POST",
              body: JSON.stringify({ manifest_url: activeInspectorPath })
            });
            valResults.innerHTML = result.valid
              ? `<span style="color:#10b981;">✓ ${result.conformance}</span>`
              : `<span style="color:#ef4444;">✕ ${result.validations.warnings.join("; ")}</span>`;
          } catch (error) {
            valResults.innerHTML = `<span style="color:#ef4444;">✕ ${error.message}</span>`;
          }
          return;
        }
        valResults.innerHTML = `<span style="color:var(--proc-orange);">Scanning manifest segments...</span>`;
        setTimeout(() => {
          valResults.innerHTML = `
            <div style="color:#10b981; font-weight:700;">✓ PASSED PLAYLIST CONFORMANCE CHECK</div>
            <div style="margin-top:6px; font-size:10px;">
              • GOP Alignment: 100% Correct (GOP: 60)<br>
              • Bandwidth tags: Matching representations<br>
              • Encryption method: AES-128 (Secure handshake)<br>
              • Conforms to schema: RFC-8216
            </div>
          `;
        }, 1200);
      });
    }
  };

  const bindTimelineEvents = () => {
    const selector = container.querySelector("#select-timeline-job");
    if (selector) {
      selector.addEventListener("change", (e) => {
        selectedJobForTimeline = e.target.value;
        renderActiveTab();
      });
    }
  };

  const bindRetryEvents = () => {
    container.querySelectorAll(".btn-force-retry").forEach(btn => {
      btn.addEventListener("click", () => {
        const id = btn.getAttribute("data-id");
        const idx = retryJobs.findIndex(j => j.id === id);
        if (idx > -1) {
          const rj = retryJobs[idx];
          addLog(`[FORCE] Bypassing backoff delay. Placing job ${id.substring(0,8)} back to QUEUED status...`);

          jobs.push({
            id: rj.id,
            file: rj.file,
            queue: rj.queue,
            resolutions: ["1080p", "720p", "480p"],
            progress: 0,
            speed: 0,
            fps: 0,
            elapsed: 0,
            status: "QUEUED",
            worker: "Unassigned",
            error: null
          });

          retryJobs.splice(idx, 1);
          renderActiveTab();
        }
      });
    });
  };

  const bindFailuresEvents = () => {
    container.querySelectorAll(".btn-re-enqueue").forEach(btn => {
      btn.addEventListener("click", () => {
        const id = btn.getAttribute("data-id");
        const idx = failedJobs.findIndex(j => j.id === id);
        if (idx > -1) {
          const fj = failedJobs[idx];
          addLog(`[RE-ENQUEUE] Re-publishing task for quarantined file ${fj.file} to broker.`);

          jobs.push({
            id: fj.id,
            file: fj.file,
            queue: fj.queue,
            resolutions: ["1080p", "720p", "480p"],
            progress: 0,
            speed: 0,
            fps: 0,
            elapsed: 0,
            status: "QUEUED",
            worker: "Unassigned",
            error: null
          });

          failedJobs.splice(idx, 1);
          renderActiveTab();
        }
      });
    });
  };

  // Helper to escape HTML characters in Manifest Code Viewer
  const escapeHtml = (text) => {
    return text
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  };

  // Initialize
  render();
  refreshProcessingApi();

  // Return cleanup method to be executed when tab changes
  return () => {
    if (simulationInterval) clearInterval(simulationInterval);
    if (systemClockInterval) clearInterval(systemClockInterval);
  };
}
