"""
AgentX — LangGraph Pipeline State
Defines the TypedDict state shared across all 9 agents in the LangGraph StateGraph.
Each agent reads from and writes to this state. The Orchestrator (Agent 1) owns
the StateGraph and manages transitions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, TypedDict

from db.models import (
    ContextPackage,
    Issue,
    Patch,
    PipelineRun,
    RCAReport,
    RunStatus,
)


class AgentXState(TypedDict, total=False):
    """
    Complete pipeline state flowing through the LangGraph StateGraph.
    All fields are optional (total=False) so agents can write partial updates.
    """

    # ── Run identity ─────────────────────────────────────────────────────────
    run_id: str
    repo_url: str
    repo_owner: str
    repo_name: str
    repo_branch: str
    github_token: str  # raw token — never persisted

    # ── Phase 01 — Ingestion ─────────────────────────────────────────────────
    repo_local_path: str          # Docker volume path to cloned repo
    file_manifest: List[Dict]     # [{path, language, size, lines}, ...]
    ingestion_complete: bool

    # ── Phase 02 — Repository Intelligence ───────────────────────────────────
    dependency_graph: Dict        # networkx serialised graph
    module_importance: Dict       # {file_path: score, ...}
    file_relationships: Dict      # {file_path: [related_files], ...}
    test_coverage_map: Dict       # {function_sig: coverage_pct, ...}
    framework_metadata: Dict      # {language, frameworks, test_runner, ...}
    context_package_id: str       # FK to ContextPackage table
    repo_intelligence_complete: bool

    # ── Phase 03 — Parallel Analysis ─────────────────────────────────────────
    bug_report: List[Dict]        # raw issues from Agent 3
    vulnerability_manifest: List[Dict]  # raw issues from Agent 4
    analysis_complete: bool

    # ── Phase 04 — Aggregate & Rank ──────────────────────────────────────────
    ranked_issues: List[Dict]     # merged, deduped, scored, ranked
    ranking_complete: bool

    # ── Phase 05 — RCA ───────────────────────────────────────────────────────
    rca_reports: List[Dict]       # one per issue
    rca_complete: bool

    # ── Phase 06 — Fix Generation ────────────────────────────────────────────
    patches: List[Dict]           # {issue_id, original_code, fixed_code, ...}
    fix_complete: bool

    # ── Phase 07 — Validation Debate ─────────────────────────────────────────
    validated_patches: List[Dict] # patches with confidence scores
    patches_needing_human: List[str]  # issue_ids
    validation_complete: bool

    # ── Phase 08 — Docker Verification ───────────────────────────────────────
    verification_results: List[Dict]
    safe_to_merge: bool
    verification_complete: bool

    # ── Phase 09 — PR Creation ───────────────────────────────────────────────
    pr_url: str
    pr_number: int
    pr_branch: str
    pdf_report_path: str
    pr_complete: bool

    # ── Pipeline control ─────────────────────────────────────────────────────
    current_phase: int
    status: str
    error_message: Optional[str]
    retry_count: int

    # ── Adaptive Feedback Engine ──────────────────────────────────────────────
    learned_weights: Dict         # loaded from DB at pipeline start
    afe_updates_pending: List[Dict]

    # ── WebSocket streaming ───────────────────────────────────────────────────
    progress_events: List[Dict]   # queued events for SSE/WS broadcast


@dataclass
class PipelineContext:
    """
    Rich context object constructed from AgentXState.
    Passed directly to agent __call__ methods for type-safe access.
    """
    run_id: str
    repo_url: str
    repo_owner: str
    repo_name: str
    repo_branch: str = "main"
    github_token: str = ""
    repo_local_path: str = ""
    file_manifest: List[Dict] = field(default_factory=list)
    dependency_graph: Dict = field(default_factory=dict)
    module_importance: Dict = field(default_factory=dict)
    file_relationships: Dict = field(default_factory=dict)
    test_coverage_map: Dict = field(default_factory=dict)
    framework_metadata: Dict = field(default_factory=dict)
    ranked_issues: List[Dict] = field(default_factory=list)
    rca_reports: List[Dict] = field(default_factory=list)
    patches: List[Dict] = field(default_factory=list)
    learned_weights: Dict = field(default_factory=dict)

    @classmethod
    def from_state(cls, state: AgentXState) -> "PipelineContext":
        return cls(
            run_id=state.get("run_id", ""),
            repo_url=state.get("repo_url", ""),
            repo_owner=state.get("repo_owner", ""),
            repo_name=state.get("repo_name", ""),
            repo_branch=state.get("repo_branch", "main"),
            github_token=state.get("github_token", ""),
            repo_local_path=state.get("repo_local_path", ""),
            file_manifest=state.get("file_manifest", []),
            dependency_graph=state.get("dependency_graph", {}),
            module_importance=state.get("module_importance", {}),
            file_relationships=state.get("file_relationships", {}),
            test_coverage_map=state.get("test_coverage_map", {}),
            framework_metadata=state.get("framework_metadata", {}),
            ranked_issues=state.get("ranked_issues", []),
            rca_reports=state.get("rca_reports", []),
            patches=state.get("patches", []),
            learned_weights=state.get("learned_weights", {}),
        )
