import asyncio
from core.schemas import TradingState
from agents.market_intel import MarketIntelAgent
from agents.fundamental import FundamentalAgent
from agents.quant import QuantAgent
from db.database import get_raw_connection
import structlog

logger = structlog.get_logger()

market_intel = MarketIntelAgent()
fundamental = FundamentalAgent()
quant = QuantAgent()

async def _run_agent_with_own_conn(agent, state: dict) -> dict:
    conn = await get_raw_connection()
    try:
        return await agent.run(state, conn)
    finally:
        await conn.close()

async def node_research(state: TradingState) -> TradingState:
    """Run all 3 core research agents in parallel (async fan-out)."""
    logger.info("node_research_start")
    results = await asyncio.gather(
        _run_agent_with_own_conn(market_intel, state),
        _run_agent_with_own_conn(fundamental, state),
        _run_agent_with_own_conn(quant, state),
        return_exceptions=True,
    )
    for r in results:
        if isinstance(r, Exception):
            logger.error("research_agent_error", error=str(r))
            state.setdefault("errors", []).append(str(r))
        else:
            state.update(r)
    state["research_done"] = True
    return state
