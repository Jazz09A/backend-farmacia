"""add performance indexes

Revision ID: a1b2c3d4e5f6
Revises: b914be4aa46d
Create Date: 2026-08-29 19:50:00.000000

"""
from typing import Sequence, Union
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = 'b914be4aa46d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add performance indexes (idempotent via IF NOT EXISTS)."""
    conn = op.get_bind()

    # Cart: índice compuesto para detección de duplicados
    op.create_index(
        'idx_cart_user_product_pres',
        'cart_items',
        ['user_id', 'product_id', 'selected_presentation'],
        unique=False,
    )

    # Blog: índice parcial para listado público (solo publicados y no eliminados)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_blog_post_published_partial
        ON blog_posts (published_at DESC)
        WHERE status = 'published' AND deleted = false
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_blog_post_published_partial")
    op.drop_index('idx_cart_user_product_pres', table_name='cart_items')
