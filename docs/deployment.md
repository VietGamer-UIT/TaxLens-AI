# TaxLens-AI — Deployment Guide

> **TaxLens-AI by Đoàn Hoàng Việt (Việt Gamer)**  
> *Local Development, Docker Compose, and CI/CD Pipeline Reference*

---

## 1. Prerequisites

| Dependency | Minimum Version | Purpose |
|---|---|---|
| Docker Engine | 24.x | Container runtime |
| Docker Compose Plugin | 2.x | Multi-container orchestration |
| Python | 3.11 | Local development / smoke testing |
| Git | 2.x | Repository management |
| `curl` | any | Health check verification |

> **Note for Hackathon Judges:** You do *not* need a live Splunk instance, SIFT workstation, or any paid API key to run the full agent workflow. All MCP tools default to **mock mode** when API keys are absent.

---

## 2. Local Deployment with Docker Compose

### Step 1 — Clone & Configure

```bash
# Clone the repository
git clone https://github.com/VietGamer-UIT/TaxLens-AI.git
cd TaxLens-AI

# Copy the environment template
cp .env.example .env
```

Open `.env` and populate values. For a full local demo with no external APIs:

```dotenv
# Required — get from https://aistudio.google.com/apikey
GOOGLE_API_KEY=your_gemini_api_key_here

# Leave all others as defaults — mock mode will activate automatically
POSTGRES_USER=taxlens
POSTGRES_PASSWORD=changeme_in_prod
POSTGRES_DB=taxlens_audit
POSTGRES_HOST=db
POSTGRES_PORT=5432

SPLUNK_BASE_URL=https://splunk.taxlens.local:8089
SPLUNK_TOKEN=REPLACE_WITH_REAL_TOKEN

VIRUSTOTAL_API_KEY=REPLACE_WITH_REAL_KEY
ABUSEIPDB_API_KEY=REPLACE_WITH_REAL_KEY

LOG_LEVEL=info
BACKEND_PORT=8000
```

### Step 2 — Build and Start

```bash
# Build images and start all services in detached mode
docker compose up --build -d
```

This launches two containers:
- `taxlens_db` — PostgreSQL 16 (audit trail persistence)
- `taxlens_backend` — FastAPI + LangGraph IR agent stack

### Step 3 — Verify Health

```bash
# Check container status (both should show "healthy")
docker compose ps

# Expected output:
# NAME               SERVICE    STATUS     PORTS
# taxlens_db         db         running    5432/tcp
# taxlens_backend    backend    running    0.0.0.0:8000->8000/tcp

# Verify the API health endpoint
curl http://localhost:8000/health
# Expected: {"status":"ok","service":"TaxLens-AI"}

# Explore the interactive API docs
open http://localhost:8000/docs   # macOS
start http://localhost:8000/docs  # Windows
xdg-open http://localhost:8000/docs  # Linux
```

### Step 4 — Run a Demo Investigation

```bash
# Trigger a full multi-agent IR investigation (mock data)
curl -s -X POST http://localhost:8000/api/v1/ir/investigate \
  -H "Content-Type: application/json" \
  -H "X-Incident-ID: IR-2024-DEMO-001" \
  -d '{
    "incident_id": "IR-2024-DEMO-001",
    "evidence_paths": ["/evidence/dc01_mem.raw", "/evidence/fw01.pcap"]
  }' | python -m json.tool
```

**Expected response fields:**

```json
{
  "graph_run_id": "<uuid>",
  "incident_id": "IR-2024-DEMO-001",
  "status": "complete",
  "severity": "critical",
  "summary": "[TaxLens-AI] Incident IR-2024-DEMO-001 analysis COMPLETE...",
  "iteration_count": 4,
  "supervisor_report": {
    "ioc_table": [...],
    "timeline": [...],
    "notable_events": [...],
    "recommendations": [...]
  }
}
```

### Step 5 — Query the Audit Trail

```bash
# Retrieve all audit events for the incident
curl -s "http://localhost:8000/api/v1/audit/events?incident_id=IR-2024-DEMO-001" \
  | python -m json.tool
```

### Step 6 — Stop Services

```bash
# Stop and remove containers (data volume is preserved)
docker compose down

# Full cleanup including the PostgreSQL data volume
docker compose down -v
```

---

## 3. Local Development (No Docker)

For rapid iteration on agent logic without rebuilding Docker images:

```bash
# Install Python dependencies
pip install -r requirements.txt

# Set environment variables (PowerShell)
$env:GOOGLE_API_KEY = "your_key_here"
$env:POSTGRES_HOST  = "localhost"   # Requires a local PG instance
$env:LOG_LEVEL      = "debug"

# Run the smoke test (all-mock, no external APIs needed)
python -m Backend.FastAPI.ir_agents.graph_builder

# Start the FastAPI development server with hot-reload
uvicorn Backend.FastAPI.main:app --reload --port 8000
```

> **Tip:** For local dev, set `POSTGRES_HOST=localhost` and run PostgreSQL in a separate container:
> ```bash
> docker run -d --name taxlens_pg_dev \
>   -e POSTGRES_USER=taxlens \
>   -e POSTGRES_PASSWORD=changeme_in_prod \
>   -e POSTGRES_DB=taxlens_audit \
>   -p 5432:5432 postgres:16-alpine
> ```

---

## 4. Docker Architecture

### Multi-Stage Build

The `DevOps/Docker/Dockerfile.backend` uses a **two-stage build** to minimise the final image surface:

```dockerfile
# Stage 1: builder — compiles Python wheels
FROM python:3.11-slim AS builder
RUN pip wheel --no-cache-dir -r requirements.txt

# Stage 2: runtime — only copies compiled wheels (no build tools)
FROM python:3.11-slim AS runtime
COPY --from=builder /wheels /wheels
RUN pip install --no-index --find-links=/wheels /wheels/*.whl

# Security: non-root user (UID 1001)
RUN useradd -u 1001 -m appuser
USER appuser
```

### Security Hardening in docker-compose.yml

| Setting | Value | Rationale |
|---|---|---|
| DB port exposure | `expose:` only (not `ports:`) | PostgreSQL unreachable from host; intra-container only |
| `read_only: true` | backend service | App cannot write to its own filesystem |
| `tmpfs: /tmp` | 64M ephemeral | Scratch space for Plaso temp files; wiped on restart |
| Non-root user | UID 1001 (`appuser`) | Principle of least privilege |

---

## 5. CI/CD Pipeline (`.github/workflows/deploy.yml`)

### Pipeline Overview

```mermaid
flowchart LR
    A["git push main"] --> B["Job 1: lint-and-test\nRuff linting\nSmoke test"]
    B -->|pass| C["Job 2: build-and-push\nDocker build\nGHCR push"]
    C --> D["Job 3: deploy-vps\nSSH rolling restart\nHealth check"]
    D --> E{Health\nCheck}
    E -->|200 OK| F["✅ Slack: Success"]
    E -->|fail|   G["❌ Slack: Failed\nManual rollback"]

    style A fill:#333,color:#fff
    style F fill:#1a7a1a,color:#fff
    style G fill:#7a1a1a,color:#fff
```

### Job 1: `lint-and-test` (Every Push & PR)

```yaml
- name: Run Ruff linter
  run: |
    ruff check Backend/ --output-format=github \
      --select=E,W,F,I,S,B,C4,UP \
      --ignore=S101,S603,S607

- name: Run LangGraph smoke test (all-mock, no external APIs)
  run: python -m Backend.FastAPI.ir_agents.graph_builder
  env:
    POSTGRES_HOST: localhost
    LOG_LEVEL: warning
```

### Job 2: `build-and-push` (Push to `main` Only)

- Builds the Docker image using `DevOps/Docker/Dockerfile.backend` (multi-stage).
- Pushes tagged images to **GitHub Container Registry (GHCR)**:
  - `:sha-<short>` — every commit
  - `:latest` — always the tip of `main`
  - `:v<semver>` — when a Git tag is pushed
- Uses GHCR layer caching (`buildcache` tag) to reduce build time by ~60%.

### Job 3: `deploy-vps` (After Successful Build)

```bash
# Actions taken on the VPS via SSH:
cd /opt/taxlens-ai
docker compose pull backend          # Pull new image from GHCR
docker compose up -d --no-deps \
    --scale backend=1 backend        # Rolling restart (zero-downtime)
docker image prune -f                # Clean up dangling images
```

### Required GitHub Secrets

Navigate to **Settings → Secrets and variables → Actions** and add:

| Secret Name | Where to Get It |
|---|---|
| `GHCR_TOKEN` | GitHub → Developer Settings → Personal Access Tokens → `packages:write` scope |
| `VPS_HOST` | Your VPS provider (IP or hostname) |
| `VPS_USER` | SSH username on deployment server (e.g., `ubuntu`, `ec2-user`) |
| `VPS_SSH_KEY` | Private half of an ED25519 keypair: `ssh-keygen -t ed25519 -C taxlens-deploy` |
| `VPS_DEPLOY_PATH` | Absolute path on VPS: `/opt/taxlens-ai` |
| `SLACK_WEBHOOK_URL` | (Optional) Slack → Apps → Incoming Webhooks |

### VPS Initial Setup (One-Time)

```bash
# On the VPS — create deploy directory and copy .env
mkdir -p /opt/taxlens-ai
cd /opt/taxlens-ai
cp .env.example .env
nano .env   # Fill in production values

# Add the deploy SSH public key to authorized_keys
echo "ssh-ed25519 AAAA... taxlens-deploy" >> ~/.ssh/authorized_keys
```

---

## 6. Environment Reference

| Variable | Required | Default | Description |
|---|---|---|---|
| `GOOGLE_API_KEY` | ✅ | — | Google Gemini API key (LLM backend) |
| `POSTGRES_USER` | ✅ | `taxlens` | PostgreSQL username |
| `POSTGRES_PASSWORD` | ✅ | `changeme_in_prod` | PostgreSQL password — **change in production** |
| `POSTGRES_DB` | ✅ | `taxlens_audit` | Audit database name |
| `POSTGRES_HOST` | — | `db` | DB hostname (Docker service name in Compose) |
| `POSTGRES_PORT` | — | `5432` | PostgreSQL port |
| `SPLUNK_BASE_URL` | — | Mock mode | Splunk REST API endpoint (e.g. `https://splunk.corp.local:8089`) |
| `SPLUNK_TOKEN` | — | Mock mode | Splunk Bearer auth token |
| `VIRUSTOTAL_API_KEY` | — | Mock mode | VirusTotal v3 API key |
| `ABUSEIPDB_API_KEY` | — | Mock mode | AbuseIPDB v2 API key |
| `LOG_LEVEL` | — | `info` | Uvicorn log level (`debug`/`info`/`warning`/`error`) |
| `BACKEND_PORT` | — | `8000` | Host port FastAPI is published on |

---

## 7. Troubleshooting

| Symptom | Likely Cause | Fix |
|---|---|---|
| `taxlens_db` not healthy | DB init failed | `docker compose logs db` — check for missing env vars |
| `taxlens_backend` crashing on startup | DB connection refused | Ensure `depends_on` healthcheck passes; `docker compose ps` |
| `422 Unprocessable Entity` from `/investigate` | Missing required field | Ensure `incident_id` is in request body |
| Blank `supervisor_report` | Graph failed silently | Check `docker compose logs backend` for Python traceback |
| CI fails on `Ruff` lint | New code fails lint rules | Run `ruff check Backend/ --fix` locally |

---

> *TaxLens-AI by Đoàn Hoàng Việt (Việt Gamer) — Deployment Guide v1.0*
