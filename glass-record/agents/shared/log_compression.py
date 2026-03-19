"""
activity_log history compression.

The activity_log collection grows unboundedly as cycles run. This module
archives entries older than `keep_days` to GCS as newline-delimited JSON
(JSONL), then batch-deletes them from Firestore.

Archive path: {journalist_id}/activity_log_archive/{YYYY-MM}.jsonl
Entries are appended to existing monthly archives so the operation is
safe to run multiple times.

Firestore deletes are performed in batches of BATCH_SIZE to stay within
the 500-write-per-batch limit.
"""
import collections
import datetime
import json
from typing import TYPE_CHECKING

import structlog
from google.cloud import firestore, storage

if TYPE_CHECKING:
    pass

log = structlog.get_logger()

BATCH_SIZE = 400  # below the 500-write Firestore limit


async def compress_activity_log(
    db: firestore.AsyncClient,
    gcs_client: storage.Client,
    journalist_id: str,
    bucket_name: str,
    keep_days: int = 90,
) -> dict:
    """
    Archive activity_log entries older than keep_days to GCS and delete them
    from Firestore.

    Returns {"archived": N, "deleted": N} with counts of affected entries.
    """
    cutoff = (
        datetime.datetime.utcnow() - datetime.timedelta(days=keep_days)
    ).isoformat()

    log.info("compress_activity_log_start", journalist_id=journalist_id,
             cutoff=cutoff, keep_days=keep_days)

    # Collect old documents (stream to avoid loading everything into memory at once)
    old_docs: list = []
    async for doc in (
        db.collection("journalists")
        .document(journalist_id)
        .collection("activity_log")
        .where("timestamp", "<", cutoff)
        .stream()
    ):
        old_docs.append(doc)

    if not old_docs:
        log.info("compress_activity_log_nothing_to_archive", journalist_id=journalist_id)
        return {"archived": 0, "deleted": 0}

    # Group by YYYY-MM for monthly archive files
    by_month: dict[str, list[dict]] = collections.defaultdict(list)
    for doc in old_docs:
        data = doc.to_dict()
        month = (data.get("timestamp") or "")[:7] or "unknown"
        by_month[month].append(data)

    # Write/append to GCS monthly JSONL files
    bucket = gcs_client.bucket(bucket_name)
    for month, entries in by_month.items():
        blob_path = f"{journalist_id}/activity_log_archive/{month}.jsonl"
        blob = bucket.blob(blob_path)

        existing = ""
        try:
            existing = blob.download_as_text()
        except Exception:
            pass  # new file

        new_lines = "\n".join(json.dumps(e, ensure_ascii=False) for e in entries)
        content = (existing.rstrip("\n") + "\n" + new_lines + "\n").lstrip("\n")
        blob.upload_from_string(content, content_type="application/jsonl")
        log.info("activity_log_archived_to_gcs", journalist_id=journalist_id,
                 month=month, count=len(entries), blob=blob_path)

    # Batch-delete from Firestore
    total_deleted = 0
    for i in range(0, len(old_docs), BATCH_SIZE):
        batch = db.batch()
        chunk = old_docs[i: i + BATCH_SIZE]
        for doc in chunk:
            batch.delete(doc.reference)
        await batch.commit()
        total_deleted += len(chunk)

    log.info("compress_activity_log_done", journalist_id=journalist_id,
             archived=len(old_docs), deleted=total_deleted)
    return {"archived": len(old_docs), "deleted": total_deleted}
