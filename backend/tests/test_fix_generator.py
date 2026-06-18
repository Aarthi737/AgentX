import asyncio
import pytest
from unittest.mock import AsyncMock, patch


@pytest.fixture
def fix_state(tmp_path):
    (tmp_path / "train.py").write_text(
        "from sklearn.model_selection import train_test_split\n"
        "X_train, X_test = train_test_split(X, test_size=0.2)\n"
    )
    return {
        "run_id": "test-fix-001",
        "current_phase": 5,
        "status": "RUNNING",
        "progress_events": [],
        "repo_local_path": str(tmp_path),
        "file_relationships": {},
        "framework_metadata": {},
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
        "rca_reports": [
            {
                "issue_id": "issue-001",
                "origin": "train_test_split at line 2",
                "propagation": "All downstream model training",
                "manifestation": "Non-reproducible accuracy scores",
                "impact": "Research results cannot be validated",
                "root_cause_summary": "Missing random_state parameter",
                "fix_strategy": "Add random_state=42 to train_test_split",
            }
        ],
    }


def test_fix_generator_produces_patches(fix_state):
    from agents.fix_generator.fix_generator import FixGeneratorAgent

    mock_response = {
        "fixed_code": (
            "from sklearn.model_selection import train_test_split\n"
            "X_train, X_test = train_test_split(X, test_size=0.2, random_state=42)  # fix: added seed\n"
        ),
        "fix_explanation": "Added random_state=42 to ensure reproducibility",
        "confidence_score": 90,
        "changes_summary": ["Added random_state=42 to train_test_split"],
        "preserved_contracts": ["train_test_split signature unchanged"],
        "requires_imports": [],
    }

    with patch("agents.fix_generator.fix_generator.get_db_session"):
        with patch(
            "core.gemini_client.GeminiClient.complete_structured_json",
            new=AsyncMock(return_value=mock_response),
        ):
            agent = FixGeneratorAgent()
            result = asyncio.run(
                agent.execute(fix_state)
            )

    assert result["fix_complete"] is True
    assert len(result["patches"]) == 1
    patch_obj = result["patches"][0]
    assert "fixed_code" in patch_obj
    assert "diff" in patch_obj
    assert "original_code" in patch_obj
    assert patch_obj["syntax_valid"] is True
    assert patch_obj["issue_id"] == "issue-001"


def test_syntax_validation_catches_bad_code(fix_state):
    from agents.fix_generator.fix_generator import FixGeneratorAgent

    agent = FixGeneratorAgent()
    bad_result = {
        "fixed_code": "def foo(\n    # missing closing paren — syntax error",
        "fix_explanation": "broken fix",
        "confidence_score": 80,
        "changes_summary": [],
        "preserved_contracts": [],
        "requires_imports": [],
    }
    issue = fix_state["ranked_issues"][0]
    original_code = "from sklearn.model_selection import train_test_split\n"

    enriched = agent._validate_and_enrich_patch(bad_result, original_code, issue)

    assert enriched["syntax_valid"] is False
    assert enriched["confidence_score"] < 80  # reduced due to syntax error


def test_fallback_patch_on_gemini_failure(fix_state):
    from agents.fix_generator.fix_generator import FixGeneratorAgent

    with patch("agents.fix_generator.fix_generator.get_db_session"):
        with patch(
            "core.gemini_client.GeminiClient.complete_structured_json",
            new=AsyncMock(side_effect=Exception("Gemini down")),
        ):
            agent = FixGeneratorAgent()
            result = asyncio.run(
                agent.execute(fix_state)
            )

    # Must not crash — fallback_patch kicks in
    assert result["fix_complete"] is True
    assert len(result["patches"]) == 1
    assert result["patches"][0]["confidence_score"] == 0
    assert "Manual review required" in result["patches"][0]["fix_explanation"]
