import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture
def client():
    from agents.editor.main import app
    return TestClient(app)


def test_spawn_validates_short_mandate(client):
    resp = client.post("/spawn", json={
        "mandate": "too short",
        "jurisdiction": "UN",
    })
    assert resp.status_code == 422
    assert "20 characters" in resp.text


def test_spawn_validates_unknown_jurisdiction(client):
    resp = client.post("/spawn", json={
        "mandate": "Investigate human rights implications of UN Security Council decisions.",
        "jurisdiction": "MARS",
    })
    assert resp.status_code == 422
    assert "Unknown jurisdiction" in resp.text


def test_spawn_validates_invalid_cron(client):
    resp = client.post("/spawn", json={
        "mandate": "Investigate human rights implications of UN Security Council decisions.",
        "jurisdiction": "UN",
        "schedule": "not-a-cron",
    })
    assert resp.status_code == 422
    assert "cron" in resp.text.lower()


@pytest.mark.asyncio
async def test_spawn_success(mock_firestore_client):
    with (
        patch("agents.editor.spawn.firestore.AsyncClient",
              return_value=mock_firestore_client),
        patch("agents.editor.spawn.register_journalist", AsyncMock()),
        patch("agents.editor.spawn._create_scheduler_job",
              AsyncMock(return_value="projects/p/locations/r/jobs/j")),
        patch("agents.editor.spawn.get_settings") as mock_settings,
    ):
        mock_settings.return_value = MagicMock(google_cloud_project="glass-record-dev")
        from agents.editor.spawn import spawn_journalist, SpawnRequest
        result = await spawn_journalist(SpawnRequest(
            mandate="Investigate human rights implications of UN Security Council decisions.",
            jurisdiction="UN",
        ))

    assert result.journalist_id.startswith("un-")
    assert result.jurisdiction == "UN"
    assert result.schedule == "0 6 * * *"
