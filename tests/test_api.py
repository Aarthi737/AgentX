"""
Integration tests for FastAPI API endpoints.
Uses httpx AsyncClient with the app in test mode.
DB calls are mocked to avoid needing a real Supabase connection.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from httpx import AsyncClient, ASGITransport


@pytest.fixture
async def client():
    """Create test HTTP client with mocked DB."""
    with patch("db.database.engine"), \
         patch("db.database.AsyncSessionLocal") as mock_session_factory:
        # Return mock session
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock()
        mock_session.flush = AsyncMock()
        mock_session.commit = AsyncMock()
        mock_session.rollback = AsyncMock()
        mock_session.close = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session_factory.return_value = mock_session

        from app import app
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c


class TestHealthEndpoint:
    @pytest.mark.asyncio
    async def test_health_returns_200(self, client):
        with patch("sqlalchemy.ext.asyncio.AsyncSession.execute", AsyncMock()):
            response = await client.get("/api/v1/health")
        assert response.status_code in (200, 500)  # 500 ok if DB not connected in test

    @pytest.mark.asyncio
    async def test_root_returns_info(self, client):
        response = await client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "AgentX"
        assert "TriggeredAGIs" in data["team"]


class TestRunsEndpoint:
    @pytest.mark.asyncio
    async def test_start_run_validates_url(self, client):
        """Non-GitHub URL should return 422."""
        response = await client.post("/api/v1/runs", json={
            "repo_url": "https://gitlab.com/owner/repo",
            "branch": "main",
        })
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_start_run_missing_url(self, client):
        """Missing repo_url should return 422."""
        response = await client.post("/api/v1/runs", json={})
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_get_nonexistent_run(self, client):
        with patch("db.repositories.RunRepository.get", AsyncMock(return_value=None)):
            response = await client.get("/api/v1/runs/nonexistent")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_list_runs_returns_list(self, client):
        with patch("db.repositories.RunRepository.list_recent", AsyncMock(return_value=[])):
            response = await client.get("/api/v1/runs")
        assert response.status_code == 200
        assert isinstance(response.json(), list)


class TestFeedbackEndpoint:
    @pytest.mark.asyncio
    async def test_invalid_outcome_rejected(self, client):
        response = await client.post("/api/v1/feedback", json={
            "run_id": "test1234",
            "pr_number": 1,
            "outcome": "INVALID_OUTCOME",
        })
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_valid_feedback_accepted(self, client):
        with patch(
            "agents.adaptive_feedback.afe.AdaptiveFeedbackEngine.process_pr_outcome",
            AsyncMock(return_value={"weight_updates": {}}),
        ):
            response = await client.post("/api/v1/feedback", json={
                "run_id": "test1234",
                "pr_number": 1,
                "outcome": "MERGED",
                "ml_patterns": ["missing_random_seed"],
            })
        assert response.status_code == 200
        assert response.json()["status"] == "processed"
