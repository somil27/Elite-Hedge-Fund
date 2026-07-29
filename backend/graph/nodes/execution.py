from core.schemas import TradingState
from agents.trade_desk import TradeDeskAgent
from agents.execution import ExecutionAgent
from db.database import get_raw_connection
import structlog

logger = structlog.get_logger()

trade_desk = TradeDeskAgent()
execution = ExecutionAgent()

async def _with_conn(agent, state: dict) -> dict:
    conn = await get_raw_connection()
    try:
        result = await agent.run(state, conn)
        state.update(result)
        return state
    finally:
        await conn.close()

async def node_trade_desk(state: TradingState) -> TradingState:
    logger.info("node_trade_desk_start")
    return await _with_conn(trade_desk, state)

async def node_execution(state: TradingState) -> TradingState:
    logger.info("node_execution_start")
    return await _with_conn(execution, state)

async def node_human_gate(state: TradingState) -> TradingState:
    logger.info("node_human_gate", awaiting=state.get("awaiting_human"))
    return state

async def node_veto_handler(state: TradingState) -> TradingState:
    logger.warning("veto_handler_triggered")
    conn = await get_raw_connection()
    try:
        await conn.execute("""
            UPDATE trade_cycles SET status='rejected', completed_at=now()
            WHERE id=$1::uuid
        """, state.get("cycle_id"))
    finally:
        await conn.close()
    state["final_status"] = "rejected"
    return state
