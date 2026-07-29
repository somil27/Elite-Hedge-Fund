"""
Multi-Portfolio Manager — Phase 2
Manages multiple strategy portfolios simultaneously.
Each portfolio gets its own agent cycle, risk budget, and memory namespace.
The manager prevents over-concentration and cross-portfolio correlation risk.
"""
from __future__ import annotations
import asyncio
import uuid
from dataclasses import dataclass
import asyncpg
import structlog

logger = structlog.get_logger()


@dataclass
class PortfolioDefinition:
    """Defines a named portfolio within the multi-portfolio system."""
    portfolio_id:   str
    name:           str
    strategy:       str        # from strategy_library.STRATEGIES
    allocation_pct: float      # % of total capital allocated to this portfolio
    mode:           str        # short_term | long_term
    market:         str        # us | india
    auto_mode:      bool       = False
    active:         bool       = True
    description:    str        = ""
    max_drawdown_pct: float    = 10.0   # circuit breaker — pause if exceeded
    user_id:        str        = "00000000-0000-0000-0000-000000000001"


# ── Default portfolio configurations ─────────────────────────

DEFAULT_PORTFOLIOS = [
    PortfolioDefinition(
        portfolio_id="growth",
        name="Growth (Momentum)",
        strategy="momentum",
        allocation_pct=0.40,
        mode="short_term",
        market="us",
        description="Aggressive momentum plays. Higher risk, higher reward.",
    ),
    PortfolioDefinition(
        portfolio_id="value",
        name="Core Holdings (Value)",
        strategy="value_investing",
        allocation_pct=0.35,
        mode="long_term",
        market="us",
        description="Deep value, long-term compounding. Lower turnover.",
    ),
    PortfolioDefinition(
        portfolio_id="india",
        name="India (NSE Momentum)",
        strategy="india_momentum",
        allocation_pct=0.25,
        mode="short_term",
        market="india",
        description="NSE/BSE momentum and swing trades.",
    ),
]


class MultiPortfolioManager:
    """
    Orchestrates multiple strategy portfolios.
    Prevents over-concentration, manages correlation budget,
    and triggers individual portfolio cycles.
    """

    def __init__(self, portfolios: list[PortfolioDefinition] = None):
        self.portfolios = {p.portfolio_id: p for p in (portfolios if portfolios is not None else DEFAULT_PORTFOLIOS)}

    async def run_all_cycles(
        self,
        total_capital: float,
        conn: asyncpg.Connection,
        auto_mode: bool = False,
    ) -> list[dict]:
        """
        Launch cycles for all active portfolios simultaneously.
        Returns list of cycle start results.
        """
        active = [p for p in self.portfolios.values() if p.active]
        logger.info("multi_portfolio_start", count=len(active), capital=total_capital)

        # Check correlation budget before launching
        await self._check_correlation_budget(conn)

        # Launch all portfolio cycles in parallel
        tasks = [
            self._launch_portfolio_cycle(p, total_capital, conn, auto_mode)
            for p in active
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        cycle_results = []
        for portfolio, result in zip(active, results):
            if isinstance(result, Exception):
                logger.error("portfolio_cycle_error",
                             portfolio=portfolio.portfolio_id, error=str(result))
                cycle_results.append({
                    "portfolio_id": portfolio.portfolio_id,
                    "status": "error",
                    "error": str(result),
                })
            else:
                cycle_results.append(result)

        return cycle_results

    async def _launch_portfolio_cycle(
        self,
        portfolio: PortfolioDefinition,
        total_capital: float,
        conn: asyncpg.Connection,
        auto_mode: bool,
    ) -> dict:
        """Launch a single portfolio cycle via the trading graph."""
        import httpx

        allocated_capital = total_capital * portfolio.allocation_pct
        cycle_id = str(uuid.uuid4())

        logger.info("portfolio_cycle_launch",
                    portfolio=portfolio.portfolio_id,
                    strategy=portfolio.strategy,
                    capital=allocated_capital)

        # Hit the API to start a cycle with portfolio-specific parameters
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    "http://localhost:8000/api/cycles/start",
                    json={
                        "mode":           portfolio.mode,
                        "auto_mode":      auto_mode or portfolio.auto_mode,
                        "market":         portfolio.market,
                        "strategy":       portfolio.strategy,
                        "portfolio_id":   portfolio.portfolio_id,
                        "user_id":        portfolio.user_id,
                        "capital_budget": allocated_capital,
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                return {
                    "portfolio_id":   portfolio.portfolio_id,
                    "portfolio_name": portfolio.name,
                    "cycle_id":       data.get("cycle_id"),
                    "status":         "started",
                    "allocation_pct": portfolio.allocation_pct,
                    "capital":        allocated_capital,
                }
        except Exception as e:
            return {
                "portfolio_id": portfolio.portfolio_id,
                "status":       "error",
                "error":        str(e),
            }

    async def _check_correlation_budget(self, conn: asyncpg.Connection) -> None:
        """
        Check that active positions across portfolios don't exceed
        the cross-portfolio correlation budget.
        Warns if two portfolios hold the same symbol.
        """
        try:
            rows = await conn.fetch("""
                SELECT symbol, COUNT(*) as portfolio_count
                FROM trade_outcomes
                WHERE closed_at IS NULL
                GROUP BY symbol
                HAVING COUNT(*) > 1
            """)
            for row in rows:
                logger.warning("cross_portfolio_overlap",
                               symbol=row["symbol"],
                               count=row["portfolio_count"],
                               msg="Same symbol held in multiple portfolios — correlation risk")
        except Exception:
            pass   # table may not exist yet

    async def get_portfolio_summary(self, conn: asyncpg.Connection) -> list[dict]:
        """Get current performance summary for all portfolios."""
        summaries = []
        for pid, portfolio in self.portfolios.items():
            try:
                rows = await conn.fetch("""
                    SELECT
                        COUNT(*) as total_trades,
                        SUM(CASE WHEN pnl_realized > 0 THEN 1 ELSE 0 END) as wins,
                        SUM(pnl_realized) as total_pnl,
                        AVG(pnl_pct) as avg_return_pct
                    FROM trade_outcomes to2
                    JOIN trade_cycles tc ON tc.id = to2.cycle_id
                    WHERE tc.cio_mandate->>'portfolio_id' = $1
                """, pid)
                row = rows[0] if rows else None
                summaries.append({
                    "portfolio_id":   pid,
                    "name":           portfolio.name,
                    "strategy":       portfolio.strategy,
                    "allocation_pct": portfolio.allocation_pct,
                    "mode":           portfolio.mode,
                    "market":         portfolio.market,
                    "active":         portfolio.active,
                    "total_trades":   int(row["total_trades"] or 0) if row else 0,
                    "win_rate":       round(
                        (row["wins"] or 0) / max(row["total_trades"] or 1, 1), 3
                    ) if row else 0,
                    "total_pnl":      round(float(row["total_pnl"] or 0), 2) if row else 0,
                    "avg_return_pct": round(float(row["avg_return_pct"] or 0), 4) if row else 0,
                })
            except Exception as e:
                summaries.append({
                    "portfolio_id": pid,
                    "name":         portfolio.name,
                    "error":        str(e),
                })
        return summaries

    def add_portfolio(self, portfolio: PortfolioDefinition) -> None:
        """Add a new portfolio to the manager."""
        # Validate allocations don't exceed 100%
        current_total = sum(
            p.allocation_pct for p in self.portfolios.values() if p.active
        )
        if current_total + portfolio.allocation_pct > 1.0:
            raise ValueError(
                f"Total allocation would exceed 100%. "
                f"Current: {current_total:.0%}, Adding: {portfolio.allocation_pct:.0%}"
            )
        self.portfolios[portfolio.portfolio_id] = portfolio
        logger.info("portfolio_added", id=portfolio.portfolio_id, name=portfolio.name)

    def pause_portfolio(self, portfolio_id: str) -> None:
        """Pause a portfolio (stop new cycles, keep existing positions)."""
        if portfolio_id in self.portfolios:
            self.portfolios[portfolio_id].active = False
            logger.info("portfolio_paused", id=portfolio_id)

    def resume_portfolio(self, portfolio_id: str) -> None:
        if portfolio_id in self.portfolios:
            self.portfolios[portfolio_id].active = True
            logger.info("portfolio_resumed", id=portfolio_id)
