"""
Fundamental Analyst Agent
Analyzes financial statements, valuation, and produces buy/sell ratings.
"""
import json
from datetime import datetime
import asyncpg
from agents.base import BaseAgent
from tools.market_data import get_fundamental_data
import structlog

logger = structlog.get_logger()

SYSTEM_PROMPT = """You are the Fundamental Analyst at an AI brokerage firm.
You analyze company financials, valuation multiples, and business quality.

Your output:
- Fair value estimate (DCF/comparable company analysis)
- Buy/sell rating with conviction level
- Key investment thesis (why this stock moves)
- Key risks to the thesis

Be rigorous. Use real financial metrics. Flag if data is unavailable."""


class FundamentalAgent(BaseAgent):
    def __init__(self):
        super().__init__("fundamental_analyst", tier="fast")

    async def run(self, state: dict, conn: asyncpg.Connection) -> dict:
        mandate = state.get("mandate", {})
        cycle_id = state.get("cycle_id")
        watchlist = mandate.get("watchlist", [])
        mode = mandate.get("mode", "short_term")

        reports = []
        for symbol in watchlist[:3]:   # analyze top 3 to keep latency manageable
            memories = await self.recall(
                conn, f"{symbol} fundamental valuation earnings",
                memory_types=["analysis", "reflection"], limit=4,
            )
            fund_data = await get_fundamental_data(symbol, market=state.get("market"))

            user_msg = f"""
Symbol: {symbol}
Mode: {mode}
Today: {datetime.utcnow().strftime('%Y-%m-%d')}

Financial data:
{json.dumps(fund_data, indent=2)}

Past analyses from memory:
{self._format_memories(memories)}

Produce a fundamental analysis. Return JSON:
{{
  "symbol": "{symbol}",
  "fair_value": 150.0,
  "current_price": 142.5,
  "upside_pct": 5.3,
  "thesis": "One sentence investment thesis",
  "key_risks": ["risk1", "risk2"],
  "metrics": {{
    "pe_fwd": 28.5,
    "ev_ebitda": 22.1,
    "revenue_growth_yoy": 0.18,
    "gross_margin": 0.62,
    "fcf_yield": 0.035
  }},
  "rating": "buy",
  "confidence": 0.72
}}

Rating options: strong_buy, buy, hold, sell, strong_sell.
If data is limited, use reasonable estimates and lower confidence.
"""
            try:
                report = await self.think_json(SYSTEM_PROMPT, user_msg, max_tokens=1200)
                report["cycle_id"] = cycle_id
                report["sender"] = "fundamental_analyst"

                await self.remember(
                    conn, "analysis",
                    f"{symbol}: {report.get('rating')} @ fair value {report.get('fair_value')}. "
                    f"{report.get('thesis')}",
                    metadata=report, cycle_id=cycle_id,
                    importance=0.65,
                )
                reports.append(report)
                logger.info("fundamental_report", symbol=symbol, rating=report.get("rating"))
            except Exception as e:
                logger.error("fundamental_error", symbol=symbol, error=str(e))

        return {"fundamentals": reports}
