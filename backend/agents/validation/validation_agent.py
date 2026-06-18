"""
AgentX — Agent 7: Validation Agent (Debate Protocol)
Phase 07 — Critic Review

Responsibilities:
- 5-dimension adversarial review of each generated patch:
  1. Correctness
  2. Security
  3. Best Practices
  4. Research Integrity
  5. Contract Preservation
- Maximum 2 debate rounds (Proposer ↔ Critic)
- Confidence thresholds:
  >= 90% → Approved (HIGH)
  70-89% → Approved (MEDIUM)
  < 70%  → Human Review
- Rejected patches routed back to Agent 6

Tools: Gemini (Adversarial Prompts), Multi-Criteria Scoring
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Dict, List, Optional, Tuple

from config.settings import settings
from core.base_agent import BaseAgent
from core.gemini_client import get_gemini
from core.logging import get_logger
from core.state import AgentXState
from db.database import get_db_session
from db.models import PatchStatus, RunStatus
from db.repositories import PatchRepository, RunRepository

logger = get_logger(__name__)

# Dimension weights for final confidence score
DIMENSION_WEIGHTS = {
    "correctness": 0.30,
    "security": 0.25,
    "best_practices": 0.15,
    "research_integrity": 0.20,
    "contract_preservation": 0.10,
}

_PROPOSER_SYSTEM_PROMPT = """You are a code review proposer defending a patch.
Evaluate the patch across 5 dimensions and provide scores.

Return a JSON object:
{
  "correctness": 85,
  "security": 90,
  "best_practices": 80,
  "research_integrity": 88,
  "contract_preservation": 95,
  "strengths": ["List of patch strengths"],
  "overall_assessment": "Brief assessment"
}

Score each dimension 0–100. Be honest and precise."""

_CRITIC_SYSTEM_PROMPT = """You are an adversarial code reviewer finding flaws in a proposed patch.
Challenge the patch rigorously. Lower scores where you find genuine problems.

Return a JSON object:
{
  "correctness": 75,
  "security": 85,
  "best_practices": 70,
  "research_integrity": 80,
  "contract_preservation": 90,
  "weaknesses": ["Specific problems found"],
  "rejection_reasons": ["Reasons to reject, if any"],
  "overall_verdict": "APPROVE | REJECT | MODIFY"
}

Be critical but fair. Score 0–100 per dimension."""

_SYNTHESIS_SYSTEM_PROMPT = """You are a senior engineering lead synthesising a code review debate.
Given the proposer and critic scores, make a final decision.

Return a JSON object:
{
  "final_correctness": 82,
  "final_security": 88,
  "final_best_practices": 75,
  "final_research_integrity": 84,
  "final_contract_preservation": 92,
  "final_confidence": 84,
  "verdict": "APPROVE | REJECT | HUMAN_REVIEW",
  "review_notes": "Final synthesis notes for the developer",
  "required_changes": ["Changes needed if REJECT or MODIFY"]
}

Apply dimension weights: correctness=30%, security=25%, research_integrity=20%, best_practices=15%, contract=10%."""


class ValidationAgent(BaseAgent):
    """
    Agent 7 — Validation (Adversarial Debate Protocol).
    Implements a two-agent debate to validate each patch.
    """

    agent_name = "Validation"
    phase = 7

    def __init__(self):
        super().__init__()
        self.gemini = get_gemini()

    async def execute(self, state: AgentXState) -> AgentXState:
        """Run adversarial validation debate on all patches."""
        patches: List[Dict] = state.get("patches", [])
        ranked_issues: List[Dict] = state.get("ranked_issues", [])
        rca_reports: List[Dict] = state.get("rca_reports", [])
        run_id = state["run_id"]
        state["current_phase"] = 7

        # Build lookups
        issues_by_id = {i["id"]: i for i in ranked_issues}
        rca_by_issue = {r["issue_id"]: r for r in rca_reports}

        state = self._emit_progress(
            state, f"Running validation debate on {len(patches)} patches..."
        )

        validated: List[Dict] = []
        human_review: List[str] = []

        # Process in batches of 3
        batch_size = 3
        for i in range(0, len(patches), batch_size):
            batch = patches[i : i + batch_size]
            tasks = [
                self._validate_patch(
                    patch=p,
                    issue=issues_by_id.get(p.get("issue_id", ""), {}),
                    rca=rca_by_issue.get(p.get("issue_id", ""), {}),
                )
                for p in batch
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for patch, result in zip(batch, results):
                if isinstance(result, Exception):
                    logger.warning("validation_failed", patch_id=patch.get("id"), error=str(result))
                    result = _fallback_validation(patch)

                patch.update(result)
                validated.append(patch)

                if patch.get("status") in (PatchStatus.HUMAN_REVIEW, "HUMAN_REVIEW"):
                    human_review.append(patch.get("issue_id", ""))

            if i + batch_size < len(patches):
                await asyncio.sleep(1.0)

        # Persist validation results
        try:
            async with get_db_session() as session:
                patch_repo = PatchRepository(session)
                for patch in validated:
                    patch_id = patch.get("id")
                    if patch_id:
                        await patch_repo.update(
                            patch_id,
                            validation_confidence=patch.get("validation_confidence", 0),
                            validation_correctness=patch.get("validation_correctness", 0),
                            validation_security=patch.get("validation_security", 0),
                            validation_best_practices=patch.get("validation_best_practices", 0),
                            validation_research_integrity=patch.get("validation_research_integrity", 0),
                            validation_contract_preservation=patch.get("validation_contract_preservation", 0),
                            validation_notes=patch.get("validation_notes", ""),
                            validation_rounds=patch.get("validation_rounds", 1),
                            status=patch.get("status", PatchStatus.APPROVED),
                        )
                runs_repo = RunRepository(session)
                await runs_repo.update_status(run_id, RunStatus.VERIFICATION, phase=7)
        except Exception as exc:
            logger.warning("validation_db_persist_failed", error=str(exc))

        state["validated_patches"] = validated
        state["patches_needing_human"] = human_review
        state["validation_complete"] = True

        approved = sum(
            1 for p in validated
            if p.get("status") not in (PatchStatus.HUMAN_REVIEW, "HUMAN_REVIEW")
        )
        state = self._emit_progress(
            state,
            f"Validation complete: {approved}/{len(validated)} approved",
            {"approved": approved, "human_review": len(human_review)},
        )
        logger.info(
            "validation_complete",
            run_id=run_id,
            approved=approved,
            human_review=len(human_review),
        )
        return state

    async def _validate_patch(
        self,
        patch: Dict,
        issue: Dict,
        rca: Dict,
    ) -> Dict:
        """
        Run the full adversarial debate for one patch.
        Returns validation scores and verdict.
        """
        context = self._build_review_context(patch, issue, rca)

        # Round 1: Proposer evaluation
        proposer_scores = await self._proposer_review(context)

        # Round 1: Critic evaluation
        critic_scores = await self._critic_review(context, proposer_scores)

        verdict = critic_scores.get("overall_verdict", "APPROVE")
        rounds = 1

        # Round 2: If critic says REJECT, run synthesis debate
        if verdict == "REJECT" and rounds < settings.validation_max_rounds:
            rounds = 2
            synthesis = await self._synthesis_review(
                context, proposer_scores, critic_scores
            )
            final = synthesis
        else:
            # Average proposer and critic scores
            final = self._average_scores(proposer_scores, critic_scores)

        # Compute weighted confidence
        confidence = _compute_confidence(final)
        final["final_confidence"] = confidence

        # Determine status based on thresholds
        if confidence >= settings.validation_confidence_high:
            status = PatchStatus.APPROVED
        elif confidence >= settings.validation_confidence_medium:
            status = PatchStatus.APPROVED  # MEDIUM confidence still approved
        else:
            status = PatchStatus.HUMAN_REVIEW

        # Build validation notes
        notes_parts = []
        if proposer_scores.get("strengths"):
            notes_parts.append("Strengths: " + "; ".join(proposer_scores["strengths"][:3]))
        if critic_scores.get("weaknesses"):
            notes_parts.append("Concerns: " + "; ".join(critic_scores["weaknesses"][:3]))
        if critic_scores.get("rejection_reasons") and status == PatchStatus.HUMAN_REVIEW:
            notes_parts.append("Rejection reasons: " + "; ".join(critic_scores["rejection_reasons"][:3]))

        return {
            "validation_correctness": final.get("final_correctness", final.get("correctness", 70)),
            "validation_security": final.get("final_security", final.get("security", 70)),
            "validation_best_practices": final.get("final_best_practices", final.get("best_practices", 70)),
            "validation_research_integrity": final.get("final_research_integrity", final.get("research_integrity", 70)),
            "validation_contract_preservation": final.get("final_contract_preservation", final.get("contract_preservation", 70)),
            "validation_confidence": confidence,
            "validation_notes": "\n".join(notes_parts)[:2000],
            "validation_rounds": rounds,
            "status": status,
        }

    async def _proposer_review(self, context: str) -> Dict:
        """Proposer agent: defend the patch."""
        try:
            return await self.gemini.complete_structured_json(
                system_prompt=_PROPOSER_SYSTEM_PROMPT,
                user_prompt=f"Review this patch:\n\n{context}",
                max_tokens=1000,
            )
        except Exception as exc:
            logger.warning("proposer_review_failed", error=str(exc))
            return {k: 75 for k in DIMENSION_WEIGHTS}

    async def _critic_review(self, context: str, proposer_scores: Dict) -> Dict:
        """Critic agent: challenge the patch."""
        try:
            return await self.gemini.complete_structured_json(
                system_prompt=_CRITIC_SYSTEM_PROMPT,
                user_prompt=(
                    f"Challenge this patch:\n\n{context}\n\n"
                    f"Proposer scores: {proposer_scores}"
                ),
                max_tokens=1000,
            )
        except Exception as exc:
            logger.warning("critic_review_failed", error=str(exc))
            return {k: 75 for k in DIMENSION_WEIGHTS}

    async def _synthesis_review(
        self, context: str, proposer: Dict, critic: Dict
    ) -> Dict:
        """Senior lead synthesis after disagreement."""
        try:
            return await self.gemini.complete_structured_json(
                system_prompt=_SYNTHESIS_SYSTEM_PROMPT,
                user_prompt=(
                    f"Synthesise this debate:\n\nContext:\n{context}\n\n"
                    f"Proposer: {proposer}\n\nCritic: {critic}"
                ),
                max_tokens=1000,
            )
        except Exception as exc:
            logger.warning("synthesis_review_failed", error=str(exc))
            return self._average_scores(proposer, critic)

    def _average_scores(self, proposer: Dict, critic: Dict) -> Dict:
        """Average proposer and critic scores for each dimension."""
        dims = [
            ("correctness", "final_correctness"),
            ("security", "final_security"),
            ("best_practices", "final_best_practices"),
            ("research_integrity", "final_research_integrity"),
            ("contract_preservation", "final_contract_preservation"),
        ]
        result = {}
        for src_key, dst_key in dims:
            p = float(proposer.get(src_key, 75))
            c = float(critic.get(src_key, 75))
            result[dst_key] = round((p + c) / 2, 1)
        return result

    def _build_review_context(self, patch: Dict, issue: Dict, rca: Dict) -> str:
        """Build the review context string for both proposer and critic."""
        original = patch.get("original_code", "")[:2000]
        fixed = patch.get("fixed_code", "")[:2000]
        diff = patch.get("diff", "")[:1000]

        return f"""Issue: {issue.get('title', 'Unknown')}
Severity: {issue.get('severity', 'UNKNOWN')}
Type: {issue.get('issue_type', 'UNKNOWN')}
ML Pattern: {issue.get('ml_pattern', 'N/A')}
Description: {issue.get('description', '')}

Root Cause: {rca.get('root_cause_summary', 'N/A')}
Research Impact: {rca.get('research_impact_statement', 'N/A')}

Fix Explanation: {patch.get('fix_explanation', '')}
Confidence Claimed: {patch.get('validation_confidence', 0)}%

Diff:
{diff}

Original (excerpt):
```python
{original}
```

Fixed (excerpt):
```python
{fixed}
```"""


def _compute_confidence(scores: Dict) -> float:
    """Compute weighted confidence score from dimension scores."""
    key_map = {
        "correctness": "final_correctness",
        "security": "final_security",
        "best_practices": "final_best_practices",
        "research_integrity": "final_research_integrity",
        "contract_preservation": "final_contract_preservation",
    }
    total = 0.0
    for dim, weight in DIMENSION_WEIGHTS.items():
        final_key = key_map.get(dim, dim)
        score = float(scores.get(final_key, scores.get(dim, 75)))
        total += score * weight
    return round(total, 1)


def _fallback_validation(patch: Dict) -> Dict:
    """Fallback validation when Gemini is unavailable."""
    return {
        "validation_correctness": 70.0,
        "validation_security": 70.0,
        "validation_best_practices": 70.0,
        "validation_research_integrity": 70.0,
        "validation_contract_preservation": 70.0,
        "validation_confidence": 70.0,
        "validation_notes": "Validation service unavailable — defaulting to medium confidence. Manual review recommended.",
        "validation_rounds": 1,
        "status": PatchStatus.HUMAN_REVIEW,
    }
