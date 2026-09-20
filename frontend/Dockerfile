# Docker image for the LabelVerify React frontend (release candidate).
# Architectural responsibility: multi-stage production static build + nginx reverse proxy.
# Prefer native linux/arm64 on Apple Silicon — do not force linux/amd64.
# Never bake OPENAI_API_KEY or Cloudflare credentials into the static bundle.

FROM node:22-alpine AS build

WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci
COPY . .
ARG VITE_APP_VERSION=0.8.0
ENV VITE_APP_VERSION=$VITE_APP_VERSION
# Empty API base → same-origin /api via nginx proxy (no secrets / no hard-coded hostname).
ENV VITE_API_BASE_URL=
RUN npm run build

FROM nginx:1.27-alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
# Optional basic-auth file may be mounted at runtime; default config works without it.
# Prefer Cloudflare Access for evaluator-facing HTTPS (see docs/DEPLOYMENT.md).
EXPOSE 80
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD wget -qO- http://127.0.0.1/ >/dev/null || exit 1
CMD ["nginx", "-g", "daemon off;"]
