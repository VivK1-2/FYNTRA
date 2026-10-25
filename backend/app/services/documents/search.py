"""
Evidence retrieval over document chunks.

Postgres: OR-of-terms to_tsquery + ts_rank on the GIN-indexed tsvector.
Other dialects (SQLite in tests): simple term-frequency scoring in Python, same output shape.
"""
import re
from dataclasses import dataclass
from typing import List, Optional, Sequence

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.filing import PROCESSED, DocumentChunk, Filing

_WORD = re.compile(r"[a-z0-9]{3,}")
_STOP = {"the", "and", "for", "are", "what", "which", "that", "this", "with", "from", "about", "have", "has",
         "was", "were", "how", "does", "did", "its", "their", "into", "any", "all", "can", "main"}


@dataclass
class Hit:
    chunk_id: int
    filing_id: int
    accession_number: Optional[str]
    form: str
    filing_date: Optional[str]
    document_url: Optional[str]
    page_start: Optional[int]
    page_end: Optional[int]
    section: Optional[str]
    text: str
    score: float


def _terms(query: str) -> List[str]:
    return [w for w in _WORD.findall(query.lower()) if w not in _STOP]


async def search_chunks(
    db: AsyncSession,
    company_id: int,
    query: str,
    limit: int = 8,
    filing_ids: Optional[Sequence[int]] = None,
) -> List[Hit]:
    base_filter = [Filing.company_id == company_id, Filing.processing_status == PROCESSED]
    if filing_ids:
        base_filter.append(Filing.id.in_(list(filing_ids)))

    terms = _terms(query)
    if not terms:
        return []

    dialect = db.bind.dialect.name if db.bind else ""
    if dialect == "postgresql":
        # Natural-language questions: match ANY meaningful word (terms are [a-z0-9] only, so the
        # to_tsquery string is injection-safe) and let ts_rank put passages with more matches first.
        tsq = func.to_tsquery("english", " | ".join(terms))
        vec = func.to_tsvector("english", DocumentChunk.text)
        rank = func.ts_rank(vec, tsq).label("score")
        stmt = (
            select(DocumentChunk, Filing, rank)
            .join(Filing, Filing.id == DocumentChunk.filing_id)
            .where(*base_filter, vec.op("@@")(tsq))
            .order_by(text("score DESC"))
            .limit(limit)
        )
        rows = (await db.execute(stmt)).all()
        return [_hit(c, f, float(s)) for c, f, s in rows]

    stmt = select(DocumentChunk, Filing).join(Filing, Filing.id == DocumentChunk.filing_id).where(*base_filter)
    scored = []
    for c, f in (await db.execute(stmt)).all():
        low = c.text.lower()
        score = sum(low.count(t) for t in terms) + 2 * sum(1 for t in terms if t in (c.section or "").lower())
        if score > 0:
            scored.append((score, c, f))
    scored.sort(key=lambda x: -x[0])
    return [_hit(c, f, float(s)) for s, c, f in scored[:limit]]


def _hit(c: DocumentChunk, f: Filing, score: float) -> Hit:
    return Hit(
        chunk_id=c.id,
        filing_id=f.id,
        accession_number=f.accession_number,
        form=f.filing_type,
        filing_date=f.filing_date.isoformat() if f.filing_date else None,
        document_url=f.document_url,
        page_start=c.page_start,
        page_end=c.page_end,
        section=c.section,
        text=c.text,
        score=score,
    )
