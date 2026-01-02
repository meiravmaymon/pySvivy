"""add municipality support

Revision ID: 28fe9f6fc312
Revises: 
Create Date: 2026-01-02 12:13:45.714963

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '28fe9f6fc312'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade database schema - Add municipality support."""
    # Create municipalities table
    op.create_table('municipalities',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('semel', sa.String(length=10), nullable=True),
        sa.Column('name_he', sa.String(length=200), nullable=False),
        sa.Column('name_en', sa.String(length=200), nullable=True),
        sa.Column('municipality_type', sa.String(length=50), nullable=True),
        sa.Column('region', sa.String(length=100), nullable=True),
        sa.Column('created_date', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('municipalities', schema=None) as batch_op:
        batch_op.create_index('ix_municipalities_name_he', ['name_he'], unique=False)
        batch_op.create_index('ix_municipalities_semel', ['semel'], unique=True)

    # Add municipality_id to boards
    with op.batch_alter_table('boards', schema=None) as batch_op:
        batch_op.add_column(sa.Column('municipality_id', sa.Integer(), nullable=True))

    # Add municipality_id to meetings
    with op.batch_alter_table('meetings', schema=None) as batch_op:
        batch_op.add_column(sa.Column('municipality_id', sa.Integer(), nullable=True))

    # Add municipality_id to persons
    with op.batch_alter_table('persons', schema=None) as batch_op:
        batch_op.add_column(sa.Column('municipality_id', sa.Integer(), nullable=True))

    # Add municipality_id to terms
    with op.batch_alter_table('terms', schema=None) as batch_op:
        batch_op.add_column(sa.Column('municipality_id', sa.Integer(), nullable=True))


def downgrade() -> None:
    """Downgrade database schema - Remove municipality support."""
    # Remove municipality_id from terms
    with op.batch_alter_table('terms', schema=None) as batch_op:
        batch_op.drop_column('municipality_id')

    # Remove municipality_id from persons
    with op.batch_alter_table('persons', schema=None) as batch_op:
        batch_op.drop_column('municipality_id')

    # Remove municipality_id from meetings
    with op.batch_alter_table('meetings', schema=None) as batch_op:
        batch_op.drop_column('municipality_id')

    # Remove municipality_id from boards
    with op.batch_alter_table('boards', schema=None) as batch_op:
        batch_op.drop_column('municipality_id')

    # Drop municipalities table
    with op.batch_alter_table('municipalities', schema=None) as batch_op:
        batch_op.drop_index('ix_municipalities_semel')
        batch_op.drop_index('ix_municipalities_name_he')
    op.drop_table('municipalities')
