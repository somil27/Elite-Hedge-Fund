"""
Portfolio Analysis Service
Uses Claude to analyse a user's Indian broker portfolio:
  - Holdings quality and concentration
  - Sector diversification
  - Risk metrics (beta, volatility estimates)
  - Actionable rebalancing suggestions
  - P&L attribution
"""
from __future__ import annotations
from datetime import datetime
from typing import Union
import structlog

from broker.indian.zerodha import ZerodhaBroker
from broker.indian.upstox  import UpstoxBroker
from broker.indian.base_indian import Holding, IndianPosition
from core.llm import chat_json

logger = structlog.get_logger()


def _holdings_to_text(holdings: list[Holding]) -> str:
    lines = []
    for h in holdings:
        lines.append(
            f"  {h.tradingsymbol} ({h.exchange}): {h.quantity} shares @ avg ₹{h.average_price:.2f}, "
            f"CMP ₹{h.last_price:.2f}, P&L ₹{h.pnl:.2f} ({h.total_return_pct:.1f}%), "
            f"Day change: {h.day_change_pct:.2f}%"
        )
    return "\n".join(lines) if lines else "No holdings."


def _positions_to_text(positions: list[IndianPosition]) -> str:
    lines = []
    for p in positions:
        if p.quantity != 0:
            lines.append(
                f"  {p.tradingsymbol} ({p.exchange}) [{p.product}]: "
                f"qty={p.quantity}, LTP=₹{p.last_price:.2f}, "
                f"P&L=₹{p.pnl:.2f}, Day change={p.change_pct:.2f}%"
            )
    return "\n".join(lines) if lines else "No open positions."


async def analyse_portfolio(
    broker_client: Union[ZerodhaBroker, UpstoxBroker],
    analysis_type: str = "full",
    # full | risk | diversification | rebalance | pnl
) -> dict:
    """
    Run an AI portfolio analysis.
    Returns structured JSON with insights and recommendations.
    """
    # Gather data
    holdings  = await broker_client.get_holdings()
    positions_raw = await broker_client.get_positions()
    positions = (positions_raw.get("net", []) if isinstance(positions_raw, dict)
                 else positions_raw)
    funds     = await broker_client.get_funds()

    total_investment = sum(h.investment_value for h in holdings)
    total_current    = sum(h.current_value for h in holdings)
    total_pnl        = sum(h.pnl for h in holdings)
    total_pnl_pct    = (total_pnl / total_investment * 100) if total_investment else 0
    day_pnl          = sum(h.quantity * h.day_change for h in holdings)

    holdings_text  = _holdings_to_text(holdings)
    positions_text = _positions_to_text(positions)

    system_prompt = """You are a SEBI-registered investment advisor AI analysing an Indian stock portfolio.
You provide precise, data-driven analysis of NSE/BSE equity portfolios.
Always respond in valid JSON. Be specific — mention exact stocks, sectors, and percentages.
Consider Indian market context: SEBI regulations, circuit limits, F&O constraints, GST impact on trading costs."""

    prompt = f"""Analyse this Indian equity portfolio and return a JSON analysis.

Analysis type requested: {analysis_type}

PORTFOLIO SUMMARY:
  Total investment:  ₹{total_investment:,.2f}
  Current value:     ₹{total_current:,.2f}
  Total P&L:         ₹{total_pnl:+,.2f} ({total_pnl_pct:+.2f}%)
  Today's P&L:       ₹{day_pnl:+,.2f}
  Available cash:    ₹{funds.available_cash:,.2f}
  Used margin:       ₹{funds.used_margin:,.2f}

LONG-TERM HOLDINGS (CNC / Delivery):
{holdings_text}

OPEN INTRADAY/F&O POSITIONS:
{positions_text}

Return JSON with exactly these fields:
{{
  "summary": {{
    "total_stocks": <int>,
    "profitable_stocks": <int>,
    "losing_stocks": <int>,
    "best_performer": "<symbol> (+X.X%)",
    "worst_performer": "<symbol> (-X.X%)",
    "overall_health": "excellent|good|average|poor",
    "health_reason": "<one sentence>"
  }},
  "sector_analysis": {{
    "<sector>": {{"count": <int>, "allocation_pct": <float>, "avg_return_pct": <float>}}
  }},
  "concentration_risk": {{
    "top_3_allocation_pct": <float>,
    "is_concentrated": <bool>,
    "concentrated_stocks": ["<sym>", ...]
  }},
  "risk_assessment": {{
    "portfolio_beta_estimate": <float>,
    "high_risk_stocks": ["<sym>", ...],
    "near_circuit_stocks": [],
    "stop_loss_missing": ["<sym>", ...]
  }},
  "insights": [
    "<specific actionable insight 1>",
    "<specific actionable insight 2>",
    "<specific actionable insight 3>",
    "<specific actionable insight 4>",
    "<specific actionable insight 5>"
  ],
  "rebalancing_suggestions": [
    {{
      "action": "buy|sell|hold|reduce",
      "symbol": "<sym>",
      "reason": "<why>",
      "priority": "high|medium|low"
    }}
  ],
  "alerts": [
    {{
      "type": "circuit_risk|concentration|stop_loss|profit_booking|sector_overweight",
      "symbol": "<sym>",
      "message": "<alert message>",
      "severity": "high|medium|low"
    }}
  ],
  "generated_at": "{datetime.utcnow().isoformat()}"
}}"""

    try:
        result = await chat_json(system_prompt, prompt, tier="strong", max_tokens=3000)
        result["holdings_count"] = len(holdings)
        result["positions_count"] = len([p for p in positions if p.quantity != 0])
        result["total_investment"] = total_investment
        result["total_current_value"] = total_current
        result["total_pnl"] = total_pnl
        result["total_pnl_pct"] = total_pnl_pct
        result["day_pnl"] = day_pnl
        result["available_cash"] = funds.available_cash

        logger.info("portfolio_analysis_complete",
                    holdings=len(holdings), type=analysis_type)
        return result
    except Exception as e:
        logger.error("portfolio_analysis_error", error=str(e))
        return {
            "error": str(e),
            "holdings_count": len(holdings),
            "total_pnl": total_pnl,
            "generated_at": datetime.utcnow().isoformat(),
        }


async def generate_stock_insight(
    broker_client: Union[ZerodhaBroker, UpstoxBroker],
    symbol: str,
    exchange: str = "NSE",
) -> dict:
    """
    Deep AI analysis of a single stock in the portfolio:
    - Entry quality assessment
    - Current technical standing
    - Should hold / reduce / exit recommendation
    """
    holdings  = await broker_client.get_holdings()
    holding   = next(
        (h for h in holdings if h.tradingsymbol.upper() == symbol.upper()),
        None,
    )
    if not holding:
        return {"error": f"{symbol} not found in holdings"}

    quote_key = f"{exchange}:{symbol}"
    try:
        quotes = await broker_client.get_quote([quote_key])
        quote  = quotes.get(quote_key)
    except Exception:
        quote  = None

    prompt = f"""Analyse this individual stock position in an Indian equity portfolio.

Stock: {symbol} ({exchange})
Avg buy price:   ₹{holding.average_price:.2f}
Current price:   ₹{holding.last_price:.2f}
Quantity:        {holding.quantity}
Investment:      ₹{holding.investment_value:,.2f}
Current value:   ₹{holding.current_value:,.2f}
P&L:             ₹{holding.pnl:+,.2f} ({holding.total_return_pct:+.2f}%)
Day change:      {holding.day_change_pct:+.2f}%
{"Upper circuit: ₹" + str(quote.upper_circuit) if quote and quote.upper_circuit else ""}
{"Lower circuit: ₹" + str(quote.lower_circuit) if quote and quote.lower_circuit else ""}

Return JSON:
{{
  "recommendation": "strong_hold|hold|reduce|exit|add_more",
  "conviction": "high|medium|low",
  "entry_quality": "excellent|good|average|poor",
  "price_targets": {{
    "support_1": <float>,
    "support_2": <float>,
    "resistance_1": <float>,
    "target": <float>,
    "stop_loss": <float>
  }},
  "reasoning": "<2-3 sentences>",
  "risk_factors": ["<risk1>", "<risk2>"],
  "catalysts": ["<catalyst1>", "<catalyst2>"]
}}"""

    try:
        result = await chat_json(
            "You are a SEBI-registered investment advisor. Respond only in JSON.",
            prompt, tier="fast", max_tokens=800,
        )
        result["symbol"] = symbol
        result["exchange"] = exchange
        result["current_pnl_pct"] = holding.total_return_pct
        return result
    except Exception as e:
        return {"error": str(e), "symbol": symbol}
