from core.schemas import TradingState
from agents.cio import CIOAgent
from broker.registry import get_portfolio_snapshot
from db.database import get_raw_connection
import structlog

logger = structlog.get_logger()
cio = CIOAgent()

async def _with_conn(agent, state: dict) -> dict:
    conn = await get_raw_connection()
    try:
        result = await agent.run(state, conn)
        state.update(result)
        return state
    finally:
        await conn.close()

async def node_cio(state: TradingState) -> TradingState:
    logger.info("node_cio_start", market=state.get("market", "us"))
    market = state.get("market", "us")

    if market == "india":
        conn = await get_raw_connection()
        try:
            snapshot = await get_portfolio_snapshot(
                market="india",
                user_id=state.get("user_id"),
                indian_broker=state.get("indian_broker", "zerodha"),
                conn=conn,
            )
        finally:
            await conn.close()
    else:
        snapshot = await get_portfolio_snapshot(market="us")

    state["portfolio_snapshot"] = snapshot
    return await _with_conn(cio, state)
