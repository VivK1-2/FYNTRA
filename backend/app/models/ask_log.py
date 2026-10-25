from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.sql import func

from app.db.base_class import Base


class AskLog(Base):
    """One row per /ask request, for the admin panel (never used to answer questions)."""

    __tablename__ = "ask_logs"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="SET NULL"), nullable=True)
    ticker = Column(String, index=True, nullable=True)
    question = Column(Text, nullable=False)
    status = Column(String, nullable=False)  # answered | insufficient_evidence | error
    reason = Column(String, nullable=True)
    model = Column(String, nullable=True)
    latency_ms = Column(Integer, nullable=True)
    citation_count = Column(Integer, nullable=False, default=0)
    dropped_sentences = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
