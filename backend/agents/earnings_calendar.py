"""
Earnings Calendar Agent — Phase 1
Tracks upcoming earnings, manages pre-earnings risk,
and triggers re-evaluation on surprise outcomes.
"""
from __future__ import annotations
import asyncio
import json
from datetime import datetime
from tools.market_data import yf_ticker
from agents.base import BaseAgent
import structlog

logger = structlog.get_logger()

SYSTEM_PROMPT = """You are an earnings analyst at an AI trading firm.
You track earnings calendars, estimate surprise potential, and recommend
position adjustments before and after earnings releases.

Pre-earnings rules:
- Earnings within 3 days: reduce position size by 40-60%
- Earnings within 7 days: widen stop-loss by 20%
- Whisper numbers often differ from consensus — check historical beat rate

Post-earnings rules:
- Beat > 5%: consider adding to position if trend intact
- Miss > 5%: re-evaluate thesis immediately
- Guidance raise: strong positive signal
- Guidance cut: strong negative signal, consider exit"""


class EarningsCalendarAgent(BaseAgent):
    def __init__(self):
        super().__init__("earnings_calendar", tier="fast")

    async def run(self, state: dict, conn) -> dict:
        mandate = state.get("mandate", {})
        watchlist = mandate.get("watchlist", [])
        cycle_id  = state.get("cycle_id")

        memories = await self.recall(
            conn, "earnings surprise beat miss guidance EPS revenue",
            memory_types=["observation", "reflection"], limit=5,
        )

        market = state.get("market", "us")
        calendar_data = await self._fetch_earnings_data(watchlist, market=market)

        user_msg = f"""
Today: {datetime.utcnow().strftime('%Y-%m-%d')}
Watchlist: {watchlist}
Mode: {mandate.get('mode', 'short_term')}

Earnings data for watchlist:
{json.dumps(calendar_data, indent=2)}

Past earnings observations:
{self._format_memories(memories)}

Analyse the earnings calendar and produce risk adjustments.
Return JSON:
{{
  "upcoming_earnings": [
    {{
      "symbol": "MSFT",
      "expected_date": "2025-01-29",
      "days_away": 5,
      "consensus_eps": 3.12,
      "consensus_revenue_b": 68.9,
      "historical_beat_rate": 0.85,
      "historical_avg_move_pct": 4.2,
      "risk_rating": "high|medium|low",
      "pre_earnings_action": {{
        "reduce_size_pct": 40,
        "widen_stop_pct": 20,
        "reasoning": "5 days to earnings, historical 4% avg move"
      }}
    }}
  ],
  "recent_earnings_results": [
    {{
      "symbol": "NVDA",
      "report_date": "2025-01-22",
      "eps_actual": 0.89,
      "eps_estimate": 0.84,
      "surprise_pct": 6.0,
      "revenue_actual_b": 39.3,
      "revenue_estimate_b": 37.1,
      "guidance": "raised|maintained|lowered",
      "stock_reaction_pct": 8.5,
      "post_earnings_action": "add_to_position|hold|reduce|exit",
      "reasoning": "Strong beat and raised guidance, momentum intact"
    }}
  ],
  "watchlist_earnings_risk": {{
    "AAPL": "low",
    "NVDA": "medium",
    "MSFT": "high"
  }},
  "overall_earnings_season": "beat_rate_above_avg|in_line|below_avg"
}}"""

        try:
            result = await self.think_json(SYSTEM_PROMPT, user_msg, max_tokens=2000)

            # Store high-risk earnings alerts as memories
            for item in result.get("upcoming_earnings", []):
                if item.get("days_away", 99) <= 7:
                    await self.remember(
                        conn, "observation",
                        f"Earnings alert: {item.get('symbol')} reports in "
                        f"{item.get('days_away')} days. "
                        f"Consensus EPS {item.get('consensus_eps')}, "
                        f"historical beat rate {item.get('historical_beat_rate', 0):.0%}, "
                        f"avg move {item.get('historical_avg_move_pct', 0):.1f}%",
                        metadata=item, cycle_id=cycle_id,
                        importance=0.8, expires_in_hours=24 * item.get("days_away", 7),
                    )

            # Apply earnings-based position adjustments to proposals
            adjustments = self._build_adjustments(result)

            logger.info("earnings_calendar_complete",
                        upcoming=len(result.get("upcoming_earnings", [])),
                        recent=len(result.get("recent_earnings_results", [])))
            return {
                "earnings_calendar": result,
                "earnings_adjustments": adjustments,
            }
        except Exception as e:
            logger.error("earnings_calendar_error", error=str(e))
            return {"earnings_calendar": {"error": str(e)}, "earnings_adjustments": {}}

    def _build_adjustments(self, result: dict) -> dict:
        """Build a symbol → adjustment map for the execution layer."""
        adj = {}
        for item in result.get("upcoming_earnings", []):
            symbol = item.get("symbol")
            days   = item.get("days_away", 99)
            if days <= 3:
                adj[symbol] = {"max_weight_multiplier": 0.5, "stop_multiplier": 1.25}
            elif days <= 7:
                adj[symbol] = {"max_weight_multiplier": 0.75, "stop_multiplier": 1.15}

        for item in result.get("recent_earnings_results", []):
            symbol = item.get("symbol")
            action = item.get("post_earnings_action", "hold")
            if action == "exit":
                adj[symbol] = {"max_weight_multiplier": 0.0, "force_exit": True}
            elif action == "reduce":
                adj[symbol] = {"max_weight_multiplier": 0.5}
        return adj

    async def _fetch_earnings_data(self, symbols: list[str], market: str = "us") -> dict:
        """Fetch earnings calendar and history via yfinance."""
        data = {}

        async def fetch_one(symbol: str):
            def _sync():
                try:
                    ticker = yf_ticker(symbol, market)
                    info   = ticker.info
                    cal    = ticker.calendar

                    # Parse calendar
                    next_earnings = None
                    if cal is not None and not (
                        hasattr(cal, "empty") and cal.empty
                    ):
                        if hasattr(cal, "to_dict"):
                            cal_dict = cal.to_dict()
                        elif isinstance(cal, dict):
                            cal_dict = cal
                        else:
                            cal_dict = {}

                        ed = cal_dict.get("Earnings Date", [None])
                        if isinstance(ed, list) and ed:
                            next_earnings = str(ed[0])[:10] if ed[0] else None
                        elif ed:
                            next_earnings = str(ed)[:10]

                    # Days until earnings
                    days_away = None
                    if next_earnings:
                        try:
                            delta = (
                                datetime.strptime(next_earnings, "%Y-%m-%d") -
                                datetime.utcnow()
                            ).days
                            days_away = max(0, delta)
                        except Exception:
                            pass

                    return {
                        "symbol":                 symbol,
                        "next_earnings_date":     next_earnings,
                        "days_until_earnings":    days_away,
                        "eps_trailing":           info.get("trailingEps"),
                        "eps_forward_estimate":   info.get("forwardEps"),
                        "revenue_estimate":       info.get("revenueEstimates"),
                        "earnings_growth_qoq":    info.get("earningsQuarterlyGrowth"),
                        "beta":                   info.get("beta"),
                        "sector":                 info.get("sector"),
                    }
                except Exception as e:
                    return {"symbol": symbol, "error": str(e)}

            return symbol, await asyncio.get_event_loop().run_in_executor(None, _sync)

        results = await asyncio.gather(*[fetch_one(s) for s in symbols[:6]])
        for symbol, d in results:
            data[symbol] = d
        return data
