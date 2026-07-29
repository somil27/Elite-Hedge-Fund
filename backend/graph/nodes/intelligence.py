import asyncio
from core.schemas import TradingState
from agents.news_sentiment import NewsSentimentAgent
from agents.macro_intel import MacroIntelAgent
from agents.options_flow import OptionsFlowAgent
from agents.earnings_calendar import EarningsCalendarAgent
from strategies.strategy_library import select_strategy, apply_strategy_to_mandate
from strategies.rl_optimiser import RLWeightOptimiser
from db.database import get_raw_connection
import structlog

logger = structlog.get_logger()

news_sentiment = NewsSentimentAgent()
macro_intel_ag = MacroIntelAgent()
options_flow = OptionsFlowAgent()
earnings_calendar = EarningsCalendarAgent()

async def _run_agent_with_own_conn(agent, state: dict) -> dict:
    conn = await get_raw_connection()
    try:
        return await agent.run(state, conn)
    finally:
        await conn.close()

async def node_phase1_intelligence(state: TradingState) -> TradingState:
    """
    Phase 1: Run all 4 intelligence agents in parallel.
    News Sentiment, Macro Intel, Options Flow, Earnings Calendar.
    Then select the best strategy for current conditions (Phase 2).
    """
    logger.info("node_phase1_start")
    results = await asyncio.gather(
        _run_agent_with_own_conn(news_sentiment, state),
        _run_agent_with_own_conn(macro_intel_ag, state),
        _run_agent_with_own_conn(options_flow, state),
        _run_agent_with_own_conn(earnings_calendar, state),
        return_exceptions=True,
    )
    for r in results:
        if isinstance(r, Exception):
            logger.error("phase1_agent_error", error=str(r))
            state.setdefault("errors", []).append(str(r))
        else:
            state.update(r)

    # Phase 2: Select strategy based on macro regime
    macro_regime  = state.get("macro_intel", {}).get("macro_regime", "NEUTRAL")
    mode          = state.get("mode", "short_term")
    market        = state.get("market", "us")
    strategy_name = state.get("strategy_override")   # optional forced strategy

    strategy = select_strategy(macro_regime, mode, market, strategy_name)
    updated_mandate = apply_strategy_to_mandate(state.get("mandate", {}), strategy)
    state["mandate"] = updated_mandate
    state["active_strategy"] = strategy.name
    logger.info("strategy_selected_phase2", strategy=strategy.name, regime=macro_regime)

    # Phase 2: Load RL-optimised weights
    try:
        optimiser = RLWeightOptimiser()
        conn = await get_raw_connection()
        try:
            rl_weights = await optimiser.get_weights(conn, market)
        finally:
            await conn.close()
        # Blend RL weights into mandate agent weights (70% strategy, 30% RL)
        current_weights = updated_mandate.get("agent_weights", {})
        blended = {}
        all_keys = set(list(current_weights.keys()) + list(rl_weights.keys()))
        for k in all_keys:
            strat_w = current_weights.get(k, 0)
            rl_w    = rl_weights.get(k, 0)
            blended[k] = 0.70 * strat_w + 0.30 * rl_w
        # Normalise
        total = sum(blended.values()) or 1
        state["mandate"]["agent_weights"] = {k: v/total for k, v in blended.items()}
        state["rl_weights"] = rl_weights
        logger.info("rl_weights_applied", weights={k: round(v, 3) for k, v in rl_weights.items()})
    except Exception as e:
        logger.warning("rl_weights_load_failed", error=str(e))

    return state
