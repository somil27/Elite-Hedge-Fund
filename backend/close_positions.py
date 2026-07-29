"""
Position closer — fetches current prices for open positions,
calculates P&L, and writes exit data to trade_outcomes.

Run periodically (e.g. market close) or call from post-trade monitoring.
    python close_positions.py --symbol NVDA --reason take_profit
    python close_positions.py --all --reason eod_close
"""
import asyncio
import argparse
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from dotenv import load_dotenv
load_dotenv()

import structlog
logger = structlog.get_logger()


async def close_position(conn, symbol: str, reason: str = "manual"):
    """Update a trade_outcome with exit price and realized P&L."""
    from tools.market_data import get_market_snapshot
    from core.memory import write_reflection

    # Get open trade outcomes for this symbol
    rows = await conn.fetch("""
        SELECT to2.id::text, to2.cycle_id::text, to2.entry_price, to2.qty, to2.direction, to2.agent_signals, tc.cio_mandate
        FROM trade_outcomes to2
        JOIN trade_cycles tc ON tc.id = to2.cycle_id
        WHERE to2.symbol = $1 AND to2.exit_price IS NULL AND to2.closed_at IS NULL
        ORDER BY to2.opened_at DESC
        LIMIT 1
    """, symbol)

    if not rows:
        print(f"No open position found for {symbol}")
        return

    row = rows[0]
    import json
    cio_mandate = row["cio_mandate"] or {}
    if isinstance(cio_mandate, str):
        try:
            cio_mandate = json.loads(cio_mandate)
        except Exception:
            cio_mandate = {}
    market = cio_mandate.get("market", "us")

    snap = await get_market_snapshot([symbol], market=market)
    exit_price = snap.get(symbol, {}).get("price", 0)

    if not exit_price:
        logger.error("could_not_get_exit_price", symbol=symbol)
        return

    entry_price = row["entry_price"]
    qty = row["qty"]
    direction = row["direction"]

    if direction == "long":
        pnl = (exit_price - entry_price) * qty
        pnl_pct = (exit_price - entry_price) / entry_price
    else:
        pnl = (entry_price - exit_price) * qty
        pnl_pct = (entry_price - exit_price) / entry_price

    await conn.execute("""
        UPDATE trade_outcomes
        SET exit_price  = $1,
            pnl_realized = $2,
            pnl_pct      = $3,
            close_reason = $4,
            closed_at    = now()
        WHERE id = $5::uuid
    """, exit_price, round(pnl, 2), round(pnl_pct, 6), reason, row["id"])

    import json
    trade_data = {
        "symbol": symbol,
        "direction": direction,
        "entry_price": entry_price,
        "exit_price": exit_price,
        "qty": qty,
        "pnl_realized": round(pnl, 2),
        "pnl_pct": round(pnl_pct, 6),
        "close_reason": reason,
        "agent_signals": row["agent_signals"] if isinstance(row["agent_signals"], dict)
                         else json.loads(row["agent_signals"] or "{}"),
    }

    # Write post-close reflections for learning agents
    for agent_id in ["portfolio_strategist", "risk_manager", "quant_researcher",
                     "fundamental_analyst"]:
        await write_reflection(conn, agent_id, row["cycle_id"], trade_data)

    outcome_str = "PROFIT" if pnl > 0 else "LOSS"
    print(f"\n  {outcome_str}: {symbol} {direction}")
    print(f"    Entry: ${entry_price:.2f}  Exit: ${exit_price:.2f}")
    print(f"    Qty:   {qty:.4f}")
    print(f"    P&L:   ${pnl:+.2f}  ({pnl_pct:+.2%})")
    print(f"    Reason: {reason}\n")
    logger.info("position_closed", symbol=symbol, pnl=pnl, pnl_pct=pnl_pct)


async def close_all_positions(conn, reason: str = "eod_close"):
    """Close all open positions."""
    rows = await conn.fetch("""
        SELECT DISTINCT symbol FROM trade_outcomes
        WHERE exit_price IS NULL AND closed_at IS NULL
    """)
    if not rows:
        print("No open positions to close.")
        return
    print(f"Closing {len(rows)} open position(s)…")
    for row in rows:
        await close_position(conn, row["symbol"], reason)


async def main():
    parser = argparse.ArgumentParser(description="Close open trading positions")
    parser.add_argument("--symbol", type=str, help="Symbol to close")
    parser.add_argument("--all", action="store_true", help="Close all open positions")
    parser.add_argument("--reason", type=str, default="manual",
                        help="Close reason: take_profit | stop_loss | eod_close | manual")
    args = parser.parse_args()

    if not args.symbol and not args.all:
        parser.print_help()
        return

    from db.database import get_raw_connection
    conn = await get_raw_connection()
    try:
        if args.all:
            await close_all_positions(conn, args.reason)
        elif args.symbol:
            await close_position(conn, args.symbol.upper(), args.reason)
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
