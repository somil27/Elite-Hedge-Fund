"""
Unified Broker Registry
Manages broker instances for BOTH US (Alpaca/IBKR/Mock) and Indian (Zerodha/Upstox) brokers.

The agent pipeline calls:
  - get_broker()                                               -> US broker
  - get_indian_broker_for_agents(user_id, broker_name, conn)  -> Indian broker
  - get_portfolio_snapshot(market="us"|"india", ...)          -> unified portfolio dict

Switching markets only requires changing the cycle's `market` field.
"""
from __future__ import annotations
from typing import Optional
from core.config import settings
from broker.base import AbstractBroker
import structlog

logger = structlog.get_logger()

_us_broker: Optional[AbstractBroker] = None


# ═══════════════════════════════════════════════════
# US Broker
# ═══════════════════════════════════════════════════

def create_us_broker() -> AbstractBroker:
    broker_name = getattr(settings, "broker", "mock").lower().strip()
    has_alpaca_keys = bool(
        getattr(settings, "alpaca_api_key", "") and
        getattr(settings, "alpaca_secret_key", "")
    )

    if broker_name == "ibkr":
        from broker.ibkr_broker import IBKRBroker
        paper = getattr(settings, "ibkr_paper", True)
        logger.info("us_broker_selected", broker="ibkr", paper=paper)
        return IBKRBroker(paper=paper)

    if broker_name == "mock" or (not has_alpaca_keys and broker_name != "alpaca"):
        from broker.mock_broker import MockBroker
        logger.info("us_broker_selected", broker="mock")
        return MockBroker(
            initial_cash=float(getattr(settings, "mock_initial_cash", 100_000)),
            slippage_bps=float(getattr(settings, "mock_slippage_bps", 2.0)),
        )

    from broker.alpaca_broker import AlpacaBroker
    base_url = getattr(settings, "alpaca_base_url", "")
    paper = "paper-api" in base_url or getattr(settings, "alpaca_paper", True)
    logger.info("us_broker_selected", broker="alpaca", paper=paper)
    return AlpacaBroker(paper=paper)


async def get_broker() -> AbstractBroker:
    """Get or initialise the US broker singleton."""
    global _us_broker
    if _us_broker is None:
        _us_broker = create_us_broker()
        await _us_broker.connect()
        logger.info("us_broker_initialised", broker=type(_us_broker).__name__)
    return _us_broker


async def reset_broker() -> None:
    global _us_broker
    if _us_broker is not None:
        await _us_broker.disconnect()
        _us_broker = None


# ═══════════════════════════════════════════════════
# Indian Broker (for agent pipeline)
# ═══════════════════════════════════════════════════

async def get_indian_broker_for_agents(
    user_id: str,
    broker_name: str,
    conn,
):
    """
    Get an authenticated Indian broker client for the agent pipeline.
    Delegates to session_manager which handles caching + token decryption.
    broker_name: "zerodha" | "upstox"
    """
    from broker.indian.session_manager import get_indian_broker
    return await get_indian_broker(user_id, broker_name, conn)


# ═══════════════════════════════════════════════════
# Unified portfolio snapshot
# ═══════════════════════════════════════════════════

async def get_portfolio_snapshot(
    market: str = "us",
    user_id: str = None,
    indian_broker: str = None,
    conn=None,
) -> dict:
    """
    Returns a standardised portfolio dict for TradingState.
    Works for both US and Indian brokers.

    US:    get_portfolio_snapshot()
    India: get_portfolio_snapshot(market="india", user_id=..., indian_broker="zerodha", conn=...)
    """
    if market == "india":
        return await _indian_portfolio_snapshot(user_id, indian_broker, conn)
    return await _us_portfolio_snapshot()


async def _us_portfolio_snapshot() -> dict:
    broker    = await get_broker()
    account   = await broker.get_account()
    positions = await broker.get_positions()

    pos_list = [
        {
            "symbol":             p.symbol,
            "qty":                p.qty,
            "side":               p.side,
            "avg_entry_price":    p.avg_entry_price,
            "current_price":      p.current_price,
            "market_value":       p.market_value,
            "unrealized_pnl":     p.unrealized_pnl,
            "unrealized_pnl_pct": p.unrealized_pnl_pct,
            "cost_basis":         p.cost_basis,
        }
        for p in positions
    ]

    return {
        "market":             "us",
        "total_value":        account.portfolio_value,
        "cash":               account.cash,
        "buying_power":       account.buying_power,
        "positions":          pos_list,
        "current_drawdown":   0.0,
        "account_id":         account.account_id,
        "day_trade_count":    account.day_trade_count,
        "pattern_day_trader": account.pattern_day_trader,
        "trading_blocked":    account.trading_blocked,
    }


async def _indian_portfolio_snapshot(
    user_id: str,
    broker_name: str,
    conn,
) -> dict:
    from broker.indian.session_manager import get_indian_broker

    client        = await get_indian_broker(user_id, broker_name, conn)
    funds         = await client.get_funds()
    holdings      = await client.get_holdings()
    positions_raw = await client.get_positions()
    positions     = (
        positions_raw.get("net", [])
        if isinstance(positions_raw, dict)
        else positions_raw
    )

    invested    = sum(h.investment_value for h in holdings)
    current_val = sum(h.current_value    for h in holdings)
    total_pnl   = sum(h.pnl             for h in holdings)
    total_value = current_val + funds.available_cash

    pos_list = [
        {
            "symbol":             p.tradingsymbol,
            "exchange":           p.exchange,
            "qty":                abs(p.quantity),
            "side":               p.side,
            "avg_entry_price":    p.buy_price or p.sell_price,
            "current_price":      p.last_price,
            "market_value":       abs(p.quantity) * p.last_price,
            "unrealized_pnl":     p.unrealised,
            "unrealized_pnl_pct": (
                p.unrealised / (abs(p.quantity) * (p.buy_price or 1)) * 100
                if p.quantity and (p.buy_price or p.sell_price) else 0
            ),
            "pnl":     p.pnl,
            "product": p.product,
        }
        for p in positions
        if p.quantity != 0
    ]

    holdings_list = [
        {
            "symbol":             h.tradingsymbol,
            "exchange":           h.exchange,
            "qty":                h.quantity,
            "side":               "long",
            "avg_entry_price":    h.average_price,
            "current_price":      h.last_price,
            "market_value":       h.current_value,
            "unrealized_pnl":     h.pnl,
            "unrealized_pnl_pct": h.total_return_pct,
            "cost_basis":         h.investment_value,
            "isin":               h.isin,
        }
        for h in holdings
    ]

    return {
        "market":           "india",
        "broker":           broker_name,
        "total_value":      total_value,
        "cash":             funds.available_cash,
        "buying_power":     funds.available_margin,
        "invested_value":   invested,
        "total_pnl":        total_pnl,
        "total_pnl_pct":    (total_pnl / invested * 100) if invested else 0,
        "positions":        pos_list,
        "holdings":         holdings_list,
        "current_drawdown": 0.0,
        "trading_blocked":  False,
        "used_margin":      funds.used_margin,
        "available_margin": funds.available_margin,
    }
