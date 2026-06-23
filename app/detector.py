from __future__ import annotations

import re
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field

from app.config import Settings
from app.models import ObjectionSignal, ObjectionType, TranscriptEvent


@dataclass(slots=True)
class SessionTranscriptBuffer:
    """Bounded transcript window for low-latency intent detection."""

    max_chars: int = 1800
    chunks: deque[str] = field(default_factory=deque)
    total_chars: int = 0

    def add(self, text: str) -> None:
        clean = " ".join(text.split())
        if not clean:
            return
        self.chunks.append(clean)
        self.total_chars += len(clean)
        while self.total_chars > self.max_chars and self.chunks:
            removed = self.chunks.popleft()
            self.total_chars -= len(removed)

    def text(self) -> str:
        return " ".join(self.chunks)


class ObjectionDetector:
    """Fast deterministic detector for objections.

    The critical path deliberately avoids an LLM. Regex + weighted phrase matching is predictable and
    fast enough for the 1.5s requirement. LLM enrichment can happen after the card is already shown.
    """

    COMPETITOR_NAMES = [
        "salesforce",
        "hubspot",
        "outreach",
        "gong",
        "chorus",
        "apollo",
        "zoominfo",
        "pipedrive",
        "clari",
        "salesloft",
    ]

    PATTERNS: dict[ObjectionType, list[tuple[re.Pattern[str], float]]] = {
        ObjectionType.PRICING: [
            (re.compile(r"\btoo expensive\b|\bprice is high\b|\bcosts? too much\b", re.I), 0.92),
            (re.compile(r"\bcheaper\b|\bdiscount\b|\bpricing\b|\bbudget\b", re.I), 0.72),
            (re.compile(r"\bcan't afford\b|\bnot in our budget\b|\broi\b", re.I), 0.82),
        ],
        ObjectionType.COMPETITOR: [
            (re.compile(r"\bwe use\b.+\b(?:salesforce|hubspot|outreach|gong|apollo|salesloft)\b", re.I), 0.88),
            (re.compile(r"\b(?:salesforce|hubspot|outreach|gong|apollo|salesloft)\b.+\b(?:cheaper|better|already|included)\b", re.I), 0.86),
            (re.compile(r"\bcompetitor\b|\balternative\b|\bvendor\b", re.I), 0.68),
        ],
        ObjectionType.FEATURE: [
            (re.compile(r"\bdoes it support\b|\bcan it integrate\b|\bmissing feature\b", re.I), 0.78),
            (re.compile(r"\bapi\b|\bsso\b|\bsoc ?2\b|\bpermission\b|\bworkflow\b", re.I), 0.66),
        ],
        ObjectionType.TIMELINE: [
            (re.compile(r"\bnot a priority\b|\bnext quarter\b|\bnext year\b|\btoo busy\b", re.I), 0.86),
            (re.compile(r"\btimeline\b|\bimplementation\b|\brollout\b|\bmigration\b", re.I), 0.72),
        ],
        ObjectionType.SECURITY: [
            (re.compile(r"\bsecurity review\b|\bdata privacy\b|\bsoc ?2\b|\bhipaa\b|\bgdpr\b", re.I), 0.86),
            (re.compile(r"\bwhere is data stored\b|\bdata retention\b|\bencryption\b", re.I), 0.80),
        ],
        ObjectionType.INTEGRATION: [
            (re.compile(r"\bintegrate with\b|\bconnect to\b|\bwebhook\b|\bapi access\b", re.I), 0.82),
            (re.compile(r"\bcrm\b|\bslack\b|\bteams\b|\bgoogle workspace\b", re.I), 0.65),
        ],
        ObjectionType.PROCUREMENT: [
            (re.compile(r"\blegal\b|\bprocurement\b|\bvendor approval\b|\bmsa\b|\bdpa\b", re.I), 0.84),
            (re.compile(r"\bneed approval\b|\bcommittee\b|\bfinance team\b", re.I), 0.76),
        ],
    }

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.buffers: dict[str, SessionTranscriptBuffer] = defaultdict(SessionTranscriptBuffer)
        self.last_emit_at: dict[tuple[str, ObjectionType], float] = defaultdict(float)

    def inspect(self, event: TranscriptEvent) -> ObjectionSignal | None:
        """Inspect transcript text and return an objection signal if confidence passes threshold."""

        buffer = self.buffers[event.session_id]
        buffer.add(event.text)
        window = buffer.text()
        if not window:
            return None

        best_type = ObjectionType.UNKNOWN
        best_score = 0.0
        best_phrase = event.text
        for objection_type, patterns in self.PATTERNS.items():
            for pattern, score in patterns:
                match = pattern.search(window)
                if match and score > best_score:
                    best_type = objection_type
                    best_score = score
                    best_phrase = match.group(0)

        if best_score < self.settings.min_objection_confidence:
            return None

        now = time.monotonic()
        debounce_key = (event.session_id, best_type)
        if now - self.last_emit_at[debounce_key] < self.settings.objection_debounce_seconds:
            return None
        self.last_emit_at[debounce_key] = now

        return ObjectionSignal(
            session_id=event.session_id,
            objection_type=best_type,
            confidence=best_score,
            phrase=best_phrase,
            transcript_window=window[-1200:],
            competitor=self._extract_competitor(window),
        )

    def _extract_competitor(self, text: str) -> str | None:
        lowered = text.lower()
        for name in self.COMPETITOR_NAMES:
            if name in lowered:
                return name.title()
        return None
