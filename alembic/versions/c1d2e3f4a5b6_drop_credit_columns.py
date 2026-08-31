"""drop user credit columns and credit_payments table

Revision ID: c1d2e3f4a5b6
Revises: b914be4aa46d
Create Date: 2026-08-30 22:55:00.000000

Removes the credit-related fields from the users table and drops the
credit_payments table. The backend credit module (credit_service,
credit_payment_service, CreditPayment model, CreditPaymentResponse schema)
was removed; the frontend no longer references these endpoints.

This migration is idempotent: it inspects the database before dropping
columns / tables so it is safe to run on databases that were created
before the credit module was introduced and never had those objects.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c1d2e3f4a5b6'
down_revision: Union[str, Sequence[str], None] = 'b914be4aa46d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return any(c["name"] == column_name for c in inspector.get_columns(table_name))


def _has_table(table_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def upgrade() -> None:
    """Drop user credit columns and credit_payments table if they exist."""
    # Drop FKs from credit_payments first if table exists (some DBs require it).
    if _has_table("credit_payments"):
        # Best-effort: drop FK constraints explicitly to avoid surprises on
        # databases where the table was added manually outside Alembic.
        try:
            op.drop_table("credit_payments")
        except Exception:
            # Fallback: try to drop the foreign keys then the table.
            try:
                op.drop_constraint(
                    "fk_credit_payments_user_id_users", "credit_payments", type_="foreignkey"
                )
            except Exception:
                pass
            op.drop_table("credit_payments")

    for col in ("available_credit", "credit_limit", "credit_status"):
        if _has_column("users", col):
            op.drop_column("users", col)


def downgrade() -> None:
    """Recreate credit columns and credit_payments table."""
    op.add_column(
        "users",
        sa.Column(
            "available_credit",
            sa.Numeric(10, 2),
            nullable=False,
            server_default="0.00",
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "credit_limit",
            sa.Numeric(10, 2),
            nullable=False,
            server_default="0.00",
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "credit_status",
            sa.String(),
            nullable=False,
            server_default="active",
        ),
    )
    op.create_table(
        "credit_payments",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("order_id", sa.String(), nullable=True),
        sa.Column("amount", sa.Numeric(10, 2), nullable=False),
        sa.Column("currency", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("payment_method", sa.String(), nullable=True),
        sa.Column("reference_number", sa.String(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("approved_by", sa.String(), nullable=True),
        sa.Column("approved_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )