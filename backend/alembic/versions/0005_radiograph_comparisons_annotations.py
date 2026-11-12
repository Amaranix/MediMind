"""radiograph comparisons and annotations (F-C6, F-C7)

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-12 13:30:00
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '0005'
down_revision: str | None = '0004'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSON = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql')


def upgrade() -> None:
    op.add_column('imaging', sa.Column('annotations', JSON, nullable=False, server_default=sa.text("'[]'")))
    op.create_table(
        'radiograph_comparisons',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('patient_id', sa.Uuid(), nullable=False),
        sa.Column('document_a_id', sa.Uuid(), nullable=False),
        sa.Column('document_b_id', sa.Uuid(), nullable=False),
        sa.Column('qualification', sa.String(length=20), nullable=False),
        sa.Column('comment', sa.Text(), nullable=True),
        sa.Column('created_by', sa.Uuid(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['patient_id'], ['patients.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['document_a_id'], ['documents.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['document_b_id'], ['documents.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['created_by'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('document_a_id', 'document_b_id'),
    )
    op.create_index(op.f('ix_radiograph_comparisons_patient_id'), 'radiograph_comparisons', ['patient_id'])


def downgrade() -> None:
    op.drop_index(op.f('ix_radiograph_comparisons_patient_id'), table_name='radiograph_comparisons')
    op.drop_table('radiograph_comparisons')
    op.drop_column('imaging', 'annotations')
