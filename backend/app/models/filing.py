from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.sql import func

from app.db.base_class import Base

# processing_status values
PENDING = "pending"
PROCESSING = "processing"
PROCESSED = "processed"
FAILED = "failed"
NEEDS_OCR = "needs_ocr"


class Filing(Base):
    __tablename__ = "filings"
    __table_args__ = (UniqueConstraint("provider", "accession_number", name="uq_filing_provider_accession"),)

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False)
    provider = Column(String, nullable=False)  # e.g., sec, nse, bse
    filing_type = Column(String, nullable=False)  # e.g., 10-K, annual_report
    accession_number = Column(String, index=True, nullable=True)
    fiscal_year = Column(Integer, nullable=True)
    fiscal_period = Column(String, nullable=True)  # e.g., FY, Q1
    filing_date = Column(Date, nullable=True)
    period_start = Column(Date, nullable=True)
    period_end = Column(Date, nullable=True)

    source_url = Column(String, nullable=True)
    document_url = Column(String, nullable=True)
    local_storage_path = Column(String, nullable=True)
    document_hash = Column(String, nullable=True)  # sha256 of the original file
    mime_type = Column(String, nullable=True)
    page_count = Column(Integer, nullable=True)
    has_page_numbers = Column(Boolean, default=False)  # false for HTML without page breaks
    needs_ocr = Column(Boolean, default=False)
    extraction_version = Column(Integer, nullable=True)
    processing_status = Column(String, default=PENDING)  # pending, processing, processed, failed, needs_ocr
    error_message = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class DocumentChunk(Base):
    __tablename__ = "document_chunks"

    id = Column(Integer, primary_key=True, index=True)
    filing_id = Column(Integer, ForeignKey("filings.id", ondelete="CASCADE"), nullable=False, index=True)
    chunk_index = Column(Integer, nullable=False)
    text = Column(Text, nullable=False)
    page_start = Column(Integer, nullable=True)
    page_end = Column(Integer, nullable=True)
    section = Column(String, nullable=True)  # e.g. "Item 1A. Risk Factors"
    char_count = Column(Integer, nullable=False)
