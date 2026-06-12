"""
AgentX — Adaptive Feedback Engine (AFE)
Continuous Improvement Loop

Behaviour:
- PR Merged   → Reinforce: increase weights, reinforce prompts & patterns
- PR Modified → Partial learn: update prompts, adjust weights from human edits
- PR Closed   → Deprioritise: lower detection weights, flag for review

Learns:
- Severity ranking weights per ML pattern
- Groq prompt templates that produced accepted fixes
- Detection rule confidence thresholds
- Test generation strategies

Storage: Supabase (learned_weights, adaptive_feedback tables)
"""

from __future__ import annotations

import asyncio
import hashlib
from datetime import datetime, timezone
from typing import Dict, List, Optional

from config.settings import settings
from core.groq_client import get_groq
from core.logging import get_logger
from db.database import get_db_session
from db.models import FeedbackOutcome
from db.repositories import (
    AdaptiveFeedbackRepository,
    LearnedWeightsRepository,
    RunRepository,
)

logger = get_logger(__name__)

# Learning rates per outcome
LEARNING_RATES = {
    FeedbackOutcome.MERGED: 0.1,     # reinforce — increase weight by 10%
    FeedbackOutcome.MODIFIED: 0.03,  # partial — small adjustment
    FeedbackOutcome.CLOSED: -0.15,   # deprioritise — decrease weight by 15%
}

# Base weights for each ML pattern (initialised if no DB record exists)
DEFAULT_PATTERN_WEIGHTS = {
    "data_leakage": 1.0,
    "missing_random_seed": 1.0,
    "vanishing_gradient": 0.8,
    "gpu_memory_leak": 0.8,
    "tensor_mismatch": 1.0,
    "wrong_cv_strategy": 0.9,
    "train_test_contamination": 1.0,
    "incorrect_loss_function": 0.9,
}


class AdaptiveFeedbackEngine:
    """
    Monitors PR outcomes and continuously updates detection/fix strategies.
    Called after PR merge/close events via GitHub webhook.
    """

    def __init__(self):
        self.groq = get_groq()

    async def process_pr_outcome(
        self,
        run_id: str,
        pr_number: int,
        outcome: str,
        human_modifications: Optional[str] = None,
        issue_types: Optional[List[str]] = None,
        ml_patterns: Optional[List[str]] = None,
    ) -> Dict:
        """
        Process a PR outcome event and update learned weights.

        Args:
            run_id: The AgentX run that produced the PR
            pr_number: GitHub PR number
            outcome: MERGED | MODIFIED | CLOSED
            human_modifications: Diff of any changes humans made before merging
            issue_types: Types of issues fixed in this PR
            ml_patterns: ML patterns detected in this PR
        """
        try:
            outcome_enum = FeedbackOutcome(outcome.upper())
        except ValueError:
            logger.warning("invalid_feedback_outcome", outcome=outcome)
            return {"error": f"Invalid outcome: {outcome}"}

        logger.info(
            "afe_processing",
            run_id=run_id,
            pr_number=pr_number,
            outcome=outcome,
        )

        updates_applied: Dict = {}

        # ── 1. Update pattern weights ─────────────────────────────────────────
        patterns = ml_patterns or []
        weight_updates = await self._update_pattern_weights(
            patterns=patterns,
            outcome=outcome_enum,
        )
        updates_applied["weight_updates"] = weight_updates

        # ── 2. Update prompt templates if MERGED ─────────────────────────────
        prompt_updates = {}
        if outcome_enum == FeedbackOutcome.MERGED and ml_patterns:
            prompt_updates = await self._reinforce_prompts(
                ml_patterns=ml_patterns,
                run_id=run_id,
            )
            updates_applied["prompt_updates"] = prompt_updates

        # ── 3. Learn from human modifications if MODIFIED ────────────────────
        modification_learnings = {}
        if outcome_enum == FeedbackOutcome.MODIFIED and human_modifications:
            modification_learnings = await self._learn_from_modifications(
                human_modifications=human_modifications,
                ml_patterns=ml_patterns or [],
            )
            updates_applied["modification_learnings"] = modification_learnings

        # ── 4. Persist feedback record ────────────────────────────────────────
        try:
            async with get_db_session() as session:
                fb_repo = AdaptiveFeedbackRepository(session)
                await fb_repo.create({
                    "run_id": run_id,
                    "pr_number": pr_number,
                    "outcome": outcome_enum,
                    "issue_type": ",".join(issue_types or []),
                    "ml_pattern": ",".join(patterns),
                    "human_modifications": human_modifications,
                    "severity_weight_delta": weight_updates,
                    "detection_rule_updates": modification_learnings,
                    "prompt_updates": prompt_updates,
                    "processed": True,
                })
        except Exception as exc:
            logger.warning("afe_persist_failed", error=str(exc))

        logger.info(
            "afe_complete",
            run_id=run_id,
            updates=len(updates_applied),
        )
        return updates_applied

    async def load_weights_for_run(self) -> Dict[str, float]:
        """Load current learned weights from DB for a new pipeline run."""
        try:
            async with get_db_session() as session:
                weights_repo = LearnedWeightsRepository(session)
                db_weights = await weights_repo.get_all()

            # Merge with defaults (DB weights override defaults)
            merged = {**DEFAULT_PATTERN_WEIGHTS, **db_weights}
            return merged
        except Exception as exc:
            logger.warning("weights_load_failed", error=str(exc))
            return {**DEFAULT_PATTERN_WEIGHTS}

    async def _update_pattern_weights(
        self,
        patterns: List[str],
        outcome: FeedbackOutcome,
    ) -> Dict[str, float]:
        """Adjust learned weights for each ML pattern based on outcome."""
        if not patterns:
            return {}

        lr = LEARNING_RATES[outcome]
        updates: Dict[str, float] = {}

        try:
            async with get_db_session() as session:
                weights_repo = LearnedWeightsRepository(session)
                current_weights = await weights_repo.get_all()

                for pattern in patterns:
                    current = current_weights.get(
                        pattern, DEFAULT_PATTERN_WEIGHTS.get(pattern, 1.0)
                    )
                    new_weight = max(0.1, min(2.0, current + lr))  # clamp [0.1, 2.0]
                    await weights_repo.upsert(key=pattern, weight=new_weight)
                    updates[pattern] = new_weight
                    logger.debug(
                        "weight_updated",
                        pattern=pattern,
                        old=current,
                        new=new_weight,
                        outcome=outcome,
                    )
        except Exception as exc:
            logger.warning("weight_update_failed", error=str(exc))

        return updates

    async def _reinforce_prompts(
        self,
        ml_patterns: List[str],
        run_id: str,
    ) -> Dict[str, str]:
        """
        When a PR is merged, mark the prompt templates used as successful.
        Updates the prompt_template field in learned_weights so future runs
        can use the reinforced prompt variant.
        """
        updates: Dict[str, str] = {}
        for pattern in ml_patterns:
            prompt_key = f"prompt:{pattern}"
            # Record that this pattern's current prompt led to a successful merge
            try:
                async with get_db_session() as session:
                    weights_repo = LearnedWeightsRepository(session)
                    await weights_repo.upsert(
                        key=prompt_key,
                        weight=1.0,
                        prompt_template=f"reinforced:{run_id}",
                    )
                updates[pattern] = "reinforced"
            except Exception:
                pass
        return updates

    async def _learn_from_modifications(
        self,
        human_modifications: str,
        ml_patterns: List[str],
    ) -> Dict:
        """
        When humans modify a fix before merging, use Groq to extract
        the learning signal from the diff.
        """
        if not human_modifications or len(human_modifications) < 50:
            return {}

        try:
            result = await self.groq.complete_structured_json(
                system_prompt="""Analyse this human modification to an AI-generated fix.
Extract learning signals.

Return JSON:
{
  "what_was_wrong": "What the AI got wrong",
  "correct_approach": "What the human did instead",
  "pattern_refinement": "How to improve detection of this pattern",
  "prompt_improvement": "Suggested improvement to the fix prompt"
}""",
                user_prompt=f"""Human modified this AI fix (diff):

{human_modifications[:2000]}

ML Patterns involved: {ml_patterns}

What can we learn from this modification?""",
                max_tokens=800,
            )
            return result
        except Exception as exc:
            logger.warning("modification_learning_failed", error=str(exc))
            return {}

    async def get_stats(self) -> Dict:
        """Return AFE statistics for the dashboard."""
        try:
            async with get_db_session() as session:
                weights_repo = LearnedWeightsRepository(session)
                weights = await weights_repo.get_all()

                fb_repo = AdaptiveFeedbackRepository(session)
                pending = await fb_repo.get_pending()

            return {
                "total_patterns_tracked": len(weights),
                "patterns": weights,
                "pending_feedback": len(pending),
                "learning_rates": {k.value: v for k, v in LEARNING_RATES.items()},
            }
        except Exception as exc:
            return {"error": str(exc)}
