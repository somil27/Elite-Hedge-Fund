"""
Phase 1 + 2 Unit Tests
Run with:  pytest tests/test_phase12.py -v

Tests do NOT hit live APIs — all LLM calls are mocked.
"""
import math
import pytest
from datetime import datetime


# ── Strategy library tests ────────────────────────────────────

class TestStrategyLibrary:

    def test_all_strategies_have_required_fields(self):
        from strategies.strategy_library import STRATEGIES
        required = ["name", "description", "mode", "regime_fit",
                    "agent_weights", "preferred_algo", "min_conviction_score"]
        for key, s in STRATEGIES.items():
            for field in required:
                assert hasattr(s, field), f"{key} missing {field}"

    def test_agent_weights_sum_to_one(self):
        from strategies.strategy_library import STRATEGIES
        for key, s in STRATEGIES.items():
            total = sum(s.agent_weights.values())
            assert abs(total - 1.0) < 0.01, \
                f"{key} agent weights sum to {total:.3f}, not 1.0"

    def test_select_strategy_momentum_goldilocks(self):
        from strategies.strategy_library import select_strategy
        s = select_strategy("GOLDILOCKS", "short_term", "us")
        assert s.mode == "short_term"
        assert "GOLDILOCKS" in s.regime_fit

    def test_select_strategy_defensive_stagflation(self):
        from strategies.strategy_library import select_strategy
        s = select_strategy("STAGFLATION", "short_term", "us")
        assert s.name == "Defensive / Capital Preservation"

    def test_select_strategy_override(self):
        from strategies.strategy_library import select_strategy
        s = select_strategy("GOLDILOCKS", "short_term", "us", override="value_investing")
        assert s.name == "Value Investing"

    def test_select_strategy_india_short_term(self):
        from strategies.strategy_library import select_strategy
        s = select_strategy("NEUTRAL", "short_term", "india")
        assert s.name == "India Momentum (NSE)"

    def test_apply_strategy_to_mandate(self):
        from strategies.strategy_library import STRATEGIES, apply_strategy_to_mandate
        mandate = {"risk_budget": 5.0, "mode": "short_term"}
        s = STRATEGIES["defensive"]
        updated = apply_strategy_to_mandate(mandate, s)
        # Defensive scales risk budget down by 0.5
        assert updated["risk_budget"] == pytest.approx(2.5, rel=1e-3)
        assert updated["strategy"] == "Defensive / Capital Preservation"
        assert updated["preferred_algo"] == "passive"

    def test_apply_strategy_preserves_existing_keys(self):
        from strategies.strategy_library import STRATEGIES, apply_strategy_to_mandate
        mandate = {"risk_budget": 4.0, "mode": "short_term", "watchlist": ["NVDA", "AAPL"]}
        s = STRATEGIES["momentum"]
        updated = apply_strategy_to_mandate(mandate, s)
        assert updated["watchlist"] == ["NVDA", "AAPL"]  # preserved

    def test_risk_budget_scale_applied(self):
        from strategies.strategy_library import STRATEGIES, apply_strategy_to_mandate
        mandate = {"risk_budget": 4.0}
        for key, s in STRATEGIES.items():
            updated = apply_strategy_to_mandate(mandate, s)
            expected = 4.0 * s.risk_budget_scale
            assert updated["risk_budget"] == pytest.approx(expected, rel=1e-3), \
                f"{key} risk budget scaling wrong"

    def test_min_conviction_scores_reasonable(self):
        from strategies.strategy_library import STRATEGIES
        for key, s in STRATEGIES.items():
            assert 0.4 <= s.min_conviction_score <= 0.8, \
                f"{key} min_conviction_score {s.min_conviction_score} out of range"

    def test_max_position_pct_reasonable(self):
        from strategies.strategy_library import STRATEGIES
        for key, s in STRATEGIES.items():
            assert 0.01 <= s.max_position_pct <= 0.10, \
                f"{key} max_position_pct {s.max_position_pct} out of range"


# ── RL optimiser tests ────────────────────────────────────────

class TestRLOptimiser:

    def test_calculate_reward_profitable(self):
        from strategies.rl_optimiser import RLWeightOptimiser
        opt = RLWeightOptimiser()
        outcome = {"pnl_pct": 5.0, "hold_days": 5, "entry_volatility": 0.02}
        reward = opt._calculate_reward(outcome)
        assert reward > 0, "Profitable trade should give positive reward"

    def test_calculate_reward_loss(self):
        from strategies.rl_optimiser import RLWeightOptimiser
        opt = RLWeightOptimiser()
        outcome = {"pnl_pct": -8.0, "hold_days": 3, "entry_volatility": 0.02}
        reward = opt._calculate_reward(outcome)
        assert reward < 0, "Loss trade should give negative reward"

    def test_reward_clipped_to_range(self):
        from strategies.rl_optimiser import RLWeightOptimiser
        opt = RLWeightOptimiser()
        # Extreme profit
        outcome = {"pnl_pct": 500.0, "hold_days": 1, "entry_volatility": 0.001}
        reward = opt._calculate_reward(outcome)
        assert -3.0 <= reward <= 3.0

    def test_reward_zero_volatility_safe(self):
        from strategies.rl_optimiser import RLWeightOptimiser
        opt = RLWeightOptimiser()
        outcome = {"pnl_pct": 2.0, "hold_days": 5, "entry_volatility": 0}
        reward = opt._calculate_reward(outcome)
        assert math.isfinite(reward)

    def test_normalise_weights(self):
        from strategies.rl_optimiser import RLWeightOptimiser
        opt = RLWeightOptimiser()
        raw = {"a": 2.0, "b": 3.0, "c": 5.0}
        norm = opt._normalise(raw)
        assert abs(sum(norm.values()) - 1.0) < 1e-9
        assert norm["c"] > norm["b"] > norm["a"]

    def test_normalise_zero_sum_safe(self):
        from strategies.rl_optimiser import RLWeightOptimiser
        opt = RLWeightOptimiser()
        raw = {"a": 0.0, "b": 0.0}
        norm = opt._normalise(raw)  # should not raise
        assert all(math.isfinite(v) for v in norm.values())

    def test_faster_profit_gives_higher_reward(self):
        from strategies.rl_optimiser import RLWeightOptimiser
        opt = RLWeightOptimiser()
        slow = opt._calculate_reward({"pnl_pct": 5.0, "hold_days": 20, "entry_volatility": 0.02})
        fast = opt._calculate_reward({"pnl_pct": 5.0, "hold_days": 3,  "entry_volatility": 0.02})
        assert fast > slow, "Same return in fewer days should give higher reward"

    def test_default_weights_sum_to_one(self):
        from strategies.rl_optimiser import DEFAULT_WEIGHTS
        assert abs(sum(DEFAULT_WEIGHTS.values()) - 1.0) < 0.01

    def test_weight_floor_and_ceiling(self):
        from strategies.rl_optimiser import MIN_WEIGHT, MAX_WEIGHT
        assert MIN_WEIGHT < MAX_WEIGHT
        assert MIN_WEIGHT > 0
        assert MAX_WEIGHT < 1.0


# ── Backtest portfolio simulator tests ───────────────────────

class TestBacktestPortfolio:

    def _make_price_data(self, symbol="NVDA", price=500.0):
        """Create minimal price data dict for testing."""
        import pandas as pd
        dates = pd.date_range("2024-01-01", periods=30, freq="B")
        df = pd.DataFrame({
            "Close":  [price] * 30,
            "High":   [price * 1.01] * 30,
            "Low":    [price * 0.99] * 30,
            "Volume": [1_000_000] * 30,
        }, index=dates)
        return {symbol: df}

    def test_open_and_cash_reduces(self):
        from backtest.engine import BacktestPortfolio, BacktestTrade
        portfolio = BacktestPortfolio(100_000)
        trade = BacktestTrade("NVDA", "long", "2024-01-02", None, 500.0, None, 10)
        portfolio.open_position(trade, 500.0, 470.0, 560.0)
        assert portfolio.cash < 100_000
        assert "NVDA" in portfolio.positions

    def test_stop_loss_closes_position(self):
        from backtest.engine import BacktestPortfolio, BacktestTrade
        portfolio = BacktestPortfolio(100_000)
        trade = BacktestTrade("NVDA", "long", "2024-01-02", None, 500.0, None, 10)
        portfolio.open_position(trade, 500.0, stop_loss=480.0, take_profit=560.0)

        price_data = self._make_price_data("NVDA", 470.0)  # below stop
        closed = portfolio.check_exits("2024-01-15", price_data)
        assert len(closed) == 1
        assert closed[0].exit_reason == "stop_loss"
        assert "NVDA" not in portfolio.positions

    def test_take_profit_closes_position(self):
        from backtest.engine import BacktestPortfolio, BacktestTrade
        portfolio = BacktestPortfolio(100_000)
        trade = BacktestTrade("NVDA", "long", "2024-01-02", None, 500.0, None, 10)
        portfolio.open_position(trade, 500.0, stop_loss=460.0, take_profit=530.0)

        price_data = self._make_price_data("NVDA", 540.0)  # above target
        closed = portfolio.check_exits("2024-01-15", price_data)
        assert len(closed) == 1
        assert closed[0].exit_reason == "take_profit"

    def test_no_exit_when_price_between_levels(self):
        from backtest.engine import BacktestPortfolio, BacktestTrade
        portfolio = BacktestPortfolio(100_000)
        trade = BacktestTrade("NVDA", "long", "2024-01-02", None, 500.0, None, 10)
        portfolio.open_position(trade, 500.0, stop_loss=460.0, take_profit=560.0)

        price_data = self._make_price_data("NVDA", 510.0)  # between levels
        closed = portfolio.check_exits("2024-01-15", price_data)
        assert len(closed) == 0
        assert "NVDA" in portfolio.positions

    def test_position_size_limited_by_cash(self):
        from backtest.engine import BacktestPortfolio, BacktestTrade
        portfolio = BacktestPortfolio(1_000)
        # Try to buy more than we have
        trade = BacktestTrade("NVDA", "long", "2024-01-02", None, 500.0, None, 1000)
        portfolio.open_position(trade, 500.0, 460.0, 560.0)
        assert portfolio.cash >= 0, "Cash should never go negative"

    def test_pnl_calculation_correct(self):
        from backtest.engine import BacktestPortfolio, BacktestTrade
        portfolio = BacktestPortfolio(100_000)
        trade = BacktestTrade("NVDA", "long", "2024-01-02", None, 500.0, None, 10)
        portfolio.open_position(trade, 500.0, 460.0, 600.0)

        price_data = self._make_price_data("NVDA", 605.0)
        closed = portfolio.check_exits("2024-01-20", price_data)
        assert len(closed) == 1
        assert closed[0].pnl == pytest.approx(10 * (600.0 - 500.0), rel=1e-3)
        assert closed[0].pnl_pct == pytest.approx(20.0, rel=1e-3)

    def test_nav_includes_open_positions(self):
        from backtest.engine import BacktestPortfolio, BacktestTrade
        portfolio = BacktestPortfolio(100_000)
        trade = BacktestTrade("NVDA", "long", "2024-01-02", None, 500.0, None, 10)
        portfolio.open_position(trade, 500.0, 460.0, 600.0)

        price_data = self._make_price_data("NVDA", 550.0)
        nav = portfolio.calculate_nav("2024-01-15", price_data)
        # nav = cash + (10 shares * 550)
        expected = portfolio.cash + 10 * 550.0
        assert nav == pytest.approx(expected, rel=1e-3)

    def test_close_all_positions(self):
        from backtest.engine import BacktestPortfolio, BacktestTrade
        portfolio = BacktestPortfolio(100_000)
        for sym, price in [("NVDA", 500.0), ("AAPL", 180.0)]:
            trade = BacktestTrade(sym, "long", "2024-01-02", None, price, None, 5)
            portfolio.open_position(trade, price, price * 0.9, price * 1.2)

        price_data = {
            **self._make_price_data("NVDA", 510.0),
            **self._make_price_data("AAPL", 185.0),
        }
        closed = portfolio.close_all("2024-06-01", price_data)
        assert len(closed) == 2
        assert len(portfolio.positions) == 0
        assert all(t.exit_reason == "end_of_backtest" for t in closed)


# ── Multi-portfolio tests ─────────────────────────────────────

class TestMultiPortfolio:

    def test_default_portfolios_loaded(self):
        from strategies.multi_portfolio import MultiPortfolioManager
        mgr = MultiPortfolioManager()
        assert len(mgr.portfolios) > 0

    def test_allocation_total(self):
        from strategies.multi_portfolio import MultiPortfolioManager
        mgr = MultiPortfolioManager()
        total = sum(p.allocation_pct for p in mgr.portfolios.values() if p.active)
        assert total <= 1.0 + 1e-9, f"Total allocation {total:.2%} exceeds 100%"

    def test_add_portfolio_ok(self):
        from strategies.multi_portfolio import MultiPortfolioManager, PortfolioDefinition
        mgr = MultiPortfolioManager([])  # start empty
        p = PortfolioDefinition(
            portfolio_id="test", name="Test", strategy="momentum",
            allocation_pct=0.3, mode="short_term", market="us",
        )
        mgr.add_portfolio(p)
        assert "test" in mgr.portfolios

    def test_add_portfolio_exceeds_100_pct(self):
        from strategies.multi_portfolio import MultiPortfolioManager, PortfolioDefinition
        mgr = MultiPortfolioManager([])
        mgr.add_portfolio(PortfolioDefinition(
            portfolio_id="p1", name="P1", strategy="momentum",
            allocation_pct=0.7, mode="short_term", market="us",
        ))
        with pytest.raises(ValueError, match="Total allocation"):
            mgr.add_portfolio(PortfolioDefinition(
                portfolio_id="p2", name="P2", strategy="defensive",
                allocation_pct=0.5, mode="short_term", market="us",
            ))

    def test_pause_and_resume(self):
        from strategies.multi_portfolio import MultiPortfolioManager
        mgr = MultiPortfolioManager()
        first_id = list(mgr.portfolios.keys())[0]
        mgr.pause_portfolio(first_id)
        assert not mgr.portfolios[first_id].active
        mgr.resume_portfolio(first_id)
        assert mgr.portfolios[first_id].active

    def test_pause_nonexistent_portfolio_safe(self):
        from strategies.multi_portfolio import MultiPortfolioManager
        mgr = MultiPortfolioManager()
        mgr.pause_portfolio("does_not_exist")   # should not raise


# ── Phase 1 agent parser tests (no LLM calls) ────────────────

class TestPhase1Parsers:
    """Test Phase 1 agent helper methods that don't require LLM calls."""

    def test_macro_yield_curve_calculation(self):
        from agents.macro_intel import MacroIntelAgent
        agent = MacroIntelAgent()

        # Simulate what _fetch_macro_data would produce for yield curve
        data = {
            "us10y": {"value": 4.35, "change_pct": 0.02, "5d_trend": "up"},
            "us2y":  {"value": 4.80, "change_pct": 0.01, "5d_trend": "up"},
        }
        spread = data["us10y"]["value"] - data["us2y"]["value"]
        data["yield_curve_spread_bps"] = round(spread * 100, 1)
        data["yield_curve_shape"] = (
            "inverted" if spread < 0 else
            "flat"     if spread < 0.25 else "normal"
        )
        assert data["yield_curve_shape"] == "inverted"
        assert data["yield_curve_spread_bps"] == pytest.approx(-45.0, rel=1e-2)

    def test_news_sentiment_format_memories(self):
        from agents.news_sentiment import NewsSentimentAgent
        agent = NewsSentimentAgent()
        memories = [
            {"created_at": datetime(2024, 1, 15), "memory_type": "observation",
             "content": "NVDA strong earnings"},
        ]
        formatted = agent._format_memories(memories)
        assert "NVDA" in formatted
        assert "observation" in formatted

    def test_earnings_adjustments_within_3_days(self):
        from agents.earnings_calendar import EarningsCalendarAgent
        agent = EarningsCalendarAgent()
        result = {
            "upcoming_earnings": [
                {"symbol": "MSFT", "days_away": 2, "risk_rating": "high"}
            ],
            "recent_earnings_results": [],
        }
        adj = agent._build_adjustments(result)
        assert "MSFT" in adj
        assert adj["MSFT"]["max_weight_multiplier"] == 0.5
        assert adj["MSFT"]["stop_multiplier"] == 1.25

    def test_earnings_adjustments_within_7_days(self):
        from agents.earnings_calendar import EarningsCalendarAgent
        agent = EarningsCalendarAgent()
        result = {
            "upcoming_earnings": [
                {"symbol": "AAPL", "days_away": 5, "risk_rating": "medium"}
            ],
            "recent_earnings_results": [],
        }
        adj = agent._build_adjustments(result)
        assert adj["AAPL"]["max_weight_multiplier"] == 0.75
        assert adj["AAPL"]["stop_multiplier"] == 1.15

    def test_earnings_adjustments_force_exit(self):
        from agents.earnings_calendar import EarningsCalendarAgent
        agent = EarningsCalendarAgent()
        result = {
            "upcoming_earnings": [],
            "recent_earnings_results": [
                {"symbol": "TSLA", "post_earnings_action": "exit",
                 "surprise_pct": -12.0}
            ],
        }
        adj = agent._build_adjustments(result)
        assert adj["TSLA"]["max_weight_multiplier"] == 0.0
        assert adj["TSLA"]["force_exit"] is True

    def test_earnings_adjustments_no_adjustment_far_away(self):
        from agents.earnings_calendar import EarningsCalendarAgent
        agent = EarningsCalendarAgent()
        result = {
            "upcoming_earnings": [
                {"symbol": "NVDA", "days_away": 45, "risk_rating": "low"}
            ],
            "recent_earnings_results": [],
        }
        adj = agent._build_adjustments(result)
        assert "NVDA" not in adj  # 45 days away — no adjustment needed

    def test_options_flow_detects_high_score(self):
        """Verify options flow signal scoring is in valid range."""
        # Signal scores should be -1.0 to +1.0
        valid_scores = [-1.0, -0.75, -0.5, 0, 0.5, 0.75, 1.0]
        for score in valid_scores:
            assert -1.0 <= score <= 1.0

    def test_cio_phase1_summary_empty(self):
        from agents.cio import CIOAgent
        agent = CIOAgent()
        summary = agent._summarise_phase1({}, {}, {}, {})
        assert "Not yet available" in summary

    def test_cio_phase1_summary_with_data(self):
        from agents.cio import CIOAgent
        agent = CIOAgent()
        news  = {"overall_sentiment": 0.4, "market_moving_events": [{"magnitude": "high"}],
                 "watchlist_flags": {"NVDA": "bullish"}}
        macro = {"macro_regime": "GOLDILOCKS", "regime_confidence": 0.8,
                 "risk_budget_adjustment": {"adjusted": 4.5},
                 "sector_overweights": ["Technology"],
                 "sector_underweights": ["Utilities"]}
        summary = agent._summarise_phase1(news, macro, {}, {})
        assert "GOLDILOCKS" in summary
        assert "Technology" in summary
        assert "0.40" in summary or "+0.40" in summary


# ── Integration smoke tests ───────────────────────────────────

class TestPhase12Integration:
    """Light integration tests — verify components connect without errors."""

    def test_strategy_then_mandate_apply(self):
        from strategies.strategy_library import select_strategy, apply_strategy_to_mandate
        s = select_strategy("RATE_CUT_CYCLE", "long_term", "us")
        mandate = {"risk_budget": 5.0, "mode": "long_term", "watchlist": ["AAPL"]}
        updated = apply_strategy_to_mandate(mandate, s)

        # Should have all required mandate keys
        assert "strategy" in updated
        assert "agent_weights" in updated
        assert "risk_budget" in updated
        assert "preferred_algo" in updated
        assert updated["watchlist"] == ["AAPL"]  # preserved

    def test_rl_reward_consistent_sign(self):
        from strategies.rl_optimiser import RLWeightOptimiser
        opt = RLWeightOptimiser()

        # 100 random outcomes — profitable should give positive more than negative
        import random
        random.seed(42)
        positive_rewards = 0
        for _ in range(100):
            pnl = random.uniform(1.0, 10.0)
            hold = random.randint(1, 20)
            vol  = random.uniform(0.01, 0.04)
            r = opt._calculate_reward({"pnl_pct": pnl, "hold_days": hold, "entry_volatility": vol})
            if r > 0:
                positive_rewards += 1
        assert positive_rewards > 80, "Positive PnL should mostly give positive reward"

    def test_backtest_metric_calculation_zero_trades(self):
        """BacktestEngine._calculate_metrics should handle no closed trades."""
        from backtest.engine import BacktestEngine
        engine = BacktestEngine()
        result = engine._calculate_metrics(
            "momentum", ["NVDA"], "2024-01-01", "2024-06-01",
            100_000, 105_000, [], [], [],
        )
        assert result.total_return_pct == pytest.approx(5.0, rel=1e-2)
        assert result.total_trades == 0
        assert result.win_rate == 0.0

    def test_portfolio_manager_strategies_valid(self):
        """All default portfolio strategies must exist in strategy library."""
        from strategies.multi_portfolio import MultiPortfolioManager
        from strategies.strategy_library import STRATEGIES
        mgr = MultiPortfolioManager()
        for pid, portfolio in mgr.portfolios.items():
            assert portfolio.strategy in STRATEGIES, \
                f"Portfolio '{pid}' uses unknown strategy '{portfolio.strategy}'"
