"""Document pipeline: filing metadata columns + document_chunks

Revision ID: a1b2c3d4e5f6
Revises: 3391330e6227
Create Date: 2026-10-11
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "3391330e6227"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("filings", sa.Column("accession_number", sa.String(), nullable=True))
    op.add_column("filings", sa.Column("mime_type", sa.String(), nullable=True))
    op.add_column("filings", sa.Column("page_count", sa.Integer(), nullable=True))
    op.add_column("filings", sa.Column("has_page_numbers", sa.Boolean(), server_default=sa.false()))
    op.add_column("filings", sa.Column("needs_ocr", sa.Boolean(), server_default=sa.false()))
    op.add_column("filings", sa.Column("extraction_version", sa.Integer(), nullable=True))
    op.add_column("filings", sa.Column("error_message", sa.Text(), nullable=True))
    op.create_index(op.f("ix_filings_accession_number"), "filings", ["accession_number"])
    op.create_unique_constraint("uq_filing_provider_accession", "filings", ["provider", "accession_number"])

    op.create_table(
        "document_chunks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("filing_id", sa.Integer(), sa.ForeignKey("filings.id", ondelete="CASCADE"), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("page_start", sa.Integer(), nullable=True),
        sa.Column("page_end", sa.Integer(), nullable=True),
        sa.Column("section", sa.String(), nullable=True),
        sa.Column("char_count", sa.Integer(), nullable=False),
    )
    op.create_index(op.f("ix_document_chunks_id"), "document_chunks", ["id"])
    op.create_index(op.f("ix_document_chunks_filing_id"), "document_chunks", ["filing_id"])

    # Postgres full-text search index (GIN). Skipped on other dialects (tests use SQLite).
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            "CREATE INDEX ix_document_chunks_fts ON document_chunks "
            "USING gin (to_tsvector('english', text))"
        )


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP INDEX IF EXISTS ix_document_chunks_fts")
    op.drop_index(op.f("ix_document_chunks_filing_id"), table_name="document_chunks")
    op.drop_index(op.f("ix_document_chunks_id"), table_name="document_chunks")
    op.drop_table("document_chunks")
    op.drop_constraint("uq_filing_provider_accession", "filings", type_="unique")
    op.drop_index(op.f("ix_filings_accession_number"), table_name="filings")
    for col in ("error_message", "extraction_version", "needs_ocr", "has_page_numbers", "page_count",
                "mime_type", "accession_number"):
        op.drop_column("filings", col)
