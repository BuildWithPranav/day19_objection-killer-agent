from __future__ import annotations

import time

from app.config import Settings
from app.db import Database
from app.models import CueCard, KnowledgeItem, ObjectionSignal, ObjectionType


class CueEngine:
    """Build private rep cue cards from objection signals and internal knowledge."""

    def __init__(self, db: Database, settings: Settings) -> None:
        self.db = db
        self.settings = settings

    async def build_card(self, signal: ObjectionSignal, started_at: float) -> CueCard:
        """Return the highest-value cue card for the detected objection."""

        items = await self.db.search_knowledge(
            query=signal.transcript_window,
            objection_type=signal.objection_type,
            competitor=signal.competitor,
            limit=self.settings.max_cards_per_objection,
        )
        card = self._compose_card(signal, items)
        card.latency_ms = int((time.perf_counter() - started_at) * 1000)
        await self.db.save_cue_card(card)
        return card

    def _compose_card(self, signal: ObjectionSignal, items: list[KnowledgeItem]) -> CueCard:
        top = items[0] if items else None
        proof_points = self._proof_points(items)
        headline = self._headline(signal, top)
        rebuttal = self._rebuttal(signal, top)
        talk_track = self._talk_track(signal, top, proof_points)

        return CueCard(
            session_id=signal.session_id,
            objection_type=signal.objection_type,
            severity="high" if signal.confidence >= 0.82 else "medium",
            headline=headline,
            rebuttal=rebuttal,
            proof_points=proof_points,
            talk_track=talk_track,
            source_titles=[item.title for item in items],
            confidence=signal.confidence,
            metadata={
                "trigger_phrase": signal.phrase,
                "competitor": signal.competitor,
                "knowledge_item_ids": [item.id for item in items],
            },
        )

    @staticmethod
    def _headline(signal: ObjectionSignal, top: KnowledgeItem | None) -> str:
        competitor = f" vs {signal.competitor}" if signal.competitor else ""
        if top:
            return f"{signal.objection_type.title()}{competitor}: use {top.title}"
        return f"{signal.objection_type.title()}{competitor}: acknowledge, quantify, redirect to value"

    @staticmethod
    def _rebuttal(signal: ObjectionSignal, top: KnowledgeItem | None) -> str:
        if top:
            return top.content.split("\n", maxsplit=1)[0][:420]

        defaults: dict[ObjectionType, str] = {
            ObjectionType.PRICING: "Do not defend the price first. Quantify the cost of the current manual process, then anchor on payback period and total cost of ownership.",
            ObjectionType.COMPETITOR: "Avoid trashing the competitor. Ask which capability matters most, then separate headline license price from hidden usage, implementation, and admin costs.",
            ObjectionType.FEATURE: "Confirm the exact workflow. Then answer with supported capability, workaround if needed, and implementation owner.",
            ObjectionType.TIMELINE: "Tie urgency to a business event. Ask what breaks if they wait one quarter and quantify the cost of delay.",
            ObjectionType.SECURITY: "Move from generic reassurance to artifacts: SOC 2, DPA, encryption, retention controls, and security-review path.",
            ObjectionType.INTEGRATION: "Ask for the source system and direction of sync. Then mention API/webhook/CRM connector coverage and typical implementation time.",
            ObjectionType.PROCUREMENT: "Map the buying path: legal, security, finance, signer. Offer the vendor packet and mutual action plan.",
            ObjectionType.UNKNOWN: "Acknowledge the concern, ask one clarifying question, and route to value with proof.",
        }
        return defaults.get(signal.objection_type, defaults[ObjectionType.UNKNOWN])

    @staticmethod
    def _proof_points(items: list[KnowledgeItem]) -> list[str]:
        points: list[str] = []
        for item in items:
            lines = [line.strip(" -•") for line in item.content.splitlines() if line.strip()]
            points.extend(lines[1:3] if len(lines) > 1 else lines[:1])
        return points[:5]

    @staticmethod
    def _talk_track(signal: ObjectionSignal, top: KnowledgeItem | None, proof_points: list[str]) -> str:
        proof = proof_points[0] if proof_points else "we can show a relevant proof point after the call"
        if signal.competitor:
            return (
                f"Say: 'That makes sense — a lot of teams compare us with {signal.competitor}. "
                f"The key difference is total cost and outcome, not just sticker price. {proof}. "
                "Can I show you the one-line cost comparison?'"
            )
        if top:
            return f"Say: 'Good point. We solved this exact issue in {top.title}. {proof}. Want the short version?'"
        return "Say: 'Totally fair. Before I answer, can I ask what matters more here: cost, implementation risk, or team adoption?'"
