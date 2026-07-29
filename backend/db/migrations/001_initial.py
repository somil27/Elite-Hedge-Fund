"""Initial schema: trade_cycles, agent_memories, trade_outcomes, human_reviews

Revision ID: 001_initial
Revises:
Create Date: 2025-01-01 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '001_initial'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Enable pgvector extension
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE EXTENSION IF NOT EXISTS \"uuid-ossp\"")

    # trade_cycles
    op.create_table(
        'trade_cycles',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('uuid_generate_v4()')),
        sa.Column('mode', sa.String(20), nullable=False),
        sa.Column('status', sa.String(30), nullable=False, server_default='running'),
        sa.Column('cio_mandate', postgresql.JSONB, nullable=False),
        sa.Column('auto_mode', sa.Boolean, server_default='false'),
        sa.Column('started_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    )

    # agent_memories with pgvector column
    op.create_table(
        'agent_memories',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('uuid_generate_v4()')),
        sa.Column('agent_id', sa.String(50), nullable=False),
        sa.Column('cycle_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('trade_cycles.id'), nullable=True),
        sa.Column('memory_type', sa.String(20), nullable=False),
        sa.Column('content', sa.Text, nullable=False),
        sa.Column('importance_score', sa.Float, server_default='0.5'),
        sa.Column('metadata', postgresql.JSONB, server_default='{}'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
    )

    # Add pgvector column separately (1536 dims for text-embedding-3-small)
    op.execute("ALTER TABLE agent_memories ADD COLUMN embedding vector(1536)")

    # Vector similarity index (IVFFlat for cosine distance)
    op.execute("""
        CREATE INDEX agent_memories_embedding_idx
        ON agent_memories
        USING ivfflat (embedding vector_cosine_ops)
        WITH (lists = 100)
    """)

    # Regular indexes
    op.create_index('ix_agent_memories_agent_type',
                    'agent_memories', ['agent_id', 'memory_type'])
    op.create_index('ix_agent_memories_created',
                    'agent_memories', ['created_at'])

    # trade_outcomes
    op.create_table(
        'trade_outcomes',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('uuid_generate_v4()')),
        sa.Column('cycle_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('trade_cycles.id'), nullable=False),
        sa.Column('symbol', sa.String(20), nullable=False),
        sa.Column('direction', sa.String(10), nullable=False),
        sa.Column('entry_price', sa.Float, nullable=False),
        sa.Column('exit_price', sa.Float, nullable=True),
        sa.Column('qty', sa.Float, nullable=False),
        sa.Column('pnl_realized', sa.Float, nullable=True),
        sa.Column('pnl_pct', sa.Float, nullable=True),
        sa.Column('agent_signals', postgresql.JSONB, nullable=False),
        sa.Column('human_decision', sa.String(20), nullable=True),
        sa.Column('close_reason', sa.String(50), nullable=True),
        sa.Column('opened_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('closed_at', sa.DateTime(timezone=True), nullable=True),
    )

    # human_reviews
    op.create_table(
        'human_reviews',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('uuid_generate_v4()')),
        sa.Column('cycle_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('trade_cycles.id'), nullable=False),
        sa.Column('proposal_data', postgresql.JSONB, nullable=False),
        sa.Column('technical_data', postgresql.JSONB, nullable=False),
        sa.Column('risk_data', postgresql.JSONB, nullable=False),
        sa.Column('estimated_notional', sa.Float, nullable=False),
        sa.Column('status', sa.String(20), server_default='pending'),
        sa.Column('decision', sa.String(20), nullable=True),
        sa.Column('override_weight', sa.Float, nullable=True),
        sa.Column('notes', sa.Text, nullable=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('decided_at', sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table('human_reviews')
    op.drop_table('trade_outcomes')
    op.drop_table('agent_memories')
    op.drop_table('trade_cycles')
    op.execute("DROP EXTENSION IF EXISTS vector")
