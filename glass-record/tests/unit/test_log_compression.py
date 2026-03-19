"""Unit tests for activity_log history compression."""
import sys
import json
import datetime
from unittest.mock import MagicMock, AsyncMock, patch

for mod in [
    "google", "google.cloud", "google.cloud.firestore",
    "google.cloud.storage",
]:
    sys.modules.setdefault(mod, MagicMock())

import pytest  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_doc(timestamp: str, action: str = "story_selected") -> MagicMock:
    doc = MagicMock()
    doc.to_dict.return_value = {"timestamp": timestamp, "action": action}
    doc.reference = MagicMock()
    return doc


def _make_db(docs: list) -> MagicMock:
    """Mock Firestore that returns docs from the activity_log stream."""
    async def fake_stream():
        for doc in docs:
            yield doc

    query = MagicMock()
    query.stream = fake_stream
    query.where = MagicMock(return_value=query)

    col_ref = MagicMock()
    col_ref.where = MagicMock(return_value=query)

    doc_ref = MagicMock()
    doc_ref.collection = MagicMock(return_value=col_ref)

    db = MagicMock()
    db.collection.return_value.document.return_value = doc_ref

    # batch() returns an object with delete() and async commit()
    batch = MagicMock()
    batch.delete = MagicMock()
    batch.commit = AsyncMock()
    db.batch.return_value = batch
    return db


def _make_gcs(existing_content: str = "") -> MagicMock:
    """Mock GCS client with a single blob."""
    blob = MagicMock()
    blob.download_as_text = MagicMock(return_value=existing_content)
    blob.upload_from_string = MagicMock()

    bucket = MagicMock()
    bucket.blob = MagicMock(return_value=blob)

    gcs = MagicMock()
    gcs.bucket = MagicMock(return_value=bucket)
    return gcs, blob


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_nothing_to_archive_returns_zeros():
    from agents.shared.log_compression import compress_activity_log
    db = _make_db([])
    gcs, _ = _make_gcs()
    result = await compress_activity_log(db, gcs, "j-001", "test-bucket", keep_days=90)
    assert result == {"archived": 0, "deleted": 0}


@pytest.mark.asyncio
async def test_old_entries_archived_and_deleted():
    from agents.shared.log_compression import compress_activity_log

    # Two old entries in the same month
    docs = [
        _make_doc("2025-11-10T00:00:00"),
        _make_doc("2025-11-20T00:00:00"),
    ]
    db = _make_db(docs)
    gcs, blob = _make_gcs()

    result = await compress_activity_log(db, gcs, "j-001", "test-bucket", keep_days=90)

    assert result["archived"] == 2
    assert result["deleted"] == 2
    # GCS upload should have been called once (one month: 2025-11)
    assert blob.upload_from_string.call_count == 1
    # Both docs should be scheduled for deletion
    assert db.batch.return_value.delete.call_count == 2
    db.batch.return_value.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_entries_grouped_by_month():
    from agents.shared.log_compression import compress_activity_log

    # Entries spanning two different months
    docs = [
        _make_doc("2025-10-05T00:00:00"),
        _make_doc("2025-11-15T00:00:00"),
        _make_doc("2025-11-28T00:00:00"),
    ]
    db = _make_db(docs)
    gcs, blob = _make_gcs()

    await compress_activity_log(db, gcs, "j-001", "test-bucket")

    # Should upload twice — once per month
    assert blob.upload_from_string.call_count == 2


@pytest.mark.asyncio
async def test_existing_gcs_content_is_appended():
    from agents.shared.log_compression import compress_activity_log

    existing = json.dumps({"timestamp": "2025-11-01T00:00:00", "action": "old"}) + "\n"
    docs = [_make_doc("2025-11-10T00:00:00")]
    db = _make_db(docs)
    gcs, blob = _make_gcs(existing_content=existing)

    await compress_activity_log(db, gcs, "j-001", "test-bucket")

    uploaded = blob.upload_from_string.call_args[0][0]
    # Both the old and new entries should appear in the uploaded content
    assert "2025-11-01" in uploaded
    assert "2025-11-10" in uploaded


@pytest.mark.asyncio
async def test_batch_delete_respects_batch_size():
    from agents.shared.log_compression import compress_activity_log, BATCH_SIZE

    # Create BATCH_SIZE + 10 docs to force two batches
    count = BATCH_SIZE + 10
    docs = [_make_doc(f"2025-10-{(i % 28) + 1:02d}T00:00:00") for i in range(count)]
    db = _make_db(docs)
    gcs, _ = _make_gcs()

    result = await compress_activity_log(db, gcs, "j-001", "test-bucket")

    assert result["deleted"] == count
    # Two batches: first of BATCH_SIZE, second of 10
    assert db.batch.return_value.commit.await_count == 2


def test_batch_size_constant_is_safe():
    from agents.shared.log_compression import BATCH_SIZE
    assert BATCH_SIZE <= 500  # Firestore hard limit


@pytest.mark.asyncio
async def test_gcs_new_file_created_when_no_existing():
    """If no existing GCS blob, download raises and we start fresh."""
    from agents.shared.log_compression import compress_activity_log

    docs = [_make_doc("2025-09-01T00:00:00")]
    db = _make_db(docs)
    gcs, blob = _make_gcs()
    blob.download_as_text = MagicMock(side_effect=Exception("blob not found"))

    # Should not raise — treat missing blob as empty
    result = await compress_activity_log(db, gcs, "j-001", "test-bucket")
    assert result["archived"] == 1
    assert blob.upload_from_string.called
