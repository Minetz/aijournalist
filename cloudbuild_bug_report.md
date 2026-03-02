# Cloud Build Deployment Bug Report: The Glass Record

## 1. Overview
During the initial deployment of the Glass Record platform to GCP, the CI/CD pipeline (`cloudbuild.yaml`) experienced a sequence of failures. The most persistent issues occurred during the `unit-tests` step and the `build-base` Docker step.

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

## 3. Current State
**Status:** **Build `52d2fd0a-03ea-4001-b05a-bf2635615cd6` is currently RUNNING.**

All the above fixes have been committed to the repository and pushed. A fresh Cloud Build pipeline was triggered with the changes.
The build is currently executing the `build-base` step. Because it must download Chromium and its OS dependencies for Playwright via `uv sync`, this step is expected to take between 10 to 15 minutes.

## 4. Pending Problems to Solve (Next Steps)
If the current Cloud Build succeeds, the following actions remain to complete the deployment loop:
1.  **Monitor Build Success:** Confirm the `unittests`, `base`, `editor`, and `researcher` images build, push, and deploy successfully to Cloud Run.
2.  **Re-run Terraform Apply:** Run `terraform apply` one final time to configure the Cloud Run services properly. Terraform initially failed to provision the `google_cloud_run_v2_service` blocks because the Docker images did not exist in Artifact Registry yet. Now that they will be built and pushed, Terraform can wire the services, environmental variables, and Pub/Sub subscriptions together natively.
3.  **Firebase Hosting Deployment:** Deploy the frontend UI via Firebase App Hosting to consume the backend APIs.
