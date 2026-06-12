"""
AgentX — Agent 5: Root Cause Analysis Agent
Phase 05 — Root Cause Analysis

Responsibilities:
- Causal chain tracing: Origin → Propagation → Manifestation → Impact
- Root cause clustering (group related issues)
- Research Impact Statement quantifying effect on reproducibility
- Per-issue RCA reports persisted to Supabase

Tools: Groq Llama 3.3 70B, AST context enrichment
"""

from __future__ import annotations

import asyncio
import uuid
from pathlib import Path
from typing import Dict, List, Optional

from config.settings import settings
from core.base_agent import BaseAgent
from core.groq_client import get_groq
from core.logging import get_logger
from core.state import AgentXState
from db.database import get_db_session
from db.models import RunStatus
from db.repositories import RCARepository, RunRepository

logger = get_logger(__name__)

_RCA_SYSTEM_PROMPT = """You are a senior software engineer and ML researcher performing root cause analysis.
Given a bug or vulnerability, trace the complete causal chain and assess research impact.

Return a JSON object with EXACTLY this structure:
{
  "origin": "Where the problem originates — the root cause code or design decision",
  "propagation": "How the problem spreads through the codebase — function calls, data flow, module boundaries crossed",
  "manifestation": "How and when the problem becomes visible — runtime error, silent wrong result, security breach",
  "impact": "Concrete impact on the system, experiment results, or users",
  "root_cause_summary": "2-3 sentence summary of why this bug exists",
  "research_impact_statement": "Specific statement on how this affects research reproducibility, result validity, or scientific integrity",
  "affected_functions": ["list", "of", "function", "names", "affected"],
  "fix_strategy": "High-level description of the correct fix approach"
}

Be specific and technical. Reference actual function names and line numbers when possible.
Return ONLY the JSON object."""


class RCAAgent(BaseAgent):
    """
    Agent 5 — Root Cause Analysis.
    Produces a full causal chain report for every ranked issue.
    """

    agent_name = "RCA"
    phase = 5

    def __init__(self):
        super().__init__()
        self.groq = get_groq()

    async def execute(self, state: AgentXState) -> AgentXState:
        """Trace causal chains for all ranked issues."""
        ranked_issues: List[Dict] = state.get("ranked_issues", [])
        repo_path = state.get("repo_local_path", "")
        run_id = state["run_id"]
        state["current_phase"] = 5

        if not ranked_issues:
            state["rca_reports"] = []
            state["rca_complete"] = True
            return state

        state = self._emit_progress(
            state,
            f"Running RCA on {len(ranked_issues)} issues...",
        )

        # Process issues in batches of 5 to respect Groq rate limits
        rca_reports: List[Dict] = []
        batch_size = 5

        for i in range(0, len(ranked_issues), batch_size):
            batch = ranked_issues[i : i + batch_size]
            tasks = [
                self._analyse_issue(issue, repo_path, state)
                for issue in batch
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for issue, result in zip(batch, results):
                if isinstance(result, Exception):
                    logger.warning("rca_issue_failed", issue_id=issue.get("id"), error=str(result))
                    # Provide fallback RCA
                    result = _fallback_rca(issue)

                result["issue_id"] = issue["id"]
                result["id"] = str(uuid.uuid4())
                rca_reports.append(result)

            # Small delay between batches to avoid rate limiting
            if i + batch_size < len(ranked_issues):
                await asyncio.sleep(1.0)

        # Persist to DB
        try:
            async with get_db_session() as session:
                rca_repo = RCARepository(session)
                for report in rca_reports:
                    await rca_repo.create(
                        issue_id=report["issue_id"],
                        data={
                            k: v for k, v in report.items()
                            if k not in ("id", "issue_id")
                        },
                    )
                runs_repo = RunRepository(session)
                await runs_repo.update_status(run_id, RunStatus.FIX_GENERATION, phase=5)
        except Exception as exc:
            logger.warning("rca_db_persist_failed", error=str(exc))

        state["rca_reports"] = rca_reports
        state["rca_complete"] = True

        state = self._emit_progress(
            state,
            f"RCA complete for {len(rca_reports)} issues",
            {"rca_count": len(rca_reports)},
        )
        logger.info("rca_complete", run_id=run_id, count=len(rca_reports))
        return state

    async def _analyse_issue(
        self, issue: Dict, repo_path: str, state: AgentXState
    ) -> Dict:
        """Perform RCA for a single issue using Groq + code context."""
        # Build rich context from the file
        code_context = await self._get_code_context(
            repo_path,
            issue.get("file_path", ""),
            issue.get("line_start"),
            issue.get("line_end"),
        )

        # Build dependency context
        file_rels = state.get("file_relationships", {})
        file_path = issue.get("file_path", "")
        related_files = []
        if file_path in file_rels:
            rel = file_rels[file_path]
            related_files = rel.get("imports", [])[:5] + rel.get("imported_by", [])[:5]

        user_prompt = f"""Perform root cause analysis for this issue:

**Issue Title**: {issue.get('title', 'Unknown')}
**Severity**: {issue.get('severity', 'UNKNOWN')}
**Type**: {issue.get('issue_type', 'UNKNOWN')}
**File**: {file_path}
**Line**: {issue.get('line_start', 'unknown')}
**Description**: {issue.get('description', '')}

**Code at Issue Location**:
```
{code_context}
```

**Files that import this module**: {related_files[:5]}
**ML Pattern (if applicable)**: {issue.get('ml_pattern', 'N/A')}

Trace the complete causal chain and assess research impact."""

        result = await self.groq.complete_structured_json(
            system_prompt=_RCA_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            max_tokens=1500,
        )

        # Validate required fields
        required = ["origin", "propagation", "manifestation", "impact",
                    "root_cause_summary", "research_impact_statement"]
        for field in required:
            if field not in result or not result[field]:
                result[field] = _fallback_rca(issue)[field]

        result.setdefault("affected_functions", [])
        result.setdefault("causal_chain_data", {
            "origin": result.get("origin"),
            "propagation": result.get("propagation"),
            "manifestation": result.get("manifestation"),
            "impact": result.get("impact"),
        })

        return result

    async def _get_code_context(
        self,
        repo_path: str,
        file_path: str,
        line_start: Optional[int],
        line_end: Optional[int],
        context_lines: int = 20,
    ) -> str:
        """Extract code context around the issue location."""
        if not repo_path or not file_path:
            return ""

        full_path = Path(repo_path) / file_path
        if not full_path.exists():
            return ""

        try:
            lines = full_path.read_text(errors="ignore").split("\n")
            if line_start is None:
                # Return first 40 lines if no location
                return "\n".join(lines[:40])

            start = max(0, line_start - context_lines - 1)
            end = min(len(lines), (line_end or line_start) + context_lines)
            context = lines[start:end]

            # Add line numbers
            numbered = [
                f"{start + i + 1:4d} | {line}"
                for i, line in enumerate(context)
            ]
            return "\n".join(numbered)
        except OSError:
            return ""


def _fallback_rca(issue: Dict) -> Dict:
    """Generate a deterministic fallback RCA when Groq is unavailable."""
    title = issue.get("title", "Unknown Issue")
    file_path = issue.get("file_path", "unknown file")
    desc = issue.get("description", "")
    line = issue.get("line_start", "unknown")

    return {
        "origin": f"The issue originates at {file_path} line {line} where {title} was introduced.",
        "propagation": f"The defect propagates through any code path that calls or depends on the affected function in {file_path}.",
        "manifestation": f"Manifests as: {desc}",
        "impact": f"Impact: {issue.get('severity', 'MEDIUM')} severity issue affecting system correctness.",
        "root_cause_summary": f"{title} — {desc[:200]}",
        "research_impact_statement": (
            "This issue may affect the reproducibility or validity of research results "
            "if the affected code is part of data processing, model training, or evaluation pipelines."
        ),
        "affected_functions": [],
        "fix_strategy": f"Review and fix the {title} at {file_path} line {line}.",
        "causal_chain_data": {},
    }
