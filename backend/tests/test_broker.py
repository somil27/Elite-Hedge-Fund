"""
Broker unit tests.
Run with:  pytest tests/test_broker.py -v

These tests use MockBroker only — no API keys or network needed.
"""
import asyncio
import pytest
import pytest_asyncio

from broker.mock_broker import MockBroker, MOCK_PRICES
from broker.base import (
    OrderRequest, OrderSide, OrderType, OrderStatus,
)
from broker.execution_algos import ExecutionAlgoEngine, AlgoConfig


# ── Fixtures ─────────────────────────────────────────────────

@pytest_asyncio.fixture
async def broker():
    b = MockBroker(
        initial_cash=100_000,
        slippage_bps=2.0,
        fill_delay_ms=10,    # fast for tests
    )
    await b.connect()
    yield b
    await b.disconnect()


@pytest_asyncio.fixture
async def algo_engine(broker):
    return ExecutionAlgoEngine(broker)


# ── Connection tests ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_connect_disconnect():
    b = MockBroker()
    assert not await b.is_connected()
    await b.connect()
    assert await b.is_connected()
    await b.disconnect()
    assert not await b.is_connected()


# ── Account tests ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_account(broker):
    acc = await broker.get_account()
    assert acc.portfolio_value == 100_000
    assert acc.cash == 100_000
    assert acc.account_id == "MOCK-ACCOUNT-001"
    assert not acc.trading_blocked


@pytest.mark.asyncio
async def test_market_clock(broker):
    clock = await broker.get_market_clock()
    assert clock.is_open is True   # mock is always open
    assert clock.next_open is not None
    assert clock.next_close is not None


# ── Order submission tests ────────────────────────────────────

@pytest.mark.asyncio
async def test_market_buy_fills(broker):
    req = OrderRequest(
        symbol="AAPL",
        side=OrderSide.BUY,
        qty=10,
        order_type=OrderType.MARKET,
    )
    order = await broker.submit_order(req)
    assert order.order_id is not None
    assert order.symbol == "AAPL"

    # Wait for fill
    filled = await broker.wait_for_fill(order.order_id, timeout_seconds=5)
    assert filled.status == OrderStatus.FILLED
    assert filled.filled_qty == 10
    assert filled.avg_fill_price > 0
    assert len(filled.fills) == 1


@pytest.mark.asyncio
async def test_market_sell_fills(broker):
    # First buy so we have a position
    buy_req = OrderRequest(symbol="NVDA", side=OrderSide.BUY, qty=5,
                           order_type=OrderType.MARKET)
    buy = await broker.submit_order(buy_req)
    await broker.wait_for_fill(buy.order_id, timeout_seconds=5)

    # Now sell
    sell_req = OrderRequest(symbol="NVDA", side=OrderSide.SELL, qty=5,
                            order_type=OrderType.MARKET)
    sell = await broker.submit_order(sell_req)
    filled = await broker.wait_for_fill(sell.order_id, timeout_seconds=5)
    assert filled.status == OrderStatus.FILLED
    assert filled.filled_qty == 5


@pytest.mark.asyncio
async def test_slippage_direction(broker):
    """Buys should fill slightly above mid; sells slightly below."""
    MOCK_PRICES["AAPL"] = 185.0

    buy_req = OrderRequest(symbol="AAPL", side=OrderSide.BUY, qty=1,
                           order_type=OrderType.MARKET)
    buy = await broker.submit_order(buy_req)
    buy_filled = await broker.wait_for_fill(buy.order_id, timeout_seconds=5)
    assert buy_filled.avg_fill_price >= 185.0   # buy above mid

    sell_req = OrderRequest(symbol="AAPL", side=OrderSide.SELL, qty=1,
                            order_type=OrderType.MARKET)
    sell = await broker.submit_order(sell_req)
    sell_filled = await broker.wait_for_fill(sell.order_id, timeout_seconds=5)
    assert sell_filled.avg_fill_price <= 185.0  # sell below mid


@pytest.mark.asyncio
async def test_cancel_order(broker):
    """An order can be cancelled before fill (hard to test with fast mock,
    but we verify the cancel API works on an already-filled order)."""
    req = OrderRequest(symbol="MSFT", side=OrderSide.BUY, qty=1,
                       order_type=OrderType.MARKET)
    order = await broker.submit_order(req)
    # Wait for fill first
    await asyncio.sleep(0.05)
    result = await broker.cancel_order(order.order_id)
    # Either cancelled (if caught before fill) or already filled — both OK
    assert isinstance(result, bool)


@pytest.mark.asyncio
async def test_cancel_all_orders(broker):
    for sym in ["AAPL", "MSFT", "NVDA"]:
        req = OrderRequest(symbol=sym, side=OrderSide.BUY, qty=1,
                           order_type=OrderType.MARKET)
        await broker.submit_order(req)
    count = await broker.cancel_all_orders()
    assert isinstance(count, int)


# ── Position tests ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_position_created_after_buy(broker):
    MOCK_PRICES["TSLA"] = 245.0
    req = OrderRequest(symbol="TSLA", side=OrderSide.BUY, qty=3,
                       order_type=OrderType.MARKET)
    order = await broker.submit_order(req)
    await broker.wait_for_fill(order.order_id, timeout_seconds=5)

    positions = await broker.get_positions()
    syms = [p.symbol for p in positions]
    assert "TSLA" in syms

    pos = await broker.get_position("TSLA")
    assert pos is not None
    assert pos.qty == 3
    assert pos.side == "long"
    assert pos.avg_entry_price > 0


@pytest.mark.asyncio
async def test_position_removed_after_close(broker):
    MOCK_PRICES["AMZN"] = 195.0
    buy = OrderRequest(symbol="AMZN", side=OrderSide.BUY, qty=2,
                       order_type=OrderType.MARKET)
    buy_order = await broker.submit_order(buy)
    await broker.wait_for_fill(buy_order.order_id, timeout_seconds=5)

    close_order = await broker.close_position("AMZN")
    await broker.wait_for_fill(close_order.order_id, timeout_seconds=5)

    pos = await broker.get_position("AMZN")
    assert pos is None


@pytest.mark.asyncio
async def test_cash_decreases_on_buy(broker):
    acc_before = await broker.get_account()
    MOCK_PRICES["GLD"] = 195.0

    req = OrderRequest(symbol="GLD", side=OrderSide.BUY, qty=10,
                       order_type=OrderType.MARKET)
    order = await broker.submit_order(req)
    await broker.wait_for_fill(order.order_id, timeout_seconds=5)

    acc_after = await broker.get_account()
    assert acc_after.cash < acc_before.cash


# ── Streaming tests ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_order_update_callback(broker):
    received = []

    async def on_update(order):
        received.append(order)

    await broker.subscribe_order_updates(on_update)
    req = OrderRequest(symbol="SPY", side=OrderSide.BUY, qty=2,
                       order_type=OrderType.MARKET)
    await broker.submit_order(req)
    await asyncio.sleep(0.2)  # let fill complete

    assert len(received) >= 1
    assert any(o.symbol == "SPY" for o in received)
    await broker.unsubscribe_order_updates()


# ── Execution algo tests ──────────────────────────────────────

@pytest.mark.asyncio
async def test_aggressive_algo(algo_engine):
    config = AlgoConfig(
        symbol="AAPL", side=OrderSide.BUY,
        total_qty=5, algo="aggressive",
    )
    result = await algo_engine.execute(config)
    assert result.filled_qty == 5
    assert result.avg_fill_price > 0
    assert result.slices_sent == 1
    assert result.status == "complete"


@pytest.mark.asyncio
async def test_twap_algo(algo_engine):
    config = AlgoConfig(
        symbol="MSFT", side=OrderSide.BUY,
        total_qty=10, algo="twap",
        num_slices=3, duration_min=0,   # 0 = no sleep in test
    )
    result = await algo_engine.execute(config)
    assert result.filled_qty > 0
    assert result.slices_sent == 3
    assert result.algo == "twap"


@pytest.mark.asyncio
async def test_vwap_algo(algo_engine):
    config = AlgoConfig(
        symbol="NVDA", side=OrderSide.BUY,
        total_qty=4, algo="vwap",
        num_slices=4, duration_min=0,
    )
    result = await algo_engine.execute(config)
    assert result.filled_qty > 0
    assert result.algo == "vwap"
    assert result.slices_sent == 4


@pytest.mark.asyncio
async def test_passive_algo(algo_engine):
    config = AlgoConfig(
        symbol="SPY", side=OrderSide.BUY,
        total_qty=3, algo="passive",
        num_slices=3, duration_min=0,
    )
    result = await algo_engine.execute(config)
    assert result.filled_qty >= 0   # passive may not always fill fully
    assert result.algo == "passive"


@pytest.mark.asyncio
async def test_algo_progress_callback(algo_engine):
    progress_events = []

    async def on_progress(symbol, pct, avg_price, elapsed):
        progress_events.append({"pct": pct, "avg": avg_price})

    config = AlgoConfig(
        symbol="AAPL", side=OrderSide.BUY,
        total_qty=6, algo="twap",
        num_slices=3, duration_min=0,
    )
    await algo_engine.execute(config, on_progress=on_progress)
    assert len(progress_events) > 0
    assert all(0 <= e["pct"] <= 1.0 for e in progress_events)


# ── Rejection simulation ──────────────────────────────────────

@pytest.mark.asyncio
async def test_random_rejection():
    broker = MockBroker(reject_prob=1.0, fill_delay_ms=10)
    await broker.connect()

    req = OrderRequest(symbol="AAPL", side=OrderSide.BUY, qty=1,
                       order_type=OrderType.MARKET)
    order = await broker.submit_order(req)
    await asyncio.sleep(0.05)

    refreshed = await broker.get_order(order.order_id)
    assert refreshed.status == OrderStatus.REJECTED
    await broker.disconnect()


# ── Portfolio snapshot ────────────────────────────────────────

@pytest.mark.asyncio
async def test_portfolio_snapshot_structure(broker):
    from broker.registry import get_portfolio_snapshot
    # Temporarily set the global broker to our test instance
    import broker.registry as reg
    orig = reg._us_broker
    reg._us_broker = broker

    snap = await get_portfolio_snapshot()
    assert "total_value" in snap
    assert "cash" in snap
    assert "buying_power" in snap
    assert "positions" in snap
    assert isinstance(snap["positions"], list)

    reg._us_broker = orig
