# The Glass Record — Launch Guide

> Complete credentials, configuration, and deployment steps.
> Follow sections in order. Estimated time: ~1 hour on a fresh GCP project.
>
> **Only external credential required: a GCP project + service account.**
> Ghost CMS, Neo4j, and Google Custom Search have been removed.
> Web research is handled by Gemini's built-in Google Search grounding.

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

### 3b. Vertex AI / Gemini (+ Google Search grounding)

No API key required — Vertex AI uses the service account above.
Ensure the account has `roles/aiplatform.user` (Terraform grants this automatically).

Set in `.env`:
```
GOOGLE_GENAI_USE_VERTEXAI=true
GEMINI_MODEL=gemini-3.1-pro-preview
```

> **Model note:** `gemini-3.1-pro-preview` supports Google Search grounding, which the
> Researcher agent uses instead of a separate search API + Playwright scraper.
>
> **Cost note:** Gemini 2.0 Flash costs $0.10/1M input, $0.40/1M output tokens.
> Google Search grounding queries are billed at $35/1000 queries via Vertex AI.
> A typical investigation cycle (3–7 sub-questions) = 3–7 grounding queries ≈ $0.02–$0.05.
> The cost ledger on each journalist's public page shows exact spend.

### 3c. Firebase (for dashboard)

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
```

To also enable the MCP log-access server for Claude Code:
```bash
uv sync --extra mcp
```

### 4b. Start local services

```bash
docker compose up -d
# Wait ~10s for Firestore emulator to be healthy
docker compose ps   # should show "healthy"
```

Local service URLs:
- Firestore emulator: http://localhost:8080

### 4c. Create `.env` from template

```bash
cp .env.example .env
# Fill in:
#   GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account.json
#   GOOGLE_CLOUD_PROJECT=glass-record-dev
# Leave FIRESTORE_EMULATOR_HOST=localhost:8080 for local dev
```

### 4d. Start the Editor service

```bash
FIRESTORE_EMULATOR_HOST=localhost:8080 \
  uv run uvicorn agents.editor.main:app --reload --port 8000
```

Health check: `curl http://localhost:8000/health` → `{"status":"ok"}`

### 4e. Start the Researcher service (optional — local mode only)

In development, `RESEARCHER_MODE=local` (the default) means the Editor spawns
researcher workers in-process using LangGraph `Send()`. You do **not** need to
run the Researcher service separately.

If you want to test the Researcher in isolation (e.g. to develop the
`grounded_research` node), run it on port 8001:

```bash
FIRESTORE_EMULATOR_HOST=localhost:8080 \
  uv run uvicorn agents.researcher.main:app --reload --port 8001
```

Health check: `curl http://localhost:8001/health` → `{"status":"ok"}`

Test a single sub-question manually:

```bash
curl -X POST http://localhost:8001/run \
  -H "Content-Type: application/json" \
  -d '{
    "journalist_id": "un-xxxxxxxx",
    "mandate": "Investigate human rights implications of UN Security Council veto use.",
    "jurisdiction": "UN",
    "tier": "free",
    "sub_question": "How many Security Council vetoes were cast between 2022 and 2024?",
    "cycle_id": "test-cycle-001"
  }'
```

Response: `{"status": "ok", "evidence_ids": ["abc123...", ...]}`

Evidence items are written to Firestore `evidence_locker` and raw text to GCS.

> **Pub/Sub mode (production):** Set `RESEARCHER_MODE=pubsub`. The Editor publishes
> one Pub/Sub message per sub-question; Cloud Run auto-scales Researcher instances
> to process them in parallel. Terraform provisions the topic, subscription, and
> Cloud Run service automatically (section 6).

### 4f. Run tests

```bash
FIRESTORE_EMULATOR_HOST=localhost:8080 \
  uv run pytest tests/unit -v
```

### 4g. Start the dashboard

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

### 6d. No additional secrets needed

All credentials (Firestore, Vertex AI, GCS, Pub/Sub) are covered by the
`glass-record-agent` service account IAM roles provisioned by Terraform.
There are no external service secrets to manage.

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
| `GEMINI_MODEL` | Yes | `gemini-2.0-flash` (required for Search grounding) |
| `FIRESTORE_EMULATOR_HOST` | Dev only | `localhost:8080` — remove in prod |
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

### Inspect knowledge graph

The graph is derived from Firestore — no separate database needed:
```bash
# Browse evidence locker in Firestore
gcloud firestore documents list \
  "projects/glass-record-prod/databases/(default)/documents/journalists/un-security-council-001/evidence_locker"

# Or via the dashboard → Knowledge Graph tab (force-directed visualization)
```

---

## 13. Architecture Quick Reference

```
Cloud Scheduler (daily cron)
  └─► POST /run → Editor Cloud Run (glass-record-editor)
        ├─ Firestore: load mandate (immutable)
        ├─ Gemini: select story + decompose sub-questions
        ├─ Pub/Sub: publish per sub-question → Researcher Cloud Run (×N parallel)
        │     └─ Gemini (google_search grounding): search + extract claims + entities
        │        → Firestore evidence_locker + GCS raw grounded text
        ├─ Compliance Agent: injection scan + mandate drift → Firestore compliance_log
        ├─ Legal Tree Builder: Gemini structured output → Firestore legal_trees
        ├─ Article synthesis: Gemini → body_html stored in Firestore stories
        └─ Cost Ledger: token counts → Firestore cost_ledger

Dashboard (Firebase App Hosting — Next.js)
  ├─ Firestore onSnapshot: real-time activity, evidence, compliance, stories, costs, tips
  ├─ GET /stream/{id}: SSE live cycle events (Editor Cloud Run)
  ├─ GET /graph/{id}: Firestore-derived knowledge graph (journalist→story→evidence→entity)
  └─ Investigation tab: sub-questions grouped with findings + entity cross-references
     Stories tab: full article rendered inline (no external CMS)

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
| Vertex AI (Gemini 2.0 Flash) | Pay per token | ~$0.10–$1/day |
| Gemini Search grounding | $35/1000 queries | ~$0.02–$0.05/cycle |
| Firebase App Hosting | Generous free tier | ~$0 |
| **Total** | | **~$0–$2/month + Gemini** |

> Gemini 2.0 Flash is significantly cheaper than 1.5 Pro and supports Search grounding
> natively. No Ghost VM, no Neo4j, no Custom Search Engine API costs.
