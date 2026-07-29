"""
Add order_fills table for granular fill tracking.

Revision ID: 002_order_fills
Revises: 001_initial
Create Date: 2025-01-02 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '002_order_fills'
down_revision = '001_initial'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── broker_orders ──────────────────────────────────────────
    # Records every order submitted to the broker (agent + manual)
    op.create_table(
        'broker_orders',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('uuid_generate_v4()')),
        sa.Column('broker_order_id', sa.String(100), nullable=False, unique=True),
        sa.Column('cycle_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('trade_cycles.id', ondelete='SET NULL'),
                  nullable=True),
        sa.Column('symbol', sa.String(20), nullable=False),
        sa.Column('side', sa.String(10), nullable=False),           # buy | sell
        sa.Column('order_type', sa.String(20), nullable=False),     # market | limit | stop
        sa.Column('qty', sa.Float, nullable=False),
        sa.Column('filled_qty', sa.Float, server_default='0'),
        sa.Column('limit_price', sa.Float, nullable=True),
        sa.Column('stop_price', sa.Float, nullable=True),
        sa.Column('avg_fill_price', sa.Float, nullable=True),
        sa.Column('status', sa.String(20), server_default='pending'),
        sa.Column('algo', sa.String(20), nullable=True),            # vwap | twap | aggressive
        sa.Column('slippage_bps', sa.Float, nullable=True),
        sa.Column('source', sa.String(20), server_default='agent'), # agent | manual | stop_loss
        sa.Column('time_in_force', sa.String(10), server_default='day'),
        sa.Column('reject_reason', sa.Text, nullable=True),
        sa.Column('submitted_at', sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
        sa.Column('filled_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('cancelled_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_broker_orders_symbol',  'broker_orders', ['symbol'])
    op.create_index('ix_broker_orders_status',  'broker_orders', ['status'])
    op.create_index('ix_broker_orders_cycle',   'broker_orders', ['cycle_id'])
    op.create_index('ix_broker_orders_submitted', 'broker_orders', ['submitted_at'])

    # ── order_fills ────────────────────────────────────────────
    # Individual fill events (partial fills, multiple fills per order)
    op.create_table(
        'order_fills',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('uuid_generate_v4()')),
        sa.Column('broker_order_id', sa.String(100),
                  sa.ForeignKey('broker_orders.broker_order_id', ondelete='CASCADE'),
                  nullable=False),
        sa.Column('fill_id', sa.String(100), nullable=False, unique=True),
        sa.Column('symbol', sa.String(20), nullable=False),
        sa.Column('side', sa.String(10), nullable=False),
        sa.Column('qty', sa.Float, nullable=False),
        sa.Column('price', sa.Float, nullable=False),
        sa.Column('commission', sa.Float, server_default='0'),
        sa.Column('filled_at', sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
    )
    op.create_index('ix_order_fills_order',  'order_fills', ['broker_order_id'])
    op.create_index('ix_order_fills_symbol', 'order_fills', ['symbol'])
    op.create_index('ix_order_fills_filled', 'order_fills', ['filled_at'])


def downgrade() -> None:
    op.drop_table('order_fills')
    op.drop_table('broker_orders')
