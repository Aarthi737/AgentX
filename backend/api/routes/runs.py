"""
AgentX — Pipeline API Routes
REST endpoints for pipeline run lifecycle management.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import List
from db.database import get_db_session
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from api.schemas.schemas import (
    ErrorResponse,
    RunDetailResponse,
    RunListItem,
    RunStartResponse,
    IssueResponse,
    PatchResponse,
    AuditLogEntry,
)
from config.settings import settings
from core.logging import get_logger
from core.pipeline import run_pipeline
from core.state import AgentXState
from db.database import get_db
from db.models import RunStatus
from db.repositories import (
    AuditLogRepository,
    IssueRepository,
    PatchRepository,
    RunRepository,
)
from services.websocket.ws_manager import ws_manager

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1/runs", tags=["pipeline"])


@router.post("", response_model=RunStartResponse, status_code=status.HTTP_202_ACCEPTED)
async def start_run(
    request_body: dict,
    background_tasks: BackgroundTasks,
):
    """
    Start a new AgentX pipeline run.
    The pipeline executes asynchronously; clients subscribe via WebSocket for progress.
    """
    from api.schemas.schemas import StartRunRequest
    try:
        req = StartRunRequest(**request_body)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    run_id = str(uuid.uuid4())[:8]

    initial_state: AgentXState = {
        "run_id": run_id,
        "repo_url": req.repo_url,
        "repo_branch": req.branch,
        "github_token": req.github_token or settings.github_default_token,
        "current_phase": 0,
        "status": RunStatus.PENDING,
        "retry_count": 0,
        "progress_events": [],
        "learned_weights": {},
        "afe_updates_pending": [],
    }
    async with get_db_session() as session:
    repo = RunRepository(session)

    await repo.create({
        "id": run_id,
        "status": RunStatus.PENDING,
        "repo_url": req.repo_url,
        "branch": req.branch,
    })

    # Launch pipeline in background
    background_tasks.add_task(_run_pipeline_task, run_id, initial_state)

    ws_url = f"{settings.app_host}:{settings.app_port}/ws/runs/{run_id}"
    logger.info("run_started", run_id=run_id, repo=req.repo_url)

    

    return RunStartResponse(
        run_id=run_id,
        status="PENDING",
        message=f"Pipeline started. Connect to WebSocket for real-time updates.",
        websocket_url=f"ws://{ws_url}",
    )


@router.get("", response_model=List[RunListItem])
async def list_runs(
    limit: int = 20,
    session: AsyncSession = Depends(get_db),
):
    """List recent pipeline runs."""
    repo = RunRepository(session)
    runs = await repo.list_recent(limit=limit)
    return [
        RunListItem(
            id=r.id,
            repo_url=r.repo_url,
            repo_owner=r.repo_owner,
            repo_name=r.repo_name,
            status=r.status,
            total_issues=r.total_issues,
            total_fixes=r.total_fixes,
            pr_url=r.pr_url,
            started_at=r.started_at,
            completed_at=r.completed_at,
        )
        for r in runs
    ]


@router.get("/{run_id}", response_model=RunDetailResponse)
async def get_run(run_id: str, session: AsyncSession = Depends(get_db)):
    """Get full details for a specific pipeline run."""
    runs_repo = RunRepository(session)
    run = await runs_repo.get(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")

    issues_repo = IssueRepository(session)
    issues = await issues_repo.get_by_run(run_id)

    patch_repo = PatchRepository(session)
    patches_raw = []
    for issue in issues:
        p = await patch_repo.get_by_issue(issue.id)
        if p:
            patches_raw.append(p)

    audit_repo = AuditLogRepository(session)
    audit_logs = await audit_repo.get_by_run(run_id)

    return RunDetailResponse(
        id=run.id,
        repo_url=run.repo_url,
        repo_owner=run.repo_owner,
        repo_name=run.repo_name,
        repo_branch=run.repo_branch,
        status=run.status,
        current_phase=run.current_phase,
        total_issues=run.total_issues,
        total_fixes=run.total_fixes,
        pr_url=run.pr_url,
        pr_number=run.pr_number,
        pdf_report_path=run.pdf_report_path,
        started_at=run.started_at,
        completed_at=run.completed_at,
        issues=[
            IssueResponse(
                id=i.id,
                issue_type=i.issue_type,
                severity=i.severity,
                title=i.title,
                description=i.description,
                file_path=i.file_path,
                line_start=i.line_start,
                line_end=i.line_end,
                code_snippet=i.code_snippet,
                cvss_score=i.cvss_score,
                research_impact_score=i.research_impact_score,
                composite_score=i.composite_score,
                rank=i.rank,
                ml_pattern=i.ml_pattern,
                owasp_category=i.owasp_category,
                detection_tool=i.detection_tool,
            )
            for i in issues
        ],
        patches=[
            PatchResponse(
                id=p.id,
                issue_id=p.issue_id,
                status=p.status,
                fix_explanation=p.fix_explanation,
                validation_confidence=p.validation_confidence,
                validation_correctness=p.validation_correctness,
                validation_security=p.validation_security,
                validation_best_practices=p.validation_best_practices,
                validation_research_integrity=p.validation_research_integrity,
                validation_contract_preservation=p.validation_contract_preservation,
                verification_passed=p.verification_passed,
                tests_passed=p.tests_passed,
                tests_failed=p.tests_failed,
                safe_to_merge=p.safe_to_merge,
                diff=p.diff,
            )
            for p in patches_raw
        ],
        audit_logs=[
            AuditLogEntry(
                id=a.id,
                agent_name=a.agent_name,
                phase=a.phase,
                action=a.action,
                status=a.status,
                message=a.message,
                duration_ms=a.duration_ms,
                created_at=a.created_at,
            )
            for a in audit_logs
        ],
    )


@router.get("/{run_id}/report")
async def download_report(run_id: str, session: AsyncSession = Depends(get_db)):
    """Download the PDF report for a completed run."""
    runs_repo = RunRepository(session)
    run = await runs_repo.get(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    if not run.pdf_report_path:
        raise HTTPException(status_code=404, detail="PDF report not yet generated")

    from pathlib import Path
    pdf_path = Path(run.pdf_report_path)
    if not pdf_path.exists():
        raise HTTPException(status_code=404, detail="PDF report file not found on disk")

    return FileResponse(
        path=str(pdf_path),
        media_type="application/pdf",
        filename=f"agentx_report_{run_id}.pdf",
    )


@router.delete("/{run_id}", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_run(run_id: str, session: AsyncSession = Depends(get_db)):
    """Cancel / mark a pending run as failed."""
    runs_repo = RunRepository(session)
    run = await runs_repo.get(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    await runs_repo.mark_failed(run_id, "Cancelled by user")


async def _run_pipeline_task(run_id: str, initial_state: AgentXState) -> None:
    """
    Background task that executes the pipeline and streams progress
    events to subscribed WebSocket clients.
    """
    from core.pipeline import run_pipeline

    async def _broadcast_events(state: AgentXState) -> None:
        events = state.get("progress_events", [])
        for event in events:
            if event.get("type") == "progress":
                await ws_manager.broadcast(run_id, event)

    try:
        final_state = await run_pipeline(initial_state)
        await _broadcast_events(final_state)

        # Broadcast completion
        await ws_manager.broadcast(run_id, {
            "type": "complete",
            "run_id": run_id,
            "status": final_state.get("status", "UNKNOWN"),
            "pr_url": final_state.get("pr_url", ""),
            "pr_number": final_state.get("pr_number", 0),
            "total_issues": len(final_state.get("ranked_issues", [])),
        })
    except Exception as exc:
        logger.exception("pipeline_task_error", run_id=run_id, error=str(exc))
        await ws_manager.broadcast(run_id, {
            "type": "error",
            "run_id": run_id,
            "error": str(exc),
        })
