"""ask_logs for the admin panel

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-10-22
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ask_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="SET NULL"), nullable=True),
        sa.Column("ticker", sa.String(), nullable=True),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("reason", sa.String(), nullable=True),
        sa.Column("model", sa.String(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("citation_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("dropped_sentences", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index(op.f("ix_ask_logs_id"), "ask_logs", ["id"])
    op.create_index(op.f("ix_ask_logs_ticker"), "ask_logs", ["ticker"])
    op.create_index(op.f("ix_ask_logs_created_at"), "ask_logs", ["created_at"])


def downgrade() -> None:
    op.drop_index(op.f("ix_ask_logs_created_at"), table_name="ask_logs")
    op.drop_index(op.f("ix_ask_logs_ticker"), table_name="ask_logs")
    op.drop_index(op.f("ix_ask_logs_id"), table_name="ask_logs")
    op.drop_table("ask_logs")
