"""Add archived column to properties

Revision ID: 001_add_archived
Revises:
Create Date: 2024-01-12

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '001_add_archived'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add archived column with default False
    op.add_column('properties', sa.Column('archived', sa.Boolean(), nullable=False, server_default='false'))
    op.create_index(op.f('ix_properties_archived'), 'properties', ['archived'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_properties_archived'), table_name='properties')
    op.drop_column('properties', 'archived')
