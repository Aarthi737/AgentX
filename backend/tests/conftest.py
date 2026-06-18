"""
AgentX Test Fixtures
Shared pytest fixtures for all test modules.
"""

import asyncio
import os
import sys
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import AsyncClient

# Ensure backend is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# Set test environment before importing app modules
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("GOOGLE_API_KEY", "test-key")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost:5432/test")
os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
os.environ.setdefault("SUPABASE_ANON_KEY", "test-anon-key")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-key")
os.environ.setdefault("APP_SECRET_KEY", "test-secret-key-that-is-long-enough")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def sample_state():
    """A minimal valid AgentXState for testing."""
    return {
        "run_id": "test1234",
        "repo_url": "https://github.com/test/repo",
        "repo_owner": "test",
        "repo_name": "repo",
        "repo_branch": "main",
        "github_token": "ghp_test",
        "current_phase": 0,
        "status": "PENDING",
        "retry_count": 0,
        "progress_events": [],
        "learned_weights": {},
        "afe_updates_pending": [],
    }


@pytest.fixture
def sample_issues():
    """Sample ranked issues for testing downstream agents."""
    return [
        {
            "id": "issue-001",
            "run_id": "test1234",
            "title": "Missing Random Seed in train_test_split",
            "description": "train_test_split called without random_state. Non-reproducible.",
            "issue_type": "ML_BUG",
            "severity": "HIGH",
            "ml_pattern": "missing_random_seed",
            "file_path": "train.py",
            "line_start": 49,
            "line_end": 49,
            "code_snippet": "X_train, X_test = train_test_split(X, test_size=0.2)",
            "cvss_score": 5.0,
            "research_impact_score": 8.5,
            "module_importance_score": 7.0,
            "composite_score": 6.8,
            "rank": 1,
            "detection_tool": "ast_visitor",
        },
        {
            "id": "issue-002",
            "run_id": "test1234",
            "title": "Hardcoded API Key",
            "description": "API key found hardcoded in source.",
            "issue_type": "SECURITY",
            "severity": "CRITICAL",
            "ml_pattern": None,
            "file_path": "config.py",
            "line_start": 3,
            "line_end": 3,
            "code_snippet": 'api_key = "sk-live-abc123"',
            "cvss_score": 9.0,
            "research_impact_score": 6.0,
            "module_importance_score": 5.0,
            "composite_score": 7.6,
            "rank": 2,
            "detection_tool": "secret_scanner",
        },
    ]


@pytest.fixture
def sample_rca_reports(sample_issues):
    """Sample RCA reports for testing fix generation."""
    return [
        {
            "id": "rca-001",
            "issue_id": "issue-001",
            "origin": "train_test_split call at train.py:49 missing random_state parameter",
            "propagation": "Any code using X_train/X_test will produce different results each run",
            "manifestation": "Model performance metrics differ across runs — results non-reproducible",
            "impact": "Research findings cannot be reproduced or validated by other researchers",
            "root_cause_summary": "random_state parameter not set in train_test_split",
            "research_impact_statement": "All reported accuracy metrics are run-dependent and scientifically invalid.",
            "affected_functions": ["train_model", "evaluate_model"],
            "fix_strategy": "Add random_state=42 to train_test_split call",
        },
    ]


@pytest.fixture
def mock_gemini():
    """Mock GeminiClient for tests that don't need real LLM calls."""
    with patch("core.gemini_client.GeminiClient") as mock_cls:
        instance = AsyncMock()
        instance.complete.return_value = '{"issues": []}'
        instance.complete_json.return_value = {"issues": []}
        instance.complete_structured.return_value = '{"issues": []}'
        instance.complete_structured_json.return_value = {"issues": []}
        mock_cls.return_value = instance
        yield instance


@pytest.fixture
def mock_db_session():
    """Mock async DB session."""
    session = AsyncMock()
    session.execute = AsyncMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.close = AsyncMock()
    return session
