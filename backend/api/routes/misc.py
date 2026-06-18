"""
AgentX — Additional API Routes
- WebSocket: real-time pipeline progress streaming
- Feedback: PR outcome webhook for Adaptive Feedback Engine
- Health: system health check
- AFE: adaptive feedback engine stats
"""

from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from agents.adaptive_feedback.afe import AdaptiveFeedbackEngine
from api.schemas.schemas import (
    AFEStatsResponse,
    FeedbackRequest,
    HealthResponse,
)
from config.settings import settings
from core.logging import get_logger
from db.database import get_db
from services.websocket.ws_manager import ws_manager

logger = get_logger(__name__)

ws_router = APIRouter(tags=["websocket"])
feedback_router = APIRouter(prefix="/api/v1/feedback", tags=["feedback"])
health_router = APIRouter(prefix="/api/v1", tags=["health"])
afe_router = APIRouter(prefix="/api/v1/afe", tags=["afe"])

_afe = AdaptiveFeedbackEngine()


# ── WebSocket ─────────────────────────────────────────────────────────────────

@ws_router.websocket("/ws/runs/{run_id}")
async def websocket_run_progress(websocket: WebSocket, run_id: str):
    """
    WebSocket endpoint for real-time pipeline progress.
    Client connects with run_id; receives JSON events as pipeline progresses.

    Event types:
    - progress: {type, run_id, agent, phase, message, data}
    - complete: {type, run_id, status, pr_url, pr_number, total_issues}
    - error:    {type, run_id, error}
    """
    await ws_manager.connect(websocket, run_id)
    try:
        while True:
            # Keep connection alive; client may send ping messages
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text('{"type":"pong"}')
    except WebSocketDisconnect:
        await ws_manager.disconnect(websocket, run_id)
    except Exception as exc:
        logger.warning("ws_error", run_id=run_id, error=str(exc))
        await ws_manager.disconnect(websocket, run_id)


# ── Feedback Webhook ──────────────────────────────────────────────────────────

@feedback_router.post("")
async def receive_feedback(req: FeedbackRequest):
    """
    Receive PR outcome feedback from GitHub webhook or manual trigger.
    Triggers the Adaptive Feedback Engine to update learned weights.

    Payload example:
    {
        "run_id": "22f07458",
        "pr_number": 1,
        "outcome": "MERGED",
        "ml_patterns": ["missing_random_seed"],
        "human_modifications": "...diff..."
    }
    """
    result = await _afe.process_pr_outcome(
        run_id=req.run_id,
        pr_number=req.pr_number,
        outcome=req.outcome,
        human_modifications=req.human_modifications,
        issue_types=req.issue_types,
        ml_patterns=req.ml_patterns,
    )
    logger.info("feedback_processed", run_id=req.run_id, outcome=req.outcome)
    return {"status": "processed", "updates": result}


# ── Health Check ──────────────────────────────────────────────────────────────

@health_router.get("/health", response_model=HealthResponse)
async def health_check(session: AsyncSession = Depends(get_db)):
    """System health check — verifies DB and LLM connectivity."""
    # Check DB
    db_status = "ok"
    try:
        from sqlalchemy import text
        await session.execute(text("SELECT 1"))
    except Exception as exc:
        db_status = f"error: {exc}"

    # Check LLM connectivity (Gemini / legacy Groq key)
    llm_status = "ok" if settings.GOOGLE_API_KEY else "missing_api_key"

    return HealthResponse(
        status="healthy" if db_status == "ok" else "degraded",
        version="1.0.0",
        environment=settings.app_env,
        database=db_status,
        llm=llm_status,
    )


# ── AFE Stats ─────────────────────────────────────────────────────────────────

@afe_router.get("/stats", response_model=AFEStatsResponse)
async def get_afe_stats():
    """Return Adaptive Feedback Engine current learned weights and statistics."""
    stats = await _afe.get_stats()
    if "error" in stats:
        raise HTTPException(status_code=500, detail=stats["error"])

    return AFEStatsResponse(
        total_patterns_tracked=stats.get("total_patterns_tracked", 0),
        patterns=stats.get("patterns", {}),
        pending_feedback=stats.get("pending_feedback", 0),
        learning_rates=stats.get("learning_rates", {}),
    )


@afe_router.get("/weights")
async def get_learned_weights():
    """Return all current learned weights."""
    weights = await _afe.load_weights_for_run()
    return {"weights": weights}
