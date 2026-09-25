# GNTV DIGITAL — Staging Deployment Smoke Test Suite

**Target Environment**: Alibaba Cloud Staging  
**Endpoints**:
- Studio: `https://studio-staging.gntvdigital.com`
- API: `https://api-staging.gntvdigital.com`

---

## 1. System Liveness & Dependency Readiness

- [ ] **API Readiness**:
  ```bash
  curl -s -f https://api-staging.gntvdigital.com/health | jq .
  # Expected: {"status": "ok", "database": "connected", "redis": "connected"}
  ```
- [ ] **Reliability Engine Snapshot**:
  ```bash
  curl -s -f -H "Authorization: Bearer $OPERATOR_TOKEN" https://api-staging.gntvdigital.com/api/v1/reliability/health/current | jq .
  # Expected: status 200, system overall_status = "HEALTHY" or "DEGRADED"
  ```
- [ ] **OpenAPI Specification**:
  ```bash
  curl -s -o /dev/null -w "%{http_code}\n" https://api-staging.gntvdigital.com/openapi.json
  # Expected: 200
  ```

---

## 2. Frontend Studio Verification

- [ ] **HTTPS Asset Loading**:
  - Open `https://studio-staging.gntvdigital.com` in a browser.
  - Verify TLS certificate is valid (`*.gntvdigital.com`).
  - Open browser DevTools Network tab: verify static JS/CSS bundles load with 200 OK without console errors.
- [ ] **No Localhost Leaks**:
  - Verify all outbound XHR/Fetch calls target `https://api-staging.gntvdigital.com` (0 calls to `localhost:8000`).
- [ ] **Navigation & Subsystem Mounting**:
  - Log in with operator credentials.
  - Verify access to tabs:
    - ⚡ Workflow Operations
    - 🔔 Event Automation
    - 🧰 Background Jobs
    - 🤖 AI Agents
    - 🛫 Autopilot
    - 🛡️ Reliability & DR

---

## 3. Workflow Orchestration & Durable Workers

- [ ] **Workflow Creation & Run (Sprint 8.1)**:
  - Submit a test workflow execution via API:
    ```bash
    curl -X POST https://api-staging.gntvdigital.com/api/v1/workflows/runs \
      -H "Authorization: Bearer $OPERATOR_TOKEN" \
      -H "Content-Type: application/json" \
      -d '{"workflow_id": "'"$TEST_WORKFLOW_ID"'", "input_data": {"test": true}}'
    ```
  - Verify run transitions from `PENDING` -> `RUNNING` -> `COMPLETED`.
- [ ] **Durable Worker Heartbeat (Sprint 8.3)**:
  - Query worker status:
    ```bash
    curl -s -H "Authorization: Bearer $OPERATOR_TOKEN" https://api-staging.gntvdigital.com/api/v1/jobs/workers | jq .
    ```
  - Verify at least one worker is `ONLINE` with active heartbeat within the last 60 seconds.

---

## 4. Event Bus & Webhook Security (Sprint 8.2)

- [ ] **Event Publishing & Dispatch**:
  - Publish internal test event:
    ```bash
    curl -X POST https://api-staging.gntvdigital.com/api/v1/events/publish \
      -H "Authorization: Bearer $OPERATOR_TOKEN" \
      -H "Content-Type: application/json" \
      -d '{"event_type": "content.created", "source": "staging_smoke_test", "correlation_id": "smoke-test-1", "idempotency_key": "smoke-idem-1", "payload": {}}'
    ```
  - Verify status 200 and event persisted in `events` table.
- [ ] **Inbound Webhook Security Isolation**:
  - Attempt sending external webhook mapped to `reliability.test`:
  - Verify API responds with `422 Unprocessable Entity` (external webhooks forbidden from triggering reliability events).

---

## 5. AI Agent & Autopilot Boundaries (Sprints 8.4 & 8.5)

- [ ] **AI Agent Control Plane**:
  - Verify tool registry exposes only allowlisted tools.
  - Execute a bounded test agent task: verify audit log emitted without shell or code execution.
- [ ] **Autopilot Production Flow**:
  - Create test brief -> generate test script -> compile production plan.
  - Verify status advances through states.
  - Verify **Human Approval Gate**: attempt publishing without approval -> verify rejected with `400 / 422`.
  - Approve publication -> trigger publish -> verify dispatch uses **MOCK** adapter with provider reference returned.
  - **Zero calls to live YouTube/TikTok/Facebook/X endpoints.**

---

## 6. Reliability, Incidents & Disaster Recovery (Sprint 8.6)

- [ ] **Incident Lifecycle**:
  - Create test incident via `/api/v1/reliability/incidents`.
  - Acknowledge incident -> verify state transitions to `ACKNOWLEDGED`.
  - Resolve incident with post-mortem notes -> verify state transitions to `RESOLVED`.
- [ ] **DR Readiness Check**:
  - Trigger DR readiness assessment:
    ```bash
    curl -X POST https://api-staging.gntvdigital.com/api/v1/reliability/dr/readiness-check \
      -H "Authorization: Bearer $OPERATOR_TOKEN"
    ```
  - Verify response evaluates RTO/RPO objectives without triggering actual infrastructure failover.

---

## 7. Data Durability Across Container Restart

- [ ] Restart backend API and worker containers on ECS.
- [ ] Query incident and workflow runs created in steps above:
  - Verify all records remain intact in PostgreSQL.
  - Verify active background jobs resume execution without data loss.
