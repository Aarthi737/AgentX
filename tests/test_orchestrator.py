"""
Tests for Agent 1 — Orchestrator
Validates composite scoring, deduplication, and URL parsing.
"""

import pytest
from agents.orchestrator.orchestrator import OrchestratorAgent, _deduplicate_issues
from services.github.github_service import GitHubService


class TestCompositeScoring:
    """Tests for the Composite Score formula: CVSS×0.4 + Research×0.4 + Importance×0.2."""

    def setup_method(self):
        self.agent = OrchestratorAgent()

    @pytest.mark.asyncio
    async def test_composite_score_formula(self, sample_state):
        """Verify the exact composite scoring formula from the architecture spec."""
        sample_state["ranked_issues"] = []
        sample_state["bug_report"] = [
            {
                "id": "i1",
                "file_path": "train.py",
                "title": "Test Issue",
                "description": "desc",
                "issue_type": "ML_BUG",
                "severity": "HIGH",
                "cvss_score": 8.0,
                "research_impact_score": 6.0,
                "module_importance_score": 4.0,  # will be overridden
            }
        ]
        sample_state["vulnerability_manifest"] = []
        sample_state["module_importance"] = {"train.py": 0.4}  # 0.4 × 10 = 4.0

        result = await self.agent.aggregate_and_rank(sample_state)

        issue = result["ranked_issues"][0]
        # CVSS=8.0×0.4 + Research=6.0×0.4 + Importance=4.0×0.2 = 3.2 + 2.4 + 0.8 = 6.4
        expected = round(8.0 * 0.4 + 6.0 * 0.4 + 4.0 * 0.2, 3)
        assert abs(issue["composite_score"] - expected) < 0.01

    @pytest.mark.asyncio
    async def test_ranking_is_descending(self, sample_state):
        """Higher composite scores should have lower rank numbers."""
        sample_state["ranked_issues"] = []
        sample_state["bug_report"] = [
            {"id": "low", "file_path": "a.py", "title": "Low", "description": "",
             "issue_type": "ML_BUG", "severity": "LOW",
             "cvss_score": 2.0, "research_impact_score": 2.0},
            {"id": "high", "file_path": "b.py", "title": "High", "description": "",
             "issue_type": "ML_BUG", "severity": "CRITICAL",
             "cvss_score": 9.0, "research_impact_score": 9.0},
        ]
        sample_state["vulnerability_manifest"] = []
        sample_state["module_importance"] = {}

        result = await self.agent.aggregate_and_rank(sample_state)
        ranks = {i["id"]: i["rank"] for i in result["ranked_issues"]}
        assert ranks["high"] < ranks["low"], "Higher score should rank first"

    @pytest.mark.asyncio
    async def test_empty_issues_returns_empty(self, sample_state):
        sample_state["bug_report"] = []
        sample_state["vulnerability_manifest"] = []
        sample_state["module_importance"] = {}
        result = await self.agent.aggregate_and_rank(sample_state)
        assert result["ranked_issues"] == []


class TestDeduplication:
    """Tests for issue deduplication logic."""

    def test_exact_duplicate_removed(self):
        issues = [
            {"file_path": "a.py", "line_start": 10, "title": "Same Issue Title"},
            {"file_path": "a.py", "line_start": 10, "title": "Same Issue Title"},
        ]
        result = _deduplicate_issues(issues)
        assert len(result) == 1

    def test_different_files_kept(self):
        issues = [
            {"file_path": "a.py", "line_start": 10, "title": "Same Issue"},
            {"file_path": "b.py", "line_start": 10, "title": "Same Issue"},
        ]
        result = _deduplicate_issues(issues)
        assert len(result) == 2

    def test_different_lines_kept(self):
        issues = [
            {"file_path": "a.py", "line_start": 10, "title": "Issue"},
            {"file_path": "a.py", "line_start": 20, "title": "Issue"},
        ]
        result = _deduplicate_issues(issues)
        assert len(result) == 2

    def test_preserves_order(self):
        issues = [
            {"file_path": "a.py", "line_start": 1, "title": "First"},
            {"file_path": "b.py", "line_start": 2, "title": "Second"},
            {"file_path": "c.py", "line_start": 3, "title": "Third"},
        ]
        result = _deduplicate_issues(issues)
        assert [i["title"] for i in result] == ["First", "Second", "Third"]


class TestGitHubService:
    """Tests for URL validation in GitHubService."""

    def setup_method(self):
        self.svc = GitHubService(token="")

    def test_valid_https_url(self):
        owner, name = self.svc.validate_repo_url("https://github.com/owner/repo")
        assert owner == "owner"
        assert name == "repo"

    def test_valid_https_url_with_git_suffix(self):
        owner, name = self.svc.validate_repo_url("https://github.com/owner/repo.git")
        assert owner == "owner"
        assert name == "repo"

    def test_valid_ssh_url(self):
        owner, name = self.svc.validate_repo_url("git@github.com:owner/repo.git")
        assert owner == "owner"
        assert name == "repo"

    def test_trailing_slash_handled(self):
        owner, name = self.svc.validate_repo_url("https://github.com/owner/repo/")
        assert owner == "owner"

    def test_non_github_url_raises(self):
        with pytest.raises(ValueError, match="GitHub"):
            self.svc.validate_repo_url("https://gitlab.com/owner/repo")

    def test_missing_repo_raises(self):
        with pytest.raises(ValueError):
            self.svc.validate_repo_url("https://github.com/owner")
