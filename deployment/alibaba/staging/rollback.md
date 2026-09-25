# GNTV DIGITAL — Staging Rollback Strategy & Emergency Procedures

**Target Environment**: Alibaba Cloud Staging  
**Platform Version**: `v0.9.0-rc1`  

---

## 1. Core Rollback Principles

1. **Independent Layer Rollbacks**: Application container, database schema, and frontend static assets must be evaluated and rolled back independently.
2. **Immutable Images**: Every release artifact is tagged with git tag / commit SHA (`registry.aliyuncs.com/gntv/backend-api:v0.9.0-rc1`). Rollback never rebuilds code; it repoints the container service to the previous immutable image tag.
3. **No Automatic Database Downgrade**: In production-like environments, `alembic downgrade` should **never** be run automatically during an automated deployment failure. A database schema error must trigger a restoration from the pre-deployment snapshot or an additive hotfix.

---

## 2. Application Layer Rollback (FastAPI & Workers)

If the backend API or background workers crash, report unhealthy on load balancer healthchecks, or exhibit fatal runtime errors:

1. **Repoint ECS Task / Kubernetes Deployment**:
   ```bash
   # Example updating ECS service to previous stable release tag
   aliyun ecs UpdateContainerGroup --RegionId me-central-1 \
     --ContainerGroupId <staging-api-group-id> \
     --Image registry.me-central-1.aliyuncs.com/gntv/backend-api:<PREVIOUS_TAG>
   ```
2. **Drain Current Pods / Containers**:
   - The load balancer gracefully finishes in-flight requests (30-second connection draining timeout).
   - In-flight durable worker jobs will release their locks upon expiration and be re-claimed by the previous worker version.
3. **Verify Health**:
   - Confirm `curl -f https://api-staging.gntvdigital.com/health` returns 200 OK.

---

## 3. Frontend Studio Rollback

If the frontend bundle has UI rendering regressions or failed assets:

1. **Repoint Frontend ECS / Ingress**:
   - Update frontend container image to the previous stable release tag.
2. **CDN / Cache Purge**:
   - In the Alibaba Cloud CDN / ALB console, trigger an immediate path purge for `/index.html`.
   - Asset chunks in `/assets/` have content hashes and do not require cache purges.

---

## 4. Database Layer Emergency Restoration

If an unrecoverable database corruption or migration failure occurs:

> [!IMPORTANT]
> Because Module 8 migrations are forward-additive (adding tables, nullable columns, and allowlist rows), database rollback is rarely required for application regressions. Only execute database restoration if physical data corruption occurred.

1. **Stop Application Workloads**:
   - Scale backend API, worker, and scheduler instances to 0 replicas to prevent writes.
2. **Point-In-Time Restore from ApsaraDB RDS**:
   - In the ApsaraDB RDS console, select **Backup and Restoration** -> **Point-in-Time Recovery**.
   - Select the snapshot captured immediately prior to the deployment execution.
   - Restore to a temporary RDS instance or overwrite `gntv_media_hub_staging`.
3. **Verify Alembic State**:
   ```sql
   SELECT current_database(), version_num FROM alembic_version;
   ```
4. **Restart Workloads**:
   - Scale backend API, workers, and frontend containers back to normal replica count.
   - Run verification smoke tests.
