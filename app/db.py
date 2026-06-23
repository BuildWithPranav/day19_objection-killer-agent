from __future__ import annotations

import json
from pathlib import Path

import aiosqlite
import structlog

from app.models import CueCard, KnowledgeItem, ObjectionType

logger = structlog.get_logger(__name__)

SCHEMA_SQL = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS knowledge_items (
    id TEXT PRIMARY KEY,
    item_type TEXT NOT NULL,
    title TEXT NOT NULL,
    company TEXT,
    competitor TEXT,
    tags_json TEXT NOT NULL,
    objection_types_json TEXT NOT NULL,
    content TEXT NOT NULL,
    source_url TEXT,
    created_at TEXT NOT NULL
);
CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_fts USING fts5(
    id UNINDEXED,
    title,
    competitor,
    tags,
    objection_types,
    content
);
CREATE TABLE IF NOT EXISTS cue_events (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    objection_type TEXT NOT NULL,
    severity TEXT NOT NULL,
    headline TEXT NOT NULL,
    rebuttal TEXT NOT NULL,
    proof_points_json TEXT NOT NULL,
    talk_track TEXT NOT NULL,
    source_titles_json TEXT NOT NULL,
    confidence REAL NOT NULL,
    latency_ms INTEGER,
    metadata_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""


class Database:
    """Async SQLite persistence and low-latency FTS search."""

    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        self.database_path.parent.mkdir(parents=True, exist_ok=True)

    async def init(self) -> None:
        """Create database schema."""

        async with aiosqlite.connect(self.database_path) as db:
            await db.executescript(SCHEMA_SQL)
            await db.commit()
        logger.info("database_initialized", path=str(self.database_path))

    async def upsert_knowledge_item(self, item: KnowledgeItem) -> None:
        """Insert or update a knowledge item and refresh FTS index."""

        async with aiosqlite.connect(self.database_path) as db:
            await db.execute(
                """
                INSERT INTO knowledge_items (
                    id, item_type, title, company, competitor, tags_json,
                    objection_types_json, content, source_url, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    item_type=excluded.item_type,
                    title=excluded.title,
                    company=excluded.company,
                    competitor=excluded.competitor,
                    tags_json=excluded.tags_json,
                    objection_types_json=excluded.objection_types_json,
                    content=excluded.content,
                    source_url=excluded.source_url
                """,
                (
                    item.id,
                    item.item_type,
                    item.title,
                    item.company,
                    item.competitor,
                    json.dumps(item.tags),
                    json.dumps([str(value) for value in item.objection_types]),
                    item.content,
                    item.source_url,
                    item.created_at.isoformat(),
                ),
            )
            await db.execute("DELETE FROM knowledge_fts WHERE id = ?", (item.id,))
            await db.execute(
                """
                INSERT INTO knowledge_fts (id, title, competitor, tags, objection_types, content)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    item.id,
                    item.title,
                    item.competitor or "",
                    " ".join(item.tags),
                    " ".join(str(value) for value in item.objection_types),
                    item.content,
                ),
            )
            await db.commit()

    async def search_knowledge(
        self,
        query: str,
        objection_type: ObjectionType,
        competitor: str | None,
        limit: int,
    ) -> list[KnowledgeItem]:
        """Search sales knowledge with FTS first, then LIKE fallback."""

        cleaned_query = self._sanitize_fts_query(query)
        terms = [cleaned_query, str(objection_type)]
        if competitor:
            terms.append(competitor)
        fts_query = " OR ".join(term for term in terms if term)

        rows: list[aiosqlite.Row] = []
        async with aiosqlite.connect(self.database_path) as db:
            db.row_factory = aiosqlite.Row
            if fts_query:
                try:
                    cursor = await db.execute(
                        """
                        SELECT k.*
                        FROM knowledge_fts f
                        JOIN knowledge_items k ON k.id = f.id
                        WHERE knowledge_fts MATCH ?
                        ORDER BY rank
                        LIMIT ?
                        """,
                        (fts_query, limit),
                    )
                    rows = await cursor.fetchall()
                except aiosqlite.OperationalError as exc:
                    logger.warning("fts_search_failed_falling_back", error=str(exc), query=fts_query)

            if not rows:
                like = f"%{query[:80]}%"
                cursor = await db.execute(
                    """
                    SELECT * FROM knowledge_items
                    WHERE content LIKE ? OR title LIKE ? OR competitor LIKE ? OR objection_types_json LIKE ?
                    LIMIT ?
                    """,
                    (like, like, f"%{competitor or ''}%", f"%{str(objection_type)}%", limit),
                )
                rows = await cursor.fetchall()

        return [self._row_to_item(row) for row in rows]

    async def save_cue_card(self, card: CueCard) -> None:
        """Persist cue card event for analytics and QA."""

        async with aiosqlite.connect(self.database_path) as db:
            await db.execute(
                """
                INSERT INTO cue_events (
                    id, session_id, objection_type, severity, headline, rebuttal,
                    proof_points_json, talk_track, source_titles_json, confidence,
                    latency_ms, metadata_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    card.id,
                    card.session_id,
                    str(card.objection_type),
                    card.severity,
                    card.headline,
                    card.rebuttal,
                    json.dumps(card.proof_points),
                    card.talk_track,
                    json.dumps(card.source_titles),
                    card.confidence,
                    card.latency_ms,
                    json.dumps(card.metadata),
                    card.created_at.isoformat(),
                ),
            )
            await db.commit()

    @staticmethod
    def _sanitize_fts_query(query: str) -> str:
        tokens = ["".join(ch for ch in token if ch.isalnum() or ch in {"_", "-"}) for token in query.split()]
        tokens = [token for token in tokens if len(token) > 2]
        return " OR ".join(tokens[:8])

    @staticmethod
    def _row_to_item(row: aiosqlite.Row) -> KnowledgeItem:
        return KnowledgeItem(
            id=row["id"],
            item_type=row["item_type"],
            title=row["title"],
            company=row["company"],
            competitor=row["competitor"],
            tags=json.loads(row["tags_json"]),
            objection_types=[ObjectionType(value) for value in json.loads(row["objection_types_json"])],
            content=row["content"],
            source_url=row["source_url"],
            created_at=row["created_at"],
        )
