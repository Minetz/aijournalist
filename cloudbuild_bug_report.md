# Cloud Build Deployment Bug Report: The Glass Record

## 1. Overview
During the initial deployment of the Glass Record platform to GCP, the CI/CD pipeline (`cloudbuild.yaml`) experienced a sequence of failures. The most persistent issues occurred during the `unit-tests` step and the `build-base` Docker step.

---

## 2. Sequence of Failures & Fixes

### Issue 1: `cloudbuild.yaml` Path and Naming Mismatches
*   **Problem:** The `cloudbuild.yaml` referenced incorrect Dockerfile names (`Dockerfile.base` instead of `base.Dockerfile`) and an incorrect Artifact Registry repository name (`glass-record` instead of the Terraform-provisioned `agents`).
*   **Fix:** Updated `cloudbuild.yaml` with correct `.Dockerfile` extensions and the correct `_AR_REPO: agents` substitution.

### Issue 2: Hardcoded Base Image in Child Dockerfiles
*   **Problem:** `editor.Dockerfile` and `researcher.Dockerfile` used a hardcoded `FROM glass-record/base:latest` instead of accepting the dynamically tagged base image from Cloud Build.
*   **Fix:** Updated both Dockerfiles to use the `ARG BASE_IMAGE` pattern.

### Issue 3: Missing IAM Permissions for Cloud Build
*   **Problem:** The default Compute Engine service account used by Cloud Build lacked permission to retrieve the source code from the Cloud Storage bucket (`storage.objects.get` denied).
*   **Fix:** Granted `roles/storage.objectAdmin` and `roles/cloudbuild.builds.builder` to the Cloud Build SAs.

### Issue 4: `unit-tests` Step Failure (Missing Extra Dependencies)
*   **Problem:** The `unit-tests` step failed with `pytest` exit code 127 (command not found). The `cloudbuild.yaml` tried to install the non-existent `.[test]` extras group.
*   **Fix:** Changed `.[test]` to `.[dev]` to match `pyproject.toml`.

### Issue 5: `unit-tests` Step Failure (Setuptools Flat-Layout Conflict)
*   **Problem:** After fixing the extras group, `pip install -e .` failed because `setuptools` detected multiple top-level packages (`agents`, `cms`, `docker`, `infra`, etc.) in a flat layout and refused to build the editable package to avoid accidental inclusions.
*   **Fix:** Added the `[tool.setuptools.packages.find]` block to `pyproject.toml`, explicitly instructing it to only include `["agents*", "tools*", "cms*", "graph*"]`. Test step was also simplified to use `python -m pytest` and plain `pip` to avoid PATH and `uv` execution issues in the Cloud Build environment.
*   *Verification:* Running the test command locally inside a `python:3.12-slim` Docker container resulted in `16 passed` ✅.

### Issue 6: `Mock` vs `AsyncMock` in Unit Tests
*   **Problem:** Local test verification revealed a `TypeError` in `test_publish.py` because `await db.collection().document().set()` was being called on a standard `MagicMock`.
*   **Fix:** Updated the `mock_firestore_client` fixture in `conftest.py` to ensure `.set()`, `.update()`, and `.add()` return `AsyncMock` instances.

### Issue 7: `SHORT_SHA` Substitution Error in Manual Triggers
*   **Problem:** When triggering `gcloud builds submit` manually, the `$SHORT_SHA` variable is not populated (it only exists for Git triggers). This caused invalid Docker image tags like `/base:` (empty tag string), causing `docker build` to fail with exit code 125.
*   **Fix:** Replaced `$SHORT_SHA` with `$_TAG` and added a default `_TAG: manual` to `substitutions` in `cloudbuild.yaml`.

### Issue 8: Docker BuildKit Cache Mount Failure
*   **Problem:** The `build-base` step failed with exit code 1 because the `docker/base.Dockerfile` utilized BuildKit-specific cache syntax (`RUN --mount=type=cache`), which the standard Cloud Build Docker executor does not support by default without advanced configuration.
*   **Fix:** Removed the `--mount=type=cache` flags from the `base.Dockerfile`.

### Issue 9: `uv.lock` Missing from Docker Build Context ✅ Fixed
*   **Problem:** `base.Dockerfile` contained `COPY pyproject.toml uv.lock ./` followed by `uv sync --frozen`. The `uv.lock` file is listed in `.gitignore` and was therefore absent from the Cloud Build source context. Docker exited immediately with a COPY failure (exit code 1). This was the root cause of the persistent `build-base` failure that survived all previous fixes.
*   **Fix:** Rewrote `base.Dockerfile` to use `pip` and an explicit venv at `/app/.venv` instead of `uv`. No lockfile is required. The venv lives inside `/app` so it is included in the multi-stage `COPY --from=builder /app /app` instruction. The install approach now matches the already-working `unit-tests` step in `cloudbuild.yaml`.

### Issue 10: Playwright Browser Binary Lost in Multi-Stage Build ✅ Fixed
*   **Problem:** `playwright install chromium` stores the browser binary at `/root/.cache/ms-playwright/` by default. The multi-stage `COPY --from=builder /app /app` only copies `/app`, silently discarding the browser. The build succeeded but the container would crash at runtime when Playwright tried to launch Chromium.
*   **Fix:** Set `PLAYWRIGHT_BROWSERS_PATH=/app/.playwright` in the builder stage before installing, so the binary lands inside `/app` and is carried through to the runtime image. The runtime stage then runs `playwright install-deps chromium` to install the required Chromium system libraries (libnss3, libgbm1, etc.) into the slim image via `apt-get`.

### Issue 11: No `.dockerignore` — Bloated Build Context ✅ Fixed
*   **Problem:** `COPY . .` had no `.dockerignore`, so Docker sent the entire repository to the build daemon on every build, including `.venv/`, `node_modules/`, `.next/`, and Terraform state — adding hundreds of MB to the build context and slowing every build.
*   **Fix:** Added `glass-record/.dockerignore` excluding all ephemeral and large paths.

---

### Issue 12: `docker push --all-tags` Unsupported by Cloud Build Docker Builder ✅ Fixed
*   **Problem:** The `push-editor` and `push-researcher` steps used `docker push --all-tags`, which is not supported by the `gcr.io/cloud-builders/docker` builder version in Cloud Build. The push failed silently with exit code 1.
*   **Fix:** Replaced `--all-tags` with explicit individual tag pushes (`:manual` and `:latest`) for base, editor, and researcher images. Also added `push-base` steps that were previously missing.

### Issue 13: Cloud Build IAM Grants on Wrong Service Account ✅ Fixed
*   **Problem:** All IAM permissions (`roles/artifactregistry.writer`, `roles/run.admin`, etc.) were granted to the Cloud Build SA (`124545852000@cloudbuild.gserviceaccount.com`), but Cloud Build actually runs as the default Compute Engine SA (`124545852000-compute@developer.gserviceaccount.com`). Docker push and Cloud Run deploy both failed with `PERMISSION_DENIED`.
*   **Fix:** Granted `roles/artifactregistry.writer`, `roles/logging.logWriter`, `roles/run.admin`, and `roles/iam.serviceAccountUser` to the Compute Engine SA.

### Issue 14: Deploy Steps Reference Non-Existent Service Accounts ✅ Fixed
*   **Problem:** The `deploy-editor` and `deploy-researcher` steps in `cloudbuild.yaml` referenced `glass-record-editor@` and `glass-record-researcher@` service accounts, which do not exist. Terraform created a single shared SA: `glass-record-agent@`.
*   **Fix:** Updated both deploy steps to use `--service-account=glass-record-agent@$PROJECT_ID.iam.gserviceaccount.com`.

### Issue 15: Terraform `image_tag` Mismatch ✅ Fixed
*   **Problem:** `prod.tfvars` used `image_tag = "stable"`, but Cloud Build pushes `:manual` and `:latest` tags. Terraform destroyed the Cloud Run services then failed to recreate them because the `:stable` image didn't exist in Artifact Registry.
*   **Fix:** Changed `prod.tfvars` to `image_tag = "latest"`.

---

## 3. Current State

**Status: Platform fully deployed. All 15 issues resolved. ✅**
**Architecture simplified to fully GCP-native. All external services removed. ✅**

| Resource | Status | URL |
|---|---|---|
| Editor Cloud Run | ✅ Healthy | `https://glass-record-editor-c6kegpaz7q-uc.a.run.app` |
| Researcher Cloud Run | ✅ Serving | `https://glass-record-researcher-c6kegpaz7q-uc.a.run.app` |
| Artifact Registry | ✅ 6 images | `us-central1-docker.pkg.dev/glass-record-prod/agents` |
| Terraform | ✅ 13 resources | All in sync |
| Firestore rules | ✅ Deployed | — |
| MCP log server | ✅ Ready | — |

---

## 4. Post-Deployment Architecture Simplification

After deployment the platform was refactored to remove all external service dependencies.
The required credentials went from 13 environment variables down to 5.

### Removed: Ghost CMS
- **Was:** Articles published to Ghost via Admin API (JWT auth); required a separate VM or Ghost Pro subscription ($6–9/month).
- **Now:** Article `body_html` stored in Firestore `stories/{story_id}` and rendered inline in the Next.js dashboard. No external service needed.
- **Deleted:** `cms/ghost.py`, `PyJWT` dependency, `GHOST_ADMIN_URL` / `GHOST_ADMIN_API_KEY` env vars.

### Removed: Neo4j Aura
- **Was:** Knowledge graph stored in Neo4j Aura (external cloud); required `neo4j` Python driver, `NEO4J_URI/USER/PASSWORD` env vars, Cypher schema setup.
- **Now:** Knowledge graph derived from Firestore `evidence_locker` collection (entities already stored on each evidence document). `/graph/{journalist_id}` API builds nodes/links from Firestore queries at request time.
- **Deleted:** `graph/client.py`, `graph/queries.py`, `graph/schema.cypher`, `neo4j>=5.28` dependency, all three `NEO4J_*` env vars.

### Removed: Google Custom Search + Playwright
- **Was:** Researcher pipeline: Custom Search API → Playwright scraper → Gemini analysis (3 nodes, 2 external API keys, Playwright bloating the Docker image by ~400 MB).
- **Now:** Single `grounded_research` node using `gemini-2.0-flash` with `google_search` tool. Gemini handles search + content retrieval natively via Vertex AI. No browser, no external search API key.
- **Deleted:** `tools/search/google_search.py`, `tools/browser/scraper.py`, `browser-use`, `playwright`, `docling` dependencies, `GOOGLE_SEARCH_API_KEY` / `GOOGLE_SEARCH_ENGINE_ID` env vars.
- **Researcher graph:** 3 nodes (search → scrape → analyse_store) → 1 node (grounded_research).

### Added: Investigation "glass window" tab
- New **Investigation** tab in the dashboard shows the AI's work as a human-readable narrative:
  - Sub-questions the journalist is researching
  - Findings grouped by question (claims + sources)
  - Entity cross-references (who/what appears repeatedly across sources)
  - Latest published article rendered inline
- Story rendering moved inline (full article HTML in the dashboard, not a Ghost URL).

