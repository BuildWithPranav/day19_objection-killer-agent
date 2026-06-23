from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import get_settings  # noqa: E402
from app.db import Database  # noqa: E402
from app.models import KnowledgeItem, ObjectionType  # noqa: E402


DEMO_ITEMS = [
    KnowledgeItem(
        item_type="competitor_pricing",
        title="HubSpot hidden API and workflow cost battlecard",
        competitor="HubSpot",
        tags=["pricing", "api", "tco", "crm"],
        objection_types=[ObjectionType.PRICING, ObjectionType.COMPETITOR, ObjectionType.INTEGRATION],
        content=(
            "HubSpot can look cheaper on base seats, but advanced automation, API volume, reporting, and onboarding often move the real annual cost above the headline quote.\n"
            "Proof: customer ops teams commonly underestimate implementation/admin effort when comparing license-only pricing.\n"
            "Use this line: 'Let's compare the all-in workflow cost, not just the seat line item.'\n"
            "Discovery question: 'How many API-driven syncs and automated sequences will you need in month one?'"
        ),
    ),
    KnowledgeItem(
        item_type="case_study",
        title="Acme SaaS cut SDR research time by 41%",
        company="Acme SaaS",
        tags=["roi", "sales productivity", "case study"],
        objection_types=[ObjectionType.PRICING, ObjectionType.TIMELINE],
        content=(
            "Acme SaaS recovered 22 rep-hours per week by automating account research and objection prep, paying back the deployment in under 47 days.\n"
            "Proof: 41% less pre-call research time across 14 reps.\n"
            "Proof: pipeline velocity improved because reps had competitor answers in-call instead of follow-up lag.\n"
            "Use when buyer says budget is tight or timing is not urgent."
        ),
    ),
    KnowledgeItem(
        item_type="technical_answer",
        title="Security and data-retention answer",
        tags=["security", "soc2", "gdpr", "encryption"],
        objection_types=[ObjectionType.SECURITY, ObjectionType.PROCUREMENT],
        content=(
            "Security answer: customer data is encrypted in transit and at rest; retention windows are configurable; enterprise deployments can restrict storage region and disable training use.\n"
            "Offer: send SOC 2, DPA, subprocessors, and architecture diagram immediately after the call.\n"
            "Ask: 'Do you want security review before commercial approval, or in parallel?'"
        ),
    ),
    KnowledgeItem(
        item_type="battlecard",
        title="Implementation timeline compression talk track",
        tags=["timeline", "migration", "rollout"],
        objection_types=[ObjectionType.TIMELINE],
        content=(
            "Timeline answer: propose a 10-business-day pilot with one workflow, one rep team, and a success metric agreed upfront.\n"
            "Proof: fastest path is shadow mode first, CRM writeback second, automation third.\n"
            "Ask: 'What date would make this valuable if we proved it without disrupting the team?'"
        ),
    ),
    KnowledgeItem(
        item_type="technical_answer",
        title="API and CRM integration response",
        tags=["api", "webhook", "salesforce", "hubspot", "integration"],
        objection_types=[ObjectionType.FEATURE, ObjectionType.INTEGRATION, ObjectionType.COMPETITOR],
        content=(
            "Integration answer: the platform supports webhook-first integration and can sync cues, call metadata, and outcomes into Salesforce or HubSpot after rep approval.\n"
            "Proof: start read-only in week one; enable writeback only after field mapping and admin approval.\n"
            "Ask: 'Which object is the source of truth: lead, contact, opportunity, or account?'"
        ),
    ),
]


async def main() -> None:
    """Seed local SQLite with demo sales knowledge."""

    settings = get_settings()
    db = Database(settings.database_path)
    await db.init()
    for item in DEMO_ITEMS:
        await db.upsert_knowledge_item(item)
    print(f"Seeded {len(DEMO_ITEMS)} knowledge items into {settings.database_path}")


if __name__ == "__main__":
    asyncio.run(main())
