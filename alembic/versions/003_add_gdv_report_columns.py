"""Add GDV report columns to manual_inputs

Revision ID: 003_add_gdv_report
Revises: 002_add_floorplan
Create Date: 2026-01-14

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

# revision identifiers
revision = '003_add_gdv_report'
down_revision = '002_add_floorplan'
branch_labels = None
depends_on = None


def table_exists(table_name: str) -> bool:
    """Check if a table exists."""
    bind = op.get_bind()
    inspector = inspect(bind)
    return table_name in inspector.get_table_names()


def column_exists(table_name: str, column_name: str) -> bool:
    """Check if a column exists in a table."""
    bind = op.get_bind()
    inspector = inspect(bind)
    if not table_exists(table_name):
        return False
    columns = [col['name'] for col in inspector.get_columns(table_name)]
    return column_name in columns


def upgrade() -> None:
    # Add columns only if they don't exist (makes migration idempotent)
    if not column_exists('manual_inputs', 'gdv_report'):
        op.add_column('manual_inputs', sa.Column('gdv_report', sa.JSON(), nullable=True))
    if not column_exists('manual_inputs', 'gdv_report_generated_at'):
        op.add_column('manual_inputs', sa.Column('gdv_report_generated_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    if column_exists('manual_inputs', 'gdv_report_generated_at'):
        op.drop_column('manual_inputs', 'gdv_report_generated_at')
    if column_exists('manual_inputs', 'gdv_report'):
        op.drop_column('manual_inputs', 'gdv_report')
