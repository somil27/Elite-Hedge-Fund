"""
Options Flow Agent — Phase 1
Monitors unusual options activity, IV spikes, and put/call ratios.
Identifies smart money positioning and feeds directional conviction signals.
"""
from __future__ import annotations
import asyncio
import json
from datetime import datetime
from tools.market_data import yf_ticker
from agents.base import BaseAgent
import structlog

logger = structlog.get_logger()

SYSTEM_PROMPT = """You are an options flow analyst at an AI trading firm.
You analyse options market data to identify unusual activity that signals
institutional positioning ahead of price moves.

Key signals you look for:
- Unusual call/put volume spikes (>3x average daily volume)
- Large block trades in near-term expiry options
- Implied volatility crush (before events) or expansion (uncertainty)
- Skew changes — put skew expensive = hedging demand; call skew = bullish bets
- Open interest build-up at specific strikes (support/resistance)

Output a signal score (-1.0 = strong put flow / bearish, +1.0 = strong call flow / bullish).
Always explain the specific option activity that drove the score."""


class OptionsFlowAgent(BaseAgent):
    def __init__(self):
        super().__init__("options_flow", tier="fast")

    async def run(self, state: dict, conn) -> dict:
        mandate = state.get("mandate", {})
        watchlist = mandate.get("watchlist", [])
        cycle_id = state.get("cycle_id")
        market = state.get("market", "us")

        if market == "india":
            # India F&O data — NSE has excellent options data
            return await self._run_india(state, conn, watchlist, cycle_id)

        memories = await self.recall(
            conn, "options flow implied volatility put call unusual activity",
            memory_types=["signal", "reflection"], limit=4,
        )

        options_data = await self._fetch_options_data(watchlist)

        user_msg = f"""
Today: {datetime.utcnow().strftime('%Y-%m-%d')}
Market: {market.upper()}
Watchlist: {watchlist}

Options market data:
{json.dumps(options_data, indent=2)}

Past options signals:
{self._format_memories(memories)}

Analyse the options flow and produce signals. Return JSON:
{{
  "flow_signals": [
    {{
      "symbol": "NVDA",
      "signal_score": 0.75,
      "signal_type": "unusual_call_volume|iv_spike|put_skew|call_skew|oi_buildup",
      "details": "3.2x average call volume in weekly $900 calls, 15k contracts",
      "iv_current": 45.2,
      "iv_percentile": 72,
      "put_call_ratio": 0.45,
      "dominant_expiry": "2025-02-07",
      "dominant_strike": 900,
      "smart_money_bias": "bullish|bearish|neutral",
      "confidence": 0.70
    }}
  ],
  "market_wide_indicators": {{
    "vix_level": 18.5,
    "vix_trend": "rising|falling|stable",
    "put_call_ratio_spx": 0.82,
    "fear_greed": "fear|neutral|greed"
  }},
  "hedging_demand": "high|medium|low",
  "summary": "brief summary of overall options sentiment"
}}"""

        try:
            result = await self.think_json(SYSTEM_PROMPT, user_msg, max_tokens=2000)

            for signal in result.get("flow_signals", []):
                if abs(signal.get("signal_score", 0)) > 0.5:
                    await self.remember(
                        conn, "signal",
                        f"Options flow {signal.get('symbol')}: "
                        f"score={signal.get('signal_score'):.2f}, "
                        f"type={signal.get('signal_type')}, "
                        f"detail={signal.get('details', '')[:100]}",
                        metadata=signal, cycle_id=cycle_id,
                        importance=0.7, expires_in_hours=48,
                    )

            logger.info("options_flow_complete",
                        signals=len(result.get("flow_signals", [])))
            return {"options_flow": result}

        except Exception as e:
            logger.error("options_flow_error", error=str(e))
            return {"options_flow": {"error": str(e), "flow_signals": []}}

    async def _fetch_options_data(self, symbols: list[str]) -> dict:
        """Fetch options chain data via yfinance."""
        data = {}

        async def fetch_one(symbol: str):
            def _sync():
                try:
                    ticker = yf_ticker(symbol)
                    info   = ticker.fast_info
                    price  = float(getattr(info, "last_price", 0) or 0)

                    # Get nearest expiry options
                    expirations = ticker.options
                    if not expirations:
                        return {"symbol": symbol, "no_options": True}

                    exp = expirations[0]
                    chain = ticker.option_chain(exp)
                    calls = chain.calls
                    puts  = chain.puts

                    total_call_vol = int(calls["volume"].fillna(0).sum())
                    total_put_vol  = int(puts["volume"].fillna(0).sum())
                    pcr = round(total_put_vol / max(total_call_vol, 1), 2)

                    # Find ATM options
                    if not calls.empty and price > 0:
                        calls["strike_diff"] = abs(calls["strike"] - price)
                        atm_call = calls.nsmallest(1, "strike_diff").iloc[0]
                        iv_atm = float(atm_call.get("impliedVolatility", 0) or 0) * 100
                    else:
                        iv_atm = 0

                    return {
                        "symbol":            symbol,
                        "price":             price,
                        "nearest_expiry":    exp,
                        "call_volume":       total_call_vol,
                        "put_volume":        total_put_vol,
                        "put_call_ratio":    pcr,
                        "iv_atm_pct":        round(iv_atm, 1),
                        "call_oi":           int(calls["openInterest"].fillna(0).sum()),
                        "put_oi":            int(puts["openInterest"].fillna(0).sum()),
                        "top_call_strike":   float(calls.nlargest(1, "volume")["strike"].iloc[0])
                                             if not calls.empty else 0,
                        "top_put_strike":    float(puts.nlargest(1, "volume")["strike"].iloc[0])
                                             if not puts.empty else 0,
                    }
                except Exception as e:
                    return {"symbol": symbol, "error": str(e)}

            return symbol, await asyncio.get_event_loop().run_in_executor(None, _sync)

        # Only run for US symbols that have listed options
        us_symbols = [s for s in symbols[:5] if not s.endswith(".NS") and not s.endswith(".BO")]
        results = await asyncio.gather(*[fetch_one(s) for s in us_symbols])
        for symbol, d in results:
            data[symbol] = d
        return data

    async def _run_india(self, state, conn, watchlist, cycle_id) -> dict:
        """Simplified India F&O flow — uses NIFTY PCR and sector OI."""
        memories = await self.recall(
            conn, "NSE options NIFTY put call open interest",
            memory_types=["signal", "reflection"], limit=4,
        )

        # Fetch NIFTY and BANKNIFTY as proxies
        nifty_data = await self._fetch_options_data(["^NSEI"])

        user_msg = f"""
Indian market F&O analysis. Today: {datetime.utcnow().strftime('%Y-%m-%d')}
Watchlist (NSE): {watchlist}

NIFTY options data:
{json.dumps(nifty_data, indent=2)}

Past signals:
{self._format_memories(memories)}

Analyse India F&O market. Key points for India:
- NIFTY PCR > 1.2 = excessive put buying = contrarian bullish
- NIFTY PCR < 0.7 = excessive call buying = market may be overbought
- Max pain theory: NIFTY tends to expire near max pain strike
- FII option positioning is a key directional indicator

Return same JSON structure as US options with india_context added:
{{
  "flow_signals": [...],
  "india_context": {{
    "nifty_pcr": 0.95,
    "market_positioning": "neutral|bullish_bets|bearish_hedge",
    "sector_flows": {{"IT": "call_buildup", "Banking": "put_buying"}}
  }},
  "summary": "..."
}}"""

        try:
            result = await self.think_json(SYSTEM_PROMPT, user_msg, max_tokens=1500)
            result["market"] = "india"
            return {"options_flow": result}
        except Exception as e:
            return {"options_flow": {"error": str(e), "flow_signals": []}}
