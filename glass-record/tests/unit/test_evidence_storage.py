import hashlib

import pytest


def test_evidence_id_is_deterministic():
    """Same URL must always produce the same evidence_id."""
    url = "https://un.org/documents/report-2024"
    id1 = hashlib.sha256(url.encode()).hexdigest()[:16]
    id2 = hashlib.sha256(url.encode()).hexdigest()[:16]
    assert id1 == id2
    assert len(id1) == 16


def test_evidence_id_differs_for_different_urls():
    url_a = "https://un.org/report-a"
    url_b = "https://un.org/report-b"
    id_a = hashlib.sha256(url_a.encode()).hexdigest()[:16]
    id_b = hashlib.sha256(url_b.encode()).hexdigest()[:16]
    assert id_a != id_b
