# Deployment guide — LabelVerify AI release candidate

**Prototype decision-support system.** Not a final regulatory determination engine.
Do not treat PASS/REVIEW/FAIL as official TTB/Treasury outcomes.

## Prerequisites

| Requirement | Notes |
|-------------|--------|
| Docker Engine + Docker Compose v2 | Primary deploy path for the dedicated evaluation Mac |
| Git | Clone this repository |
| ~4 GB free disk | Images + layers |
| Optional: OpenAI API key | Enabled for evaluation deploy; still optional for readiness |
| Optional: Cloudflare Access + Tunnel | External access control for the public hostname (see below) |

Backend images include **openpyxl** for Excel report generation (no extra host install).

Development (without Docker) still works on Windows/macOS/Linux with Python 3.12, Node 22+, and a host Tesseract install. **Production-like deploy must use the backend image**, which embeds Tesseract so the host need not install OCR.

### Apple Silicon / arm64 notes

Target evaluation host: **macOS arm64 (Apple Silicon)**.

1. Confirm architecture:
   ```bash
   uname -m
   # expect: arm64
   ```
2. Install Docker Desktop for Mac (Apple Silicon build).
3. Keep the Mac plugged in; disable **system** sleep (display sleep is OK).
4. Prefer **native** `linux/arm64` images. Do **not** force `platform: linux/amd64` in Compose unless a specific dependency fails on arm64.
5. Production image installs `.[ocr-tesseract]` only. Optional RapidOCR / Paddle extras are **not** required for evaluation and remain disabled by default.
6. Base images (`python:3.12-slim-bookworm`, `nginx:*-alpine`, `node:*-alpine`) publish multi-arch manifests including arm64. Validate `docker compose build` on the Mac before Cloudflare exposure.

No macOS-specific application code is required. cloudflared is a **host** service, not a container in this stack.

## Quick start (Docker Compose)

```bash
git clone <repository-url> labelverify-ai
cd labelverify-ai
cp backend/.env.example backend/.env
# Edit backend/.env: for evaluation, set OPENAI_ENABLED=true and paste OPENAI_API_KEY
# manually (never commit). Core verification still works with OpenAI disabled.
# Optional Compose host interpolation: cp .env.example .env
# Defaults: FRONTEND_BIND_HOST=127.0.0.1, FRONTEND_HOST_PORT=8080

docker compose up --build -d
```

Open **http://localhost:8080**

Useful checks:

```bash
docker compose ps
curl -fsS http://localhost:8080/health/live
curl -fsS http://localhost:8080/ready
# Ready must succeed with OpenAI disabled / unreachable / Cloudflare unavailable.
```

Common lifecycle:

```bash
docker compose up --build -d
docker compose ps
docker compose logs -f backend
docker compose restart
docker compose down
```

## Services

| Service | Role | Host exposure |
|---------|------|----------------|
| `backend` | FastAPI + Tesseract + OpenCV | **Not** published (internal `8000` only) |
| `frontend` | Static UI + nginx reverse proxy | `127.0.0.1:${FRONTEND_HOST_PORT:-8080}:80` by default |

Same-origin API: browser calls `/api/...`; nginx proxies to `backend:8000`. No API key in the frontend bundle. No hard-coded production hostname in application code.

Restart policy: `unless-stopped` on both services. Healthchecks: backend `/ready` (Tesseract present; **not** OpenAI/Cloudflare/Internet), frontend root HTTP (image HEALTHCHECK).

### Port binding decision

Published frontend port binds to **loopback only** by default:

```text
127.0.0.1:8080:80
```

Rationale:

- Local validation at `http://localhost:8080`
- Same-host `cloudflared` reaches `http://localhost:8080`
- UI is not unnecessarily listening on every LAN interface
- No router port forwarding is required

Override with `FRONTEND_BIND_HOST=0.0.0.0` only for rare LAN demos. Cloudflare Tunnel does **not** need LAN-wide bind.

The FastAPI backend remains internal (`expose: 8000` only). Frontend nginx is the single application entry point.

## Environment variables

See [`backend/.env.example`](../backend/.env.example) and [`.env.example`](../.env.example). Critical deployment variables:

| Variable | Purpose | Default |
|----------|---------|---------|
| `OPENAI_ENABLED` | Opt-in AI evidence fallback | `false` (enable for evaluation) |
| `OPENAI_API_KEY` | Backend-only secret | empty |
| `OPENAI_MODEL` | Configurable model id | `gpt-4o-mini` |
| `OPENAI_TIMEOUT_SECONDS` | Provider timeout | `8` |
| `BATCH_MAX_ITEMS` | Manifest size cap | `300` |
| `BATCH_MAX_CONCURRENCY` | Parallel OCR/verify | `2` |
| `BATCH_AI_MAX_CALLS` | Batch AI budget | `25` |
| `BATCH_AI_CONCURRENCY` | Parallel AI calls | `1` |
| `CORS_ORIGINS` | Allowed origins if calling API directly | Compose: `http://localhost:8080` |
| `FRONTEND_HOST_PORT` | Published UI port | `8080` |
| `FRONTEND_BIND_HOST` | Host interface for UI port | `127.0.0.1` |
| `APP_VERSION` | Build/version stamp | `0.8.0` |
| `APP_ENV` | `production` disables `/docs` | Compose forces `production` |

**Secrets must never appear in:** git, Docker layers, `VITE_*` vars, docs examples, or test fixtures.

Compose injects `backend/.env` at **runtime** (`env_file`, required: false). Build contexts exclude `.env` files. Do not put `OPENAI_API_KEY` in frontend env or image ARG/ENV.

## Tesseract inside the container

The backend Dockerfile installs:

- `tesseract-ocr`
- `tesseract-ocr-eng` (English traineddata)

Validate after `docker compose up`:

```bash
docker compose exec backend tesseract --version
docker compose exec backend python -c "import shutil; print(shutil.which('tesseract'))"
# From host (API via nginx):
python backend/scripts/validate_container_ocr.py --base-url http://localhost:8080
```

Host Tesseract is **not** required for Compose deploys.

## Cloudflare Access + Tunnel

### Intended public path

```text
https://labelverify.framesfirstsystems.com
  → Cloudflare Access
  → Cloudflare Tunnel
  → http://localhost:8080   (Mac host loopback)
  → frontend nginx
  → FastAPI backend (/api)
```

Evaluator-facing hostname: **https://labelverify.framesfirstsystems.com**

The zone `framesfirstsystems.com` already exists in Cloudflare and is used by other applications. LabelVerify uses the **dedicated** subdomain `labelverify.framesfirstsystems.com` only. Do **not** modify, replace, or interfere with existing Cloudflare hostnames, DNS records, tunnels, Access applications, or services for other apps on that zone.

### Separation of concerns

| Layer | Ownership |
|-------|-----------|
| LabelVerify Docker Compose | This repository — independently deployable at `localhost:8080` without Cloudflare |
| cloudflared | macOS **host** service — **not** in `docker-compose.yml` |
| Cloudflare Access / Tunnel / DNS | External deployment configuration — credentials stay out of git |

Docker and cloudflared restart independently. No router port forwarding. Origin remains loopback-bound when using the default Compose publish.

Do **not** commit: Cloudflare account/zone IDs, tunnel tokens, credential JSON files, Access tokens, API tokens, or service tokens.

### Prerequisites (Cloudflare)

- Existing Cloudflare account
- Existing `framesfirstsystems.com` zone (do not disturb other apps)
- LabelVerify-specific Cloudflare Access application/policy
- Remotely managed LabelVerify Tunnel public hostname → `http://localhost:8080`
- `cloudflared` installed and running as a macOS host service

Actual Cloudflare account/tunnel configuration is performed **interactively** after local Docker validation on the Mac. This repository does not create tunnels or Access apps.

### Recommended deployment order

1. Verify LabelVerify locally in Docker (`http://localhost:8080`)
2. Create/configure the LabelVerify Cloudflare Access application/policy
3. Configure the LabelVerify Tunnel / public hostname (to `http://localhost:8080`)
4. Verify Access protection (unauthorized requests blocked)
5. Test externally at `https://labelverify.framesfirstsystems.com`

**Access protection must be established before the application is generally reachable through its public hostname.**

### Application behavior behind Cloudflare

- Browser continues to use **same-origin** `/api/...` (no hard-coded backend URL; no separate public API hostname)
- LabelVerify does **not** implement a duplicate login system; Access is external
- Local use without Cloudflare remains supported
- nginx forwards `Host`, `X-Real-IP`, `X-Forwarded-For`, `X-Forwarded-Proto` (preserving tunnel `https` when present), and `X-Request-ID` when supplied
- Uvicorn runs with `--proxy-headers` (backend only reachable from the Docker network)
- Operational audit events (`site_access`, review start/complete, `application_error`) continue to work; do not log Access cookies, JWTs, Authorization headers, IPs for analytics, or geolocation

### Optional nginx basic auth

Commented `auth_basic` template in `frontend/nginx.conf` remains a last-resort edge gate. Prefer Cloudflare Access — no custom account-management system in the app.

## Updating deployment

```bash
cd labelverify-ai
git pull
docker compose up --build -d
```

Confirm version in UI footer and `X-App-Version` response header / `/health`.

## Restarting services

```bash
docker compose restart
# or individually:
docker compose restart backend
docker compose restart frontend
```

Containers should recover with `unless-stopped` after Docker Desktop / host reboot (ensure Docker starts on login). cloudflared (host) recovers separately if installed as a launchd/service unit.

## Viewing logs

```bash
docker compose logs -f --tail=200
docker compose logs -f backend
```

### Operational / audit events (Phase 8.10)

Backend emits one-line **JSON** audit events on the `labelverify.audit` logger
(stdout). These are prototype operational telemetry for administrators — not
user analytics and not label-content logging.

| Event | When |
|-------|------|
| `site_access` | SPA load via `POST /api/v1/telemetry/access` (once per page load) |
| `single_review_started` | Single Label `/api/v1/verify` begins |
| `single_review_completed` | Single Label verify finishes (status, duration, AI/secondary OCR flags, quality) |
| `batch_review_started` | Batch job created |
| `batch_review_completed` | Batch finishes (aggregate PASS/REVIEW/FAIL/error counts, AI call count, duration) |
| `application_error` | Safe operational errors (type, stage, short message) |

**Explicitly excluded from audit logs:** uploaded images, filenames, extracted
brand/class/ABV/net/warning text, application field values, OpenAI prompts or
responses, API keys, Authorization headers, cookies, Cloudflare Access JWTs,
browser fingerprints, IP addresses / geolocation, forwarding-header dumps.

Filter examples:

```bash
docker compose logs backend 2>&1 | findstr site_access
docker compose logs backend 2>&1 | findstr single_review_completed
docker compose logs backend 2>&1 | findstr batch_review_completed
docker compose logs backend 2>&1 | findstr application_error
```

On macOS/Linux:

```bash
docker compose logs -f backend | grep site_access
docker compose logs -f backend | grep single_review_completed
docker compose logs -f backend | grep '"event":"batch_review_completed"'
docker compose logs -f backend | grep application_error
```

Logs include request IDs for correlation. They must not include API keys or
document payloads. No telemetry database is used — Docker/container logs are
sufficient for this prototype.

## Rollback basics

1. Note the previous working git tag/commit and image ids (`docker images`).
2. `git checkout <known-good>`
3. `docker compose up --build -d`
4. Re-check `/ready` and a Single Review sample.

No durable queue/database is required for Phase 8; in-memory batch jobs are lost on restart (documented limitation).

## Demo path (evaluators)

**Single Label**

1. Open the UI — Review Setup / Results workspace
2. Choose **Single Label**
3. Upload `test-data/demo/old-tom-demo.jpg` → **Analyze Label**
4. Review Results → optional **Download Excel Report**

**Batch Review**

1. Choose **Batch Review**
2. Sample manifest + three JPEGs in `test-data/batch-sample/`
3. Validate → Process Batch → Results → **Download Excel Report**

## Security posture (prototype)

- API key backend-only; no arbitrary prompt endpoint
- Upload size + magic-byte validation; safe client errors (no stack traces/paths)
- Batch path-traversal + CSV formula-injection defenses; bounded concurrency/AI budget
- Production docs disabled; CORS limited to configured origins; nginx security headers
- Cloudflare Access recommended before any public HTTPS hostname
- Origin loopback-bound by default; backend not published to the host

See [RELEASE_QA.md](RELEASE_QA.md) for the QA matrix and measured results.

## Deployment acceptance checklist

Do **not** mark items complete until validated on the target Mac / Cloudflare path.

### Local Mac validation

- [ ] `docker compose build` succeeds on Apple Silicon
- [ ] containers start and report healthy
- [ ] Tesseract works inside backend container
- [ ] `http://localhost:8080` loads
- [ ] Single Label clean-label review works
- [ ] difficult-label REVIEW/recovery path works
- [ ] Excel report downloads
- [ ] Analyze Another Label works
- [ ] How It Works modal works
- [ ] operational audit events appear in Docker logs
- [ ] `docker compose restart` recovers the application
- [ ] application remains reachable at `localhost:8080` after restart
- [ ] no unnecessary application port is exposed to the LAN

### Cloudflare validation

- [ ] LabelVerify Access application/policy exists before public exposure
- [ ] existing `framesfirstsystems.com` services remain unaffected
- [ ] LabelVerify tunnel is connected/healthy
- [ ] `labelverify.framesfirstsystems.com` routes to `http://localhost:8080`
- [ ] unauthorized external request is intercepted/blocked by Cloudflare Access
- [ ] authorized evaluator can pass Access
- [ ] application loads at `https://labelverify.framesfirstsystems.com`
- [ ] frontend `/api` requests work through the same public hostname
- [ ] Single Label Review works externally
- [ ] difficult-label recovery path works externally
- [ ] Excel report downloads externally
- [ ] How It Works modal works externally
- [ ] operational audit events appear during external use
- [ ] Mac exposes no unnecessary inbound application port
- [ ] existing Mnemosyne/other `framesfirstsystems.com` services still work
