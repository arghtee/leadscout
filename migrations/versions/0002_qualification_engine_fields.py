"""qualification engine fields

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-07 01:52:16.123637
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("business", schema=None) as batch_op:
        batch_op.add_column(sa.Column("company_status", sa.String(length=32), nullable=True))
        batch_op.add_column(sa.Column("incorporated_on", sa.Date(), nullable=True))
        batch_op.add_column(sa.Column("website_live", sa.Boolean(), nullable=True))
        batch_op.add_column(sa.Column("is_chain", sa.Boolean(), nullable=True))
        batch_op.add_column(
            sa.Column("contact_search_at", sa.DateTime(timezone=True), nullable=True)
        )

    with op.batch_alter_table("lead_score", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "stage",
                sa.Enum(
                    "pre_lookup",
                    "final",
                    name="score_stage",
                    native_enum=False,
                    create_constraint=False,
                    length=32,
                ),
                server_default="final",
                nullable=False,
            )
        )
        batch_op.add_column(
            sa.Column(
                "lookup_eligible", sa.Boolean(), server_default=sa.text("false"), nullable=False
            )
        )
        batch_op.add_column(
            sa.Column(
                "rule_results",
                sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
                server_default="[]",
                nullable=False,
            )
        )
        batch_op.create_check_constraint(
            op.f("ck_lead_score_score_stage"), "stage IN ('pre_lookup', 'final')"
        )


def downgrade() -> None:
    with op.batch_alter_table("lead_score", schema=None) as batch_op:
        batch_op.drop_constraint(op.f("ck_lead_score_score_stage"), type_="check")
        batch_op.drop_column("rule_results")
        batch_op.drop_column("lookup_eligible")
        batch_op.drop_column("stage")

    with op.batch_alter_table("business", schema=None) as batch_op:
        batch_op.drop_column("contact_search_at")
        batch_op.drop_column("is_chain")
        batch_op.drop_column("website_live")
        batch_op.drop_column("incorporated_on")
        batch_op.drop_column("company_status")
