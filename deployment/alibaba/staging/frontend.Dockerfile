# ==============================================================================
# GNTV DIGITAL Platform — Production/Staging Frontend Studio Dockerfile
# Service: Creator & Operator Back-Office Studio SPA (Nginx)
# ==============================================================================

# STAGE 1: Deterministic Build Layer
FROM node:20-alpine AS builder

WORKDIR /app

# Copy dependency locks
COPY frontend-studio/package.json frontend-studio/package-lock.json ./
RUN npm ci

# Copy frontend source files
COPY frontend-studio/ ./

# Staging API endpoint injected at build time (replaced into client bundle by Vite)
ARG VITE_API_URL=https://api-staging.gntvdigital.com
ENV VITE_API_URL=$VITE_API_URL

# Build static production bundle
RUN npm run build

# STAGE 2: Lightweight Production Nginx Layer
FROM nginx:1.27-alpine AS runtime

# Remove default boilerplate configuration
RUN rm -rf /etc/nginx/conf.d/* /usr/share/nginx/html/*

# Copy compiled static assets from builder stage
COPY --from=builder /app/dist /usr/share/nginx/html

# Copy optimized staging Nginx configuration
COPY deployment/alibaba/staging/nginx.conf /etc/nginx/conf.d/default.conf

# Ensure nginx user has access
RUN chown -R nginx:nginx /usr/share/nginx/html && \
    chmod -R 755 /usr/share/nginx/html

EXPOSE 80

# Basic container healthcheck
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD wget -qO- http://localhost/health || exit 1

CMD ["nginx", "-g", "daemon off;"]
