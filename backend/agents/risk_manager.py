"""
Risk Manager Agent (Phase 5 - Advanced Portfolio Math)
Gatekeeping agent with veto power. Checks VaR, concentration, drawdown headroom,
and applies Markowitz Efficient Frontier (Mean-Variance Optimization) logic.
"""
import json
from datetime import datetime
import asyncpg
from agents.base import BaseAgent
import structlog

logger = structlog.get_logger()

SYSTEM_PROMPT = """You are the Risk Manager at an AI brokerage firm.
You are the final gatekeeper before any trade reaches execution.
You have full veto power.

You check:
1. Position VaR contribution (max single trade VaR = risk_budget %)
2. Portfolio concentration (max 25% in single sector)
3. Drawdown headroom (how close are we to max drawdown limit)
4. Correlation with existing positions (avoid doubling up risk)
5. Technical setup alignment with risk parameters
6. **Markowitz Optimization**: Align approved weights closely with the mathematically optimal weights provided to maximize the Sharpe ratio.

Decisions:
- "approved": trade passes all checks at proposed size
- "approved_resized": trade approved but at smaller size
- "rejected": trade fails risk criteria — explain why

Be conservative. Protect capital first."""


class RiskManagerAgent(BaseAgent):
    def __init__(self):
        super().__init__("risk_manager", tier="strong")

    def _calculate_markowitz_weights(self, proposals: list, tech_map: dict) -> dict:
        """
        Simulated Markowitz Mean-Variance Optimization.
        Uses expected return (take profit distance) and volatility (stop loss distance)
        from technical assessments to approximate the Efficient Frontier weights.
        """
        optimal_weights = {}
        total_score = 0.0
        
        for p in proposals:
            symbol = p.get("symbol")
            tech = tech_map.get(symbol, {})
            current_price = tech.get("entry_zone_high", 100) # fallback
            tp = tech.get("take_profit_1", current_price * 1.05)
            sl = tech.get("stop_loss", current_price * 0.95)
            
            # Expected Return Proxy
            expected_return = abs(tp - current_price) / current_price
            # Volatility (Risk) Proxy
            volatility = abs(current_price - sl) / current_price
            
            if volatility == 0:
                volatility = 0.01
                
            # Sharpe Ratio Proxy (Risk-Free Rate = 0)
            sharpe_proxy = expected_return / volatility
            
            # We want to weight by Sharpe Ratio (Mean-Variance proxy)
            # Only consider positive sharpe
            if sharpe_proxy > 0 and tech.get("setup_quality") not in ["avoid", "poor"]:
                optimal_weights[symbol] = sharpe_proxy
                total_score += sharpe_proxy
                
        # Normalize weights
        if total_score > 0:
            for sym in optimal_weights:
                optimal_weights[sym] = round(optimal_weights[sym] / total_score, 4)
                
        return optimal_weights

    async def run(self, state: dict, conn: asyncpg.Connection) -> dict:
        cycle_id = state.get("cycle_id")
        mandate = state.get("mandate", {})
        proposals = state.get("proposals", [])
        technical_assessments = state.get("technical_assessments", [])
        portfolio_snapshot = state.get("portfolio_snapshot", {})
        risk_budget = mandate.get("risk_budget", 4.0)

        memories = await self.recall(
            conn, "risk assessment VaR drawdown position sizing",
            memory_types=["analysis", "reflection"], limit=4,
        )

        # Build a technical lookup map
        tech_map = {t.get("symbol"): t for t in technical_assessments}
        
        # Phase 5: Calculate Markowitz Optimal Weights
        markowitz_weights = self._calculate_markowitz_weights(proposals, tech_map)
        logger.info("markowitz_optimization_complete", optimal_weights=markowitz_weights)

        assessments = []
        any_approved = False

        for proposal in proposals:
            symbol = proposal.get("symbol")
            technical = tech_map.get(symbol, {})
            optimal_weight = markowitz_weights.get(symbol, 0.0)

            user_msg = f"""
Today: {datetime.utcnow().strftime('%Y-%m-%d')}
Risk budget (max VaR %): {risk_budget}
Max drawdown limit: 8%

Trade proposal:
{json.dumps(proposal, indent=2)}

Technical assessment:
{json.dumps(technical, indent=2)}

Markowitz Optimal Weight (Efficient Frontier Target): {optimal_weight}

Current portfolio snapshot:
{json.dumps(portfolio_snapshot, indent=2)}

Past risk decisions:
{self._format_memories(memories)}

Perform risk assessment. Return JSON:
{{
  "symbol": "{symbol}",
  "decision": "approved|approved_resized|rejected",
  "original_weight": {proposal.get('proposed_weight', 0.03)},
  "approved_weight": {optimal_weight if optimal_weight > 0 else 0.0},
  "rejection_reason": null,
  "portfolio_var_after": 3.2,
  "concentration_check": true,
  "drawdown_headroom": 5.5
}}

If setup_quality is "avoid" or "poor", reject.
If proposed_weight > risk_budget/100 * 0.8, resize down.
Try to align the 'approved_weight' with the 'Markowitz Optimal Weight' if it is safe to do so.
portfolio_var_after = estimated portfolio VaR if trade executes.
drawdown_headroom = max_drawdown_limit - current_drawdown.
"""
            try:
                assessment = await self.think_json(SYSTEM_PROMPT, user_msg, max_tokens=1200)
                assessment["cycle_id"] = cycle_id
                assessment["sender"] = "risk_manager"

                if assessment.get("decision") in ("approved", "approved_resized"):
                    any_approved = True

                await self.remember(
                    conn, "analysis",
                    f"Risk assessment {symbol}: {assessment.get('decision')}. "
                    f"Approved weight: {assessment.get('approved_weight')}. "
                    f"VaR after: {assessment.get('portfolio_var_after')}%",
                    metadata=assessment, cycle_id=cycle_id, importance=0.7,
                )
                assessments.append(assessment)
                logger.info("risk_assessment", symbol=symbol,
                            decision=assessment.get("decision"))
            except Exception as e:
                logger.error("risk_error", symbol=symbol, error=str(e))
                assessments.append({
                    "symbol": symbol,
                    "decision": "rejected",
                    "rejection_reason": f"Risk assessment error: {e}",
                    "original_weight": proposal.get("proposed_weight", 0),
                    "approved_weight": 0,
                    "portfolio_var_after": 0,
                    "concentration_check": False,
                    "drawdown_headroom": 0,
                })

        risk_veto = not any_approved
        logger.info("risk_layer_complete", approved=any_approved, veto=risk_veto)
        return {
            "risk_assessments": assessments,
            "risk_veto": risk_veto,
        }

