"""
Technical Analyst Agent (Phase 5 - Vision Enabled)
Reviews chart patterns, entry zones, stop-loss, and take-profit levels.
Now supports Vision capabilities to visually analyze charts.
"""
import json
from datetime import datetime
import asyncpg
from agents.base import BaseAgent
from tools.market_data import get_price_history, compute_indicators
import structlog

logger = structlog.get_logger()

SYSTEM_PROMPT = """You are the Technical Analyst at an AI brokerage firm.
You are a highly advanced multimodal model capable of seeing and analyzing price charts.
You review price charts, raw price data, and technical indicators to determine entry quality, timing, and price targets.

You produce:
- Setup quality rating (excellent/good/poor/avoid)
- Entry zone (price range to enter)
- Stop-loss level (max acceptable loss)
- Take-profit targets (TP1 required, TP2 optional)
- Timing recommendation (enter now / wait for pullback / avoid)

Use specific price levels. Reference patterns: flags, breakouts, support/resistance,
moving average crossovers, RSI divergence, volume confirmation. 
If an image of a chart is provided, use visual evidence to strengthen your analysis."""


class TechnicalAnalystAgent(BaseAgent):
    def __init__(self):
        super().__init__("technical_analyst", tier="fast")
        
    def _get_mock_chart_image(self, symbol: str) -> str:
        """
        Placeholder for fetching a real base64 encoded chart image.
        In production, this would use a charting library (like mplfinance)
        or an API (like Polygon snapshot) to get a real image of the chart.
        """
        # Return a tiny 1x1 transparent PNG as a placeholder for multimodal testing
        return "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="

    async def run(self, state: dict, conn: asyncpg.Connection) -> dict:
        cycle_id = state.get("cycle_id")
        proposals = state.get("proposals", [])

        assessments = []
        for proposal in proposals:
            symbol = proposal.get("symbol")
            direction = proposal.get("direction", "long")

            memories = await self.recall(
                conn, f"{symbol} technical chart pattern entry",
                memory_types=["analysis", "reflection"], limit=3,
            )
            price_data = await get_price_history(symbol, period="90d")
            indicators = await compute_indicators(price_data)
            
            # Phase 5: Fetch visual chart
            chart_base64 = self._get_mock_chart_image(symbol)

            user_msg_text = f"""
Symbol: {symbol}
Proposed direction: {direction}
Today: {datetime.utcnow().strftime('%Y-%m-%d')}

Price & technical indicators:
{json.dumps(indicators, indent=2)}

Past technical observations:
{self._format_memories(memories)}

Assess the technical setup and return JSON:
{{
  "symbol": "{symbol}",
  "setup_quality": "excellent|good|poor|avoid",
  "entry_zone_low": 145.0,
  "entry_zone_high": 148.0,
  "stop_loss": 140.5,
  "take_profit_1": 158.0,
  "take_profit_2": 165.0,
  "pattern": "bull flag breakout on strong volume",
  "timing": "enter_now|wait_pullback|avoid"
}}

For LONG: stop_loss < current_price < entry_zone < take_profit
For SHORT: take_profit < entry_zone < current_price < stop_loss
Risk/reward must be at least 1.5:1 for "good" or better quality.
"""
            
            # Construct multimodal payload
            if self.provider == "gemini":
                user_msg = [
                    user_msg_text,
                    {"mime_type": "image/png", "data": chart_base64}
                ]
            else:
                user_msg = [
                    {"type": "text", "text": user_msg_text},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{chart_base64}"}
                    }
                ]

            try:
                # Agent uses think_json which now routes the multimodal list to the LLM
                assessment = await self.think_json(SYSTEM_PROMPT, user_msg, max_tokens=1000)
                assessment["cycle_id"] = cycle_id
                assessment["sender"] = "technical_analyst"
                assessment["vision_enabled"] = True

                await self.remember(
                    conn, "analysis",
                    f"{symbol}: {assessment.get('setup_quality')} setup — "
                    f"{assessment.get('pattern')}. Entry {assessment.get('entry_zone_low')}-"
                    f"{assessment.get('entry_zone_high')}, SL {assessment.get('stop_loss')}",
                    metadata=assessment, cycle_id=cycle_id, importance=0.6,
                )
                assessments.append(assessment)
                logger.info("technical_assessment", symbol=symbol,
                            quality=assessment.get("setup_quality"), vision=True)
            except Exception as e:
                logger.error("technical_error", symbol=symbol, error=str(e))

        return {"technical_assessments": assessments}

