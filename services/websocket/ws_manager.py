"""
AgentX — WebSocket Connection Manager
Manages active WebSocket connections and broadcasts pipeline
progress events to subscribed clients in real-time.
Clients subscribe by run_id to receive per-pipeline updates.
"""

from __future__ import annotations

import asyncio
import json
from collections import defaultdict
from typing import Dict, List, Set

from fastapi import WebSocket, WebSocketDisconnect

from core.logging import get_logger

logger = get_logger(__name__)


class ConnectionManager:
    """
    Thread-safe WebSocket connection registry.
    Supports multiple clients subscribing to the same run_id.
    """

    def __init__(self):
        # run_id → set of active WebSocket connections
        self._connections: Dict[str, Set[WebSocket]] = defaultdict(set)
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket, run_id: str) -> None:
        """Accept a new WebSocket connection for a given run."""
        await websocket.accept()
        async with self._lock:
            self._connections[run_id].add(websocket)
        logger.info("ws_connected", run_id=run_id, total=len(self._connections[run_id]))

    async def disconnect(self, websocket: WebSocket, run_id: str) -> None:
        """Remove a WebSocket connection."""
        async with self._lock:
            self._connections[run_id].discard(websocket)
            if not self._connections[run_id]:
                del self._connections[run_id]
        logger.info("ws_disconnected", run_id=run_id)

    async def broadcast(self, run_id: str, event: Dict) -> None:
        """
        Send an event to all clients subscribed to a run.
        Dead connections are pruned automatically.
        """
        connections = list(self._connections.get(run_id, set()))
        if not connections:
            return

        message = json.dumps(event)
        dead: List[WebSocket] = []

        for ws in connections:
            try:
                await ws.send_text(message)
            except Exception:
                dead.append(ws)

        # Prune dead connections
        if dead:
            async with self._lock:
                for ws in dead:
                    self._connections[run_id].discard(ws)

    async def broadcast_all_runs(self, event: Dict) -> None:
        """Broadcast to ALL connected clients (used for system-wide events)."""
        for run_id in list(self._connections.keys()):
            await self.broadcast(run_id, event)

    def active_run_count(self) -> int:
        return len(self._connections)


# Module-level singleton
ws_manager = ConnectionManager()
