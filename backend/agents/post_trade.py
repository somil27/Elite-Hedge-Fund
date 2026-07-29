"""
Post-trade agents:
- ComplianceAgent: checks regulatory rules
- PortfolioMonitorAgent: tracks P&L, drift, rebalance triggers
- ReportingAgent: generates audit logs and summaries
"""
import json
import uuid
from datetime import datetime
import asyncpg
from agents.base import BaseAgent
from core.memory import write_reflection
import structlog

logger = structlog.get_logger()


class ComplianceAgent(BaseAgent):
    def __init__(self):
        super().__init__("compliance_monitor", tier="fast")

    async def run(self, state: dict, conn: asyncpg.Connection) -> dict:
        cycle_id = state.get("cycle_id")
        order = state.get("order", {})
        execution_report = state.get("execution_report", {})

        if not execution_report:
            return {"compliance_flags": ["No execution to review"]}

        user_msg = f"""
Executed order:
{json.dumps(order, indent=2)}

Fill report:
{json.dumps(execution_report, indent=2)}

Check compliance with standard US equity trading rules:
1. No wash-sale violations (selling and rebuying within 30 days)
2. No market manipulation patterns (e.g. large orders at close)
3. Position limits (no single stock > 10% NAV)
4. Restricted securities list check
5. Short-sale locate requirement (if short)

Return JSON:
{{
  "flags": [],
  "status": "clean|flagged",
  "notes": "brief compliance note"
}}

flags: list of violation descriptions (empty if clean).
"""
        try:
            result = await self.think_json(
                "You are a compliance officer. Check trades for regulatory violations. "
                "Return only JSON.",
                user_msg, max_tokens=600,
            )
            flags = result.get("flags", [])
            if result.get("status") == "flagged":
                logger.warning("compliance_flagged", flags=flags)
                await self.remember(
                    conn, "observation",
                    f"Compliance flag on {order.get('symbol')}: {flags}",
                    metadata=result, cycle_id=cycle_id, importance=0.9,
                )
            return {"compliance_flags": flags}
        except Exception as e:
            return {"compliance_flags": [f"Compliance check error: {e}"]}


class PortfolioMonitorAgent(BaseAgent):
    def __init__(self):
        super().__init__("portfolio_monitor", tier="fast")

    async def run(self, state: dict, conn: asyncpg.Connection) -> dict:
        """
        Monitors live P&L after execution.
        In production this runs continuously; here we log the opening position.
        """
        cycle_id = state.get("cycle_id")
        execution_report = state.get("execution_report", {})
        order = state.get("order", {})

        if execution_report and execution_report.get("status") == "filled":
            await self.remember(
                conn, "observation",
                f"Position opened: {order.get('symbol')} {order.get('direction')} "
                f"@ {execution_report.get('avg_fill_price')}, "
                f"SL={order.get('stop_loss')}, TP={order.get('take_profit')}",
                metadata={
                    "symbol": order.get("symbol"),
                    "direction": order.get("direction"),
                    "entry_price": execution_report.get("avg_fill_price"),
                    "stop_loss": order.get("stop_loss"),
                    "take_profit": order.get("take_profit"),
                    "qty": execution_report.get("qty_filled"),
                },
                cycle_id=cycle_id, importance=0.8,
            )
            logger.info("portfolio_position_logged", symbol=order.get("symbol"))
        return {}


class ReportingAgent(BaseAgent):
    def __init__(self):
        super().__init__("reporting", tier="fast")

    async def run(self, state: dict, conn: asyncpg.Connection) -> dict:
        """Generates end-of-cycle summary and writes trade_outcomes row."""
        cycle_id = state.get("cycle_id")
        execution_report = state.get("execution_report", {})
        order = state.get("order", {})
        proposals = state.get("proposals", [])
        risk_assessments = state.get("risk_assessments", [])
        human_decision = state.get("human_decision", {})
        final_status = state.get("final_status", "unknown")

        # Write trade outcome to DB
        if execution_report and execution_report.get("status") == "filled":
            agent_signals = {}
            for p in proposals:
                if p.get("symbol") == order.get("symbol"):
                    agent_signals = p.get("research_inputs", {})
                    agent_signals["composite_score"] = p.get("composite_score")

            outcome_id = str(uuid.uuid4())
            await conn.execute("""
                INSERT INTO trade_outcomes
                    (id, cycle_id, symbol, direction, entry_price, qty,
                     agent_signals, human_decision, opened_at)
                VALUES ($1::uuid, $2::uuid, $3, $4, $5, $6, $7, $8, now())
            """,
                outcome_id,
                cycle_id,
                order.get("symbol"),
                order.get("direction"),
                execution_report.get("avg_fill_price"),
                execution_report.get("qty_filled"),
                json.dumps(agent_signals),
                human_decision.get("decision") if human_decision else None,
            )

            # Write post-trade reflections for key agents
            trade_data = {
                "symbol": order.get("symbol"),
                "direction": order.get("direction"),
                "entry_price": execution_report.get("avg_fill_price"),
                "qty": execution_report.get("qty_filled"),
                "agent_signals": agent_signals,
                "slippage_bps": execution_report.get("slippage_bps"),
                "pnl_pct": None,   # filled when trade closes
                "close_reason": None,
            }
            for agent_id in ["portfolio_strategist", "risk_manager", "quant_researcher"]:
                await write_reflection(conn, agent_id, cycle_id, trade_data)

        # Mark cycle complete
        await conn.execute("""
            UPDATE trade_cycles
            SET status = $1, completed_at = now()
            WHERE id = $2::uuid
        """, final_status, cycle_id)

        summary = {
            "cycle_id": cycle_id,
            "status": final_status,
            "symbol": order.get("symbol") if order else None,
            "direction": order.get("direction") if order else None,
            "fill_price": execution_report.get("avg_fill_price") if execution_report else None,
            "qty": execution_report.get("qty_filled") if execution_report else None,
            "proposals_count": len(proposals),
            "risk_approved": sum(1 for r in risk_assessments
                                 if r.get("decision") in ("approved", "approved_resized")),
            "human_decision": human_decision.get("decision") if human_decision else "auto",
            "completed_at": datetime.utcnow().isoformat(),
        }

        await self.remember(
            conn, "observation",
            f"Cycle {cycle_id} completed: status={final_status}, "
            f"traded={order.get('symbol') if order else 'none'}",
            metadata=summary, cycle_id=cycle_id, importance=0.7,
        )
        logger.info("cycle_complete", **summary)
        return {"cycle_summary": summary}
