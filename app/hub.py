from __future__ import annotations

from collections import defaultdict
from typing import Any

import orjson
import structlog
from fastapi import WebSocket

from app.models import CueCard

logger = structlog.get_logger(__name__)


class CueHub:
    """In-memory websocket fanout for private rep dashboards."""

    def __init__(self) -> None:
        self._rep_connections: dict[str, set[WebSocket]] = defaultdict(set)
        self._session_to_rep: dict[str, str] = {}

    def bind_session(self, session_id: str, rep_id: str) -> None:
        """Associate a call session with the sales rep receiving cue cards."""

        self._session_to_rep[session_id] = rep_id

    async def connect(self, rep_id: str, websocket: WebSocket) -> None:
        """Register dashboard websocket."""

        await websocket.accept()
        self._rep_connections[rep_id].add(websocket)
        logger.info("dashboard_connected", rep_id=rep_id, connections=len(self._rep_connections[rep_id]))

    def disconnect(self, rep_id: str, websocket: WebSocket) -> None:
        """Remove dashboard websocket."""

        self._rep_connections[rep_id].discard(websocket)
        logger.info("dashboard_disconnected", rep_id=rep_id, connections=len(self._rep_connections[rep_id]))

    async def publish_card(self, card: CueCard) -> None:
        """Push cue card to every dashboard owned by the session rep."""

        rep_id = self._session_to_rep.get(card.session_id)
        if not rep_id:
            logger.warning("cue_has_no_rep_binding", session_id=card.session_id)
            return
        payload: dict[str, Any] = {"type": "cue_card", "data": card.model_dump(mode="json")}
        encoded = orjson.dumps(payload).decode("utf-8")
        stale: list[WebSocket] = []
        for ws in list(self._rep_connections[rep_id]):
            try:
                await ws.send_text(encoded)
            except RuntimeError:
                stale.append(ws)
        for ws in stale:
            self.disconnect(rep_id, ws)
