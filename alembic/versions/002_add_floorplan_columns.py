"""Add floorplan analysis columns to manual_inputs

Revision ID: 002_add_floorplan
Revises: 001_add_archived
Create Date: 2026-01-13

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

# revision identifiers
revision = '002_add_floorplan'
down_revision = '001_add_archived'
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
    # Create manual_inputs table if it doesn't exist
    if not table_exists('manual_inputs'):
        op.create_table(
            'manual_inputs',
            sa.Column('id', sa.UUID(), primary_key=True),
            sa.Column('property_id', sa.UUID(), sa.ForeignKey('properties.id'), nullable=False, index=True),
            sa.Column('verified_tenure', sa.String(50), nullable=True),
            sa.Column('title_number', sa.String(50), nullable=True),
            sa.Column('is_single_title', sa.Boolean(), nullable=True),
            sa.Column('title_verified_date', sa.DateTime(), nullable=True),
            sa.Column('title_notes', sa.Text(), nullable=True),
            sa.Column('verified_units', sa.Integer(), nullable=True),
            sa.Column('unit_breakdown', sa.JSON(), nullable=True),
            sa.Column('units_verified_date', sa.DateTime(), nullable=True),
            sa.Column('planning_checked', sa.Boolean(), default=False),
            sa.Column('planning_applications', sa.JSON(), nullable=True),
            sa.Column('planning_constraints', sa.JSON(), nullable=True),
            sa.Column('planning_notes', sa.Text(), nullable=True),
            sa.Column('hmo_license_required', sa.Boolean(), nullable=True),
            sa.Column('hmo_license_status', sa.String(50), nullable=True),
            sa.Column('additional_licensing', sa.JSON(), nullable=True),
            sa.Column('site_visited', sa.Boolean(), default=False),
            sa.Column('site_visit_date', sa.DateTime(), nullable=True),
            sa.Column('condition_rating', sa.String(20), nullable=True),
            sa.Column('access_issues', sa.Text(), nullable=True),
            sa.Column('structural_concerns', sa.Text(), nullable=True),
            sa.Column('floorplan_base64', sa.Text(), nullable=True),
            sa.Column('floorplan_filename', sa.String(255), nullable=True),
            sa.Column('floorplan_analysis', sa.JSON(), nullable=True),
            sa.Column('floorplan_analyzed_at', sa.DateTime(), nullable=True),
            sa.Column('revised_asking_price', sa.Integer(), nullable=True),
            sa.Column('additional_costs_identified', sa.JSON(), nullable=True),
            sa.Column('negotiation_notes', sa.Text(), nullable=True),
            sa.Column('blockers', sa.JSON(), nullable=True),
            sa.Column('deal_status', sa.String(50), default='active'),
            sa.Column('created_at', sa.DateTime(), default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(), default=sa.func.now(), onupdate=sa.func.now()),
        )
        return  # Table created with all columns, no need to add individually
    # Add columns only if they don't exist (makes migration idempotent)
    if not column_exists('manual_inputs', 'floorplan_base64'):
        op.add_column('manual_inputs', sa.Column('floorplan_base64', sa.Text(), nullable=True))
    if not column_exists('manual_inputs', 'floorplan_filename'):
        op.add_column('manual_inputs', sa.Column('floorplan_filename', sa.String(255), nullable=True))
    if not column_exists('manual_inputs', 'floorplan_analysis'):
        op.add_column('manual_inputs', sa.Column('floorplan_analysis', sa.JSON(), nullable=True))
    if not column_exists('manual_inputs', 'floorplan_analyzed_at'):
        op.add_column('manual_inputs', sa.Column('floorplan_analyzed_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    if column_exists('manual_inputs', 'floorplan_analyzed_at'):
        op.drop_column('manual_inputs', 'floorplan_analyzed_at')
    if column_exists('manual_inputs', 'floorplan_analysis'):
        op.drop_column('manual_inputs', 'floorplan_analysis')
    if column_exists('manual_inputs', 'floorplan_filename'):
        op.drop_column('manual_inputs', 'floorplan_filename')
    if column_exists('manual_inputs', 'floorplan_base64'):
        op.drop_column('manual_inputs', 'floorplan_base64')
