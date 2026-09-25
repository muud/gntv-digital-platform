# GNTV DIGITAL — Staging Deployment Execution Checklist

**Version**: `v0.9.0-rc1`  
**Target Environment**: Alibaba Cloud Staging  

---

## Pre-Deployment Verification (Local / CI)

- [ ] 1. Base commit confirmed at `76037fb` (Tag `v0.9.0-rc1`).
- [ ] 2. All Module 8 regression suites passing (97 tests passed).
- [ ] 3. All Module 7 regression suites passing (54 tests passed).
- [ ] 4. OpenAPI validation passing (2 tests passed).
- [ ] 5. Frontend unit tests passing (21 tests passed).
- [ ] 6. Frontend linter passing (0 syntax/check errors).
- [ ] 7. Frontend bundle build passing (`npm run build`).
- [ ] 8. Dependency audit clear (`npm audit` shows 0 vulnerabilities).
- [ ] 9. Verified `backend-api/app/utils/jwt.py` has no unapproved edits.
- [ ] 10. Verified no secrets, passwords, or cloud API keys exist in git tracking.

---

## Infrastructure Provisioning (Alibaba Cloud Console / CLI)

- [ ] 1. **VPC & Subnets**:
  - Region: `me-central-1` (Dubai) or `eu-central-1` (Frankfurt).
  - Staging VPC CIDR: `172.16.0.0/16`.
  - Public Subnet (ALB): `172.16.0.0/24`.
  - Private App Subnet (ECS): `172.16.1.0/24`.
  - Private Data Subnet (RDS / Redis): `172.16.2.0/24`.
- [ ] 2. **Security Groups**:
  - `sg-alb`: Allow inbound 80, 443 from `0.0.0.0/0`.
  - `sg-app`: Allow inbound 8000 (API) and 80 (Studio) *only* from `sg-alb`.
  - `sg-db`: Allow inbound 5432 *only* from `sg-app`. No public IP.
  - `sg-redis`: Allow inbound 6379 *only* from `sg-app`. No public IP.
- [ ] 3. **ApsaraDB RDS for PostgreSQL**:
  - Engine Version: PostgreSQL 15 or 16.
  - Spec: `pg.n2.small.2c` (2 vCPU, 4GB RAM) for staging.
  - Whitelist: Bound to `sg-app`.
  - Database created: `gntv_media_hub_staging` (Encoding: `UTF8`, Collation: `en_US.UTF-8`).
  - Application User: `gntv_staging_app` with schema ownership.
- [ ] 4. **ApsaraDB for Redis**:
  - Engine Version: Redis 7.0 Community Edition.
  - Whitelist: Bound to `sg-app`.
- [ ] 5. **OSS Storage**:
  - Bucket Name: `gntv-staging-media`.
  - Access Control: Private.
  - CORS: Allow `https://studio-staging.gntvdigital.com` GET, PUT, POST.
- [ ] 6. **Application Load Balancer (ALB)**:
  - HTTPS Listener on 443 with SSL Certificate for `*.gntvdigital.com`.
  - HTTP Listener on 80 with automatic 301 redirect to HTTPS.
  - Route rule 1: `Host: studio-staging.gntvdigital.com` -> Forward to Studio ECS Target Group.
  - Route rule 2: `Host: api-staging.gntvdigital.com` -> Forward to Backend API ECS Target Group.

---

## Database Initialization & Migration (Fresh Database Protocol)

> [!CAUTION]
> NEVER restore or copy the developer's local database (`gntv_media_hub`).
> Staging MUST initialize via clean Alembic migrations from base to head.

- [ ] 1. Obtain private RDS connection string.
- [ ] 2. Run initial migration migration pre-check:
  ```bash
  export DATABASE_URL="postgresql://gntv_staging_app:PASSWORD@172.16.2.10:5432/gntv_media_hub_staging?sslmode=require"
  export PYTHONPATH=.
  alembic upgrade head
  ```
- [ ] 3. Verify target head:
  ```sql
  SELECT current_database();
  -- Output must be: gntv_media_hub_staging

  SELECT version_num FROM alembic_version;
  -- Output must be: 202609211200
  ```
- [ ] 4. Verify 159 tables created cleanly without errors.

---

## Container Deployment

- [ ] 1. Build and push backend image:
  ```bash
  docker build -f deployment/alibaba/staging/backend.Dockerfile -t registry.me-central-1.aliyuncs.com/gntv/backend-api:v0.9.0-rc1 .
  docker push registry.me-central-1.aliyuncs.com/gntv/backend-api:v0.9.0-rc1
  ```
- [ ] 2. Build and push frontend studio image (with staging API URL baked in):
  ```bash
  docker build -f deployment/alibaba/staging/frontend.Dockerfile \
    --build-arg VITE_API_URL=https://api-staging.gntvdigital.com \
    -t registry.me-central-1.aliyuncs.com/gntv/frontend-studio:v0.9.0-rc1 .
  docker push registry.me-central-1.aliyuncs.com/gntv/frontend-studio:v0.9.0-rc1
  ```
- [ ] 3. Launch ECS tasks / ACK Pods injecting staging environment variables from Alibaba KMS.
- [ ] 4. Verify ALB healthchecks report healthy (200 OK) for both services.
- [ ] 5. Execute Staging Smoke Tests (`smoke-tests.md`).
