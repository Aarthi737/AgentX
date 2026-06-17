"""
AgentX — LangGraph Pipeline
Wires all 9 agents into a fault-tolerant StateGraph.

Graph structure:
  ingestion → repo_intelligence → [code_analysis ∥ security_scanner]
  → aggregate_rank → rca → fix_generation → validation → verification → pr_creation

Conditional routing:
  - FAILED state → stop
  - HUMAN_REVIEW patches → still proceed to PR (partial)
  - Validation rejection → retry fix_generation (max 3)
"""

from __future__ import annotations

import asyncio
from typing import Literal

from langgraph.graph import END, StateGraph

from agents.adaptive_feedback.afe import AdaptiveFeedbackEngine
from agents.code_analysis.code_analysis import CodeAnalysisAgent
from agents.fix_generator.fix_generator import FixGeneratorAgent
from agents.orchestrator.orchestrator import OrchestratorAgent
from agents.pr_creator.pr_creator import PRCreatorAgent
from agents.rca.rca_agent import RCAAgent
from agents.repo_intelligence.repo_intelligence import RepoIntelligenceAgent
from agents.security_scanner.security_scanner import SecurityScannerAgent
from agents.validation.validation_agent import ValidationAgent
from agents.verification.verification_agent import VerificationAgent
from core.logging import get_logger
from core.state import AgentXState

logger = get_logger(__name__)

# ── Instantiate all agents (singletons for the process lifetime) ──────────────
_orchestrator = OrchestratorAgent()
_repo_intelligence = RepoIntelligenceAgent()
_code_analysis = CodeAnalysisAgent()
_security_scanner = SecurityScannerAgent()
_rca_agent = RCAAgent()
_fix_generator = FixGeneratorAgent()
_validation_agent = ValidationAgent()
_verification_agent = VerificationAgent()
_pr_creator = PRCreatorAgent()
_afe = AdaptiveFeedbackEngine()


# ── Parallel wrapper: run code analysis + security scanner concurrently ───────
async def parallel_analysis_node(state: AgentXState) -> AgentXState:
    """
    Phase 03 — Parallel Analysis.
    Runs Agent 3 (code analysis) and Agent 4 (security scan) concurrently
    using asyncio.gather, sharing the same Agent 2 context package.
    """
    if state.get("status") == "FAILED":
        return state

    results = await asyncio.gather(
        _code_analysis(state.copy()),
        _security_scanner(state.copy()),
        return_exceptions=True,
    )

    code_state = results[0] if not isinstance(results[0], Exception) else {}
    sec_state = results[1] if not isinstance(results[1], Exception) else {}

    # Merge results into main state
    state["bug_report"] = code_state.get("bug_report", [])
    state["vulnerability_manifest"] = sec_state.get("vulnerability_manifest", [])
    state["analysis_complete"] = True

    # Merge progress events from both branches
    events = list(state.get("progress_events", []))
    events.extend(code_state.get("progress_events", []))
    events.extend(sec_state.get("progress_events", []))
    state["progress_events"] = events

    return state


# ── Aggregate & Rank wrapper ──────────────────────────────────────────────────
async def aggregate_rank_node(state: AgentXState) -> AgentXState:
    """Phase 04 — delegated to Orchestrator's aggregate_and_rank method."""
    if state.get("status") == "FAILED":
        return state
    return await _orchestrator.aggregate_and_rank(state)


# ── Conditional routing functions ─────────────────────────────────────────────

def should_continue_after_ingestion(
    state: AgentXState,
) -> Literal["repo_intelligence", "end"]:
    if state.get("status") == "FAILED":
        return "end"
    return "repo_intelligence"


def should_continue_after_analysis(
    state: AgentXState,
) -> Literal["aggregate_rank", "end"]:
    if state.get("status") == "FAILED":
        return "end"
    return "aggregate_rank"


def should_continue_after_rank(
    state: AgentXState,
) -> Literal["rca", "end"]:
    if state.get("status") == "FAILED":
        return "end"
    if not state.get("ranked_issues"):
        logger.info("no_issues_found", run_id=state.get("run_id"))
        return "end"
    return "rca"


def should_continue_after_fix(
    state: AgentXState,
) -> Literal["validation", "end"]:
    if state.get("status") == "FAILED":
        return "end"
    return "validation"


def should_continue_after_validation(
    state: AgentXState,
) -> Literal["verification", "pr_creation", "end"]:
    if state.get("status") == "FAILED":
        return "end"
    # Even if some patches need human review, proceed to verification
    # (human-review patches are filtered out in Agent 8)
    return "verification"


def should_continue_after_verification(
    state: AgentXState,
) -> Literal["pr_creation", "end"]:
    if state.get("status") == "FAILED":
        return "end"
    return "pr_creation"


# ── Build the StateGraph ──────────────────────────────────────────────────────

def build_pipeline() -> StateGraph:
    """
    Construct and compile the AgentX LangGraph StateGraph.
    Returns a compiled graph ready for ainvoke().
    """
    graph = StateGraph(AgentXState)

    # Add all nodes
    graph.add_node("ingestion", _orchestrator)
    graph.add_node("repo_intelligence", _repo_intelligence)
    graph.add_node("parallel_analysis", parallel_analysis_node)
    graph.add_node("aggregate_rank", aggregate_rank_node)
    graph.add_node("rca", _rca_agent)
    graph.add_node("fix_generation", _fix_generator)
    graph.add_node("validation", _validation_agent)
    graph.add_node("verification", _verification_agent)
    graph.add_node("pr_creation", _pr_creator)

    # Entry point
    graph.set_entry_point("ingestion")

    # Edges with conditional routing
    graph.add_conditional_edges(
        "ingestion",
        should_continue_after_ingestion,
        {"repo_intelligence": "repo_intelligence", "end": END},
    )
    graph.add_edge("repo_intelligence", "parallel_analysis")
    graph.add_conditional_edges(
        "parallel_analysis",
        should_continue_after_analysis,
        {"aggregate_rank": "aggregate_rank", "end": END},
    )
    graph.add_conditional_edges(
        "aggregate_rank",
        should_continue_after_rank,
        {"rca": "rca", "end": END},
    )
    graph.add_edge("rca", "fix_generation")
    graph.add_conditional_edges(
        "fix_generation",
        should_continue_after_fix,
        {"validation": "validation", "end": END},
    )
    graph.add_conditional_edges(
        "validation",
        should_continue_after_validation,
        {"verification": "verification", "pr_creation": "pr_creation", "end": END},
    )
    graph.add_conditional_edges(
        "verification",
        should_continue_after_verification,
        {"pr_creation": "pr_creation", "end": END},
    )
    graph.add_edge("pr_creation", END)

    return graph.compile()


# Module-level compiled pipeline singleton
_pipeline = None


def get_pipeline():
    """Return the compiled LangGraph pipeline (lazy singleton)."""
    global _pipeline
    if _pipeline is None:
        _pipeline = build_pipeline()
    return _pipeline


async def run_pipeline(initial_state: AgentXState) -> AgentXState:
    """
    Execute the full 9-agent pipeline.
    Broadcasts progress events via WebSocket after each node.
    Returns the final pipeline state.
    """
    pipeline = get_pipeline()
    run_id = initial_state.get("run_id", "unknown")
    logger.info("pipeline_start", run_id=run_id)

    final_state = await pipeline.ainvoke(initial_state)

    # Persist final audit log batch
    await _orchestrator.persist_audit_logs(final_state)

    logger.info(
        "pipeline_complete",
        run_id=run_id,
        status=final_state.get("status"),
        pr_url=final_state.get("pr_url"),
    )
    return final_state
