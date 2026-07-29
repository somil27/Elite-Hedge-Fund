"""
Strategy Library — Phase 2
Pluggable strategy modules. The CIO selects the active strategy
based on market regime. Each strategy defines:
  - Agent weight overrides
  - Risk parameter overrides
  - Preferred execution algorithm
  - Universe filters (which symbols qualify)
  - Entry / exit rules for the Quant Researcher
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
import structlog

logger = structlog.get_logger()


@dataclass
class StrategyConfig:
    """Complete configuration for one trading strategy."""
    name:        str
    description: str
    mode:        str          # "short_term" | "long_term"
    regime_fit:  list[str]   # which macro regimes this strategy suits

    # Agent weight overrides (sum should ~= 1.0)
    agent_weights: dict[str, float] = field(default_factory=dict)

    # Risk overrides
    max_position_pct:  float = 0.03   # max single position as % of portfolio
    risk_budget_scale: float = 1.0    # multiply the CIO risk_budget by this
    stop_loss_pct:     float = 0.07   # default stop-loss from entry
    take_profit_pct:   float = 0.15   # default take-profit from entry

    # Execution preference
    preferred_algo: str = "vwap"      # vwap|twap|aggressive|passive

    # Universe filters applied to the watchlist
    min_market_cap_b:  Optional[float] = None
    min_avg_volume:    Optional[int]   = None
    require_options:   bool = False    # only trade if options exist

    # Phase 1 signal weights (how much each new agent contributes)
    news_sentiment_weight:  float = 0.15
    macro_weight:           float = 0.10
    options_flow_weight:    float = 0.10
    earnings_caution:       bool  = True  # reduce size near earnings

    # Minimum composite score to generate a proposal
    min_conviction_score: float = 0.55


# ── Strategy definitions ──────────────────────────────────────

STRATEGIES: dict[str, StrategyConfig] = {

    "momentum": StrategyConfig(
        name="Momentum",
        description=(
            "Trend-following. Buys breakouts and strong relative strength. "
            "Quant signals dominate. Fast execution to capture momentum."
        ),
        mode="short_term",
        regime_fit=["GOLDILOCKS", "REFLATION", "RATE_CUT_CYCLE"],
        agent_weights={
            "quant":        0.45,
            "technical":    0.25,
            "fundamental":  0.10,
            "market_intel": 0.10,
            "news":         0.10,
        },
        max_position_pct=0.04,
        risk_budget_scale=1.1,
        stop_loss_pct=0.06,
        take_profit_pct=0.18,
        preferred_algo="aggressive",
        min_avg_volume=500_000,
        options_flow_weight=0.15,
        min_conviction_score=0.60,
    ),

    "mean_reversion": StrategyConfig(
        name="Mean Reversion",
        description=(
            "Buys oversold high-quality stocks. "
            "Fundamental value + technical RSI divergence. "
            "Passive execution with limit orders."
        ),
        mode="short_term",
        regime_fit=["NEUTRAL", "DEFLATION_RISK", "GOLDILOCKS"],
        agent_weights={
            "quant":        0.35,
            "technical":    0.30,
            "fundamental":  0.20,
            "market_intel": 0.10,
            "news":         0.05,
        },
        max_position_pct=0.03,
        risk_budget_scale=0.9,
        stop_loss_pct=0.05,
        take_profit_pct=0.10,
        preferred_algo="passive",
        min_conviction_score=0.55,
    ),

    "sector_rotation": StrategyConfig(
        name="Sector Rotation",
        description=(
            "Rotates between sectors based on macro regime and business cycle. "
            "Macro agent drives sector weights. Medium-term holding period."
        ),
        mode="long_term",
        regime_fit=["REFLATION", "STAGFLATION", "RATE_HIKE_CYCLE", "RATE_CUT_CYCLE"],
        agent_weights={
            "fundamental":  0.30,
            "market_intel": 0.30,
            "quant":        0.20,
            "technical":    0.10,
            "news":         0.10,
        },
        max_position_pct=0.05,
        risk_budget_scale=0.85,
        stop_loss_pct=0.10,
        take_profit_pct=0.25,
        preferred_algo="twap",
        macro_weight=0.25,
        min_conviction_score=0.60,
    ),

    "earnings_play": StrategyConfig(
        name="Earnings Play",
        description=(
            "Event-driven. Positions before earnings based on "
            "historical beat rate, whisper numbers, and options pricing. "
            "Reduces size aggressively before the print."
        ),
        mode="short_term",
        regime_fit=["GOLDILOCKS", "REFLATION", "NEUTRAL"],
        agent_weights={
            "fundamental":  0.35,
            "quant":        0.25,
            "news":         0.25,
            "technical":    0.10,
            "market_intel": 0.05,
        },
        max_position_pct=0.025,  # smaller due to binary event risk
        risk_budget_scale=0.8,
        stop_loss_pct=0.08,
        take_profit_pct=0.12,
        preferred_algo="market",
        options_flow_weight=0.20,
        earnings_caution=False,   # this strategy IS the earnings play
        require_options=True,
        min_conviction_score=0.65,
    ),

    "value_investing": StrategyConfig(
        name="Value Investing",
        description=(
            "Deep fundamental analysis. DCF-driven. Long-term compounding. "
            "Fundamental agent dominates. Ignores short-term noise."
        ),
        mode="long_term",
        regime_fit=["DEFLATION_RISK", "STAGFLATION", "NEUTRAL", "GOLDILOCKS"],
        agent_weights={
            "fundamental":  0.55,
            "market_intel": 0.20,
            "quant":        0.15,
            "technical":    0.05,
            "news":         0.05,
        },
        max_position_pct=0.05,
        risk_budget_scale=0.75,
        stop_loss_pct=0.15,
        take_profit_pct=0.40,
        preferred_algo="twap",
        min_market_cap_b=10.0,
        news_sentiment_weight=0.05,
        options_flow_weight=0.05,
        min_conviction_score=0.65,
    ),

    "defensive": StrategyConfig(
        name="Defensive / Capital Preservation",
        description=(
            "Risk-off mode. Focuses on low-beta, dividend stocks, gold, "
            "and short-duration positions. Used in crisis or high-VIX environments."
        ),
        mode="short_term",
        regime_fit=["STAGFLATION", "DEFLATION_RISK", "RATE_HIKE_CYCLE"],
        agent_weights={
            "market_intel": 0.40,
            "fundamental":  0.30,
            "quant":        0.15,
            "technical":    0.10,
            "news":         0.05,
        },
        max_position_pct=0.02,
        risk_budget_scale=0.50,  # very conservative
        stop_loss_pct=0.05,
        take_profit_pct=0.08,
        preferred_algo="passive",
        macro_weight=0.30,
        min_conviction_score=0.70,
    ),

    "india_momentum": StrategyConfig(
        name="India Momentum (NSE)",
        description=(
            "NSE-specific momentum strategy. Focuses on NIFTY 50 breakouts, "
            "FII flow alignment, and India VIX. MIS for short-term, CNC for swing."
        ),
        mode="short_term",
        regime_fit=["GOLDILOCKS", "REFLATION", "NEUTRAL"],
        agent_weights={
            "quant":        0.40,
            "technical":    0.30,
            "market_intel": 0.15,
            "fundamental":  0.10,
            "news":         0.05,
        },
        max_position_pct=0.03,
        risk_budget_scale=1.0,
        stop_loss_pct=0.05,
        take_profit_pct=0.12,
        preferred_algo="aggressive",
        options_flow_weight=0.20,
        min_conviction_score=0.60,
    ),
}


def select_strategy(
    macro_regime: str,
    mode: str,
    market: str = "us",
    override: str = None,
) -> StrategyConfig:
    """
    Select the best strategy for the current macro regime and mode.
    Returns the StrategyConfig to use for this cycle.

    Args:
        macro_regime: from MacroIntelAgent (e.g. "GOLDILOCKS")
        mode:         "short_term" | "long_term"
        market:       "us" | "india"
        override:     force a specific strategy by name
    """
    if override and override in STRATEGIES:
        logger.info("strategy_override", strategy=override)
        return STRATEGIES[override]

    if market == "india":
        if mode == "short_term":
            return STRATEGIES["india_momentum"]
        return STRATEGIES["value_investing"]

    # Filter strategies that match mode and regime
    candidates = [
        s for s in STRATEGIES.values()
        if s.mode == mode and macro_regime in s.regime_fit
    ]

    if not candidates:
        # Fallback: match mode only
        candidates = [s for s in STRATEGIES.values() if s.mode == mode]

    if not candidates:
        return STRATEGIES["momentum"] if mode == "short_term" else STRATEGIES["value_investing"]

    # Crisis regime → always defensive
    if macro_regime in ("STAGFLATION", "DEFLATION_RISK") and mode == "short_term":
        return STRATEGIES["defensive"]

    # Rate hike cycle → sector rotation or defensive
    if macro_regime == "RATE_HIKE_CYCLE":
        return STRATEGIES.get("sector_rotation" if mode == "long_term" else "defensive")

    # Default: first matching candidate
    logger.info("strategy_selected", strategy=candidates[0].name, regime=macro_regime)
    return candidates[0]


def apply_strategy_to_mandate(mandate: dict, strategy: StrategyConfig) -> dict:
    """
    Merge strategy config into the CIO mandate.
    Returns updated mandate dict.
    """
    updated = dict(mandate)
    updated["strategy"]       = strategy.name
    updated["agent_weights"]  = strategy.agent_weights
    updated["risk_budget"]    = mandate.get("risk_budget", 4.0) * strategy.risk_budget_scale
    updated["preferred_algo"] = strategy.preferred_algo
    updated["stop_loss_pct"]  = strategy.stop_loss_pct
    updated["take_profit_pct"] = strategy.take_profit_pct
    updated["min_conviction"] = strategy.min_conviction_score
    updated["earnings_caution"] = strategy.earnings_caution
    updated["max_position_pct"]  = strategy.max_position_pct
    updated["phase1_weights"] = {
        "news_sentiment": strategy.news_sentiment_weight,
        "macro":          strategy.macro_weight,
        "options_flow":   strategy.options_flow_weight,
    }
    logger.info("strategy_applied", strategy=strategy.name,
                risk_budget=updated["risk_budget"],
                algo=strategy.preferred_algo)
    return updated
