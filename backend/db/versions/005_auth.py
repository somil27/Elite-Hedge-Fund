"""Add hashed_password to users

Revision ID: 005_auth
Revises: 004_phase12
Create Date: 2026-07-29 16:30:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '005_auth'
down_revision = '004_phase12'
branch_labels = None
depends_on = None


def upgrade():
    # We add nullable=True initially so we can populate existing users, then we'll alter it to nullable=False
    op.add_column('users', sa.Column('hashed_password', sa.String(length=255), nullable=True))
    
    # We need a default password for existing users. The hash of 'password' is:
    # $2b$12$EixZaYVK1fsbw1ZfbX3OXePaWxn96p36WQoeG6Lruj3vjIQG8INj6
    op.execute("UPDATE users SET hashed_password = '$2b$12$EixZaYVK1fsbw1ZfbX3OXePaWxn96p36WQoeG6Lruj3vjIQG8INj6' WHERE hashed_password IS NULL")
    
    op.alter_column('users', 'hashed_password', nullable=False)


def downgrade():
    op.drop_column('users', 'hashed_password')
