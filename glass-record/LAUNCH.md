# The Glass Record — Launch Guide

> Complete credentials, configuration, and deployment steps.
> Follow sections in order. Estimated time: 2–3 hours on a fresh GCP project.

---

## 1. Prerequisites

| Tool | Version | Install |
|---|---|---|
| Python | 3.12 | `pyenv install 3.12` |
| uv | latest | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| Docker | 24+ | docker.com |
| Terraform | 1.7+ | `brew install terraform` |
| gcloud CLI | latest | `brew install google-cloud-sdk` |
| Firebase CLI | latest | `npm install -g firebase-tools` |
| Node.js | 20 LTS | `brew install node` |

---

## 2. GCP Project

### 2a. Create project

```bash
gcloud projects create glass-record-prod --name="The Glass Record"
gcloud config set project glass-record-prod
gcloud billing accounts list                         # find your billing account ID
gcloud billing projects link glass-record-prod \
  --billing-account=XXXXXX-XXXXXX-XXXXXX
```

### 2b. Enable APIs

```bash
gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  cloudscheduler.googleapis.com \
  pubsub.googleapis.com \
  firestore.googleapis.com \
  storage.googleapis.com \
  artifactregistry.googleapis.com \
  aiplatform.googleapis.com \
  secretmanager.googleapis.com \
  firebase.googleapis.com
```

### 2c. Create Firestore database (native mode)

```bash
gcloud firestore databases create --location=us-central1
```

---

## 3. Credentials Checklist

### 3a. GCP Service Account (for local dev)

```bash
gcloud iam service-accounts create glass-record-local \
  --display-name="Glass Record local dev"

gcloud projects add-iam-policy-binding glass-record-prod \
  --member="serviceAccount:glass-record-local@glass-record-prod.iam.gserviceaccount.com" \
  --role="roles/editor"

gcloud iam service-accounts keys create ~/glass-record-sa.json \
  --iam-account=glass-record-local@glass-record-prod.iam.gserviceaccount.com
```

Set in `.env`:
```
GOOGLE_APPLICATION_CREDENTIALS=/Users/you/glass-record-sa.json
GOOGLE_CLOUD_PROJECT=glass-record-prod
```

### 3b. Vertex AI / Gemini

No API key required — Vertex AI uses the service account above.
Ensure the account has `roles/aiplatform.user` (Terraform grants this automatically).

Set in `.env`:
```
GOOGLE_GENAI_USE_VERTEXAI=true
GEMINI_MODEL=gemini-1.5-pro-002
```

> **Cost note:** Gemini 1.5 Pro costs $3.50/1M input tokens, $10.50/1M output tokens.
> A typical investigation cycle uses ~50–200k tokens ≈ $0.30–$2.50 per cycle.
> The cost ledger on each journalist's public page shows exact spend.

### 3c. Google Programmable Search Engine

1. Go to https://programmablesearchengine.google.com/
2. Create a new search engine → enable "Search the entire web"
3. Copy **Search Engine ID** (cx)
4. Go to https://console.cloud.google.com/apis/credentials → **Create API Key**
5. Restrict the key to **Custom Search API**

Set in `.env`:
```
GOOGLE_SEARCH_API_KEY=AIzaSy...
GOOGLE_SEARCH_ENGINE_ID=b4f3c9...
```

### 3d. Neo4j (production — Aura Free Tier)

1. Go to https://console.neo4j.io/
2. Create a **Free** AuraDB instance (5 GB, always-on)
3. Download the connection credentials file — it contains URI, user, password

Set in `.env` (and in Cloud Run env vars / Secret Manager for prod):
```
NEO4J_URI=neo4j+s://xxxxxxxx.databases.neo4j.io
NEO4J_USER=neo4j
NEO4J_PASSWORD=<from Aura credentials file>
```

Apply the schema after Aura is running:
```bash
# Install cypher-shell locally: https://neo4j.com/deployment-center/
cypher-shell -a $NEO4J_URI -u $NEO4J_USER -p $NEO4J_PASSWORD \
  --file glass-record/graph/schema.cypher
```

### 3e. Ghost CMS

**Option A — Self-hosted (recommended for prod)**

```bash
# On a small VM (e.g. GCP e2-micro, $6/month)
bash <(curl -s https://ghost.org/install.sh)
```

**Option B — Ghost Pro** at ghost.org (managed, ~$9/month)

After Ghost is running:
1. Ghost Admin → Settings → Integrations → Add custom integration
2. Name it "Glass Record"
3. Copy **Admin API Key** (format: `id:secret` — a hex id, colon, hex secret)
4. Copy **Admin URL**

Set in `.env`:
```
GHOST_ADMIN_URL=https://your-ghost-site.com
GHOST_ADMIN_API_KEY=6478a3b2c1d4e5f6:9a8b7c6d5e4f3a2b1c0d9e8f7a6b5c4d3e2f1a0
```

### 3f. Firebase (for dashboard)

```bash
firebase login
firebase use --add glass-record-prod
```

Go to Firebase Console → Project Settings → **Your apps** → Add web app:

```
App name: glass-record-dashboard
```

Copy the config object. Set in `dashboard/.env.local`:
```
NEXT_PUBLIC_FIREBASE_API_KEY=AIzaSy...
NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN=glass-record-prod.firebaseapp.com
NEXT_PUBLIC_FIREBASE_PROJECT_ID=glass-record-prod
NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET=glass-record-prod.appspot.com
NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID=123456789
NEXT_PUBLIC_FIREBASE_APP_ID=1:123456789:web:abc123
NEXT_PUBLIC_EDITOR_URL=https://glass-record-editor-<project-hash>.us-central1.run.app
```

> `NEXT_PUBLIC_EDITOR_URL` is filled in after Terraform deploys the Cloud Run service (step 7).

---

## 4. Local Development

### 4a. Python environment

```bash
cd glass-record
uv sync
uv run playwright install chromium  # only needed for local runs; Docker handles this in prod
```

To also enable the MCP log-access server for Claude Code:
```bash
uv sync --extra mcp
```

### 4b. Start local services

```bash
docker compose up -d
# Wait ~30s for Neo4j and Ghost to be healthy
docker compose ps   # all should show "healthy"
```

Local service URLs:
- Neo4j Browser: http://localhost:7474 (neo4j / devpassword)
- Firestore emulator: http://localhost:8080
- Ghost: http://localhost:2368

### 4c. Create `.env` from template

```bash
cp .env.example .env
# Fill in GOOGLE_APPLICATION_CREDENTIALS, GOOGLE_CLOUD_PROJECT,
# GOOGLE_SEARCH_API_KEY, GOOGLE_SEARCH_ENGINE_ID,
# GHOST_ADMIN_URL, GHOST_ADMIN_API_KEY
# Leave FIRESTORE_EMULATOR_HOST=localhost:8080 for local dev
```

### 4d. Apply Neo4j schema

```bash
docker exec -i $(docker compose ps -q neo4j) \
  cypher-shell -u neo4j -p devpassword \
  < graph/schema.cypher
```

### 4e. Get Ghost Admin API key (local)

1. Go to http://localhost:2368/ghost
2. Complete Ghost setup (create admin account)
3. Settings → Integrations → Add custom integration → "Glass Record"
4. Copy Admin API key → paste into `.env` as `GHOST_ADMIN_API_KEY`

### 4f. Start the Editor service

```bash
FIRESTORE_EMULATOR_HOST=localhost:8080 \
  uv run uvicorn agents.editor.main:app --reload --port 8000
```

Health check: `curl http://localhost:8000/health` → `{"status":"ok"}`

### 4g. Run tests

```bash
FIRESTORE_EMULATOR_HOST=localhost:8080 \
  uv run pytest tests/unit -v
```

### 4h. Start the dashboard

```bash
cd dashboard
cp ../.env.local.example .env.local
# Edit .env.local with your Firebase config
npm install
npm run dev
# Dashboard at http://localhost:3000
```

---

## 5. Spawn your first journalist (local)

```bash
curl -X POST http://localhost:8000/spawn \
  -H "Content-Type: application/json" \
  -d '{
    "mandate": "Investigate human rights implications of UN Security Council decisions and vetoes.",
    "jurisdiction": "UN",
    "tier": "free",
    "schedule": "0 6 * * *"
  }'
```

Response includes the `journalist_id`. Open http://localhost:3000/{journalist_id} to see the public page.

Trigger a manual cycle:
```bash
curl -X POST http://localhost:8000/run \
  -H "Content-Type: application/json" \
  -d '{
    "journalist_id": "un-xxxxxxxx",
    "mandate": "Investigate human rights implications of UN Security Council decisions and vetoes.",
    "jurisdiction": "UN",
    "tier": "free"
  }'
```

---

## 6. Terraform — GCP Infrastructure

### 6a. Create Terraform state bucket

```bash
gsutil mb -l us-central1 gs://glass-record-tf-state
gsutil versioning set on gs://glass-record-tf-state
```

### 6b. Create `infra/envs/prod.tfvars`

```hcl
project_id = "glass-record-prod"
region     = "us-central1"
env        = "prod"
image_tag  = "latest"

journalists = {
  "un-security-council-001" = {
    mandate      = "Investigate human rights implications of UN Security Council decisions and vetoes."
    jurisdiction = "UN"
    tier         = "free"
    schedule     = "0 6 * * *"
  }
}
```

### 6c. Apply

```bash
cd infra
terraform init
terraform plan -var-file=envs/prod.tfvars
terraform apply -var-file=envs/prod.tfvars
```

This creates:
- Artifact Registry repository (`agents`)
- Pub/Sub topic (`glass-record-researcher-tasks`) + subscription
- Cloud Run services (`glass-record-editor`, `glass-record-researcher`)
- Cloud Scheduler jobs (one per journalist in `journalists` map)
- GCS bucket (`glass-record-evidence-prod`) with NEARLINE lifecycle
- Service accounts + IAM bindings

### 6d. Store secrets in Secret Manager

```bash
# Neo4j password
echo -n "YOUR_NEO4J_PASSWORD" | \
  gcloud secrets create NEO4J_PASSWORD --data-file=- --project=glass-record-prod

# Ghost API key
echo -n "YOUR_GHOST_API_KEY" | \
  gcloud secrets create GHOST_ADMIN_API_KEY --data-file=- --project=glass-record-prod

# Grant Cloud Run access to secrets
gcloud secrets add-iam-policy-binding NEO4J_PASSWORD \
  --member="serviceAccount:glass-record-agent@glass-record-prod.iam.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"

gcloud secrets add-iam-policy-binding GHOST_ADMIN_API_KEY \
  --member="serviceAccount:glass-record-agent@glass-record-prod.iam.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"
```

Add these to the Cloud Run service env (re-run `terraform apply` after updating the module or via console):
```
NEO4J_URI=neo4j+s://xxxxxxxx.databases.neo4j.io
NEO4J_USER=neo4j
GHOST_ADMIN_URL=https://your-ghost-site.com
```

---

## 7. Cloud Build CI/CD

### 7a. Connect the repository

```bash
gcloud builds triggers create github \
  --project=glass-record-prod \
  --repo-name=aijournalist \
  --repo-owner=<your-github-org> \
  --branch-pattern="^main$" \
  --build-config=glass-record/cloudbuild.yaml \
  --name=glass-record-deploy
```

Or via console: Cloud Build → Triggers → Connect Repository → GitHub.

### 7b. Grant Cloud Build permissions

```bash
PROJECT_NUMBER=$(gcloud projects describe glass-record-prod --format='value(projectNumber)')
CB_SA="${PROJECT_NUMBER}@cloudbuild.gserviceaccount.com"

gcloud projects add-iam-policy-binding glass-record-prod \
  --member="serviceAccount:${CB_SA}" --role="roles/run.admin"
gcloud projects add-iam-policy-binding glass-record-prod \
  --member="serviceAccount:${CB_SA}" --role="roles/iam.serviceAccountUser"
gcloud projects add-iam-policy-binding glass-record-prod \
  --member="serviceAccount:${CB_SA}" --role="roles/artifactregistry.writer"
```

### 7c. Trigger a build manually

```bash
cd glass-record
gcloud builds submit --config=cloudbuild.yaml \
  --project=glass-record-prod \
  --substitutions=_AR_REGION=us-central1,_AR_REPO=agents,_REGION=us-central1
```

> `_AR_REPO` must be `agents` — that is the name of the Artifact Registry repository
> provisioned by Terraform. Using any other value will cause the push step to fail
> with a 404 from the registry.

Pipeline: unit tests → build base image → build editor + researcher images (parallel) → push → deploy both Cloud Run services.

---

## 8. Firebase App Hosting (dashboard)

### 8a. Deploy Firestore security rules

```bash
cd glass-record
firebase deploy --only firestore:rules --project=glass-record-prod
```

### 8b. Store dashboard secrets in Secret Manager

```bash
echo -n "glass-record-prod" | \
  gcloud secrets create FIREBASE_PROJECT_ID --data-file=- --project=glass-record-prod

# Get Cloud Run Editor URL after Terraform apply:
EDITOR_URL=$(gcloud run services describe glass-record-editor \
  --region=us-central1 --format='value(status.url)')

echo -n "$EDITOR_URL" | \
  gcloud secrets create EDITOR_SERVICE_URL --data-file=- --project=glass-record-prod
```

### 8c. Deploy App Hosting backend

```bash
firebase apphosting:backends:create \
  --project=glass-record-prod \
  --location=us-central1

# Point it to the dashboard directory:
firebase deploy --only hosting --project=glass-record-prod
```

Dashboard will be available at:
```
https://glass-record-prod.web.app
https://glass-record-prod.firebaseapp.com
```

Custom domain (optional):
```bash
firebase hosting:channel:deploy prod --project=glass-record-prod
# Then add CNAME at your DNS registrar pointing to Firebase Hosting
```

---

## 9. Spawn journalists in production

After Cloud Run is deployed, call the Editor service directly (OIDC-authenticated):

```bash
EDITOR_URL=$(gcloud run services describe glass-record-editor \
  --region=us-central1 --format='value(status.url)')

TOKEN=$(gcloud auth print-identity-token)

curl -X POST "${EDITOR_URL}/spawn" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "mandate": "Investigate human rights implications of UN Security Council decisions and vetoes.",
    "jurisdiction": "UN",
    "tier": "free",
    "schedule": "0 6 * * *"
  }'
```

Supported jurisdictions: `UN`, `EU`, `ICC`, `ICJ`, `US_FEDERAL`, `NATO`, `WORLD_BANK`, `ECHR`

---

## 10. Environment Variable Reference

### Backend (`.env` / Cloud Run)

| Variable | Required | Description |
|---|---|---|
| `GOOGLE_CLOUD_PROJECT` | Yes | GCP project ID |
| `GOOGLE_GENAI_USE_VERTEXAI` | Yes | Must be `true` |
| `GOOGLE_APPLICATION_CREDENTIALS` | Local only | Path to service account JSON |
| `GEMINI_MODEL` | Yes | `gemini-1.5-pro-002` (or flash for cheaper) |
| `NEO4J_URI` | Yes | `bolt://localhost:7687` (dev) or Aura URI (prod) |
| `NEO4J_USER` | Yes | `neo4j` |
| `NEO4J_PASSWORD` | Yes | Set via Secret Manager in prod |
| `FIRESTORE_EMULATOR_HOST` | Dev only | `localhost:8080` — remove in prod |
| `GHOST_ADMIN_URL` | Yes | Ghost instance root URL |
| `GHOST_ADMIN_API_KEY` | Yes | `<id>:<secret>` from Ghost integration page |
| `GOOGLE_SEARCH_API_KEY` | Yes | Google Custom Search API key |
| `GOOGLE_SEARCH_ENGINE_ID` | Yes | Programmable Search Engine cx |
| `GCS_EVIDENCE_BUCKET` | Yes | Set by Terraform; `glass-record-evidence-{env}` |
| `PUBSUB_RESEARCHER_TOPIC` | Prod only | Set by Terraform |
| `RESEARCHER_MODE` | Yes | `local` (dev) or `pubsub` (Cloud Run) |

### Dashboard (`dashboard/.env.local`)

| Variable | Description |
|---|---|
| `NEXT_PUBLIC_FIREBASE_API_KEY` | From Firebase Console → Project Settings → Web App |
| `NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN` | `<project-id>.firebaseapp.com` |
| `NEXT_PUBLIC_FIREBASE_PROJECT_ID` | GCP project ID |
| `NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET` | `<project-id>.appspot.com` |
| `NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID` | From Firebase Console |
| `NEXT_PUBLIC_FIREBASE_APP_ID` | From Firebase Console |
| `NEXT_PUBLIC_EDITOR_URL` | Cloud Run Editor service URL (for SSE + tips API) |

---

## 11. MCP Log Server (Claude Code integration)

The repo ships a FastMCP server at `mcp/logs_server.py` that gives Claude Code
direct read access to Cloud Run error logs and Firestore cycle failures — no
manual copy-paste required.

### 11a. Install dependencies

```bash
cd glass-record
uv sync --extra mcp
```

### 11b. Register with Claude Code

The `.mcp.json` at the repo root registers the server automatically. Just
re-open the project in Claude Code after installing. Verify it loaded:

```
/mcp
```

You should see `glass-record-logs` listed with three tools:
- `get_cloud_run_errors` — Cloud Logging ERROR/CRITICAL entries
- `get_cycle_errors` — Firestore `activity_log` cycle_failed entries
- `get_compliance_failures` — Firestore `compliance_log` passed=False entries

### 11c. Usage examples

```
# Last 30 min of editor errors
get_cloud_run_errors("glass-record-editor", minutes=30)

# Last 20 cycle failures for a journalist
get_cycle_errors("un-security-council-001")

# Compliance failures
get_compliance_failures("un-security-council-001")
```

> The server uses `GOOGLE_CLOUD_PROJECT=glass-record-prod` from `.mcp.json`.
> For a different environment, override it in `.mcp.json` or set the env var
> before opening Claude Code.

---

## 12. Operational Runbook

### Check a journalist's cycle status

```bash
# Via Firestore
gcloud firestore documents get \
  "projects/glass-record-prod/databases/(default)/documents/journalists/un-security-council-001"

# Via SSE stream (pipe to jq)
curl -N "${EDITOR_URL}/stream/un-security-council-001" \
  -H "Authorization: Bearer $(gcloud auth print-identity-token)"
```

### Trigger a manual cycle

```bash
curl -X POST "${EDITOR_URL}/run" \
  -H "Authorization: Bearer $(gcloud auth print-identity-token)" \
  -H "Content-Type: application/json" \
  -d '{
    "journalist_id": "un-security-council-001",
    "mandate": "Investigate human rights implications of UN Security Council decisions and vetoes.",
    "jurisdiction": "UN",
    "tier": "free"
  }'
```

### View costs

```bash
# All cycles for a journalist
gcloud firestore documents list \
  "projects/glass-record-prod/databases/(default)/documents/journalists/un-security-council-001/cost_ledger"

# Or on the public dashboard: /{journalist_id} → Cost tab
```

### Tail Cloud Run logs

```bash
gcloud logging tail \
  'resource.type="cloud_run_revision" resource.labels.service_name="glass-record-editor"' \
  --project=glass-record-prod --format="value(jsonPayload)"
```

Or ask Claude Code directly (no shell needed — uses MCP log server):
```
get_cloud_run_errors("glass-record-editor", minutes=60)
get_cycle_errors("un-security-council-001")
```

### Neo4j graph inspect

```bash
# Connect to Aura via cypher-shell
cypher-shell -a $NEO4J_URI -u $NEO4J_USER -p $NEO4J_PASSWORD \
  "MATCH (j:Journalist)-[:INVESTIGATED]->(s:Story) RETURN j.journalist_id, s.title LIMIT 25"
```

---

## 13. Architecture Quick Reference

```
Cloud Scheduler (daily cron)
  └─► POST /run → Editor Cloud Run (glass-record-editor)
        ├─ Firestore: load mandate (immutable)
        ├─ Gemini: select story + decompose sub-questions
        ├─ Pub/Sub: publish per sub-question → Researcher Cloud Run (×N parallel)
        │     └─ Google Search → Playwright scrape → Gemini analysis
        │        → Firestore evidence_locker + GCS raw files + Neo4j graph
        ├─ Compliance Agent: injection scan + mandate drift check → Firestore compliance_log
        ├─ Legal Tree Builder: Gemini structured output → Firestore legal_trees
        ├─ Ghost CMS: publish story → Firestore stories
        └─ Cost Ledger: token counts → Firestore cost_ledger

Dashboard (Firebase App Hosting — Next.js)
  ├─ Firestore onSnapshot: real-time activity, evidence, compliance, stories, costs, tips
  ├─ GET /stream/{id}: SSE live cycle events (Editor Cloud Run)
  └─ GET /graph/{id}: Neo4j nodes+edges → Knowledge Graph visualization

Tips flow:
  POST /tips/{id} → Firestore tips (public)
  └─ BackgroundTask: Verification Agent → Gemini cross-check → update tip.verification
```

---

## 14. Cost Estimates (GCP free tier optimised)

| Service | Free tier | Estimated monthly at 1 journalist |
|---|---|---|
| Cloud Run | 2M req / 360k vCPU-s / 180k GiB-s | ~$0 (scale-to-zero) |
| Firestore | 1 GB storage, 50k reads/day | ~$0 |
| Cloud Scheduler | 3 jobs free | ~$0 |
| Pub/Sub | 10 GB/month | ~$0 |
| Artifact Registry | 0.5 GB free | ~$0.10 |
| Cloud Storage | 5 GB free | ~$0 |
| Vertex AI (Gemini) | Pay per token | ~$1–$5/day |
| Neo4j Aura Free | 5 GB, always-on | ~$0 |
| Ghost (self-hosted, e2-micro) | — | ~$6/month |
| Firebase App Hosting | Generous free tier | ~$0 |
| **Total (ex-Gemini)** | | **~$6–$8/month** |

> The biggest cost is Gemini. Use `GEMINI_MODEL=gemini-1.5-flash-002` ($0.075/1M input, $0.30/1M output) during development to reduce spend by ~95%.
