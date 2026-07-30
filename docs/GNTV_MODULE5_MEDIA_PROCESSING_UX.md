# GNTV DIGITAL — Processing Operations Center (NOC) UX & API Specification

**Module:** 5 — Distribution, Streaming & Geo-Fencing Platform
**Sprint:** 5.3 — Media Processing & Packaging
**Document Code:** GNTV-MOD5-MPUX-01
**Status:** APPROVED / IMPLEMENTATION SPECIFICATION

---

## 1. Design System & Visual Guidelines

The Processing Operations Center (NOC) is built as a high-density, real-time control interface engineered for enterprise broadcast monitors, large network wall displays (NOC display walls), and responsive desktop screens.

### 1.1 Color Tokens (Blue / Orange / Black)
The color palette deliberately departs from the consumer app's red branding to reduce cognitive fatigue and emphasize high-throughput computing operations.

| Token | CSS Variable Value | HEX Value | Semantic Usage |
| :--- | :--- | :---: | :--- |
| **Onyx Black** | `#020205` / `hsl(240, 30%, 2%)` | `#020205` | Primary application canvas, infinite depth base. |
| **Signal Blue** | `#0066ff` / `hsl(215, 100%, 50%)` | `#0066ff` | Core telemetry, standard operations, network status. |
| **Neon Blue Glow** | `rgba(0, 102, 255, 0.45)` | — | Glassmorphic card borders, highlights, hover glow. |
| **Warning Orange** | `#ff6600` / `hsl(24, 100%, 50%)` | `#ff6600` | Alert states, GPU concurrency limits, queue warnings, retries. |
| **Neon Orange Glow** | `rgba(255, 102, 0, 0.45)` | — | Active failure borders, high-temperature indicators, retries. |
| **Cyber Cyan** | `#00d2ff` / `hsl(190, 100%, 50%)` | `#00d2ff` | Real-time speeds, data flow lines, manifest paths. |
| **Semantic Green** | `#10b981` | `#10b981` | Completed jobs, healthy workers, valid manifests. |
| **Semantic Red** | `#ef4444` | `#ef4444` | Terminally failed jobs, dead-letter alerts, SIGKILL commands. |

### 1.2 Glassmorphism & Elevation
To convey state-of-the-art technological depth, all panels utilize a layered glassmorphic design:
- **Card Background:** `rgba(10, 10, 18, 0.75)` with `backdrop-filter: blur(25px)`.
- **Card Border:** `1px solid rgba(255, 255, 255, 0.08)` or `1px solid var(--brand-primary)` transitions on active focus.
- **Hover Micro-Animations:** Focus triggers a subtle $1.02\times$ scale-up and an outer box-shadow glow using the corresponding accent color.

### 1.3 Typography
- **Headings & Labels:** **Outfit** (geometric sans-serif) for high legibility on projection walls.
- **Telemetry & Logs:** **JetBrains Mono** (monospaced) for strict character alignment of speeds, frames, bitrates, and UUID keys.

---

## 2. Interactive Screens (The 11 Pages)

### 2.1 Processing Dashboard (Overview)
- **Visuals:** Layout optimized for a 2-column grid or wall displays. The top row features large-format KPI blocks:
  - **Active Transcodes:** Large number, neon blue indicator.
  - **Queued Messages:** Large number, warnings if $> 20$ (orange).
  - **Cluster Health:** Online/offline ratio of transcode nodes.
  - **Speed Factor:** Average performance metric.
- **Charts:** A dual-axis SVG plot visualizing Broker Queue Traffic (blue spline line) alongside Active transcode sessions (orange vertical bars).
- **Log Feed:** Live, non-blocking rolling console listing timestamps, event codes, and job state updates.

### 2.2 Active Jobs
- **Visuals:** Structured data grid. Each row displays:
  - **Job ID:** Clickable link displaying detail drawer.
  - **Input Source:** Text path, sanitized.
  - **Queues:** `transcode-cpu` or `transcode-accelerated`.
  - **Resolution Ladder:** Badge elements representing target outputs (e.g. `1080p`, `720p`, `480p`).
  - **Progress Bar:** Real-time animating blue bar with percentage indicator.
  - **Metrics:** Speed factor (e.g., `3.2x`) and current frame count.
- **Actions:** Safe "Cancel" button, which issues a sequential `SIGTERM` followed by a `SIGKILL` to the virtual worker process.

### 2.3 Worker Fleet
- **Visuals:** Grid of compute cards representing active Docker container namespaces in the cluster.
- **Card Telemetry:** Hostname, node type (e.g., `Docker Namespace Node 02`), hardware profile (e.g., `NVIDIA NVENC T4`), status (`IDLE`, `PROBING`, `PROCESSING`), and age of last heartbeat.
- **Actions:** "Reboot Worker" (simulates Docker namespace cycle) and "Decommission Node".

### 2.4 CPU/GPU Utilization
- **Visuals:** Graphic telemetry monitors for hardware states.
  - **CPU Utilization:** Radial dial gauge showing cluster average load.
  - **GPU Utilization:** Side-by-side progress gauges tracking GPU Load, VRAM Load, Encoder Load, and Decoder Load.
- **Hardware Profile:** Details NVENC cap warning banners (max 3 concurrent encoder streams) and Intel QSV VAAPI driver paths.

### 2.5 Queue Monitor
- **Visuals:** Dedicated column layout representing the 6 Celery queues:
  - `transcode-cpu` (Standard transcode VOD/Live)
  - `transcode-accelerated` (GPU accelerated transcodes)
  - `manifest` (HLS/DASH manifest high I/O updates)
  - `thumbnail` (Keyframes and WebVTT sprite builders)
  - `recording` (Live archiving streams)
  - `maintenance` (Disk purging, dead-letter cleanup)
- **Metrics:** Broker connection state, enqueued items, lease rate, and dead-letter count.

### 2.6 Manifest Inspector
- **Visuals:** split-pane explorer.
  - **Left Pane:** File directory navigation under the private OSS layout (e.g., `tenant_gntv/channels/{id}/sessions/{id}/`).
  - **Right Pane:** Read-only syntax-highlighted editor showing generated `master.m3u8` or `manifest.mpd` contents.
- **Validator Engine:** Interactive button triggers mock HLS/DASH parser checks, asserting GOP alignment, AES-128 KMS gates, and segment duration boundaries.

### 2.7 Thumbnail Gallery
- **Visuals:** Grid layout representing catalog thumbnail sets.
- **Cards:** Display name of catalog item, keyframe snapshots (0s, 10s, 20s, etc.), sprite sheet preview, and VTT mapping script details.
- **Metadata:** Shows resolution, file size, and target path coordinates upon hover.

### 2.8 Processing Timeline
- **Visuals:** Horizontal state-machine flow diagram mapping the lifecycle of selected jobs.
- **Phases:** `QUEUED` ➔ `CLAIMED` ➔ `PROBING` ➔ `PROCESSING` ➔ `PACKAGING` ➔ `VALIDATING` ➔ `PUBLISHING` ➔ `COMPLETED`.
- **States:** Interactive tooltip showing elapsed durations at each phase, and red-highlighted alert zones if a state falls into `FAILED` or `RETRYING`.

### 2.9 Retry Center
- **Visuals:** Registry of jobs recovering from transient errors (e.g. storage network timeout).
- **Details:** Displays retry attempts (e.g. `2 / 3`), delay duration calculated via exponential backoff formula, and the string message of the recoverable exception.
- **Actions:** "Force Retry Now" (bypasses remaining backoff time) and "Skip to Quarantine".

### 2.10 Failed Jobs
- **Visuals:** High-contrast error registry. Row colors are tinted with subtle red boundaries.
- **Columns:** Job ID, Source File, Terminal State, Error Code (e.g., `ERR_CODEC_NOT_SUPPORTED`), stack trace snippet, and quarantine storage link.
- **Actions:** "Re-enqueue Job" (clears failure state and places back to `QUEUED`) and "View Logs".

### 2.11 Performance Analytics
- **Visuals:** High-density historical reports.
  - **Speed Spline Chart:** Visualizes encoding speeds across CPU/GPU over the last 24h.
  - **Latency Spline Chart:** Segment publication latency to storage origin (ideal target $< 2.0\text{s}$).
  - **Freshness Gauge:** Live drift indicator between manifest timestamp and wall clock.

---

## 3. Future API Boundaries

Although the current sprint operates as a standalone UI sandbox without backend integration, it is designed to strictly conform to future API contracts. The following sections outline the endpoint boundaries.

### 3.1 REST API Controller Endpoints

#### 1. Enqueue Media Processing Job
- **Endpoint:** `POST /api/v1/processing/jobs`
- **Authentication:** Bearer token (JWT with `admin` or `operator` role).
- **Request Payload (`application/json`):**
  ```json
  {
    "idempotency_key": "idem_vod_transcode_10294",
    "job_type": "vod_transcode",
    "input_url": "rtmp://ingest.gntv.net/raw/file_1029.mp4",
    "renditions": ["1080p", "720p", "480p"],
    "output_prefix": "tenant_gntv/vod/channels/ch_sports/sessions/sess_1029/",
    "aes_encryption": {
      "enabled": true,
      "key_url": "https://api.gntv.tv/api/v1/streaming/playback/key/ch_sports",
      "iv": "0x000102030405060708090a0b0c0d0e0f"
    },
    "max_attempts": 3
  }
  ```
- **Response Payload (`202 Accepted`):**
  ```json
  {
    "job_id": "job_9f8e7d6c-5b4a-3b2c-1d0e-9f8e7d6c5b4a",
    "status": "QUEUED",
    "attempt": 1,
    "created_at": "2026-07-24T17:39:00.000Z"
  }
  ```

#### 2. Retrieve Active Job Status
- **Endpoint:** `GET /api/v1/processing/jobs/{job_id}`
- **Response Payload (`200 OK`):**
  ```json
  {
    "job_id": "job_9f8e7d6c-5b4a-3b2c-1d0e-9f8e7d6c5b4a",
    "status": "PROCESSING",
    "progress": 68.5,
    "metrics": {
      "fps": 29.97,
      "speed_factor": 3.2,
      "frame_drops": 0,
      "elapsed_seconds": 124,
      "estimated_remaining_seconds": 45
    },
    "worker_id": "worker-accel-node-02"
  }
  ```

#### 3. Cancel Active Processing Job
- **Endpoint:** `DELETE /api/v1/processing/jobs/{job_id}`
- **Response Payload (`200 OK`):**
  ```json
  {
    "job_id": "job_9f8e7d6c-5b4a-3b2c-1d0e-9f8e7d6c5b4a",
    "status": "CANCELLED",
    "terminated_at": "2026-07-24T17:40:02.100Z"
  }
  ```

#### 4. List Worker Fleet Nodes
- **Endpoint:** `GET /api/v1/processing/workers`
- **Response Payload (`200 OK`):**
  ```json
  [
    {
      "worker_id": "worker-accel-node-02",
      "hostname": "transcode-acc-02",
      "queue": "transcode-accelerated",
      "status": "PROCESSING",
      "last_heartbeat": "2026-07-24T17:40:00Z",
      "hardware": {
        "device": "NVIDIA NVENC T4",
        "cpu_usage_pct": 34.2,
        "gpu_usage_pct": 68.0,
        "vram_allocated_mb": 4096,
        "temperature_celsius": 62
      }
    }
  ]
  ```

#### 5. Retrieve Queue Broker Telemetry
- **Endpoint:** `GET /api/v1/processing/queues`
- **Response Payload (`200 OK`):**
  ```json
  {
    "broker": "Redis Core Node 01 (Online)",
    "queues": {
      "transcode-cpu": { "messages_queued": 14, "lease_rate_per_min": 2.5, "active_workers": 6 },
      "transcode-accelerated": { "messages_queued": 2, "lease_rate_per_min": 1.2, "active_workers": 4 },
      "manifest": { "messages_queued": 0, "lease_rate_per_min": 14.5, "active_workers": 2 }
    }
  }
  ```

#### 6. dry-run Manifest Validation Check
- **Endpoint:** `POST /api/v1/processing/manifests/validate`
- **Request Payload (`application/json`):**
  ```json
  {
    "manifest_url": "tenant_gntv/channels/ch01/sessions/sess_102/master.m3u8"
  }
  ```
- **Response Payload (`200 OK`):**
  ```json
  {
    "valid": true,
    "conformance": "HLS H.264 ABR Ladder Conforming",
    "validations": {
      "gop_alignment": "PASSED",
      "bandwidth_tags": "PASSED",
      "aes_encryption_key": "SECURED",
      "warnings": []
    }
  }
  ```

---

### 3.2 Celery Task Message Broker Contract

Messages pushed to the message broker (Redis/RabbitMQ) for transcoding workers conform to the following schema:
- **Broker Route Key:** `celery.transcode`
- **Message Headers:**
  ```json
  {
    "task": "gntv.tasks.media.transcode",
    "id": "job_9f8e7d6c-5b4a-3b2c-1d0e-9f8e7d6c5b4a",
    "lang": "py",
    "retries": 0,
    "root_id": "job_9f8e7d6c-5b4a-3b2c-1d0e-9f8e7d6c5b4a"
  }
  ```
- **Message Body (Base64 Encoded JSON Args):**
  ```json
  [
    {
      "job_id": "job_9f8e7d6c-5b4a-3b2c-1d0e-9f8e7d6c5b4a",
      "input_url": "rtmp://127.0.0.1:1935/live/ch01_active",
      "renditions": ["1080p", "720p", "480p"],
      "output_prefix": "tenant_gntv/channels/ch01/sessions/sess_20260722/",
      "aes_encryption": { "enabled": true }
    }
  ]
  ```

---

### 3.3 Redis Real-time Pub/Sub Channels

Active workers broadcast metrics continuously onto Redis Pub/Sub channels to enable the Processing Center dashboard to update without polling databases.

#### Channel Name: `gntv.events.processing`
- **Payload: `job.processing`** (published every 2.0 seconds during transcode):
  ```json
  {
    "event_id": "evt_p1o2i3u4",
    "event_type": "job.processing",
    "job_id": "job_9f8e7d6c-5b4a-3b2c-1d0e-9f8e7d6c5b4a",
    "timestamp": "2026-07-24T17:41:00.000Z",
    "metrics": {
      "fps": 29.97,
      "speed_factor": 3.12,
      "frame_drops": 0,
      "current_time_ms": 240500,
      "resolution": "1920x1080"
    }
  }
  ```
- **Payload: `job.completed`** (published upon job terminal success):
  ```json
  {
    "event_id": "evt_c9a8b7c6",
    "event_type": "job.completed",
    "job_id": "job_9f8e7d6c-5b4a-3b2c-1d0e-9f8e7d6c5b4a",
    "timestamp": "2026-07-24T17:42:15.000Z",
    "total_duration_seconds": 159.2,
    "manifest_master_url": "tenant_gntv/channels/ch01/sessions/sess_20260722/master.m3u8"
  }
  ```
- **Payload: `job.failed`** (published on fatal failure):
  ```json
  {
    "event_id": "evt_f2e3d4c5",
    "event_type": "job.failed",
    "job_id": "job_9f8e7d6c-5b4a-3b2c-1d0e-9f8e7d6c5b4a",
    "timestamp": "2026-07-24T17:41:10.000Z",
    "error_code": "ERR_WRITE_TIMEOUT",
    "error_message": "OSS upload speed dropped below 100 KB/s for 15.0 seconds. Connection aborted."
  }
  ```
