"""
User broker connections — stores OAuth tokens per user per broker.
Each user can connect multiple brokers simultaneously.

Revision ID: 003_user_broker_connections
Revises: 002_order_fills
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '003_user_broker_connections'
down_revision = '002_order_fills'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── users ─────────────────────────────────────────────────
    op.create_table(
        'users',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('uuid_generate_v4()')),
        sa.Column('email',       sa.String(255), nullable=False, unique=True),
        sa.Column('name',        sa.String(255), nullable=True),
        sa.Column('created_at',  sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('last_login',  sa.DateTime(timezone=True), nullable=True),
        sa.Column('is_active',   sa.Boolean, server_default='true'),
    )
    op.create_index('ix_users_email', 'users', ['email'])

    # ── user_broker_connections ────────────────────────────────
    op.create_table(
        'user_broker_connections',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('uuid_generate_v4()')),
        sa.Column('user_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('broker',           sa.String(20),  nullable=False),
        # zerodha | upstox | alpaca | ibkr
        sa.Column('broker_user_id',   sa.String(100), nullable=True),
        sa.Column('broker_user_name', sa.String(255), nullable=True),
        sa.Column('access_token_enc', sa.Text,        nullable=True),
        # AES-256 encrypted; never store plaintext
        sa.Column('refresh_token_enc',sa.Text,        nullable=True),
        sa.Column('token_expiry',     sa.DateTime(timezone=True), nullable=True),
        sa.Column('is_active',        sa.Boolean,     server_default='true'),
        sa.Column('connected_at',     sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
        sa.Column('last_synced',      sa.DateTime(timezone=True), nullable=True),
        sa.Column('metadata',        postgresql.JSONB,
                  server_default=sa.text("'{}'")),
        # stores broker-specific extras (api_key, etc.)
    )
    op.create_index('ix_ubc_user_broker',
                    'user_broker_connections', ['user_id', 'broker'], unique=True)

    # ── portfolio_snapshots ────────────────────────────────────
    # Periodic snapshots of holdings value for analytics / charting
    op.create_table(
        'portfolio_snapshots',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('uuid_generate_v4()')),
        sa.Column('user_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('broker',         sa.String(20),  nullable=False),
        sa.Column('total_value',    sa.Float,        nullable=False),
        sa.Column('cash',           sa.Float,        nullable=False),
        sa.Column('invested_value', sa.Float,        nullable=False),
        sa.Column('day_pnl',        sa.Float,        server_default='0'),
        sa.Column('overall_pnl',    sa.Float,        server_default='0'),
        sa.Column('overall_pnl_pct',sa.Float,        server_default='0'),
        sa.Column('holdings_json',  postgresql.JSONB, server_default=sa.text("'[]'")),
        sa.Column('positions_json', postgresql.JSONB, server_default=sa.text("'[]'")),
        sa.Column('snapped_at',     sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
    )
    op.create_index('ix_ps_user_broker_time',
                    'portfolio_snapshots', ['user_id', 'broker', 'snapped_at'])

    # ── portfolio_alerts ──────────────────────────────────────
    op.create_table(
        'portfolio_alerts',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('uuid_generate_v4()')),
        sa.Column('user_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('broker',       sa.String(20),  nullable=False),
        sa.Column('symbol',       sa.String(50),  nullable=False),
        sa.Column('alert_type',   sa.String(30),  nullable=False),
        # price_above | price_below | pnl_above | pnl_below |
        # circuit_upper | circuit_lower | volume_spike | ai_insight
        sa.Column('threshold',    sa.Float,        nullable=True),
        sa.Column('message',      sa.Text,         nullable=False),
        sa.Column('is_read',      sa.Boolean,      server_default='false'),
        sa.Column('triggered_at', sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
        sa.Column('metadata',    postgresql.JSONB,
                  server_default=sa.text("'{}'")),
    )
    op.create_index('ix_alerts_user_unread',
                    'portfolio_alerts', ['user_id', 'is_read', 'triggered_at'])


def downgrade() -> None:
    op.drop_table('portfolio_alerts')
    op.drop_table('portfolio_snapshots')
    op.drop_table('user_broker_connections')
    op.drop_table('users')
