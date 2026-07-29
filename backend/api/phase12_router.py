"""
Phase 1 + 2 API Router
New endpoints:
  /api/backtest/*          — run and retrieve backtests
  /api/strategies/*        — list strategies, get active strategy info
  /api/rl/*                — RL weight state and performance
  /api/portfolios/*        — multi-portfolio management
"""
import uuid

from fastapi import APIRouter, HTTPException, Query, BackgroundTasks
from pydantic import BaseModel

from db.database import get_raw_connection
from strategies.strategy_library import STRATEGIES, select_strategy
from strategies.rl_optimiser import RLWeightOptimiser
from strategies.multi_portfolio import MultiPortfolioManager, PortfolioDefinition
import structlog

logger = structlog.get_logger()
router = APIRouter(tags=["phase1-phase2"])


# ═══════════════════════════════════════════════════
# Strategy endpoints
# ═══════════════════════════════════════════════════

@router.get("/api/strategies")
async def list_strategies():
    """List all available trading strategies."""
    return [
        {
            "name":             s.name,
            "key":              key,
            "description":      s.description,
            "mode":             s.mode,
            "regime_fit":       s.regime_fit,
            "preferred_algo":   s.preferred_algo,
            "min_conviction":   s.min_conviction_score,
            "risk_budget_scale": s.risk_budget_scale,
            "agent_weights":    s.agent_weights,
        }
        for key, s in STRATEGIES.items()
    ]


@router.get("/api/strategies/recommend")
async def recommend_strategy(
    macro_regime: str = Query("NEUTRAL"),
    mode: str         = Query("short_term"),
    market: str       = Query("us"),
):
    """Recommend the best strategy for current macro conditions."""
    strategy = select_strategy(macro_regime, mode, market)
    return {
        "recommended": strategy.name,
        "regime":       macro_regime,
        "mode":         mode,
        "market":       market,
        "reasoning":    strategy.description,
        "agent_weights": strategy.agent_weights,
    }


# ═══════════════════════════════════════════════════
# Backtest endpoints
# ═══════════════════════════════════════════════════

class BacktestRequest(BaseModel):
    strategy:        str   = "momentum"
    symbols:         list[str] = ["NVDA", "AAPL", "MSFT"]
    start_date:      str   = "2024-01-01"
    end_date:        str   = "2024-12-31"
    mode:            str   = "short_term"
    market:          str   = "us"
    initial_capital: float = 100_000.0
    rebalance_freq:  str   = "weekly"


@router.post("/api/backtest/run")
async def run_backtest(req: BacktestRequest, background_tasks: BackgroundTasks):
    """
    Run a backtest. Executes in the background and stores results in DB.
    Returns a backtest_id to poll for results.
    """
    backtest_id = str(uuid.uuid4())

    async def _run():
        from backtest.engine import BacktestEngine
        conn = await get_raw_connection()
        try:
            engine = BacktestEngine()
            result = await engine.run(
                strategy=req.strategy,
                symbols=req.symbols,
                start_date=req.start_date,
                end_date=req.end_date,
                mode=req.mode,
                market=req.market,
                initial_capital=req.initial_capital,
                rebalance_freq=req.rebalance_freq,
            )

            import json
            # Persist result
            await conn.execute("""
                INSERT INTO backtest_results (
                    id, strategy, symbols, start_date, end_date, mode, market,
                    initial_capital, final_capital, total_return_pct,
                    annualised_return, sharpe_ratio, max_drawdown_pct,
                    win_rate, profit_factor, total_trades, avg_hold_days,
                    equity_curve, agent_attribution, walkforward
                ) VALUES (
                    $1::uuid, $2, $3, $4, $5, $6, $7,
                    $8, $9, $10, $11, $12, $13, $14, $15, $16, $17,
                    $18, $19, $20
                )
            """,
                backtest_id,
                result.strategy,
                json.dumps(result.symbols),
                result.start_date, result.end_date,
                result.mode, result.market,
                result.initial_capital, result.final_capital,
                result.total_return_pct, result.annualised_return,
                result.sharpe_ratio, result.max_drawdown_pct,
                result.win_rate, result.profit_factor,
                result.total_trades, result.avg_hold_days,
                json.dumps(result.equity_curve),
                json.dumps(result.agent_attribution),
                json.dumps(result.walkforward),
            )

            # Persist individual trades
            for trade in result.trades:
                if trade.exit_price is not None:
                    trade_uuid = str(uuid.uuid4())
                    await conn.execute("""
                        INSERT INTO backtest_trades (
                            id, backtest_id, symbol, direction, entry_date, exit_date,
                            entry_price, exit_price, qty, pnl, pnl_pct,
                            hold_days, exit_reason, agent_signals, composite_score
                        ) VALUES ($1::uuid,$2::uuid,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15)
                    """,
                        trade_uuid,
                        backtest_id, trade.symbol, trade.direction,
                        trade.entry_date, trade.exit_date,
                        trade.entry_price, trade.exit_price, trade.qty,
                        trade.pnl, trade.pnl_pct, trade.hold_days,
                        trade.exit_reason,
                        json.dumps(trade.agent_signals),
                        trade.composite_score,
                    )
            logger.info("backtest_stored", id=backtest_id)
        except Exception as e:
            logger.error("backtest_run_error", error=str(e))
        finally:
            await conn.close()

    background_tasks.add_task(_run)
    return {
        "backtest_id": backtest_id,
        "status":      "running",
        "message":     "Backtest started. Poll /api/backtest/{id} for results.",
    }


@router.get("/api/backtest/{backtest_id}")
async def get_backtest(backtest_id: str):
    """Get backtest results by ID."""
    conn = await get_raw_connection()
    try:
        row = await conn.fetchrow("""
            SELECT * FROM backtest_results WHERE id = $1::uuid
        """, backtest_id)
        if not row:
            raise HTTPException(404, "Backtest not found or still running")

        import json
        r = dict(row)
        for key in ["symbols", "equity_curve", "agent_attribution", "walkforward"]:
            if isinstance(r.get(key), str):
                r[key] = json.loads(r[key])
        if r.get("created_at"):
            r["created_at"] = r["created_at"].isoformat()
        return r
    finally:
        await conn.close()


@router.get("/api/backtest/{backtest_id}/trades")
async def get_backtest_trades(backtest_id: str, limit: int = Query(100, le=500)):
    """Get individual trades from a backtest."""
    conn = await get_raw_connection()
    try:
        import json
        rows = await conn.fetch("""
            SELECT * FROM backtest_trades
            WHERE backtest_id = $1::uuid
            ORDER BY entry_date
            LIMIT $2
        """, backtest_id, limit)
        result = []
        for row in rows:
            r = dict(row)
            r["id"] = str(r["id"])
            r["backtest_id"] = str(r["backtest_id"])
            if isinstance(r.get("agent_signals"), str):
                r["agent_signals"] = json.loads(r["agent_signals"])
            result.append(r)
        return result
    finally:
        await conn.close()


@router.get("/api/backtest")
async def list_backtests(limit: int = Query(20, le=100)):
    """List recent backtests."""
    conn = await get_raw_connection()
    try:
        rows = await conn.fetch("""
            SELECT id::text, strategy, start_date, end_date, mode, market,
                   total_return_pct, sharpe_ratio, max_drawdown_pct,
                   win_rate, total_trades, created_at
            FROM backtest_results
            ORDER BY created_at DESC
            LIMIT $1
        """, limit)
        return [
            {**dict(r), "created_at": r["created_at"].isoformat() if r["created_at"] else None}
            for r in rows
        ]
    finally:
        await conn.close()


# ═══════════════════════════════════════════════════
# RL weight endpoints
# ═══════════════════════════════════════════════════

@router.get("/api/rl/weights")
async def get_rl_weights(market: str = Query("us")):
    """Get current RL-optimised signal weights."""
    conn = await get_raw_connection()
    try:
        optimiser = RLWeightOptimiser()
        weights   = await optimiser.get_weights(conn, market)
        summary   = await optimiser.get_performance_summary(conn, market)
        return {
            "market":  market,
            "weights": {k: round(v, 4) for k, v in weights.items()},
            "performance": summary,
        }
    finally:
        await conn.close()


@router.post("/api/rl/reset")
async def reset_rl_weights(market: str = Query("us")):
    """Reset RL weights to defaults (useful after strategy change)."""
    from strategies.strategy_library import DEFAULT_WEIGHTS
    conn = await get_raw_connection()
    try:
        for key, w in DEFAULT_WEIGHTS.items():
            await conn.execute("""
                UPDATE rl_signal_weights
                SET weight=$1, total_reward=0, pull_count=0
                WHERE signal_key=$2 AND market=$3
            """, w, key, market)
        return {"status": "reset", "market": market}
    finally:
        await conn.close()


# ═══════════════════════════════════════════════════
# Multi-portfolio endpoints
# ═══════════════════════════════════════════════════

_portfolio_manager = MultiPortfolioManager()


@router.get("/api/portfolios")
async def list_portfolios():
    """List all portfolio definitions."""
    conn = await get_raw_connection()
    try:
        summary = await _portfolio_manager.get_portfolio_summary(conn)
        return summary
    finally:
        await conn.close()


@router.post("/api/portfolios/run-all")
async def run_all_portfolios(
    background_tasks: BackgroundTasks,
    auto_mode: bool = Query(False),
):
    """Launch cycles for all active portfolios simultaneously."""
    from broker.registry import get_portfolio_snapshot
    conn = await get_raw_connection()
    try:
        snapshot = await get_portfolio_snapshot(market="us")
        total_capital = snapshot.get("total_value", 100_000)
    finally:
        await conn.close()

    async def _run():
        conn2 = await get_raw_connection()
        try:
            results = await _portfolio_manager.run_all_cycles(
                total_capital, conn2, auto_mode
            )
            logger.info("multi_portfolio_complete", results=len(results))
        finally:
            await conn2.close()

    background_tasks.add_task(_run)
    return {
        "status":    "launched",
        "portfolios": len([p for p in _portfolio_manager.portfolios.values() if p.active]),
        "total_capital": total_capital,
    }


class AddPortfolioBody(BaseModel):
    portfolio_id:   str
    name:           str
    strategy:       str
    allocation_pct: float
    mode:           str = "short_term"
    market:         str = "us"
    auto_mode:      bool = False
    description:    str = ""


@router.post("/api/portfolios")
async def add_portfolio(body: AddPortfolioBody):
    """Add a new portfolio to the multi-portfolio manager."""
    if body.strategy not in STRATEGIES:
        raise HTTPException(400, f"Unknown strategy: {body.strategy}. "
                                 f"Valid: {list(STRATEGIES.keys())}")
    try:
        p = PortfolioDefinition(**body.model_dump())
        _portfolio_manager.add_portfolio(p)
        conn = await get_raw_connection()
        try:
            await conn.execute("""
                INSERT INTO portfolio_definitions
                    (portfolio_id, name, strategy, allocation_pct, mode, market,
                     auto_mode, description)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
                ON CONFLICT (portfolio_id) DO UPDATE SET
                    name=EXCLUDED.name, strategy=EXCLUDED.strategy,
                    allocation_pct=EXCLUDED.allocation_pct, active=true,
                    updated_at=now()
            """,
                p.portfolio_id, p.name, p.strategy,
                p.allocation_pct, p.mode, p.market,
                p.auto_mode, p.description,
            )
        finally:
            await conn.close()
        return {"status": "added", "portfolio_id": body.portfolio_id}
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/api/portfolios/{portfolio_id}/pause")
async def pause_portfolio(portfolio_id: str):
    _portfolio_manager.pause_portfolio(portfolio_id)
    return {"status": "paused", "portfolio_id": portfolio_id}


@router.post("/api/portfolios/{portfolio_id}/resume")
async def resume_portfolio(portfolio_id: str):
    _portfolio_manager.resume_portfolio(portfolio_id)
    return {"status": "resumed", "portfolio_id": portfolio_id}
