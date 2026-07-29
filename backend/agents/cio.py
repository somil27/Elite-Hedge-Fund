"""
Updated CIO Agent — Phase 1 + 2
Sets mandate incorporating:
  - Phase 1: requests news, macro, options and earnings analysis
  - Phase 2: applies strategy library selection and RL weight context
  - Market-aware watchlists (US/India symbols)

Drop into: backend/agents/cio.py
"""
from __future__ import annotations
import json
from uuid import uuid4
from datetime import datetime
import asyncpg
from agents.base import BaseAgent
from core.memory import get_portfolio_context
import structlog

logger = structlog.get_logger()

SYSTEM_PROMPT = """You are the Chief Investment Officer of an AI-powered brokerage firm.
Your role is to set the investment mandate for each trading cycle.

You define:
1. The market theme and thesis (informed by macro regime and news)
2. A watchlist of 3-5 ticker symbols appropriate for the market and strategy
3. Risk budget (max VaR contribution %)
4. Time horizon appropriate for the mode and strategy
5. A brief rationale tying together all available intelligence

For SHORT_TERM mode: momentum, technical setups, quantitative signals.
For LONG_TERM mode: fundamentals, macro themes, value.

IMPORTANT: Use the provided macro regime, news sentiment, and strategy
context to make a more informed mandate. Do NOT ignore Phase 1 intelligence."""


class CIOAgent(BaseAgent):
    def __init__(self):
        super().__init__("cio", tier="strong")

    async def run(self, state: dict, conn: asyncpg.Connection) -> dict:
        mode     = state.get("mode", "short_term")
        cycle_id = state.get("cycle_id", str(uuid4()))
        market   = state.get("market", "us")
        indian_broker  = state.get("indian_broker", "")
        strategy_name  = state.get("active_strategy", "")
        portfolio_id   = state.get("portfolio_id", "")
        capital_budget = state.get("capital_budget", 0)

        # Load memory context
        past_regimes = await get_portfolio_context(conn)
        reflections  = await self.recall(
            conn,
            f"investment mandate {mode} trading strategy",
            memory_types=["reflection"],
            limit=4,
        )
        memory_context = self._format_memories(past_regimes + reflections)

        # Pull Phase 1 intelligence if already available in state
        news_sentiment  = state.get("news_sentiment", {}) or {}
        macro_intel     = state.get("macro_intel", {}) or {}
        options_flow    = state.get("options_flow", {}) or {}
        earnings_cal    = state.get("earnings_calendar", {}) or {}

        # Build Phase 1 summary block
        p1_summary = self._summarise_phase1(
            news_sentiment, macro_intel, options_flow, earnings_cal
        )

        # Market-specific symbol guidance
        if market == "india":
            market_label = f"INDIA ({indian_broker.upper()})"
            symbol_guidance = (
                "Use NSE-listed symbols only. Examples: RELIANCE, TCS, INFY, "
                "HDFCBANK, ICICIBANK, WIPRO, BHARTIARTL, ITC, KOTAKBANK, "
                "AXISBANK, HINDUNILVR, BAJFINANCE, SBIN, MARUTI, TATAMOTORS, "
                "NIFTY50 components. Use plain ticker (no .NS suffix)."
            )
        else:
            market_label = "US"
            symbol_guidance = (
                "Use actively traded US equities. Examples: AAPL, NVDA, MSFT, "
                "TSLA, AMZN, META, GOOGL, AMD, NFLX, GLD, SPY, QQQ."
            )

        user_msg = f"""
Current mode:     {mode.upper()}
Market:           {market_label}
Strategy:         {strategy_name or 'auto-select'}
Portfolio:        {portfolio_id or 'default'}
Capital budget:   {'$' + str(int(capital_budget)) if capital_budget else 'default'}
Today:            {datetime.utcnow().strftime('%Y-%m-%d')}

{p1_summary}

Past cycles and reflections:
{memory_context}

Symbol guidance: {symbol_guidance}

Generate a trading cycle mandate. Return JSON:
{{
  "theme": "brief market thesis (1 sentence incorporating macro + news context)",
  "watchlist": ["TICK1", "TICK2", "TICK3"],
  "risk_budget": 4.0,
  "time_horizon": "3-10 days",
  "agent_weights": {{
    "market_intel": 0.20,
    "fundamental":  0.20,
    "quant":        0.40,
    "news":         0.10,
    "macro":        0.10
  }},
  "rationale": "2-3 sentences explaining the mandate given current conditions"
}}

Mode guidance:
  short_term → boost quant (0.40-0.55), tighter risk_budget (3-5)
  long_term  → boost fundamental (0.40-0.50), wider risk_budget (4-6)

Adjust weights based on Phase 1 signals:
  - High news magnitude events → boost news weight
  - Strong macro regime signal  → boost macro weight
  - Unusual options activity    → boost quant weight
  - Earnings within 7 days      → reduce risk_budget by 20%"""

        mandate_data = await self.think_json(SYSTEM_PROMPT, user_msg)
        mandate_data["mode"]         = mode
        mandate_data["cycle_id"]     = cycle_id
        mandate_data["market"]       = market
        mandate_data["indian_broker"] = indian_broker
        mandate_data["strategy"]     = strategy_name
        mandate_data["portfolio_id"] = portfolio_id

        # Store mandate as memory
        await self.remember(
            conn, "analysis",
            f"CIO mandate [{market}/{mode}]: theme='{mandate_data.get('theme')}', "
            f"strategy={strategy_name}, watchlist={mandate_data.get('watchlist')}, "
            f"macro_regime={macro_intel.get('macro_regime', 'unknown')}",
            metadata=mandate_data,
            cycle_id=cycle_id,
            importance=0.65,
        )

        # Update trade_cycles table with the generated mandate
        await conn.execute("""
            UPDATE trade_cycles
            SET cio_mandate = $1
            WHERE id = $2::uuid
        """, json.dumps(mandate_data), cycle_id)

        logger.info("cio_mandate_set",
                    mode=mode, market=market,
                    strategy=strategy_name,
                    watchlist=mandate_data.get("watchlist"),
                    regime=macro_intel.get("macro_regime", "unknown"))

        return {
            "cycle_id":  cycle_id,
            "mandate":   mandate_data,
            "research_done": False,
            "risk_veto":     False,
            "awaiting_human": False,
            "auto_mode":  state.get("auto_mode", False),
            "proposals":  [],
            "fundamentals": [],
            "quant_signals": [],
            "technical_assessments": [],
            "risk_assessments": [],
            "compliance_flags": [],
            "errors": [],
            "final_status": "running",
        }

    def _summarise_phase1(
        self,
        news: dict,
        macro: dict,
        options: dict,
        earnings: dict,
    ) -> str:
        """Build a concise Phase 1 context block for the CIO prompt."""
        lines = ["Phase 1 Intelligence Summary:"]

        # News
        if news and not news.get("error"):
            score  = news.get("overall_sentiment", 0)
            events = news.get("market_moving_events", [])
            flags  = news.get("watchlist_flags", {})
            lines.append(
                f"  News: overall_sentiment={score:+.2f}, "
                f"high-impact events={sum(1 for e in events if e.get('magnitude')=='high')}, "
                f"flags={json.dumps(flags)}"
            )

        # Macro
        if macro and not macro.get("error"):
            regime = macro.get("macro_regime", "NEUTRAL")
            conf   = macro.get("regime_confidence", 0)
            adj    = macro.get("risk_budget_adjustment", {})
            over   = macro.get("sector_overweights", [])
            under  = macro.get("sector_underweights", [])
            lines.append(
                f"  Macro: regime={regime} (conf={conf:.0%}), "
                f"risk_adj={adj.get('adjusted', 'none')}, "
                f"overweight={over}, underweight={under}"
            )

        # Options
        if options and not options.get("error"):
            signals = options.get("flow_signals", [])
            hedging = options.get("hedging_demand", "unknown")
            strong  = [s for s in signals if abs(s.get("signal_score", 0)) > 0.5]
            strong_formatted = [f"{s['symbol']}:{s['signal_score']:+.2f}" for s in strong]
            lines.append(
                f"  Options: hedging_demand={hedging}, "
                f"strong signals={strong_formatted}"
            )

        # Earnings
        if earnings and not earnings.get("error"):
            upcoming = earnings.get("upcoming_earnings", [])
            close    = [e for e in upcoming if (e.get("days_away") or 99) <= 7]
            lines.append(
                f"  Earnings: {len(upcoming)} upcoming, "
                f"{len(close)} within 7 days: {[e.get('symbol') for e in close]}"
            )

        if len(lines) == 1:
            return "Phase 1 Intelligence: Not yet available (first agent run)"
        return "\n".join(lines)
