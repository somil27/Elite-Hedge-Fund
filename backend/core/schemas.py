"""
Updated core/schemas.py — Phase 1 + 2 additions.
Adds Phase 1 agent output fields and Phase 2 strategy/RL fields to TradingState.

Drop this file into backend/core/schemas.py — replaces the original.
"""
from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Optional, Literal, Any
from datetime import datetime
from uuid import UUID, uuid4


# ─────────────────────────────────────────────
# BASE MESSAGE
# ─────────────────────────────────────────────
class BaseMessage(BaseModel):
    message_id: UUID = Field(default_factory=uuid4)
    cycle_id:   UUID
    sender:     str
    timestamp:  datetime = Field(default_factory=datetime.utcnow)


# ─────────────────────────────────────────────
# CIO → Research Agents
# ─────────────────────────────────────────────
class CycleMandate(BaseMessage):
    mode:          Literal["short_term", "long_term"]
    theme:         str
    watchlist:     list[str]
    risk_budget:   float = 5.0
    time_horizon:  str
    agent_weights: dict[str, float] = Field(default_factory=dict)
    strategy:      str = "momentum"           # Phase 2
    preferred_algo: str = "vwap"              # Phase 2


# ─────────────────────────────────────────────
# Research Layer
# ─────────────────────────────────────────────
class MarketIntelReport(BaseMessage):
    regime:          Literal["risk_on", "risk_off", "neutral", "crisis"]
    macro_summary:   str
    notable_events:  list[str]
    sentiment_score: float
    symbol_flags:    dict[str, str]
    confidence:      float = 0.7


class FundamentalReport(BaseMessage):
    symbol:        str
    fair_value:    float
    current_price: float
    upside_pct:    float
    thesis:        str
    key_risks:     list[str]
    metrics:       dict[str, float]
    rating:        Literal["strong_buy", "buy", "hold", "sell", "strong_sell"]
    confidence:    float = 0.7


class QuantSignal(BaseMessage):
    symbol:            str
    signal_type:       Literal["momentum", "mean_reversion", "breakout",
                               "factor", "options_flow"]
    signal_score:      float
    entry_trigger:     str
    backtest_sharpe:   float
    backtest_win_rate: float
    suggested_hold:    str
    confidence:        float = 0.7


# ─────────────────────────────────────────────
# Phase 1 — New agent outputs
# ─────────────────────────────────────────────
class NewsSentimentReport(BaseMessage):
    overall_sentiment:   float
    market_moving_events: list[dict]
    symbol_sentiment:    dict[str, dict]
    sector_sentiment:    dict[str, float]
    macro_alerts:        list[str]
    earnings_calendar:   list[dict]
    watchlist_flags:     dict[str, str]


class MacroIntelReport(BaseMessage):
    macro_regime:            str
    regime_confidence:       float
    regime_description:      str
    risk_budget_adjustment:  dict
    sector_overweights:      list[str]
    sector_underweights:     list[str]
    key_indicators:          dict
    macro_risks:             list[str]
    macro_tailwinds:         list[str]
    india_specific:          dict = Field(default_factory=dict)
    mandate_override:        dict = Field(default_factory=dict)


class OptionsFlowReport(BaseMessage):
    flow_signals:           list[dict]
    market_wide_indicators: dict
    hedging_demand:         str
    summary:                str


class EarningsCalendarReport(BaseMessage):
    upcoming_earnings:       list[dict]
    recent_earnings_results: list[dict]
    watchlist_earnings_risk: dict
    overall_earnings_season: str


# ─────────────────────────────────────────────
# Analysis Layer
# ─────────────────────────────────────────────
class TradeProposal(BaseMessage):
    symbol:          str
    direction:       Literal["long", "short"]
    proposed_weight: float
    rationale:       str
    composite_score: float
    research_inputs: dict[str, Any]


class TechnicalAssessment(BaseMessage):
    symbol:           str
    setup_quality:    Literal["excellent", "good", "poor", "avoid"]
    entry_zone_low:   float
    entry_zone_high:  float
    stop_loss:        float
    take_profit_1:    float
    take_profit_2:    Optional[float] = None
    pattern:          str
    timing:           Literal["enter_now", "wait_pullback", "avoid"]


class RiskAssessment(BaseMessage):
    symbol:              str
    decision:            Literal["approved", "approved_resized", "rejected"]
    original_weight:     float
    approved_weight:     float
    rejection_reason:    Optional[str] = None
    portfolio_var_after: float
    concentration_check: bool
    drawdown_headroom:   float


# ─────────────────────────────────────────────
# Execution Layer
# ─────────────────────────────────────────────
class HumanReviewRequest(BaseModel):
    request_id:         UUID = Field(default_factory=uuid4)
    cycle_id:           UUID
    proposal:           TradeProposal
    technical:          TechnicalAssessment
    risk:               RiskAssessment
    estimated_notional: float
    expires_at:         datetime
    created_at:         datetime = Field(default_factory=datetime.utcnow)


class HumanDecision(BaseModel):
    review_request_id: UUID
    cycle_id:          UUID
    decision:          Literal["approved", "rejected", "resized"]
    override_weight:   Optional[float] = None
    notes:             Optional[str]   = None
    decided_at:        datetime = Field(default_factory=datetime.utcnow)
    decided_by:        str = "human"


class OrderInstruction(BaseMessage):
    symbol:       str
    direction:    Literal["long", "short"]
    qty:          float
    order_type:   Literal["market", "limit", "stop_limit"]
    limit_price:  Optional[float] = None
    stop_price:   Optional[float] = None
    algo:         Literal["vwap", "twap", "aggressive", "passive"] = "vwap"
    time_horizon: str = "2h"
    stop_loss:    float
    take_profit:  float


class ExecutionReport(BaseMessage):
    order_id:       str
    symbol:         str
    direction:      Literal["long", "short"]
    qty_filled:     float
    avg_fill_price: float
    slippage_bps:   float
    status:         Literal["filled", "partial", "failed"]
    fills:          list[dict] = Field(default_factory=list)


# ─────────────────────────────────────────────
# LangGraph State — Phase 1 + 2 extended
# ─────────────────────────────────────────────
CycleStatus = Literal[
    "running", "awaiting_human", "approved",
    "rejected", "executed", "failed"
]

from typing import TypedDict


class TradingState(TypedDict, total=False):
    # ── Core cycle config ─────────────────────────────────────
    cycle_id:      str
    mode:          Literal["short_term", "long_term"]
    mandate:       dict

    # ── Market routing ─────────────────────────────────────────
    market:        str        # "us" | "india"
    indian_broker: str        # "zerodha" | "upstox"
    user_id:       str

    # ── Phase 2: Strategy & RL ────────────────────────────────
    active_strategy:     str  # name from strategy_library
    strategy_override:   str  # force a specific strategy
    rl_weights:          dict # current UCB1 weights
    updated_rl_weights:  dict # after post-trade RL update
    portfolio_id:        str  # for multi-portfolio support
    capital_budget:      float

    # ── Phase 1: Intelligence agent outputs ──────────────────
    news_sentiment:      Optional[dict]  # NewsSentimentAgent output
    macro_intel:         Optional[dict]  # MacroIntelAgent output
    options_flow:        Optional[dict]  # OptionsFlowAgent output
    earnings_calendar:   Optional[dict]  # EarningsCalendarAgent output
    earnings_adjustments: dict           # symbol → size/stop adjustments
    phase1_context:      dict            # summarised for strategist

    # ── Core research outputs ─────────────────────────────────
    market_intel:  Optional[dict]
    fundamentals:  list[dict]
    quant_signals: list[dict]
    research_done: bool

    # ── Analysis outputs ──────────────────────────────────────
    proposals:             list[dict]
    technical_assessments: list[dict]
    risk_assessments:      list[dict]
    risk_veto:             bool

    # ── Human gate ────────────────────────────────────────────
    review_request: Optional[dict]
    human_decision: Optional[dict]
    awaiting_human: bool
    auto_mode:      bool

    # ── Execution ─────────────────────────────────────────────
    order:            Optional[dict]
    execution_report: Optional[dict]
    broker_order_id:  Optional[str]

    # ── Post-trade ────────────────────────────────────────────
    compliance_flags: list[str]
    final_status:     str
    errors:           list[str]
    cycle_summary:    Optional[dict]

    # ── Memory context (loaded at cycle start) ────────────────
    past_similar_trades: list[dict]
    agent_reflections:   dict
    regime_history:      list[dict]
    portfolio_snapshot:  dict
