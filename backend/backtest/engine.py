"""
Backtesting Engine — Phase 2
Replays the full agent reasoning pipeline on historical market data.
Produces performance attribution per agent and walk-forward validation.

Usage:
    engine = BacktestEngine()
    result = await engine.run(
        strategy="momentum",
        symbols=["NVDA", "AAPL", "MSFT"],
        start_date="2024-01-01",
        end_date="2024-12-31",
        mode="short_term",
        initial_capital=100_000,
    )
"""
from __future__ import annotations
import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional
import pandas as pd
import numpy as np
import yfinance as yf
from core.llm import chat_json
import structlog

logger = structlog.get_logger()


# ── Data structures ───────────────────────────────────────────

@dataclass
class BacktestTrade:
    symbol:        str
    direction:     str          # "long" | "short"
    entry_date:    str
    exit_date:     Optional[str]
    entry_price:   float
    exit_price:    Optional[float]
    qty:           float
    pnl:           float = 0.0
    pnl_pct:       float = 0.0
    hold_days:     int = 0
    exit_reason:   str = ""
    agent_signals: dict = field(default_factory=dict)
    # scores from each agent at entry
    composite_score: float = 0.0


@dataclass
class BacktestResult:
    strategy:        str
    symbols:         list[str]
    start_date:      str
    end_date:        str
    initial_capital: float
    final_capital:   float

    total_return_pct:  float = 0.0
    annualised_return: float = 0.0
    sharpe_ratio:      float = 0.0
    max_drawdown_pct:  float = 0.0
    win_rate:          float = 0.0
    profit_factor:     float = 0.0
    total_trades:      int   = 0
    avg_hold_days:     float = 0.0

    trades:            list[BacktestTrade] = field(default_factory=list)
    equity_curve:      list[dict]          = field(default_factory=list)

    # Agent attribution: which agent's signal best predicted returns
    agent_attribution: dict = field(default_factory=dict)
    # Walk-forward validation results
    walkforward:       list[dict] = field(default_factory=list)


BACKTEST_SYSTEM = """You are a quantitative analyst simulating a trading agent's analysis
on historical data. Given historical OHLCV data and technical indicators for a specific date,
produce the same signals that agent would have generated ON THAT DATE (not with future information).

Critical: You must only use information available up to and including the 'analysis_date'.
Never look ahead. Simulate the agent's reasoning as if you are standing on that date."""


class BacktestEngine:
    """
    Full agent pipeline backtesting engine.
    For each date in the backtest window, asks Claude to simulate
    each agent's reasoning given only historical data up to that date.
    """

    def __init__(self, max_concurrent: int = 3):
        self.max_concurrent = max_concurrent

    async def run(
        self,
        strategy: str,
        symbols: list[str],
        start_date: str,
        end_date: str,
        mode: str = "short_term",
        initial_capital: float = 100_000.0,
        rebalance_freq: str = "weekly",   # daily|weekly|monthly
        market: str = "us",
    ) -> BacktestResult:
        """
        Run the full backtest. Returns a BacktestResult with all metrics.
        """
        logger.info("backtest_start", strategy=strategy, symbols=symbols,
                    start=start_date, end=end_date)

        # Fetch all historical data upfront
        price_data = await self._fetch_all_prices(symbols, start_date, end_date)
        if not price_data:
            raise ValueError(f"No price data found for {symbols}")

        # Build rebalance dates
        dates = self._build_rebalance_dates(start_date, end_date, rebalance_freq, price_data)

        # Run simulation
        portfolio = BacktestPortfolio(initial_capital)
        all_trades: list[BacktestTrade] = []
        equity_curve: list[dict] = []
        agent_scores: dict[str, list[float]] = {s: [] for s in symbols}
        returns: list[float] = []

        sem = asyncio.Semaphore(self.max_concurrent)

        for i, date in enumerate(dates):
            async with sem:
                # Close positions that hit stop/target
                closed = portfolio.check_exits(date, price_data)
                all_trades.extend(closed)

                # Generate new signals for this date
                signals = await self._generate_signals_for_date(
                    date, symbols, strategy, mode, price_data, market
                )

                # Apply strategy filters and sizing
                from strategies.strategy_library import STRATEGIES
                strat = STRATEGIES.get(strategy, STRATEGIES["momentum"])

                for sig in signals:
                    symbol = sig.get("symbol")
                    score  = sig.get("composite_score", 0)

                    if score < strat.min_conviction_score:
                        continue
                    if portfolio.has_position(symbol):
                        continue

                    # Get current price
                    curr_price = self._get_price_on_date(price_data, symbol, date)
                    if not curr_price:
                        continue

                    # Size position
                    position_value = portfolio.cash * strat.max_position_pct
                    qty = position_value / curr_price

                    stop_loss  = curr_price * (1 - strat.stop_loss_pct)
                    take_profit = curr_price * (1 + strat.take_profit_pct)

                    trade = BacktestTrade(
                        symbol=symbol,
                        direction="long" if score > 0 else "short",
                        entry_date=date,
                        exit_date=None,
                        entry_price=curr_price,
                        exit_price=None,
                        qty=qty,
                        agent_signals=sig.get("agent_breakdown", {}),
                        composite_score=score,
                    )
                    portfolio.open_position(trade, curr_price, stop_loss, take_profit)

                # Record equity value
                nav = portfolio.calculate_nav(date, price_data)
                equity_curve.append({"date": date, "nav": nav})

                if i > 0:
                    prev_nav = equity_curve[-2]["nav"]
                    ret = (nav - prev_nav) / prev_nav if prev_nav else 0
                    returns.append(ret)

                logger.debug("backtest_date", date=date, nav=nav,
                             open_positions=len(portfolio.positions))

        # Close all remaining open positions at end
        final_date = dates[-1] if dates else end_date
        remaining = portfolio.close_all(final_date, price_data)
        all_trades.extend(remaining)

        final_nav = portfolio.calculate_nav(final_date, price_data)

        # Calculate performance metrics
        result = self._calculate_metrics(
            strategy, symbols, start_date, end_date,
            initial_capital, final_nav, all_trades,
            equity_curve, returns,
        )
        result.agent_attribution = self._calculate_attribution(all_trades)

        # Walk-forward validation (split into 3 periods)
        result.walkforward = await self._walk_forward(
            strategy, symbols, start_date, end_date,
            mode, initial_capital, rebalance_freq, market,
        )

        logger.info("backtest_complete",
                    total_return=result.total_return_pct,
                    sharpe=result.sharpe_ratio,
                    trades=result.total_trades)
        return result

    async def _generate_signals_for_date(
        self,
        date: str,
        symbols: list[str],
        strategy: str,
        mode: str,
        price_data: dict,
        market: str,
    ) -> list[dict]:
        """
        Simulate agent signal generation for a specific historical date.
        Uses Claude to replay agent reasoning with only pre-date information.
        """
        # Build historical context (only data up to 'date')
        hist_context = {}
        for symbol in symbols:
            df = price_data.get(symbol)
            if df is None:
                continue
            # Only include data up to and including the analysis date
            mask = df.index.strftime("%Y-%m-%d") <= date
            hist_df = df[mask].tail(60)  # last 60 days
            if hist_df.empty:
                continue
            hist_context[symbol] = {
                "closes":         [round(x, 2) for x in hist_df["Close"].tolist()],
                "volumes":        [int(x) for x in hist_df["Volume"].tolist()],
                "highs":          [round(x, 2) for x in hist_df["High"].tolist()],
                "lows":           [round(x, 2) for x in hist_df["Low"].tolist()],
                "current_price":  round(float(hist_df["Close"].iloc[-1]), 2),
                "30d_return_pct": round(
                    (hist_df["Close"].iloc[-1] / hist_df["Close"].iloc[0] - 1) * 100, 2
                ) if len(hist_df) > 1 else 0,
                "avg_volume_20d": int(hist_df["Volume"].tail(20).mean()),
                "volatility_pct": round(float(hist_df["Close"].pct_change().std() * 100), 2),
            }

        prompt = f"""
Backtesting simulation. Analysis date: {date}
Strategy: {strategy}
Mode: {mode}
Market: {market}

Historical OHLCV data (only up to {date} — do NOT use future information):
{json.dumps(hist_context, indent=2)}

Simulate what the agent pipeline would have decided on {date}.
For each symbol, produce a composite signal score based on:
1. Price momentum (last 30 days return, volume trend)
2. Technical setup (RSI estimate, trend direction)
3. Volatility regime (low vol = better entry)
4. Volume confirmation

Return JSON array:
[
  {{
    "symbol": "NVDA",
    "composite_score": 0.72,
    "direction": "long",
    "agent_breakdown": {{
      "quant_score":       0.80,
      "technical_score":   0.65,
      "fundamental_score": 0.70,
      "news_score":        0.60
    }},
    "reasoning": "Strong 30-day momentum with volume confirmation"
  }}
]

Only include symbols with |composite_score| > 0.5.
Base scores ONLY on the historical data provided. No future knowledge."""

        try:
            results = await chat_json(
                BACKTEST_SYSTEM, prompt, tier="fast", max_tokens=1500,
            )
            return results if isinstance(results, list) else results.get("signals", [])
        except Exception as e:
            logger.warning("backtest_signal_error", date=date, error=str(e))
            return []

    async def _fetch_all_prices(
        self, symbols: list[str], start_date: str, end_date: str
    ) -> dict[str, pd.DataFrame]:
        """Fetch OHLCV data for all symbols over the backtest window."""
        def _sync_fetch(symbol):
            try:
                # Add buffer for indicators
                start = (
                    datetime.strptime(start_date, "%Y-%m-%d") - timedelta(days=90)
                ).strftime("%Y-%m-%d")
                ticker = yf.Ticker(symbol)
                df = ticker.history(start=start, end=end_date)
                df.index = pd.to_datetime(df.index).tz_localize(None)
                return symbol, df
            except Exception as e:
                logger.warning("price_fetch_failed", symbol=symbol, error=str(e))
                return symbol, None

        loop = asyncio.get_event_loop()
        results = await asyncio.gather(*[
            loop.run_in_executor(None, _sync_fetch, s) for s in symbols
        ])
        return {sym: df for sym, df in results if df is not None and not df.empty}

    def _build_rebalance_dates(
        self,
        start_date: str,
        end_date: str,
        freq: str,
        price_data: dict,
    ) -> list[str]:
        """Build list of rebalance dates (trading days only)."""
        # Get trading days from first symbol's price data
        ref_df = next(iter(price_data.values()))
        all_days = ref_df.index.strftime("%Y-%m-%d").tolist()

        # Filter to backtest window
        days = [d for d in all_days if start_date <= d <= end_date]

        if freq == "daily":
            return days
        if freq == "weekly":
            # Every Monday (or first trading day of week)
            result, last_week = [], None
            for d in days:
                week = datetime.strptime(d, "%Y-%m-%d").isocalendar()[1]
                if week != last_week:
                    result.append(d)
                    last_week = week
            return result
        if freq == "monthly":
            result, last_month = [], None
            for d in days:
                month = d[:7]
                if month != last_month:
                    result.append(d)
                    last_month = month
            return result
        return days

    def _get_price_on_date(
        self, price_data: dict, symbol: str, date: str
    ) -> Optional[float]:
        df = price_data.get(symbol)
        if df is None:
            return None
        mask = df.index.strftime("%Y-%m-%d") <= date
        filtered = df[mask]
        if filtered.empty:
            return None
        return float(filtered["Close"].iloc[-1])

    def _calculate_metrics(
        self,
        strategy, symbols, start_date, end_date,
        initial_capital, final_nav, trades, equity_curve, returns,
    ) -> BacktestResult:
        total_return = (final_nav - initial_capital) / initial_capital * 100

        # Annualise
        days = (
            datetime.strptime(end_date, "%Y-%m-%d") -
            datetime.strptime(start_date, "%Y-%m-%d")
        ).days or 1
        annualised = ((final_nav / initial_capital) ** (365 / days) - 1) * 100

        # Sharpe (assume 5% risk-free)
        if returns:
            ret_arr = np.array(returns)
            rf_daily = 0.05 / 252
            excess   = ret_arr - rf_daily
            sharpe   = (excess.mean() / (excess.std() + 1e-9)) * np.sqrt(252)
        else:
            sharpe = 0.0

        # Max drawdown
        navs = [e["nav"] for e in equity_curve]
        if navs:
            peak = navs[0]
            max_dd = 0.0
            for nav in navs:
                peak = max(peak, nav)
                dd = (peak - nav) / peak * 100
                max_dd = max(max_dd, dd)
        else:
            max_dd = 0.0

        # Win rate and profit factor
        closed = [t for t in trades if t.exit_price is not None]
        wins   = [t for t in closed if t.pnl > 0]
        losses = [t for t in closed if t.pnl <= 0]
        win_rate = len(wins) / max(len(closed), 1)
        gross_profit = sum(t.pnl for t in wins)
        gross_loss   = abs(sum(t.pnl for t in losses))
        profit_factor = gross_profit / max(gross_loss, 0.01)
        avg_hold = np.mean([t.hold_days for t in closed]) if closed else 0.0

        return BacktestResult(
            strategy=strategy, symbols=symbols,
            start_date=start_date, end_date=end_date,
            initial_capital=initial_capital, final_capital=final_nav,
            total_return_pct=round(total_return, 2),
            annualised_return=round(annualised, 2),
            sharpe_ratio=round(float(sharpe), 2),
            max_drawdown_pct=round(max_dd, 2),
            win_rate=round(win_rate, 3),
            profit_factor=round(profit_factor, 2),
            total_trades=len(closed),
            avg_hold_days=round(float(avg_hold), 1),
            trades=trades,
            equity_curve=equity_curve,
        )

    def _calculate_attribution(self, trades: list[BacktestTrade]) -> dict:
        """Measure which agent's signal best correlated with trade PnL."""
        attribution = {}
        closed = [t for t in trades if t.exit_price is not None and t.agent_signals]
        if not closed:
            return {}

        agent_keys = list(closed[0].agent_signals.keys()) if closed else []
        for key in agent_keys:
            scores = [t.agent_signals.get(key, 0) for t in closed]
            pnls   = [t.pnl_pct for t in closed]
            if len(scores) > 1:
                corr = float(np.corrcoef(scores, pnls)[0, 1])
                attribution[key] = round(corr, 3)

        return dict(sorted(attribution.items(), key=lambda x: -abs(x[1])))

    async def _walk_forward(
        self,
        strategy, symbols, start_date, end_date,
        mode, initial_capital, freq, market,
    ) -> list[dict]:
        """
        Split the backtest period into 3 non-overlapping windows
        and run each independently to detect overfitting.
        """
        start = datetime.strptime(start_date, "%Y-%m-%d")
        end   = datetime.strptime(end_date, "%Y-%m-%d")
        total_days = (end - start).days
        period_days = total_days // 3

        results = []
        for i in range(3):
            p_start = (start + timedelta(days=i * period_days)).strftime("%Y-%m-%d")
            p_end   = (start + timedelta(days=(i + 1) * period_days)).strftime("%Y-%m-%d")
            try:
                sub = await self.run(
                    strategy, symbols, p_start, p_end,
                    mode, initial_capital, freq, market,
                )
                results.append({
                    "period": f"P{i+1}",
                    "start":  p_start,
                    "end":    p_end,
                    "return": sub.total_return_pct,
                    "sharpe": sub.sharpe_ratio,
                    "trades": sub.total_trades,
                    "win_rate": sub.win_rate,
                })
            except Exception as e:
                results.append({"period": f"P{i+1}", "error": str(e)})
        return results


# ── Portfolio simulator ───────────────────────────────────────

class BacktestPortfolio:
    """Simple portfolio simulator for the backtest engine."""

    def __init__(self, initial_capital: float):
        self.cash      = initial_capital
        self.positions: dict[str, dict] = {}   # symbol → {trade, stop, target}

    def has_position(self, symbol: str) -> bool:
        return symbol in self.positions

    def open_position(
        self,
        trade: BacktestTrade,
        price: float,
        stop_loss: float,
        take_profit: float,
    ):
        cost = trade.qty * price
        if cost > self.cash:
            trade.qty = self.cash * 0.95 / price
            cost = trade.qty * price
        self.cash -= cost
        self.positions[trade.symbol] = {
            "trade":       trade,
            "stop_loss":   stop_loss,
            "take_profit": take_profit,
        }

    def check_exits(self, date: str, price_data: dict) -> list[BacktestTrade]:
        """Check all open positions for stop/target hits. Return closed trades."""
        closed = []
        to_remove = []
        for symbol, pos in self.positions.items():
            price = _get_price(price_data, symbol, date)
            if price is None:
                continue
            trade  = pos["trade"]
            hit_stop   = price <= pos["stop_loss"]
            hit_target = price >= pos["take_profit"]
            if hit_stop or hit_target:
                exit_price = pos["stop_loss"] if hit_stop else pos["take_profit"]
                self._close(trade, date, exit_price,
                            "stop_loss" if hit_stop else "take_profit")
                closed.append(trade)
                to_remove.append(symbol)
        for s in to_remove:
            del self.positions[s]
        return closed

    def close_all(self, date: str, price_data: dict) -> list[BacktestTrade]:
        """Force-close all positions at market on the final date."""
        closed = []
        for symbol, pos in list(self.positions.items()):
            price = _get_price(price_data, symbol, date) or pos["trade"].entry_price
            self._close(pos["trade"], date, price, "end_of_backtest")
            closed.append(pos["trade"])
        self.positions.clear()
        return closed

    def _close(self, trade: BacktestTrade, date: str, price: float, reason: str):
        trade.exit_date  = date
        trade.exit_price = price
        trade.pnl        = (price - trade.entry_price) * trade.qty
        trade.pnl_pct    = (price - trade.entry_price) / trade.entry_price * 100
        trade.exit_reason = reason
        try:
            e_dt = datetime.strptime(trade.entry_date, "%Y-%m-%d")
            x_dt = datetime.strptime(date, "%Y-%m-%d")
            trade.hold_days = (x_dt - e_dt).days
        except Exception:
            pass
        self.cash += price * trade.qty

    def calculate_nav(self, date: str, price_data: dict) -> float:
        nav = self.cash
        for symbol, pos in self.positions.items():
            price = _get_price(price_data, symbol, date)
            if price:
                nav += price * pos["trade"].qty
        return nav


def _get_price(price_data: dict, symbol: str, date: str) -> Optional[float]:
    df = price_data.get(symbol)
    if df is None:
        return None
    mask = df.index.strftime("%Y-%m-%d") <= date
    filtered = df[mask]
    return float(filtered["Close"].iloc[-1]) if not filtered.empty else None
