"""
AgentX — Database Repository Layer
Provides async CRUD operations for all pipeline entities.
Agents use these repositories instead of writing SQL directly.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import (
    AdaptiveFeedback,
    AuditLog,
    ContextPackage,
    FeedbackOutcome,
    Issue,
    LearnedWeights,
    Patch,
    PatchStatus,
    PipelineRun,
    RCAReport,
    RunStatus,
)


class RunRepository:
    """CRUD for PipelineRun records."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, run_id: str, repo_url: str, repo_owner: str, repo_name: str,
                     repo_branch: str, github_token_hash: str) -> PipelineRun:
        run = PipelineRun(
            id=run_id,
            repo_url=repo_url,
            repo_owner=repo_owner,
            repo_name=repo_name,
            repo_branch=repo_branch,
            github_token_hash=github_token_hash,
            status=RunStatus.PENDING,
        )
        self.session.add(run)
        await self.session.flush()
        return run

    async def get(self, run_id: str) -> Optional[PipelineRun]:
        result = await self.session.execute(
            select(PipelineRun).where(PipelineRun.id == run_id)
        )
        return result.scalar_one_or_none()

    async def update_status(
        self, run_id: str, status: RunStatus, phase: Optional[int] = None, **kwargs
    ) -> None:
        values: Dict = {"status": status, "updated_at": datetime.now(timezone.utc)}
        if phase is not None:
            values["current_phase"] = phase
        values.update(kwargs)
        await self.session.execute(
            update(PipelineRun).where(PipelineRun.id == run_id).values(**values)
        )

    async def list_recent(self, limit: int = 20) -> List[PipelineRun]:
        result = await self.session.execute(
            select(PipelineRun).order_by(PipelineRun.started_at.desc()).limit(limit)
        )
        return list(result.scalars().all())

    async def mark_complete(self, run_id: str, pr_url: str, pr_number: int) -> None:
        await self.session.execute(
            update(PipelineRun)
            .where(PipelineRun.id == run_id)
            .values(
                status=RunStatus.PR_CREATED,
                pr_url=pr_url,
                pr_number=pr_number,
                completed_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
        )

    async def mark_failed(self, run_id: str, error: str) -> None:
        await self.session.execute(
            update(PipelineRun)
            .where(PipelineRun.id == run_id)
            .values(
                status=RunStatus.FAILED,
                error_message=error[:2000],
                updated_at=datetime.now(timezone.utc),
            )
        )


class ContextPackageRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def save(self, run_id: str, data: Dict) -> ContextPackage:
        pkg = ContextPackage(
            id=str(uuid.uuid4()),
            run_id=run_id,
            **data,
        )
        self.session.add(pkg)
        await self.session.flush()
        return pkg

    async def get_by_run(self, run_id: str) -> Optional[ContextPackage]:
        result = await self.session.execute(
            select(ContextPackage).where(ContextPackage.run_id == run_id)
        )
        return result.scalar_one_or_none()


class IssueRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def bulk_create(self, run_id: str, issues: List[Dict]) -> List[Issue]:
        created = []
        for data in issues:
            issue = Issue(
                id=data.get("id", str(uuid.uuid4())),
                run_id=run_id,
                **{k: v for k, v in data.items() if k != "id"},
            )
            self.session.add(issue)
            created.append(issue)
        await self.session.flush()
        return created

    async def get_by_run(self, run_id: str) -> List[Issue]:
        result = await self.session.execute(
            select(Issue).where(Issue.run_id == run_id).order_by(Issue.rank)
        )
        return list(result.scalars().all())

    async def update_ranks(self, ranked_issues: List[Dict]) -> None:
        for item in ranked_issues:
            await self.session.execute(
                update(Issue)
                .where(Issue.id == item["id"])
                .values(
                    composite_score=item.get("composite_score", 0),
                    rank=item.get("rank", 0),
                )
            )


class RCARepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, issue_id: str, data: Dict) -> RCAReport:
        report = RCAReport(
            id=str(uuid.uuid4()),
            issue_id=issue_id,
            **data,
        )
        self.session.add(report)
        await self.session.flush()
        return report

    async def get_by_issue(self, issue_id: str) -> Optional[RCAReport]:
        result = await self.session.execute(
            select(RCAReport).where(RCAReport.issue_id == issue_id)
        )
        return result.scalar_one_or_none()


class PatchRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, issue_id: str, data: Dict) -> Patch:
        patch = Patch(
            id=str(uuid.uuid4()),
            issue_id=issue_id,
            **data,
        )
        self.session.add(patch)
        await self.session.flush()
        return patch

    async def update(self, patch_id: str, **kwargs) -> None:
        await self.session.execute(
            update(Patch).where(Patch.id == patch_id).values(**kwargs)
        )

    async def get_by_issue(self, issue_id: str) -> Optional[Patch]:
        result = await self.session.execute(
            select(Patch).where(Patch.issue_id == issue_id)
        )
        return result.scalar_one_or_none()


class AuditLogRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def bulk_create(self, events: List[Dict]) -> None:
        for event in events:
            if event.get("type") != "audit":
                continue
            log = AuditLog(
                id=event.get("id", str(uuid.uuid4())),
                run_id=event["run_id"],
                agent_name=event["agent_name"],
                phase=event["phase"],
                action=event["action"],
                status=event["status"],
                message=event.get("message"),
                duration_ms=event.get("duration_ms"),
                metadata=event.get("metadata"),
            )
            self.session.add(log)
        await self.session.flush()

    async def get_by_run(self, run_id: str) -> List[AuditLog]:
        result = await self.session.execute(
            select(AuditLog)
            .where(AuditLog.run_id == run_id)
            .order_by(AuditLog.created_at)
        )
        return list(result.scalars().all())


class AdaptiveFeedbackRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, data: Dict) -> AdaptiveFeedback:
        fb = AdaptiveFeedback(id=str(uuid.uuid4()), **data)
        self.session.add(fb)
        await self.session.flush()
        return fb

    async def get_pending(self) -> List[AdaptiveFeedback]:
        result = await self.session.execute(
            select(AdaptiveFeedback).where(AdaptiveFeedback.processed == False)
        )
        return list(result.scalars().all())

    async def mark_processed(self, feedback_id: str) -> None:
        await self.session.execute(
            update(AdaptiveFeedback)
            .where(AdaptiveFeedback.id == feedback_id)
            .values(processed=True)
        )


class LearnedWeightsRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_all(self) -> Dict[str, float]:
        result = await self.session.execute(select(LearnedWeights))
        return {row.key: row.weight for row in result.scalars().all()}

    async def upsert(self, key: str, weight: float, prompt_template: Optional[str] = None) -> None:
        result = await self.session.execute(
            select(LearnedWeights).where(LearnedWeights.key == key)
        )
        existing = result.scalar_one_or_none()
        if existing:
            await self.session.execute(
                update(LearnedWeights)
                .where(LearnedWeights.key == key)
                .values(
                    weight=weight,
                    prompt_template=prompt_template,
                    occurrences=LearnedWeights.occurrences + 1,
                )
            )
        else:
            self.session.add(
                LearnedWeights(
                    id=str(uuid.uuid4()),
                    key=key,
                    weight=weight,
                    prompt_template=prompt_template,
                )
            )
        await self.session.flush()
