# ==============================================================================
# GNTV DIGITAL Platform — Production/Staging Backend Dockerfile
# Service: FastAPI Application API / Durable Worker / Scheduler
# ==============================================================================

FROM python:3.12-slim AS runtime

# System environment flags
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PORT=8000

WORKDIR /app

# Install minimal OS dependencies for Postgres client, SSL, curl (healthcheck), and FFmpeg
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    libpq-dev \
    gcc \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Create dedicated non-root application user
RUN groupadd -g 10001 gntv && \
    useradd -u 10001 -g gntv -s /bin/bash -m gntvuser

# Copy backend requirements first to leverage Docker layer caching
COPY backend-api/requirements.txt ./
RUN pip install -r requirements.txt

# Copy application source and Alembic migration suite
COPY backend-api/app ./app
COPY backend-api/alembic ./alembic
COPY backend-api/alembic.ini ./alembic.ini

# Ensure media directory exists and assign permissions to non-root user
RUN mkdir -p /app/var/media /app/var/streaming-media /tmp/gntv-transcode && \
    chown -R gntvuser:gntv /app /tmp/gntv-transcode

USER gntvuser

EXPOSE 8000

# Container readiness check against the FastAPI health route (verifies DB + Redis)
# Note: /health serves as readiness probe; dedicated liveness is planned for future iterations.
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Default runtime entrypoint: FastAPI ASGI Server behind reverse proxy
# For durable background workers: ["python", "-m", "app.modules.jobs.worker"] (or ["python", "-m", "app.modules.jobs.worker_runner"])
# For distributed scheduler: ["python", "-m", "app.modules.jobs.scheduler"] (or ["python", "-m", "app.modules.jobs.scheduler_runner"])
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips=*"]
