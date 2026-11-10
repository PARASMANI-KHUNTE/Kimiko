"""Add hot-path retrieval indexes

Revision ID: b7c9d1e2f3a4
Revises: 904f1b76fdd3
Create Date: 2026-11-10

These composite indexes cover the two queries executed on every chat request:

* memories: WHERE user_id = ? AND is_active ORDER BY importance DESC, created_at DESC
* user_facts: WHERE user_id = ? AND confidence_score >= ? ORDER BY last_seen DESC

Without them PostgreSQL falls back to a per-user sort of every memory/fact row.
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b7c9d1e2f3a4"
down_revision: Union[str, None] = "904f1b76fdd3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "ix_memories_user_active_rank",
        "memories",
        ["user_id", "is_active", "importance", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_user_facts_user_confidence_seen",
        "user_facts",
        ["user_id", "confidence_score", "last_seen"],
        unique=False,
    )
    op.create_index(
        "ix_user_activity_user_time",
        "user_activity",
        ["user_id", "timestamp"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_user_activity_user_time", table_name="user_activity")
    op.drop_index("ix_user_facts_user_confidence_seen", table_name="user_facts")
    op.drop_index("ix_memories_user_active_rank", table_name="memories")
