"""
Reinforcement Learning Loop — Phase 2
Agent signal weights auto-adjust based on live trade outcomes.
Uses a multi-armed bandit (UCB1) approach — simple, explainable,
and robust to overfitting vs deep RL.

How it works:
  1. After every closed trade, record which agent signals were present
     and what the trade outcome was (reward)
  2. The UCB1 bandit updates weight estimates for each signal type
  3. Next cycle, the CIO uses updated weights when blending agent scores
  4. Over time, signals that consistently predict profitable trades
     get higher weights; noise signals decay

Reward signal: Sharpe-adjusted return per trade
  reward = (pnl_pct - risk_free_rate) / volatility_at_entry
"""
from __future__ import annotations
import json
import math
from typing import Optional
import asyncpg
import structlog

logger = structlog.get_logger()

# Default starting weights — equal across all signals
DEFAULT_WEIGHTS = {
    "quant_score":       0.30,
    "fundamental_score": 0.25,
    "technical_score":   0.20,
    "news_score":        0.10,
    "macro_score":       0.10,
    "options_flow_score": 0.05,
}

RISK_FREE_RATE_DAILY = 0.05 / 252   # 5% annual → daily
MIN_WEIGHT = 0.02                    # floor — no signal completely excluded
MAX_WEIGHT = 0.60                    # ceiling — no signal dominates


class RLWeightOptimiser:
    """
    UCB1-based multi-armed bandit for agent signal weight optimisation.
    Each signal type is an "arm". The reward is the Sharpe-adjusted return.
    UCB1 balances exploitation (use what works) with exploration (try all signals).
    """

    def __init__(self, signal_keys: list[str] = None):
        self.signal_keys = signal_keys or list(DEFAULT_WEIGHTS.keys())

    async def get_weights(self, conn: asyncpg.Connection, market: str = "us") -> dict[str, float]:
        """
        Load current weights from DB.
        Returns normalised weight dict ready to use in CIO mandate.
        """
        rows = await conn.fetch("""
            SELECT signal_key, weight, total_reward, pull_count
            FROM rl_signal_weights
            WHERE market = $1
            ORDER BY signal_key
        """, market)

        if not rows:
            # First time — return defaults
            return dict(DEFAULT_WEIGHTS)

        weights = {r["signal_key"]: float(r["weight"]) for r in rows}
        return self._normalise(weights)

    async def update_weights(
        self,
        conn: asyncpg.Connection,
        trade_outcome: dict,
        agent_signals: dict,
        market: str = "us",
    ) -> dict[str, float]:
        """
        Update signal weights after a trade closes.

        trade_outcome: {pnl_pct, hold_days, entry_volatility, symbol, direction}
        agent_signals: {quant_score: 0.8, fundamental_score: 0.6, ...}

        Returns new weight dict.
        """
        reward = self._calculate_reward(trade_outcome)
        logger.info("rl_reward_calculated",
                    symbol=trade_outcome.get("symbol"),
                    reward=round(reward, 4),
                    pnl=trade_outcome.get("pnl_pct"))

        # Ensure weight table rows exist
        await self._ensure_rows(conn, market)

        # Update each signal that contributed to this trade
        for key in self.signal_keys:
            score = agent_signals.get(key)
            if score is None:
                continue

            # Scaled reward: signal with higher score gets more credit/blame
            scaled_reward = reward * abs(float(score))

            await conn.execute("""
                UPDATE rl_signal_weights
                SET
                    total_reward  = total_reward + $1,
                    pull_count    = pull_count + 1,
                    last_updated  = now()
                WHERE signal_key = $2 AND market = $3
            """, scaled_reward, key, market)

        # Recalculate UCB1 weights
        new_weights = await self._recalculate_ucb1(conn, market)

        logger.info("rl_weights_updated", market=market,
                    weights={k: round(v, 3) for k, v in new_weights.items()})
        return new_weights

    async def _recalculate_ucb1(
        self, conn: asyncpg.Connection, market: str
    ) -> dict[str, float]:
        """
        UCB1 formula: weight = avg_reward + C * sqrt(ln(total_pulls) / pull_count)
        C (exploration constant) = 0.5 — higher = more exploration
        """
        rows = await conn.fetch("""
            SELECT signal_key, total_reward, pull_count
            FROM rl_signal_weights
            WHERE market = $1
        """, market)

        if not rows:
            return dict(DEFAULT_WEIGHTS)

        total_pulls = sum(r["pull_count"] for r in rows) or 1
        C = 0.5

        ucb_scores = {}
        for r in rows:
            key    = r["signal_key"]
            pulls  = max(r["pull_count"], 1)
            avg_r  = r["total_reward"] / pulls
            # UCB1 exploration bonus
            bonus  = C * math.sqrt(math.log(total_pulls) / pulls)
            ucb_scores[key] = avg_r + bonus

        # Shift to positive range and normalise
        min_score = min(ucb_scores.values())
        if min_score < 0:
            ucb_scores = {k: v - min_score + 0.01 for k, v in ucb_scores.items()}

        weights = self._normalise(ucb_scores)

        # Apply floor and ceiling
        weights = {k: max(MIN_WEIGHT, min(MAX_WEIGHT, v)) for k, v in weights.items()}
        weights = self._normalise(weights)

        # Persist new weights
        for key, w in weights.items():
            await conn.execute("""
                UPDATE rl_signal_weights SET weight = $1
                WHERE signal_key = $2 AND market = $3
            """, w, key, market)

        return weights

    def _calculate_reward(self, outcome: dict) -> float:
        """
        Sharpe-adjusted reward per trade.
        Positive = profitable, negative = loss.
        Scaled by how fast the profit came (fewer hold days = higher reward rate).
        """
        pnl_pct = float(outcome.get("pnl_pct", 0) or 0)
        hold    = max(int(outcome.get("hold_days", 1) or 1), 1)
        vol     = float(outcome.get("entry_volatility", 0.02) or 0.02)

        # Daily return
        daily_return = pnl_pct / 100 / hold
        # Sharpe-like: excess return / volatility
        reward = (daily_return - RISK_FREE_RATE_DAILY) / vol
        # Clip to reasonable range
        return max(-3.0, min(3.0, reward))

    def _normalise(self, weights: dict) -> dict:
        """Normalise weights to sum to 1.0."""
        total = sum(weights.values()) or 1
        return {k: v / total for k, v in weights.items()}

    async def _ensure_rows(self, conn: asyncpg.Connection, market: str):
        """Insert default rows if they don't exist."""
        for key, default_w in DEFAULT_WEIGHTS.items():
            await conn.execute("""
                INSERT INTO rl_signal_weights
                    (signal_key, market, weight, total_reward, pull_count)
                VALUES ($1, $2, $3, 0.0, 0)
                ON CONFLICT (signal_key, market) DO NOTHING
            """, key, market, default_w)

    async def get_performance_summary(
        self, conn: asyncpg.Connection, market: str = "us"
    ) -> dict:
        """Return a human-readable summary of current signal performance."""
        rows = await conn.fetch("""
            SELECT signal_key, weight, total_reward, pull_count, last_updated
            FROM rl_signal_weights
            WHERE market = $1
            ORDER BY weight DESC
        """, market)

        summary = []
        for r in rows:
            pulls = max(r["pull_count"], 1)
            summary.append({
                "signal":       r["signal_key"],
                "weight":       round(float(r["weight"]), 4),
                "avg_reward":   round(float(r["total_reward"]) / pulls, 4),
                "trade_count":  r["pull_count"],
                "last_updated": r["last_updated"].isoformat() if r["last_updated"] else None,
            })

        return {
            "market":  market,
            "signals": summary,
            "top_signal":     summary[0]["signal"] if summary else None,
            "bottom_signal":  summary[-1]["signal"] if summary else None,
            "total_trades_learned_from": sum(r["pull_count"] for r in rows),
        }


async def trigger_rl_update(
    conn: asyncpg.Connection,
    cycle_id: str,
    market: str = "us",
) -> Optional[dict]:
    """
    Called by the Reporting Agent after a trade closes.
    Loads the trade outcome and runs the RL weight update.
    Returns new weights or None if no outcome found.
    """
    row = await conn.fetchrow("""
        SELECT symbol, direction, entry_price, exit_price,
               pnl_pct, agent_signals,
               EXTRACT(DAY FROM (closed_at - opened_at)) AS hold_days
        FROM trade_outcomes
        WHERE cycle_id = $1::uuid AND closed_at IS NOT NULL
        ORDER BY closed_at DESC
        LIMIT 1
    """, cycle_id)

    if not row:
        return None

    pnl_pct    = float(row["pnl_pct"] or 0)
    entry_p    = float(row["entry_price"] or 1)
    hold_days  = int(row["hold_days"] or 1)

    # Estimate entry volatility from recent price history
    try:
        import yfinance as yf
        ticker = yf.Ticker(row["symbol"])
        hist   = ticker.history(period="30d")
        vol    = float(hist["Close"].pct_change().std()) if not hist.empty else 0.02
    except Exception:
        vol = 0.02

    trade_outcome = {
        "symbol":            row["symbol"],
        "direction":         row["direction"],
        "pnl_pct":           pnl_pct,
        "hold_days":         hold_days,
        "entry_volatility":  vol,
    }

    agent_signals = row["agent_signals"] or {}
    if isinstance(agent_signals, str):
        agent_signals = json.loads(agent_signals)

    optimiser   = RLWeightOptimiser()
    new_weights = await optimiser.update_weights(conn, trade_outcome, agent_signals, market)
    return new_weights
