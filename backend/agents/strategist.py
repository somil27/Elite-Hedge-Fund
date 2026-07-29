"""
Portfolio Strategist Agent
Synthesizes all research into sized trade proposals.
"""
import json
from datetime import datetime
import asyncpg
from agents.base import BaseAgent
import structlog

logger = structlog.get_logger()

SYSTEM_PROMPT = """You are the Portfolio Strategist at an AI brokerage firm.
You synthesize research from Market Intelligence, Fundamental, and Quant agents
into concrete, sized trade proposals.

Sizing rules:
- Max single position: 5% of portfolio
- Default conviction range: 1-3% of portfolio
- Higher conviction (composite_score > 0.75): up to 4%
- Scale down for risk_off regime or low confidence research
- Never propose both long and short the same symbol

Output actionable proposals with clear rationale."""


class PortfolioStrategistAgent(BaseAgent):
    def __init__(self):
        super().__init__("portfolio_strategist", tier="fast")

    async def run(self, state: dict, conn: asyncpg.Connection) -> dict:
        mandate = state.get("mandate", {})
        cycle_id = state.get("cycle_id")
        market_intel = state.get("market_intel", {})
        fundamentals = state.get("fundamentals", [])
        quant_signals = state.get("quant_signals", [])
        agent_weights = mandate.get("agent_weights", {
            "market_intel": 0.25, "fundamental": 0.25, "quant": 0.50
        })

        memories = await self.recall(
            conn, "portfolio allocation sizing trade proposals",
            memory_types=["analysis", "reflection"], limit=4,
        )

        user_msg = f"""
Today: {datetime.utcnow().strftime('%Y-%m-%d')}
Mandate theme: {mandate.get('theme')}
Mode: {mandate.get('mode')}
Risk budget: {mandate.get('risk_budget', 4.0)}% VaR
Agent weights: {json.dumps(agent_weights)}

Market Intel:
- Regime: {market_intel.get('regime', 'unknown')}
- Sentiment: {market_intel.get('sentiment_score', 0)}
- Summary: {market_intel.get('macro_summary', '')}

Fundamental Reports:
{json.dumps(fundamentals, indent=2)}

Quant Signals:
{json.dumps(quant_signals, indent=2)}

Past allocation decisions:
{self._format_memories(memories)}

Synthesize into trade proposals. Return JSON array:
[
  {{
    "symbol": "NVDA",
    "direction": "long",
    "proposed_weight": 0.03,
    "rationale": "Strong quant momentum + fundamental upside + risk_on regime",
    "composite_score": 0.78,
    "research_inputs": {{
      "fundamental_rating": "buy",
      "quant_score": 0.81,
      "regime": "risk_on",
      "sentiment": 0.4
    }}
  }}
]

Only propose trades where composite_score > 0.55.
Composite score = weighted average of available signals using agent_weights.
Max 3 proposals per cycle.
"""
        try:
            proposals_raw = await self.think_json(SYSTEM_PROMPT, user_msg, max_tokens=2000)
            # Handle both array and {"proposals": [...]} format
            if isinstance(proposals_raw, dict):
                proposals = proposals_raw.get("proposals", [proposals_raw])
            else:
                proposals = proposals_raw

            for p in proposals:
                p["cycle_id"] = cycle_id
                p["sender"] = "portfolio_strategist"

            await self.remember(
                conn, "analysis",
                f"Proposed {len(proposals)} trades: "
                + ", ".join(f"{p.get('symbol')} {p.get('direction')}" for p in proposals),
                metadata={"proposals": proposals},
                cycle_id=cycle_id, importance=0.7,
            )
            logger.info("proposals_created", count=len(proposals))
            return {"proposals": proposals}
        except Exception as e:
            logger.error("strategist_error", error=str(e))
            return {"proposals": [], "errors": [f"Strategist error: {e}"]}
