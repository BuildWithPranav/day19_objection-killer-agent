from __future__ import annotations

import time
from pathlib import Path

import pytest

from app.config import Settings
from app.cue_engine import CueEngine
from app.db import Database
from app.models import KnowledgeItem, ObjectionSignal, ObjectionType


@pytest.mark.asyncio
async def test_cue_engine_builds_card_from_knowledge(tmp_path: Path) -> None:
    settings = Settings(database_path=tmp_path / "test.db", stt_provider="mock")
    db = Database(settings.database_path)
    await db.init()
    await db.upsert_knowledge_item(
        KnowledgeItem(
            item_type="competitor_pricing",
            title="HubSpot TCO battlecard",
            competitor="HubSpot",
            tags=["pricing"],
            objection_types=[ObjectionType.PRICING, ObjectionType.COMPETITOR],
            content="HubSpot headline seat pricing excludes important workflow and API costs.\nProof: compare all-in annual cost.",
        )
    )
    engine = CueEngine(db, settings)
    signal = ObjectionSignal(
        session_id="s1",
        objection_type=ObjectionType.PRICING,
        confidence=0.9,
        phrase="too expensive",
        competitor="HubSpot",
        transcript_window="HubSpot is cheaper and this is too expensive",
    )

    card = await engine.build_card(signal, started_at=time.perf_counter())

    assert "HubSpot" in card.headline
    assert card.proof_points
    assert card.latency_ms is not None
