# GNTV DIGITAL Platform — Alibaba Cloud Staging Architecture & Deployment Blueprint

**Release Baseline**: `v0.9.0-rc1` (Base Commit: `76037fb`)  
**Target Environment**: Alibaba Cloud Staging  
**Primary Domain**: `gntvdigital.com`  

---

## 1. Executive Summary

This blueprint defines the architecture, configuration, containerization, database provisioning, and operational procedures for deploying **GNTV DIGITAL v0.9.0-rc1** to a dedicated Alibaba Cloud Staging environment.

In accordance with release engineering and security rules:
- Staging begins on a **NEW, EMPTY managed PostgreSQL database** (`gntv_media_hub_staging`).
- The developer's local PostgreSQL database containing prototype/historical artifacts is **strictly excluded**.
- The complete Alembic migration sequence executes from base to head `202609211200`.
- External publishing adapters remain in deterministic **MOCK mode** (no live credentials for YouTube, TikTok, Facebook, Instagram, or X).
- Disaster Recovery and health monitoring operate within the staging application boundary without mutating production infrastructure.

---

## 2. Target Architecture Topology

```
                         [ Internet Users / QA / Operators ]
                                        │
                                        ▼ HTTPS (Port 443)
                         [ Alibaba Cloud DNS (Alidns) ]
                     ├── api-staging.gntvdigital.com
                     └── studio-staging.gntvdigital.com
                                        │
                                        ▼
                  [ Application Load Balancer (ALB / SLB) ]
                  (SSL Termination / HTTP -> HTTPS Redirect)
                         │                          │
                         │ Forward /api & /ws       │ Forward /*
                         ▼                          ▼
          ┌───────────────────────────┐    ┌───────────────────────────┐
          │  Backend API ECS / ACK    │    │  Frontend Studio ECS/ACK  │
          │  (FastAPI ASGI - Port 8000)│   │  (Nginx SPA - Port 80)    │
          └─────────────┬─────────────┘    └───────────────────────────┘
                        │
                        │ Internal Private VPC Communication
                        ├──────────────────────────┐
                        ▼                          ▼
         ┌─────────────────────────────┐  ┌─────────────────────────────┐
         │ Durable Worker Container(s) │  │  Scheduler Container        │
         │ (Job Execution & Triggers)  │  │  (Singleton Cron Leader)    │
         └──────────────┬──────────────┘  └──────────────┬──────────────┘
                        │                                │
                        └───────────────┬────────────────┘
                                        ▼
             ┌─────────────────────────────────────────────────────┐
             │       Alibaba Cloud VPC (172.16.0.0/16 Private)     │
             │                                                     │
             │  ┌───────────────────────────────────────────────┐  │
             │  │ ApsaraDB RDS for PostgreSQL (v15+)            │  │
             │  │ Database: gntv_media_hub_staging              │  │
             │  │ Private VPC Endpoint: 172.16.1.10:5432        │  │
             │  └───────────────────────────────────────────────┘  │
             │                                                     │
             │  ┌───────────────────────────────────────────────┐  │
             │  │ ApsaraDB for Redis (v7.0)                     │  │
             │  │ Cache, Locks & WebSocket Pub/Sub              │  │
             │  │ Private VPC Endpoint: 172.16.1.20:6379        │  │
             │  └───────────────────────────────────────────────┘  │
             │                                                     │
             │  ┌───────────────────────────────────────────────┐  │
             │  │ Alibaba Cloud OSS (Object Storage)            │  │
             │  │ Bucket: gntv-staging-media (Private)          │  │
             │  └───────────────────────────────────────────────┘  │
             └─────────────────────────────────────────────────────┘
```

---

## 3. Subdomain & DNS Plan

| Domain Name | Role / Target | Traffic Type | Ports |
| :--- | :--- | :--- | :--- |
| `studio-staging.gntvdigital.com` | Operator & Creator Back-Office Studio SPA | Public HTTPS | 443 -> Nginx (80) |
| `api-staging.gntvdigital.com` | Backend REST API & WebSockets (`/ws/chat`) | Public HTTPS / WSS | 443 -> FastAPI (8000) |
| `stream-staging.gntvdigital.com` | Staging Media Playback / CDN Endpoint | HTTPS / HLS | 443 -> OSS / Edge |

*Note: Production domain `gntvdigital.com` and `api.gntvdigital.com` remain completely untouched.*

---

## 4. Workload Process Separation

To ensure predictable scaling and prevent race conditions, the backend container is deployed into three distinct execution roles:

1. **Web API Role (`api`)**:
   - Command: `uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips=*`
   - Handles REST requests, public webhooks, WebSocket subscriptions, health probes.
   - Horizontally scalable.

2. **Durable Worker Role (`worker`)**:
   - Command: `python -m app.modules.jobs.worker` (or `python -m app.modules.jobs.worker_runner`)
   - Picks up pending jobs from `jobs` table, executes allowlisted `SafeJobType` handlers, handles retries and dead-lettering via `DatabaseJobQueue`.
   - Horizontally scalable.

3. **Distributed Scheduler Role (`scheduler`)**:
   - Command: `python -m app.modules.jobs.scheduler` (or `python -m app.modules.jobs.scheduler_runner`)
   - Evaluates cron and interval schedules from `job_schedules` table, emits periodic health check and autopilot trigger jobs.
   - **Concurrency Safety**: Employs PostgreSQL row-level locks (`SELECT FOR UPDATE SKIP LOCKED` on `job_schedules`) and `claim_expires_at` lease timestamps to prevent duplicate job generation.

4. **Health Check & Probing Contract**:
   - The `/health` endpoint checks **readiness** (both PostgreSQL and Redis connectivity must return healthy).
   - ALB target groups and container orchestrators should use `/health` as a readiness probe. Container-level liveness relies on process monitoring (e.g., container runtime restart policy). Separate `/health/live` probe is reserved for future enhancements.

---

## 5. Security & Isolation Matrix

- **Network Security Groups**:
  - Load Balancer: Open 80 (redirects to 443) and 443 from Internet.
  - Backend / Studio ECS: Allow incoming traffic *only* from the ALB Security Group.
  - RDS PostgreSQL: Allow incoming 5432 *only* from Backend/Worker ECS Private IP block. Zero public internet IP assigned.
  - Redis: Allow incoming 6379 *only* from Backend/Worker ECS Private IP block.
- **Storage Security**:
  - OSS staging bucket `gntv-staging-media` is strictly **Private**. Read access uses signed expiring URLs; write access uses RAM role temporary credentials.
