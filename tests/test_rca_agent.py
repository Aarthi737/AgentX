import asyncio
import pytest
from unittest.mock import AsyncMock, patch


@pytest.fixture
def rca_state(tmp_path):
    (tmp_path / "train.py").write_text(
        "from sklearn.model_selection import train_test_split\n"
        "X_train, X_test = train_test_split(X, test_size=0.2)\n"
    )
    return {
        "run_id": "test-rca-001",
        "current_phase": 4,
        "status": "RUNNING",
        "progress_events": [],
        "file_relationships": {},
        "repo_local_path": str(tmp_path),
        "ranked_issues": [
            {
                "id": "issue-001",
                "file_path": "train.py",
                "title": "Missing Random Seed in train_test_split",
                "description": "train_test_split called without random_state",
                "severity": "HIGH",
                "issue_type": "ML_BUG",
                "line_start": 2,
                "line_end": 2,
                "code_snippet": "train_test_split(X, test_size=0.2)",
                "cvss_score": 5.0,
                "research_impact_score": 8.5,
                "ml_pattern": "missing_random_seed",
            }
        ],
    }


def test_rca_produces_reports(rca_state):
    from agents.rca.rca_agent import RCAAgent

    mock_response = {
        "origin": "train_test_split at line 2 called without random_state",
        "propagation": "All downstream model training uses non-deterministic splits",
        "manifestation": "Non-reproducible accuracy scores across runs",
        "impact": "Research results cannot be validated or reproduced",
        "root_cause_summary": "Missing random_state parameter in train_test_split.",
        "research_impact_statement": "All reported metrics are run-dependent and non-reproducible.",
        "affected_functions": ["train_model"],
        "fix_strategy": "Add random_state=42 to train_test_split call",
    }

    with patch("agents.rca.rca_agent.get_db_session"):
        with patch(
            "core.groq_client.GroqClient.complete_structured_json",
            new=AsyncMock(return_value=mock_response),
        ):
            agent = RCAAgent()
            result = asyncio.run(
                agent.execute(rca_state)
            )

    assert result["rca_complete"] is True
    assert len(result["rca_reports"]) == 1
    assert result["rca_reports"][0]["issue_id"] == "issue-001"
    assert result["rca_reports"][0]["origin"] != ""
    assert result["rca_reports"][0]["fix_strategy"] != ""


def test_rca_empty_issues():
    from agents.rca.rca_agent import RCAAgent

    state = {
        "run_id": "test-rca-002",
        "current_phase": 4,
        "status": "RUNNING",
        "progress_events": [],
        "file_relationships": {},
        "repo_local_path": "",
        "ranked_issues": [],
    }

    agent = RCAAgent()
    result = asyncio.run(agent.execute(state))

    assert result["rca_complete"] is True
    assert result["rca_reports"] == []


def test_rca_fallback_on_groq_failure(rca_state):
    from agents.rca.rca_agent import RCAAgent

    with patch("agents.rca.rca_agent.get_db_session"):
        with patch(
            "core.groq_client.GroqClient.complete_structured_json",
            new=AsyncMock(side_effect=Exception("Groq timeout")),
        ):
            agent = RCAAgent()
            result = asyncio.run(
                agent.execute(rca_state)
            )

    # Must not crash — fallback_rca kicks in
    assert result["rca_complete"] is True
    assert len(result["rca_reports"]) == 1
    assert result["rca_reports"][0]["issue_id"] == "issue-001"
    # Fallback always fills these fields
    assert "origin" in result["rca_reports"][0]
    assert "fix_strategy" in result["rca_reports"][0]
