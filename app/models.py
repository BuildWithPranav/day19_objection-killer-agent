from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field, computed_field


class ObjectionType(StrEnum):
    """Supported real-time objection categories."""

    PRICING = "pricing"
    COMPETITOR = "competitor"
    FEATURE = "feature"
    TIMELINE = "timeline"
    SECURITY = "security"
    INTEGRATION = "integration"
    PROCUREMENT = "procurement"
    UNKNOWN = "unknown"


class TranscriptEvent(BaseModel):
    """A partial or final speech-to-text event from the call stream."""

    session_id: str
    speaker: str = "unknown"
    text: str
    is_final: bool = False
    start_ms: int | None = None
    end_ms: int | None = None
    received_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ObjectionSignal(BaseModel):
    """Detected objection intent with confidence and triggering evidence."""

    session_id: str
    objection_type: ObjectionType
    confidence: float = Field(ge=0.0, le=1.0)
    phrase: str
    transcript_window: str
    competitor: str | None = None
    detected_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class KnowledgeItem(BaseModel):
    """Internal sales knowledge used to generate cue cards."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    item_type: str = Field(description="case_study, competitor_pricing, battlecard, technical_answer")
    title: str
    company: str | None = None
    competitor: str | None = None
    tags: list[str] = Field(default_factory=list)
    objection_types: list[ObjectionType] = Field(default_factory=list)
    content: str
    source_url: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @computed_field
    @property
    def searchable_text(self) -> str:
        """Flatten item text for full-text search."""

        return " ".join(
            [
                self.item_type,
                self.title,
                self.company or "",
                self.competitor or "",
                " ".join(self.tags),
                " ".join(self.objection_types),
                self.content,
            ]
        )


class CueCard(BaseModel):
    """Rep-facing cue card shown on the private sales dashboard."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    session_id: str
    objection_type: ObjectionType
    severity: str = "high"
    headline: str
    rebuttal: str
    proof_points: list[str] = Field(default_factory=list)
    talk_track: str
    source_titles: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    latency_ms: int | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = Field(default_factory=dict)


class SessionCreate(BaseModel):
    """Request payload for creating a monitored sales-call session."""

    rep_id: str = Field(min_length=1)
    account_name: str | None = None
    meeting_provider: str | None = Field(default=None, description="zoom, google_meet, teams, browser_tab")


class SessionInfo(BaseModel):
    """Created session details and URLs."""

    session_id: str
    rep_id: str
    audio_ws_url: str
    dashboard_url: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
