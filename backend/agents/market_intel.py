"""
Market Intelligence Agent
Reads news, macro data, and sentiment. Returns market regime assessment.
"""
import json
from datetime import datetime
import asyncpg
from agents.base import BaseAgent
from tools.market_data import get_market_snapshot
import structlog

logger = structlog.get_logger()

SYSTEM_PROMPT = """You are the Market Intelligence analyst at an AI brokerage firm.
Your job is to assess the current market environment using news, macro data, and sentiment.

You determine:
- The current market regime (risk_on / risk_off / neutral / crisis)
- Key macro events and news that affect trading
- Sentiment score for the overall market
- Symbol-specific flags (unusual volume, news catalysts, etc.)

Be precise, data-driven, and concise. Your output feeds directly into trading decisions."""


class MarketIntelAgent(BaseAgent):
    def __init__(self):
        super().__init__("market_intelligence", tier="fast")

    async def run(self, state: dict, conn: asyncpg.Connection) -> dict:
        mandate = state.get("mandate", {})
        cycle_id = state.get("cycle_id")
        watchlist = mandate.get("watchlist", [])

        # Recall past regime observations
        memories = await self.recall(
            conn, "market regime sentiment macro",
            memory_types=["observation", "reflection"], limit=5,
        )

        # Get live market data
        market_data = await get_market_snapshot(watchlist, market=state.get("market"))

        user_msg = f"""
Today: {datetime.utcnow().strftime('%Y-%m-%d')}
Mandate theme: {mandate.get('theme', 'general')}
Watchlist: {watchlist}
Mode: {mandate.get('mode', 'short_term')}

Live market data:
{json.dumps(market_data, indent=2)}

Past observations from memory:
{self._format_memories(memories)}

Analyze the current market environment and return JSON:
{{
  "regime": "risk_on|risk_off|neutral|crisis",
  "macro_summary": "2-3 sentence brief on current macro environment",
  "notable_events": ["event1", "event2"],
  "sentiment_score": 0.3,
  "symbol_flags": {{"NVDA": "strong_momentum", "GLD": "safe_haven_demand"}},
  "confidence": 0.75
}}

Base your regime assessment on: VIX levels (if available), trend direction,
volume patterns, and any known macro catalysts.
"""
        result = await self.think_json(SYSTEM_PROMPT, user_msg, max_tokens=1500)

        # Store as observation memory
        await self.remember(
            conn, "observation",
            f"Market regime: {result.get('regime')}. {result.get('macro_summary', '')}",
            metadata={
                "regime": result.get("regime"),
                "sentiment_score": result.get("sentiment_score"),
                "symbol_flags": result.get("symbol_flags", {}),
            },
            cycle_id=cycle_id,
            importance=0.6,
            expires_in_hours=48,
        )

        result["cycle_id"] = cycle_id
        result["sender"] = "market_intelligence"
        logger.info("market_intel_complete", regime=result.get("regime"))
        return {"market_intel": result}
