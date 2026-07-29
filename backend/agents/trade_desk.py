"""
Trade Desk / OMS Agent
Converts approved risk assessments into order instructions.
Triggers the human review gate or passes straight to execution in auto mode.
"""
import json
from datetime import datetime, timedelta
from uuid import uuid4
import asyncpg
from agents.base import BaseAgent
import structlog

logger = structlog.get_logger()

SYSTEM_PROMPT = """You are the Trade Desk (OMS) at an AI brokerage firm.
You convert approved trade proposals into precise order instructions.

You determine:
- Order type (market/limit/stop_limit)
- Execution algorithm (vwap/twap/aggressive/passive)
- Time horizon for execution
- Final stop-loss and take-profit levels from technical assessment

For market orders in liquid stocks: use VWAP algo during market hours.
For less liquid: use TWAP to minimize impact.
For momentum breakouts: use aggressive.
For mean-reversion entries: use passive (limit orders)."""


class TradeDeskAgent(BaseAgent):
    def __init__(self):
        super().__init__("trade_desk", tier="fast")

    async def run(self, state: dict, conn: asyncpg.Connection) -> dict:
        cycle_id = state.get("cycle_id")
        proposals = state.get("proposals", [])
        risk_assessments = state.get("risk_assessments", [])
        technical_assessments = state.get("technical_assessments", [])
        auto_mode = state.get("auto_mode", False)
        portfolio_snapshot = state.get("portfolio_snapshot", {})

        # Build lookup maps
        risk_map = {r.get("symbol"): r for r in risk_assessments}
        tech_map = {t.get("symbol"): t for t in technical_assessments}
        proposal_map = {p.get("symbol"): p for p in proposals}

        # Find approved trades
        approved = [r for r in risk_assessments
                    if r.get("decision") in ("approved", "approved_resized")]

        if not approved:
            logger.warning("no_approved_trades")
            return {"final_status": "rejected", "order": None}

        # Pick the best single trade (highest composite score among approved)
        best_symbol = None
        best_score = -1
        for r in approved:
            sym = r.get("symbol")
            proposal = proposal_map.get(sym, {})
            score = proposal.get("composite_score", 0)
            if score > best_score:
                best_score = score
                best_symbol = sym

        risk = risk_map.get(best_symbol, {})
        tech = tech_map.get(best_symbol, {})
        proposal = proposal_map.get(best_symbol, {})

        # Estimate portfolio value (default $100k for paper trading)
        portfolio_value = portfolio_snapshot.get("total_value", 100_000)
        approved_weight = risk.get("approved_weight", 0.02)
        notional = portfolio_value * approved_weight

        # Build order via LLM
        user_msg = f"""
Symbol: {best_symbol}
Direction: {proposal.get('direction', 'long')}
Approved weight: {approved_weight} ({notional:.2f} USD notional)
Portfolio value: {portfolio_value}

Technical assessment:
{json.dumps(tech, indent=2)}

Risk assessment:
{json.dumps(risk, indent=2)}

Proposal rationale: {proposal.get('rationale', '')}

Build an order instruction. Return JSON:
{{
  "symbol": "{best_symbol}",
  "direction": "{proposal.get('direction', 'long')}",
  "qty": 10.5,
  "order_type": "market|limit|stop_limit",
  "limit_price": null,
  "stop_price": null,
  "algo": "vwap|twap|aggressive|passive",
  "time_horizon": "2h",
  "stop_loss": 140.0,
  "take_profit": 158.0
}}

qty = notional / current_price (estimate from entry_zone midpoint).
Use stop_loss from technical assessment.
Use take_profit_1 as take_profit.
"""
        try:
            order = await self.think_json(SYSTEM_PROMPT, user_msg, max_tokens=800)
            order["cycle_id"] = cycle_id
            order["sender"] = "trade_desk"

            # Build human review request
            review = {
                "request_id": str(uuid4()),
                "cycle_id": cycle_id,
                "proposal": proposal,
                "technical": tech,
                "risk": risk,
                "order": order,
                "estimated_notional": notional,
                "expires_at": (datetime.utcnow() + timedelta(minutes=30)).isoformat(),
                "created_at": datetime.utcnow().isoformat(),
            }

            if auto_mode:
                logger.info("auto_mode_bypass_human_gate", symbol=best_symbol)
                return {
                    "order": order,
                    "review_request": review,
                    "awaiting_human": False,
                    "human_decision": {
                        "decision": "approved",
                        "decided_by": "auto",
                        "cycle_id": cycle_id,
                    },
                }
            else:
                logger.info("awaiting_human_approval", symbol=best_symbol)
                return {
                    "order": order,
                    "review_request": review,
                    "awaiting_human": True,
                    "final_status": "awaiting_human",
                }
        except Exception as e:
            logger.error("trade_desk_error", error=str(e))
            return {"errors": [f"Trade desk error: {e}"], "final_status": "failed"}
