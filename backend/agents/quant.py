"""
Quant Researcher Agent
Computes momentum, mean-reversion, and technical signals from price data.
"""
import json
from datetime import datetime
import asyncpg
from agents.base import BaseAgent
from tools.market_data import get_price_history, compute_indicators
import structlog

logger = structlog.get_logger()

SYSTEM_PROMPT = """You are the Quantitative Researcher at an AI brokerage firm.
You analyze price/volume data and statistical signals.

You produce:
- Signal type and strength (-1.0 = strong short, +1.0 = strong long)
- Entry trigger conditions
- Expected hold period
- Simulated backtest metrics (Sharpe, win rate)

Be quantitative. Reference specific price levels, moving averages, and statistical measures."""


class QuantAgent(BaseAgent):
    def __init__(self):
        super().__init__("quant_researcher", tier="fast")

    async def run(self, state: dict, conn: asyncpg.Connection) -> dict:
        mandate = state.get("mandate", {})
        cycle_id = state.get("cycle_id")
        watchlist = mandate.get("watchlist", [])
        mode = mandate.get("mode", "short_term")

        signals = []
        for symbol in watchlist[:3]:
            memories = await self.recall(
                conn, f"{symbol} momentum signal quantitative",
                memory_types=["signal", "reflection"], limit=4,
            )
            price_data = await get_price_history(symbol, period="60d", market=state.get("market"))
            indicators = await compute_indicators(price_data)

            user_msg = f"""
Symbol: {symbol}
Mode: {mode}  (short_term = days/weeks, long_term = weeks/months)
Today: {datetime.utcnow().strftime('%Y-%m-%d')}

Price & indicators:
{json.dumps(indicators, indent=2)}

Past signals from memory:
{self._format_memories(memories)}

Analyze quantitative signals and return JSON:
{{
  "symbol": "{symbol}",
  "signal_type": "momentum|mean_reversion|breakout|factor|options_flow",
  "signal_score": 0.65,
  "entry_trigger": "specific price/indicator condition to enter",
  "backtest_sharpe": 1.45,
  "backtest_win_rate": 0.58,
  "suggested_hold": "5-10 days",
  "confidence": 0.70
}}

signal_score: -1.0 (strong short) to +1.0 (strong long), 0.0 = neutral.
Base on: RSI, MACD, Bollinger Bands, volume, price vs moving averages.
"""
            try:
                signal = await self.think_json(SYSTEM_PROMPT, user_msg, max_tokens=1000)
                signal["cycle_id"] = cycle_id
                signal["sender"] = "quant_researcher"

                await self.remember(
                    conn, "signal",
                    f"{symbol}: {signal.get('signal_type')} score={signal.get('signal_score'):.2f}. "
                    f"Trigger: {signal.get('entry_trigger')}",
                    metadata=signal, cycle_id=cycle_id,
                    importance=0.6,
                    expires_in_hours=72,
                )
                signals.append(signal)
                logger.info("quant_signal", symbol=symbol, score=signal.get("signal_score"))
            except Exception as e:
                logger.error("quant_error", symbol=symbol, error=str(e))

        return {"quant_signals": signals, "research_done": True}
