"""add faction municipality support

Revision ID: 50f98cb60f30
Revises: 28fe9f6fc312
Create Date: 2026-01-02 12:37:47.774796

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '50f98cb60f30'
down_revision: Union[str, None] = '28fe9f6fc312'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade database schema - Add faction municipality support."""
    # Add faction_type column to factions
    with op.batch_alter_table('factions', schema=None) as batch_op:
        batch_op.add_column(sa.Column('faction_type', sa.String(length=20), nullable=True))
        batch_op.add_column(sa.Column('municipality_id', sa.Integer(), nullable=True))

    # Set default faction_type to 'national' for existing factions
    op.execute("UPDATE factions SET faction_type = 'national' WHERE faction_type IS NULL")


def downgrade() -> None:
    """Downgrade database schema - Remove faction municipality support."""
    with op.batch_alter_table('factions', schema=None) as batch_op:
        batch_op.drop_column('municipality_id')
        batch_op.drop_column('faction_type')
