"""
AgentX — Base Agent
Abstract base class implementing shared lifecycle, audit logging,
timing, and error handling for all 9 pipeline agents.
"""

from __future__ import annotations

import time
import uuid
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

from core.logging import get_logger
from core.state import AgentXState

logger = get_logger(__name__)


class BaseAgent(ABC):
    """
    All 9 AgentX agents inherit from this class.
    Provides:
    - Standardised __call__ interface for LangGraph nodes
    - Audit log emission
    - Phase timing
    - Structured error wrapping
    """

    agent_name: str = "BaseAgent"
    phase: int = 0

    def __init__(self):
        self._logger = get_logger(self.__class__.__name__)

    async def __call__(self, state: AgentXState) -> AgentXState:
        """
        LangGraph node entry point.
        Wraps execute() with timing, logging, and error handling.
        """
        run_id = state.get("run_id", "unknown")
        t_start = time.monotonic()
        self._logger.info(
            "agent_start",
            agent=self.agent_name,
            phase=self.phase,
            run_id=run_id,
        )

        try:
            updated_state = await self.execute(state)
            duration_ms = round((time.monotonic() - t_start) * 1000)
            self._logger.info(
                "agent_complete",
                agent=self.agent_name,
                phase=self.phase,
                run_id=run_id,
                duration_ms=duration_ms,
            )
            # Append audit log entry
            updated_state = self._append_audit(
                updated_state,
                action="execute",
                status="SUCCESS",
                duration_ms=duration_ms,
            )
            return updated_state

        except Exception as exc:
            duration_ms = round((time.monotonic() - t_start) * 1000)
            self._logger.exception(
                "agent_error",
                agent=self.agent_name,
                phase=self.phase,
                run_id=run_id,
                error=str(exc),
                duration_ms=duration_ms,
            )
            state["error_message"] = f"[{self.agent_name}] {exc!s}"
            state["status"] = "FAILED"
            return self._append_audit(
                state,
                action="execute",
                status="FAILURE",
                message=str(exc),
                duration_ms=duration_ms,
            )

    @abstractmethod
    async def execute(self, state: AgentXState) -> AgentXState:
        """
        Core agent logic. Receives current pipeline state, returns updated state.
        Must be implemented by every concrete agent.
        """
        ...

    def _append_audit(
        self,
        state: AgentXState,
        action: str,
        status: str,
        message: Optional[str] = None,
        duration_ms: Optional[int] = None,
        metadata: Optional[Dict] = None,
    ) -> AgentXState:
        """Append an audit log entry to state for later persistence."""
        events: list = list(state.get("progress_events", []))
        events.append(
            {
                "id": str(uuid.uuid4()),
                "run_id": state.get("run_id", ""),
                "agent_name": self.agent_name,
                "phase": self.phase,
                "action": action,
                "status": status,
                "message": message,
                "duration_ms": duration_ms,
                "metadata": metadata or {},
                "type": "audit",
            }
        )
        state["progress_events"] = events
        return state

    def _emit_progress(
        self,
        state: AgentXState,
        message: str,
        data: Optional[Dict] = None,
    ) -> AgentXState:
        """Emit a real-time progress event to the WebSocket stream."""
        events: list = list(state.get("progress_events", []))
        events.append(
            {
                "id": str(uuid.uuid4()),
                "run_id": state.get("run_id", ""),
                "agent": self.agent_name,
                "phase": self.phase,
                "message": message,
                "data": data or {},
                "type": "progress",
            }
        )
        state["progress_events"] = events
        return state
