"""
Phase 1 + 2 DB Migration
Adds:
  - rl_signal_weights      — UCB1 bandit state for RL optimiser
  - backtest_results       — stored backtest runs with metrics
  - backtest_trades        — individual trades from backtests
  - portfolio_definitions  — multi-portfolio configurations
  - news_events            — significant news events cache

Revision ID: 004_phase12
Revises: 003_user_broker_connections
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision      = "004_phase12"
down_revision = "003_user_broker_connections"
branch_labels = None
depends_on    = None


def upgrade() -> None:

    # ── rl_signal_weights ──────────────────────────────────────
    # Stores the UCB1 bandit state for each agent signal
    op.create_table(
        "rl_signal_weights",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("uuid_generate_v4()")),
        sa.Column("signal_key",   sa.String(60),  nullable=False),
        # quant_score|fundamental_score|technical_score|news_score|macro_score|options_flow_score
        sa.Column("market",       sa.String(20),  nullable=False, server_default="us"),
        sa.Column("weight",       sa.Float,        nullable=False, server_default="0.167"),
        sa.Column("total_reward", sa.Float,        nullable=False, server_default="0.0"),
        sa.Column("pull_count",   sa.Integer,      nullable=False, server_default="0"),
        sa.Column("last_updated", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at",   sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
        sa.UniqueConstraint("signal_key", "market", name="uq_rl_signal_market"),
    )

    # ── backtest_results ───────────────────────────────────────
    op.create_table(
        "backtest_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("uuid_generate_v4()")),
        sa.Column("strategy",         sa.String(50),    nullable=False),
        sa.Column("symbols",          postgresql.JSONB,  nullable=False),
        sa.Column("start_date",       sa.String(10),    nullable=False),
        sa.Column("end_date",         sa.String(10),    nullable=False),
        sa.Column("mode",             sa.String(20),    nullable=False),
        sa.Column("market",           sa.String(20),    nullable=False),
        sa.Column("initial_capital",  sa.Float,          nullable=False),
        sa.Column("final_capital",    sa.Float,          nullable=False),
        sa.Column("total_return_pct", sa.Float,          nullable=True),
        sa.Column("annualised_return",sa.Float,          nullable=True),
        sa.Column("sharpe_ratio",     sa.Float,          nullable=True),
        sa.Column("max_drawdown_pct", sa.Float,          nullable=True),
        sa.Column("win_rate",         sa.Float,          nullable=True),
        sa.Column("profit_factor",    sa.Float,          nullable=True),
        sa.Column("total_trades",     sa.Integer,        nullable=True),
        sa.Column("avg_hold_days",    sa.Float,          nullable=True),
        sa.Column("equity_curve",     postgresql.JSONB,  server_default=sa.text("'[]'")),
        sa.Column("agent_attribution",postgresql.JSONB,  server_default=sa.text("'{}'")),
        sa.Column("walkforward",      postgresql.JSONB,  server_default=sa.text("'[]'")),
        sa.Column("run_by",           sa.String(100),   nullable=True),
        sa.Column("created_at",       sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
    )
    op.create_index("ix_bt_strategy", "backtest_results", ["strategy"])
    op.create_index("ix_bt_created",  "backtest_results", ["created_at"])

    # ── backtest_trades ────────────────────────────────────────
    op.create_table(
        "backtest_trades",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("uuid_generate_v4()")),
        sa.Column("backtest_id",   postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("backtest_results.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("symbol",        sa.String(20),    nullable=False),
        sa.Column("direction",     sa.String(10),    nullable=False),
        sa.Column("entry_date",    sa.String(10),    nullable=False),
        sa.Column("exit_date",     sa.String(10),    nullable=True),
        sa.Column("entry_price",   sa.Float,          nullable=False),
        sa.Column("exit_price",    sa.Float,          nullable=True),
        sa.Column("qty",           sa.Float,          nullable=False),
        sa.Column("pnl",           sa.Float,          server_default="0"),
        sa.Column("pnl_pct",       sa.Float,          server_default="0"),
        sa.Column("hold_days",     sa.Integer,        server_default="0"),
        sa.Column("exit_reason",   sa.String(50),    nullable=True),
        sa.Column("agent_signals", postgresql.JSONB,  server_default=sa.text("'{}'")),
        sa.Column("composite_score",sa.Float,         server_default="0"),
    )
    op.create_index("ix_btt_backtest", "backtest_trades", ["backtest_id"])
    op.create_index("ix_btt_symbol",   "backtest_trades", ["symbol"])

    # ── portfolio_definitions ──────────────────────────────────
    op.create_table(
        "portfolio_definitions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("uuid_generate_v4()")),
        sa.Column("portfolio_id",    sa.String(50),  nullable=False, unique=True),
        sa.Column("user_id",         postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=True),
        sa.Column("name",            sa.String(100), nullable=False),
        sa.Column("strategy",        sa.String(50),  nullable=False),
        sa.Column("allocation_pct",  sa.Float,        nullable=False),
        sa.Column("mode",            sa.String(20),  nullable=False),
        sa.Column("market",          sa.String(20),  nullable=False),
        sa.Column("auto_mode",       sa.Boolean,      server_default="false"),
        sa.Column("active",          sa.Boolean,      server_default="true"),
        sa.Column("description",     sa.Text,         nullable=True),
        sa.Column("max_drawdown_pct",sa.Float,        server_default="10.0"),
        sa.Column("created_at",      sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
        sa.Column("updated_at",      sa.DateTime(timezone=True), nullable=True),
    )

    # ── news_events ────────────────────────────────────────────
    op.create_table(
        "news_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("uuid_generate_v4()")),
        sa.Column("cycle_id",      postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("trade_cycles.id", ondelete="SET NULL"),
                  nullable=True),
        sa.Column("symbol",        sa.String(20),  nullable=True),
        sa.Column("event_type",    sa.String(50),  nullable=False),
        sa.Column("headline",      sa.Text,         nullable=False),
        sa.Column("sentiment",     sa.Float,         nullable=True),
        sa.Column("magnitude",     sa.String(10),  nullable=True),
        sa.Column("source",        sa.String(100), nullable=True),
        sa.Column("metadata",      postgresql.JSONB,
                  server_default=sa.text("'{}'")),
        sa.Column("event_time",    sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
    )
    op.create_index("ix_news_symbol",  "news_events", ["symbol"])
    op.create_index("ix_news_type",    "news_events", ["event_type"])
    op.create_index("ix_news_time",    "news_events", ["event_time"])


def downgrade() -> None:
    op.drop_table("news_events")
    op.drop_table("portfolio_definitions")
    op.drop_table("backtest_trades")
    op.drop_table("backtest_results")
    op.drop_table("rl_signal_weights")
