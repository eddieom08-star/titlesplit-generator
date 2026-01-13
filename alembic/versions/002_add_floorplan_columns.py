"""Add floorplan analysis columns to manual_inputs

Revision ID: 002
Revises: 001
Create Date: 2026-01-13

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = '002'
down_revision = '001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('manual_inputs', sa.Column('floorplan_base64', sa.Text(), nullable=True))
    op.add_column('manual_inputs', sa.Column('floorplan_filename', sa.String(255), nullable=True))
    op.add_column('manual_inputs', sa.Column('floorplan_analysis', sa.JSON(), nullable=True))
    op.add_column('manual_inputs', sa.Column('floorplan_analyzed_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column('manual_inputs', 'floorplan_analyzed_at')
    op.drop_column('manual_inputs', 'floorplan_analysis')
    op.drop_column('manual_inputs', 'floorplan_filename')
    op.drop_column('manual_inputs', 'floorplan_base64')
