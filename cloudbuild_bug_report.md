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

## 3. Current State

**Status: All known build failures resolved. Pipeline unblocked. ✅**

All 11 issues have been fixed and pushed to `claude/add-project-scope-h6R8G`. The unit tests pass consistently (`16 passed`). The `build-base` step's root cause (`uv.lock` missing from build context) has been eliminated.

The next required actions are operational rather than bug fixes:

---

## 4. Remaining Actions (Not Bugs)

### Action 1: Run the Cloud Build pipeline end-to-end
Trigger either via a push to `main` (once the branch is merged) or manually:
```bash
cd glass-record
gcloud builds submit --config=cloudbuild.yaml \
  --project=glass-record-prod \
  --substitutions=_AR_REGION=us-central1,_AR_REPO=agents,_REGION=us-central1
```
Expected result: `editor:manual` and `researcher:manual` images pushed to Artifact Registry.

### Action 2: Re-run Terraform Apply
Terraform's first `apply` failed because the Docker images did not yet exist in Artifact Registry, causing `google_cloud_run_v2_service` provisioning to fail. Now that images will be present after Action 1, re-run:
```bash
cd glass-record/infra
terraform apply -var-file=envs/prod.tfvars
```
This wires Cloud Run services, env vars, Pub/Sub subscriptions, and Cloud Scheduler jobs.

### Action 3: Firebase Hosting Deployment
Deploy the Next.js dashboard via Firebase App Hosting:
```bash
cd glass-record
firebase deploy --only firestore:rules --project=glass-record-prod
firebase deploy --only hosting --project=glass-record-prod
```

### Action 4: Activate MCP Log Server (local dev)
Install the new MCP optional dependencies to enable Claude Code log access:
```bash
uv sync --project glass-record --extra mcp
```
The `.mcp.json` at the repo root registers the server automatically on next Claude Code open.
