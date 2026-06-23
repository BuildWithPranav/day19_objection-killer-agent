from __future__ import annotations

from app.config import Settings
from app.detector import ObjectionDetector
from app.models import ObjectionType, TranscriptEvent


def test_detector_finds_pricing_competitor_objection() -> None:
    settings = Settings(stt_provider="mock", min_objection_confidence=0.5)
    detector = ObjectionDetector(settings)
    event = TranscriptEvent(
        session_id="s1",
        text="This is too expensive and HubSpot seems cheaper for our team.",
        is_final=True,
    )

    signal = detector.inspect(event)

    assert signal is not None
    assert signal.objection_type in {ObjectionType.PRICING, ObjectionType.COMPETITOR}
    assert signal.competitor == "Hubspot"
    assert signal.confidence >= 0.5
