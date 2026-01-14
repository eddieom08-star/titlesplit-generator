"""Add archived column to properties

Revision ID: 001_add_archived
Revises:
Create Date: 2024-01-12

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = '001_add_archived'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def column_exists(table_name: str, column_name: str) -> bool:
    """Check if a column exists in a table."""
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = [col['name'] for col in inspector.get_columns(table_name)]
    return column_name in columns


def index_exists(table_name: str, index_name: str) -> bool:
    """Check if an index exists on a table."""
    bind = op.get_bind()
    inspector = inspect(bind)
    indexes = [idx['name'] for idx in inspector.get_indexes(table_name)]
    return index_name in indexes


def upgrade() -> None:
    # Add archived column with default False (only if it doesn't exist)
    if not column_exists('properties', 'archived'):
        op.add_column('properties', sa.Column('archived', sa.Boolean(), nullable=False, server_default='false'))

    if not index_exists('properties', 'ix_properties_archived'):
        op.create_index(op.f('ix_properties_archived'), 'properties', ['archived'], unique=False)


def downgrade() -> None:
    if index_exists('properties', 'ix_properties_archived'):
        op.drop_index(op.f('ix_properties_archived'), table_name='properties')
    if column_exists('properties', 'archived'):
        op.drop_column('properties', 'archived')
