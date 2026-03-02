"""
Glass Record MCP log-access server.

Exposes three tools to Claude Code so it can pull error logs directly
during a session without manual copy-paste:

  get_cloud_run_errors    — Cloud Logging ERROR/CRITICAL entries
  get_cycle_errors        — Firestore activity_log cycle_failed entries
  get_compliance_failures — Firestore compliance_log passed=False entries

Setup (local):
  uv sync --extra mcp          # installs mcp[cli] + google-cloud-logging

The project .mcp.json registers this server automatically when Claude Code
opens the repo.
"""

import json
import os
from datetime import datetime, timedelta, timezone

import structlog
from mcp.server.fastmcp import FastMCP

log = structlog.get_logger()

PROJECT = os.environ.get("GOOGLE_CLOUD_PROJECT", "glass-record-prod")

mcp = FastMCP("glass-record-logs")


# ── lazy clients (avoids import errors when deps are missing at startup) ──────

def _log_client():
    from google.cloud import logging as gcloud_logging  # noqa: PLC0415
    return gcloud_logging.Client(project=PROJECT)


def _firestore_client():
    from google.cloud import firestore  # noqa: PLC0415
    return firestore.Client(project=PROJECT)


# ── tools ─────────────────────────────────────────────────────────────────────

@mcp.tool()
def get_cloud_run_errors(
    service: str = "glass-record-editor",
    minutes: int = 60,
    limit: int = 50,
) -> str:
    """Fetch recent ERROR/CRITICAL log entries from a Glass Record Cloud Run service.

    Args:
        service: Cloud Run service name — 'glass-record-editor' or
                 'glass-record-researcher'
        minutes: How far back to look (default 60)
        limit:   Max entries to return (default 50)
    """
    since = (datetime.now(timezone.utc) - timedelta(minutes=minutes)).isoformat()
    log_filter = (
        f'resource.type="cloud_run_revision" '
        f'resource.labels.service_name="{service}" '
        f'severity>=ERROR '
        f'timestamp>="{since}"'
    )

    entries = []
    for entry in _log_client().list_entries(
        filter_=log_filter,
        max_results=limit,
        order_by="timestamp desc",
    ):
        payload = entry.payload
        text = json.dumps(payload) if isinstance(payload, dict) else str(payload)
        entries.append(
            f"[{entry.timestamp.isoformat() if entry.timestamp else 'unknown'}]"
            f" {entry.severity}: {text[:2000]}"
        )

    if not entries:
        return f"No ERROR/CRITICAL entries in the last {minutes} min for '{service}'."
    return "\n---\n".join(entries)


@mcp.tool()
def get_cycle_errors(journalist_id: str, limit: int = 20) -> str:
    """Fetch recent cycle_failed entries from a journalist's Firestore activity_log.

    Args:
        journalist_id: The journalist document ID (e.g. 'un-security-council-001')
        limit:         Max entries to return (default 20)
    """
    db = _firestore_client()
    docs = (
        db.collection("journalists")
        .document(journalist_id)
        .collection("activity_log")
        .where("action", "==", "cycle_failed")
        .limit(limit * 3)  # over-fetch; sort in Python to avoid composite index
        .stream()
    )

    results = sorted(
        [d.to_dict() for d in docs],
        key=lambda x: x.get("timestamp", ""),
        reverse=True,
    )[:limit]

    if not results:
        return f"No cycle_failed entries for journalist '{journalist_id}'."

    lines = [
        f"[{r.get('timestamp', 'unknown')}] cycle={r.get('cycle_id', 'unknown')} "
        f"| {json.dumps(r.get('data', {}))}"
        for r in results
    ]
    return "\n".join(lines)


@mcp.tool()
def get_compliance_failures(journalist_id: str, limit: int = 20) -> str:
    """Fetch recent failed compliance checks from a journalist's Firestore compliance_log.

    Args:
        journalist_id: The journalist document ID
        limit:         Max entries to return (default 20)
    """
    db = _firestore_client()
    docs = (
        db.collection("journalists")
        .document(journalist_id)
        .collection("compliance_log")
        .where("passed", "==", False)
        .limit(limit * 3)  # over-fetch; sort in Python to avoid composite index
        .stream()
    )

    results = sorted(
        [d.to_dict() for d in docs],
        key=lambda x: x.get("recorded_at", ""),
        reverse=True,
    )[:limit]

    if not results:
        return f"No compliance failures for journalist '{journalist_id}'."

    lines = []
    for r in results:
        flags = r.get("injection_flags", []) + r.get("drift_flags", [])
        lines.append(
            f"[{r.get('recorded_at', 'unknown')}] cycle={r.get('cycle_id', 'unknown')}\n"
            f"  flags: {flags}\n"
            f"  reasoning: {r.get('reasoning', '')[:500]}"
        )
    return "\n---\n".join(lines)


# ── entrypoint ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    mcp.run()
