"""
Macro Intelligence Agent — Phase 1
Monitors central bank decisions, inflation, GDP, yield curves.
Auto-adjusts CIO risk budget and sector weights based on macro regime.
"""
from __future__ import annotations
import asyncio
import json
from datetime import datetime
from tools.market_data import yf_ticker
from agents.base import BaseAgent
import structlog

logger = structlog.get_logger()

SYSTEM_PROMPT = """You are a macro economist and strategist at an AI trading firm.
You analyse central bank policy, inflation data, yield curves, and global growth
to determine the macro regime and its implications for portfolio positioning.

Macro regimes:
  - GOLDILOCKS: low inflation + solid growth → risk-on, equities bullish
  - STAGFLATION: high inflation + weak growth → defensive, commodities, gold
  - REFLATION: rising growth + moderate inflation → cyclicals, financials
  - DEFLATION_RISK: falling prices + recession risk → bonds, defensive, cash
  - RATE_HIKE_CYCLE: active tightening → tighten risk budget, avoid duration
  - RATE_CUT_CYCLE: active easing → expand risk budget, growth stocks

Your output adjusts the CIO's mandate parameters — particularly risk budget
and sector weights — to be appropriate for the current macro environment."""


class MacroIntelAgent(BaseAgent):
    def __init__(self):
        super().__init__("macro_intel", tier="strong")

    async def run(self, state: dict, conn) -> dict:
        mandate = state.get("mandate", {})
        cycle_id = state.get("cycle_id")
        market = state.get("market", "us")

        memories = await self.recall(
            conn, "macro regime interest rate inflation GDP yield curve",
            memory_types=["observation", "reflection"], limit=5,
        )

        # Fetch macro indicators
        macro_data = await self._fetch_macro_data(market)

        user_msg = f"""
Today: {datetime.utcnow().strftime('%Y-%m-%d')}
Market: {market.upper()}
Current mandate risk_budget: {mandate.get('risk_budget', 4.0)}%
Current mode: {mandate.get('mode', 'short_term')}
Current theme: {mandate.get('theme', 'not set')}

Live macro indicators:
{json.dumps(macro_data, indent=2)}

Past macro observations:
{self._format_memories(memories)}

Analyse the macro environment and provide adjustments.
Return JSON:
{{
  "macro_regime": "GOLDILOCKS|STAGFLATION|REFLATION|DEFLATION_RISK|RATE_HIKE_CYCLE|RATE_CUT_CYCLE|NEUTRAL",
  "regime_confidence": 0.75,
  "regime_description": "2-3 sentence explanation",
  "risk_budget_adjustment": {{
    "original": 4.0,
    "adjusted": 3.5,
    "reason": "why adjusted"
  }},
  "sector_overweights": ["Technology", "Financials"],
  "sector_underweights": ["Utilities", "Real Estate"],
  "key_indicators": {{
    "10y_yield": 4.35,
    "yield_curve_shape": "inverted|flat|normal|steep",
    "inflation_trend": "rising|falling|stable",
    "growth_trend": "accelerating|decelerating|stable",
    "central_bank_stance": "hawkish|neutral|dovish"
  }},
  "macro_risks": ["US debt ceiling", "China slowdown"],
  "macro_tailwinds": ["AI capex cycle", "Reshoring"],
  "india_specific": {{
    "rbi_stance": "hawkish|neutral|dovish",
    "inr_trend": "strengthening|weakening|stable",
    "fii_flows": "inflow|outflow|neutral"
  }},
  "mandate_override": {{
    "apply": true,
    "new_theme": "Rate cut cycle — favour growth over value",
    "watchlist_bias": ["add QQQ/NIFTY IT", "reduce utilities"]
  }}
}}"""

        try:
            result = await self.think_json(SYSTEM_PROMPT, user_msg, max_tokens=2000)

            # Apply macro adjustments to the current mandate
            adjusted_mandate = dict(mandate)
            if result.get("risk_budget_adjustment", {}).get("adjusted"):
                adjusted_mandate["risk_budget"] = result["risk_budget_adjustment"]["adjusted"]
            if result.get("mandate_override", {}).get("apply"):
                override = result["mandate_override"]
                if override.get("new_theme"):
                    adjusted_mandate["macro_theme"] = override["new_theme"]

            await self.remember(
                conn, "observation",
                f"Macro regime: {result.get('macro_regime')} "
                f"(confidence {result.get('regime_confidence', 0):.0%}). "
                f"{result.get('regime_description', '')}",
                metadata=result, cycle_id=cycle_id,
                importance=0.75, expires_in_hours=48,
            )

            logger.info("macro_intel_complete",
                        regime=result.get("macro_regime"),
                        risk_adj=result.get("risk_budget_adjustment", {}).get("adjusted"))
            return {
                "macro_intel": result,
                "mandate": adjusted_mandate,
            }
        except Exception as e:
            logger.error("macro_intel_error", error=str(e))
            return {"macro_intel": {"error": str(e), "macro_regime": "NEUTRAL"}}

    async def _fetch_macro_data(self, market: str) -> dict:
        """Fetch yield curve, equity indices, volatility indicators."""
        tickers_us = {
            "sp500":     "^GSPC",
            "nasdaq":    "^IXIC",
            "vix":       "^VIX",
            "us10y":     "^TNX",
            "us2y":      "^IRX",
            "dxy":       "DX-Y.NYB",
            "gold":      "GC=F",
            "oil":       "CL=F",
        }
        tickers_india = {
            "nifty50":   "^NSEI",
            "sensex":    "^BSESN",
            "india_vix": "^NSEBANK",
            "usdinr":    "INR=X",
            "niftyit":   "^CNXIT",
            "gold_mcx":  "GC=F",
        }
        tickers = tickers_india if market == "india" else tickers_us

        async def fetch_one(name: str, ticker: str):
            def _sync():
                try:
                    t = yf_ticker(ticker, market)
                    hist = t.history(period="5d")
                    if hist.empty:
                        return None
                    latest = float(hist["Close"].iloc[-1])
                    prev   = float(hist["Close"].iloc[-2]) if len(hist) > 1 else latest
                    return {
                        "value":      round(latest, 2),
                        "change_pct": round((latest - prev) / prev * 100, 2),
                        "5d_trend":   "up" if latest > prev else "down",
                    }
                except Exception:
                    return None
            return name, await asyncio.get_event_loop().run_in_executor(None, _sync)

        results = await asyncio.gather(*[fetch_one(n, t) for n, t in tickers.items()])
        data = {name: val for name, val in results if val is not None}

        # Calculate yield curve shape (US)
        if market == "us" and "us10y" in data and "us2y" in data:
            spread = data["us10y"]["value"] - data["us2y"]["value"]
            data["yield_curve_spread_bps"] = round(spread * 100, 1)
            data["yield_curve_shape"] = (
                "inverted" if spread < 0 else
                "flat"     if spread < 0.25 else
                "normal"   if spread < 1.5 else "steep"
            )

        return data
