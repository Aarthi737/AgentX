"""
AgentX — Agent 1: Orchestrator (Central Controller)
Phase 01 — Ingestion

Responsibilities:
- Validate GitHub URL and authenticate via PyGitHub
- Clone repository to ephemeral Docker volume
- Catalogue all files into a manifest
- Initialise LangGraph StateGraph with checkpoint recovery
- Record Run ID and full audit trail to Supabase
- Own the conditional routing logic between all phases
- Handle Phase 04 aggregation & ranking (Composite Score)
- Manage fault-tolerant retry and human review routing
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Dict, List, Optional

from config.settings import settings
from core.base_agent import BaseAgent
from core.logging import get_logger
from core.state import AgentXState
from db.database import get_db_session
from db.models import RunStatus
from db.repositories import (
    AuditLogRepository,
    IssueRepository,
    LearnedWeightsRepository,
    RunRepository,
)
from services.github.github_service import GitHubService

logger = get_logger(__name__)

# Composite Score weights (from architecture spec)
CVSS_WEIGHT = 0.4
RESEARCH_IMPACT_WEIGHT = 0.4
IMPORTANCE_WEIGHT = 0.2


class OrchestratorAgent(BaseAgent):
    """
    Agent 1 — Orchestrator.
    Manages pipeline lifecycle and owns all cross-cutting concerns.
    """

    agent_name = "Orchestrator"
    phase = 1

    async def execute(self, state: AgentXState) -> AgentXState:
        """Phase 01: Ingestion — validate, clone, manifest, initialise."""
        repo_url: str = state["repo_url"]
        github_token: str = state.get("github_token", settings.github_default_token)

        # ── Generate Run ID ───────────────────────────────────────────────────
        run_id = str(uuid.uuid4())[:8]
        state["run_id"] = run_id
        state["status"] = RunStatus.INGESTING
        state["current_phase"] = 1
        state["retry_count"] = 0
        state["progress_events"] = []
        state["github_token"] = github_token

        state = self._emit_progress(state, f"Starting pipeline run {run_id}", {"run_id": run_id})

        # ── GitHub service ────────────────────────────────────────────────────
        gh_service = GitHubService(github_token)

        # Validate URL
        try:
            owner, repo_name = gh_service.validate_repo_url(repo_url)
        except ValueError as exc:
            state["error_message"] = str(exc)
            state["status"] = RunStatus.FAILED
            return state

        state["repo_owner"] = owner
        state["repo_name"] = repo_name

        state = self._emit_progress(
            state, f"Validated repository: {owner}/{repo_name}"
        )

        # ── Load learned weights from DB ──────────────────────────────────────
        try:
            async with get_db_session() as session:
                weights_repo = LearnedWeightsRepository(session)
                learned_weights = await weights_repo.get_all()
                state["learned_weights"] = learned_weights
        except Exception as exc:
            logger.warning("weights_load_failed", error=str(exc))
            state["learned_weights"] = {}

        # ── Create DB record ──────────────────────────────────────────────────
        try:
            async with get_db_session() as session:
                runs_repo = RunRepository(session)
                await runs_repo.create(
                    run_id=run_id,
                    repo_url=repo_url,
                    repo_owner=owner,
                    repo_name=repo_name,
                    repo_branch=state.get("repo_branch", "main"),
                    github_token_hash=gh_service.hash_token(),
                )
        except Exception as exc:
            logger.error("db_run_create_failed", error=str(exc))
            # Non-fatal — continue pipeline

        # ── Clone repository ──────────────────────────────────────────────────
        state = self._emit_progress(state, "Cloning repository...")
        branch = state.get("repo_branch", "main")

        try:
            repo_path = gh_service.clone_repo(repo_url, branch=branch)
            state["repo_local_path"] = repo_path
        except RuntimeError as exc:
            await self._fail_run(run_id, str(exc))
            state["error_message"] = str(exc)
            state["status"] = RunStatus.FAILED
            return state

        # ── Build file manifest ───────────────────────────────────────────────
        state = self._emit_progress(state, "Building file manifest...")
        manifest = gh_service.build_file_manifest(repo_path)
        state["file_manifest"] = manifest

        state = self._emit_progress(
            state,
            f"Catalogued {len(manifest)} files",
            {"total_files": len(manifest)},
        )

        # ── Update DB ─────────────────────────────────────────────────────────
        try:
            async with get_db_session() as session:
                runs_repo = RunRepository(session)
                await runs_repo.update_status(
                    run_id,
                    RunStatus.REPO_INTELLIGENCE,
                    phase=1,
                    total_issues=0,
                )
        except Exception as exc:
            logger.warning("db_status_update_failed", error=str(exc))

        state["ingestion_complete"] = True
        state["status"] = RunStatus.REPO_INTELLIGENCE

        logger.info(
            "ingestion_complete",
            run_id=run_id,
            owner=owner,
            repo=repo_name,
            files=len(manifest),
        )
        return state

    async def aggregate_and_rank(self, state: AgentXState) -> AgentXState:
        """
        Phase 04 — Aggregate & Rank.
        Merges findings from Agents 3 and 4, deduplicates, computes Composite Score.
        Composite Score = (CVSS × 0.4) + (Research Impact × 0.4) + (Importance × 0.2)
        """
        state["current_phase"] = 4
        state = self._emit_progress(state, "Aggregating and ranking findings...")

        bug_report: List[Dict] = state.get("bug_report", [])
        vuln_manifest: List[Dict] = state.get("vulnerability_manifest", [])
        module_importance: Dict = state.get("module_importance", {})
        learned_weights: Dict = state.get("learned_weights", {})

        # Merge
        all_issues = bug_report + vuln_manifest

        # Deduplicate by (file_path, line_start, title) similarity
        all_issues = _deduplicate_issues(all_issues)

        # Apply learned weight adjustments
        for issue in all_issues:
            pattern = issue.get("ml_pattern", "")
            if pattern and pattern in learned_weights:
                issue["research_impact_score"] = min(
                    10.0,
                    issue.get("research_impact_score", 0) * learned_weights[pattern],
                )

        # Compute composite scores and enrich with module importance
        for issue in all_issues:
            file_path = issue.get("file_path", "")
            importance = module_importance.get(file_path, 0.5)
            issue["module_importance_score"] = importance * 10

            cvss = issue.get("cvss_score", 5.0)
            research = issue.get("research_impact_score", 5.0)
            imp = issue["module_importance_score"]

            composite = (cvss * CVSS_WEIGHT) + (research * RESEARCH_IMPACT_WEIGHT) + (imp * IMPORTANCE_WEIGHT)
            issue["composite_score"] = round(composite, 3)

        # Sort by composite score descending
        all_issues.sort(key=lambda x: x["composite_score"], reverse=True)

        # Assign ranks
        for i, issue in enumerate(all_issues, start=1):
            issue["rank"] = i

        state["ranked_issues"] = all_issues
        state["ranking_complete"] = True

        # Persist to DB
        try:
            async with get_db_session() as session:
                issue_repo = IssueRepository(session)
                await issue_repo.bulk_create(state["run_id"], all_issues)
                await issue_repo.update_ranks(all_issues)
                runs_repo = RunRepository(session)
                await runs_repo.update_status(
                    state["run_id"],
                    RunStatus.RCA,
                    phase=4,
                    total_issues=len(all_issues),
                )
        except Exception as exc:
            logger.warning("db_rank_persist_failed", error=str(exc))

        state = self._emit_progress(
            state,
            f"Ranked {len(all_issues)} issues",
            {"total_issues": len(all_issues)},
        )
        logger.info("ranking_complete", run_id=state["run_id"], total=len(all_issues))
        return state

    async def persist_audit_logs(self, state: AgentXState) -> None:
        """Flush all progress_events of type 'audit' to the database."""
        events = state.get("progress_events", [])
        if not events:
            return
        try:
            async with get_db_session() as session:
                audit_repo = AuditLogRepository(session)
                await audit_repo.bulk_create(events)
        except Exception as exc:
            logger.warning("audit_persist_failed", error=str(exc))

    async def _fail_run(self, run_id: str, error: str) -> None:
        try:
            async with get_db_session() as session:
                repo = RunRepository(session)
                await repo.mark_failed(run_id, error)
        except Exception:
            pass


def _deduplicate_issues(issues: List[Dict]) -> List[Dict]:
    """Remove duplicate issues based on file_path + line_start + title prefix."""
    seen = set()
    unique = []
    for issue in issues:
        key = (
            issue.get("file_path", ""),
            issue.get("line_start", 0),
            issue.get("title", "")[:60],
        )
        if key not in seen:
            seen.add(key)
            unique.append(issue)
    return unique
