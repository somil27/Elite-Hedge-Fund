import asyncio
from core.schemas import TradingState
from agents.post_trade import ComplianceAgent, PortfolioMonitorAgent, ReportingAgent
from db.database import get_raw_connection
import structlog

logger = structlog.get_logger()

compliance = ComplianceAgent()
portfolio_monitor = PortfolioMonitorAgent()
reporting = ReportingAgent()

async def _run_agent_with_own_conn(agent, state: dict) -> dict:
    conn = await get_raw_connection()
    try:
        return await agent.run(state, conn)
    finally:
        await conn.close()

async def node_post_trade(state: TradingState) -> TradingState:
    """Post-trade agents + RL weight update in parallel."""
    logger.info("node_post_trade_start")
    results = await asyncio.gather(
        _run_agent_with_own_conn(compliance, state),
        _run_agent_with_own_conn(portfolio_monitor, state),
        _run_agent_with_own_conn(reporting, state),
        return_exceptions=True,
    )
    for r in results:
        if not isinstance(r, Exception):
            state.update(r)

    # Phase 2: Trigger RL weight update after trade closes
    cycle_id = state.get("cycle_id")
    market   = state.get("market", "us")
    if cycle_id and state.get("execution_report"):
        try:
            conn = await get_raw_connection()
            try:
                from strategies.rl_optimiser import trigger_rl_update
                new_weights = await trigger_rl_update(conn, cycle_id, market)
                if new_weights:
                    state["updated_rl_weights"] = new_weights
                    logger.info("rl_update_complete",
                                weights={k: round(v, 3) for k, v in new_weights.items()})
            finally:
                await conn.close()
        except Exception as e:
            logger.warning("rl_update_failed", error=str(e))

    return state
