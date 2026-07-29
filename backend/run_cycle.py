#!/usr/bin/env python3
"""
CLI runner — run a trading cycle directly from the terminal
without needing the full FastAPI server running.

Usage:
    python run_cycle.py --mode short_term --auto
    python run_cycle.py --mode long_term
    python run_cycle.py --mode short_term --auto --watchlist NVDA AAPL MSFT
"""
import asyncio
import argparse
import sys
import os

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(__file__))

import structlog
from dotenv import load_dotenv
load_dotenv()

logger = structlog.get_logger()


async def run_cycle(
    mode: str = "short_term",
    auto_mode: bool = False,
    watchlist: list[str] = None,
    market: str = "us",
) -> dict:
    from graph.trading_graph import trading_graph
    from tools.broker import get_portfolio_snapshot
    from db.database import get_raw_connection
    import uuid

    cycle_id = str(uuid.uuid4())
    print(f"\n{'='*60}")
    print("  AlphaDesk — Trading Cycle")
    print(f"  Cycle ID : {cycle_id[:8]}…")
    print(f"  Mode     : {mode}")
    print(f"  Market   : {market}")
    print(f"  Auto     : {auto_mode}")
    print(f"{'='*60}\n")

    # Persist to DB
    conn = await get_raw_connection()
    try:
        await conn.execute("""
            INSERT INTO trade_cycles (id, mode, status, cio_mandate, auto_mode)
            VALUES ($1::uuid, $2, 'running', '{}', $3)
        """, cycle_id, mode, auto_mode)
    finally:
        await conn.close()

    portfolio = await get_portfolio_snapshot()

    initial_state = {
        "cycle_id": cycle_id,
        "mode": mode,
        "market": market,
        "auto_mode": auto_mode,
        "mandate": {},
        "portfolio_snapshot": portfolio,
        "fundamentals": [],
        "quant_signals": [],
        "proposals": [],
        "technical_assessments": [],
        "risk_assessments": [],
        "compliance_flags": [],
        "errors": [],
        "final_status": "running",
        "past_similar_trades": [],
        "agent_reflections": {},
        "regime_history": [],
    }

    # Override watchlist if provided
    if watchlist:
        initial_state["mandate"]["watchlist"] = watchlist

    print("⟳  Running agent pipeline…\n")
    result = await trading_graph.ainvoke(initial_state)

    # Print summary
    print(f"\n{'='*60}")
    print("  CYCLE COMPLETE")
    print(f"{'='*60}")
    print(f"  Status     : {result.get('final_status')}")

    mandate = result.get("mandate", {})
    if mandate.get("theme"):
        print(f"  Theme      : {mandate['theme']}")
    if mandate.get("watchlist"):
        print(f"  Watchlist  : {', '.join(mandate['watchlist'])}")

    intel = result.get("market_intel", {})
    if intel.get("regime"):
        print(f"  Regime     : {intel['regime']}  (sentiment {intel.get('sentiment_score', 0):.2f})")

    proposals = result.get("proposals", [])
    print(f"  Proposals  : {len(proposals)}")
    for p in proposals:
        risk = next((r for r in result.get("risk_assessments", [])
                     if r.get("symbol") == p.get("symbol")), {})
        print(f"    • {p.get('symbol')} {p.get('direction')} "
              f"score={p.get('composite_score', 0):.2f} "
              f"risk={risk.get('decision', 'n/a')}")

    exec_rep = result.get("execution_report")
    if exec_rep:
        print("\n  EXECUTION")
        print(f"    Symbol     : {exec_rep.get('symbol')}")
        print(f"    Direction  : {exec_rep.get('direction')}")
        print(f"    Fill price : ${exec_rep.get('avg_fill_price', 0):.2f}")
        print(f"    Qty filled : {exec_rep.get('qty_filled', 0):.2f}")
        print(f"    Slippage   : {exec_rep.get('slippage_bps', 0):.1f} bps")

    if result.get("awaiting_human"):
        print("\n  ⏳ Awaiting human approval.")
        print("  Open the dashboard to approve: http://localhost:5173")
        print("  Or use the API:")
        print(f"  POST /api/cycles/{cycle_id}/decide")

    errors = result.get("errors", [])
    if errors:
        print("\n  ⚠️  ERRORS:")
        for e in errors:
            print(f"    • {e}")

    print(f"\n{'='*60}\n")
    return result


def main():
    parser = argparse.ArgumentParser(description="Run a trading cycle")
    parser.add_argument("--mode", choices=["short_term", "long_term"],
                        default="short_term", help="Trading mode")
    parser.add_argument("--auto", action="store_true",
                        help="Auto mode — skip human gate")
    parser.add_argument("--market", choices=["us", "india"],
                        default="us", help="Trading market")
    parser.add_argument("--watchlist", nargs="+", metavar="TICKER",
                        help="Override watchlist e.g. --watchlist NVDA AAPL MSFT")
    args = parser.parse_args()

    asyncio.run(run_cycle(
        mode=args.mode,
        auto_mode=args.auto,
        watchlist=args.watchlist,
        market=args.market,
    ))


if __name__ == "__main__":
    main()
