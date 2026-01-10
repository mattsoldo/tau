import pytest
from httpx import AsyncClient, ASGITransport

from tau.api import create_app
from tau.config import Settings
from tau.database import get_db_session


class DummyUpdateService:
    """Minimal stub to avoid real git/system calls in update routes."""

    def __init__(self, db_session=None):
        self.db_session = db_session

    async def get_update_status(self):
        return {
            "current_version": "abc123",
            "available_version": None,
            "update_available": False,
            "is_updating": False,
            "last_check_at": None,
        }

    async def check_for_updates(self):
        return {
            "update_available": False,
            "current_version": "abc123",
            "latest_version": "abc123",
            "commits_behind": 0,
            "changelog": "",
        }

    async def start_update(self, background_tasks):
        return {"message": "Update started. System will restart when complete.", "update_id": 1}

    async def get_update_history(self, limit: int = 10):
        return []

    async def get_changelog(self, from_commit: str, to_commit: str = "HEAD"):
        return "changelog"


@pytest.mark.asyncio
async def test_updates_require_token(monkeypatch):
    import tau.api.routes.updates as updates

    # Force settings to require a token
    settings = Settings(updates_auth_token="secret-token", api_docs_enabled=True, cors_origins=["*"])
    monkeypatch.setattr(updates, "get_settings", lambda: settings)
    # Replace UpdateService with dummy to avoid real git/system interactions
    monkeypatch.setattr(updates, "UpdateService", DummyUpdateService)

    # Create isolated app and override DB dependency to avoid real DB usage
    app = create_app(settings)
    async def dummy_session():
        yield None
    app.dependency_overrides[get_db_session] = dummy_session

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Missing token should be rejected
        resp = await client.get("/api/updates/status")
        assert resp.status_code == 401

        # Correct token should allow access
        resp_ok = await client.get("/api/updates/status", headers={"X-Update-Token": "secret-token"})
        assert resp_ok.status_code == 200
        body = resp_ok.json()
        assert body["current_version"] == "abc123"
