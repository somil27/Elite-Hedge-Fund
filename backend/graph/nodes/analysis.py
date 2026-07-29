import asyncio
from core.schemas import TradingState
from agents.strategist import PortfolioStrategistAgent
from agents.technical import TechnicalAnalystAgent
from agents.risk_manager import RiskManagerAgent
from db.database import get_raw_connection
import structlog

logger = structlog.get_logger()

strategist = PortfolioStrategistAgent()
technical = TechnicalAnalystAgent()
risk_manager = RiskManagerAgent()

async def _run_agent_with_own_conn(agent, state: dict) -> dict:
    conn = await get_raw_connection()
    try:
        return await agent.run(state, conn)
    finally:
        await conn.close()

def _build_phase1_context(state: dict) -> dict:
    """Summarise Phase 1 agent outputs for the strategist."""
    news     = state.get("news_sentiment", {})
    macro    = state.get("macro_intel", {})
    options  = state.get("options_flow", {})
    earnings = state.get("earnings_calendar", {})
    weights  = state.get("mandate", {}).get("phase1_weights", {})

    return {
        "news_overall_sentiment":  news.get("overall_sentiment", 0),
        "news_watchlist_flags":    news.get("watchlist_flags", {}),
        "macro_regime":            macro.get("macro_regime", "NEUTRAL"),
        "macro_sector_overweights": macro.get("sector_overweights", []),
        "macro_sector_underweights": macro.get("sector_underweights", []),
        "options_signals":         {
            sig.get("symbol"): sig.get("signal_score", 0)
            for sig in options.get("flow_signals", [])
        },
        "earnings_risk":           earnings.get("watchlist_earnings_risk", {}),
        "phase1_weights":          weights,
    }


async def node_analysis(state: TradingState) -> TradingState:
    """Strategist first, then Technical + Risk in parallel."""
    logger.info("node_analysis_start")
    # Inject Phase 1 signals into state for strategist to use
    phase1_context = _build_phase1_context(state)
    state["phase1_context"] = phase1_context

    strat_result = await _run_agent_with_own_conn(strategist, state)
    state.update(strat_result)

    # Apply earnings adjustments to proposals
    earnings_adj = state.get("earnings_adjustments", {})
    if earnings_adj:
        proposals = state.get("proposals", [])
        for p in proposals:
            symbol = p.get("symbol")
            if symbol in earnings_adj:
                adj = earnings_adj[symbol]
                if adj.get("force_exit"):
                    proposals = [x for x in proposals if x.get("symbol") != symbol]
                elif adj.get("max_weight_multiplier"):
                    p["proposed_weight"] = p.get("proposed_weight", 0.03) * adj["max_weight_multiplier"]
        state["proposals"] = proposals

    tech_result, risk_result = await asyncio.gather(
        _run_agent_with_own_conn(technical, state),
        _run_agent_with_own_conn(risk_manager, state),
        return_exceptions=True,
    )
    for r in [tech_result, risk_result]:
        if isinstance(r, Exception):
            logger.error("analysis_agent_error", error=str(r))
            state.setdefault("errors", []).append(str(r))
        else:
            state.update(r)
    return state
