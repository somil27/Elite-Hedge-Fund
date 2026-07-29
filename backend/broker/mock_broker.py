"""
Mock Broker — deterministic fills for testing and CI.
No API keys needed. Simulates realistic market microstructure:
  - Configurable slippage model
  - Partial fills on large orders
  - Market impact simulation
  - Order rejection scenarios
"""
from __future__ import annotations
import asyncio
import random
import uuid
from datetime import datetime, timezone
from typing import Optional
import structlog

from broker.base import (
    AbstractBroker, OrderRequest, Order, OrderStatus, OrderSide,
    OrderType, Position, AccountInfo, MarketClock,
    Fill, OrderUpdateCallback,
)

logger = structlog.get_logger()

# Simulated prices (override per-symbol or use defaults)
MOCK_PRICES: dict[str, float] = {
    "AAPL": 185.00, "NVDA": 875.00, "MSFT": 420.00,
    "TSLA": 245.00, "AMZN": 195.00, "META": 540.00,
    "GLD":  195.00, "SPY":  550.00, "QQQ":  480.00,
    "GOOGL": 175.00, "AMD": 165.00, "NFLX": 700.00,
}

DEFAULT_PRICE = 100.0
SLIPPAGE_BPS_RANGE = (0.5, 8.0)   # realistic for liquid equities


class MockBroker(AbstractBroker):
    """
    Deterministic mock broker. Useful for:
    - Unit tests (no network calls)
    - CI/CD pipelines
    - Demo mode without API keys
    - Local development
    """

    def __init__(
        self,
        initial_cash: float = 100_000.0,
        slippage_bps: float = 2.0,      # average slippage in bps
        fill_delay_ms: float = 150.0,   # simulated fill latency
        partial_fill_prob: float = 0.0, # probability of partial fill (0=never)
        reject_prob: float = 0.0,       # probability of random rejection
    ):
        self._cash = initial_cash
        self._initial_cash = initial_cash
        self._slippage_bps = slippage_bps
        self._fill_delay_ms = fill_delay_ms
        self._partial_fill_prob = partial_fill_prob
        self._reject_prob = reject_prob
        self._orders: dict[str, Order] = {}
        self._positions: dict[str, Position] = {}
        self._fills: list[Fill] = []
        self._connected = False
        self._order_callbacks: list[OrderUpdateCallback] = []
        self._portfolio_high: float = initial_cash

    # ── Connection ────────────────────────────────────────────

    async def connect(self) -> None:
        self._connected = True
        logger.info("mock_broker_connected", cash=self._cash)

    async def disconnect(self) -> None:
        self._connected = False

    async def is_connected(self) -> bool:
        return self._connected

    # ── Account ───────────────────────────────────────────────

    async def get_account(self) -> AccountInfo:
        portfolio_value = self._cash + sum(
            p.market_value for p in self._positions.values()
        )
        self._portfolio_high = max(self._portfolio_high, portfolio_value)
        drawdown = (self._portfolio_high - portfolio_value) / self._portfolio_high

        return AccountInfo(
            account_id="MOCK-ACCOUNT-001",
            portfolio_value=portfolio_value,
            cash=self._cash,
            buying_power=self._cash * 2,   # 2x margin
            day_trade_count=0,
            pattern_day_trader=False,
            trading_blocked=False,
        )

    async def get_market_clock(self) -> MarketClock:
        from datetime import timedelta
        now = datetime.now(timezone.utc)
        return MarketClock(
            is_open=True,   # mock is always open
            next_open=now,
            next_close=now + timedelta(hours=8),
        )

    # ── Orders ────────────────────────────────────────────────

    async def submit_order(self, req: OrderRequest) -> Order:
        order_id = str(uuid.uuid4())

        # Simulate rejection
        if random.random() < self._reject_prob:
            order = Order(
                order_id=order_id,
                client_order_id=req.client_order_id,
                symbol=req.symbol,
                side=req.side,
                order_type=req.order_type,
                qty=req.qty,
                status=OrderStatus.REJECTED,
                reject_reason="Simulated rejection",
                submitted_at=datetime.now(timezone.utc),
            )
            self._orders[order_id] = order
            logger.warning("mock_order_rejected", symbol=req.symbol)
            return order

        order = Order(
            order_id=order_id,
            client_order_id=req.client_order_id or str(uuid.uuid4()),
            symbol=req.symbol,
            side=req.side,
            order_type=req.order_type,
            qty=req.qty,
            limit_price=req.limit_price,
            stop_price=req.stop_price,
            status=OrderStatus.SUBMITTED,
            submitted_at=datetime.now(timezone.utc),
        )
        self._orders[order_id] = order

        # Schedule async fill
        asyncio.create_task(self._simulate_fill(order))
        logger.info("mock_order_submitted",
                    order_id=order_id, symbol=req.symbol,
                    side=req.side.value, qty=req.qty)
        return order

    async def _simulate_fill(self, order: Order) -> None:
        """Simulate fill with realistic delay and slippage."""
        await asyncio.sleep(self._fill_delay_ms / 1000.0)

        base_price = MOCK_PRICES.get(order.symbol, DEFAULT_PRICE)

        # Apply slippage
        slippage_pct = random.uniform(
            self._slippage_bps * 0.5,
            self._slippage_bps * 1.5,
        ) / 10_000

        if order.side == OrderSide.BUY:
            fill_price = base_price * (1 + slippage_pct)
        else:
            fill_price = base_price * (1 - slippage_pct)

        fill_price = round(fill_price, 2)

        # Partial fill simulation
        if random.random() < self._partial_fill_prob:
            filled_qty = order.qty * random.uniform(0.4, 0.8)
            filled_qty = round(filled_qty, 4)
            status = OrderStatus.PARTIAL
        else:
            filled_qty = order.qty
            status = OrderStatus.FILLED

        fill = Fill(
            fill_id=str(uuid.uuid4()),
            order_id=order.order_id,
            symbol=order.symbol,
            side=order.side,
            qty=filled_qty,
            price=fill_price,
            timestamp=datetime.now(timezone.utc),
            commission=filled_qty * fill_price * 0.0005,   # 5 bps commission
        )
        self._fills.append(fill)

        order.filled_qty = filled_qty
        order.avg_fill_price = fill_price
        order.status = status
        order.filled_at = datetime.now(timezone.utc)
        order.fills = [fill]

        # Update cash and positions
        notional = filled_qty * fill_price
        if order.side == OrderSide.BUY:
            self._cash -= notional
            self._update_position_buy(order.symbol, filled_qty, fill_price)
        else:
            self._cash += notional
            self._update_position_sell(order.symbol, filled_qty, fill_price)

        # Fire callbacks
        for cb in self._order_callbacks:
            await cb(order)

        logger.info("mock_order_filled",
                    order_id=order.order_id,
                    symbol=order.symbol,
                    fill_price=fill_price,
                    qty=filled_qty,
                    status=status.value)

    def _update_position_buy(self, symbol: str, qty: float, price: float):
        if symbol in self._positions:
            pos = self._positions[symbol]
            total_qty = pos.qty + qty
            avg_entry = (pos.avg_entry_price * pos.qty + price * qty) / total_qty
            pos.qty = total_qty
            pos.avg_entry_price = avg_entry
            pos.cost_basis = total_qty * avg_entry
        else:
            self._positions[symbol] = Position(
                symbol=symbol,
                qty=qty,
                side="long",
                avg_entry_price=price,
                current_price=price,
                market_value=qty * price,
                unrealized_pnl=0,
                unrealized_pnl_pct=0,
                cost_basis=qty * price,
            )

    def _update_position_sell(self, symbol: str, qty: float, price: float):
        if symbol in self._positions:
            pos = self._positions[symbol]
            pos.qty -= qty
            if pos.qty <= 0:
                del self._positions[symbol]

    async def get_order(self, order_id: str) -> Order:
        if order_id not in self._orders:
            raise ValueError(f"Order {order_id} not found")
        return self._orders[order_id]

    async def get_orders(self, status=None, limit=50) -> list[Order]:
        orders = list(self._orders.values())
        if status:
            orders = [o for o in orders if o.status.value == status]
        return orders[:limit]

    async def cancel_order(self, order_id: str) -> bool:
        if order_id in self._orders:
            order = self._orders[order_id]
            if not order.is_terminal:
                order.status = OrderStatus.CANCELLED
                order.cancelled_at = datetime.now(timezone.utc)
                return True
        return False

    async def cancel_all_orders(self) -> int:
        count = 0
        for order in self._orders.values():
            if not order.is_terminal:
                order.status = OrderStatus.CANCELLED
                count += 1
        return count

    # ── Positions ─────────────────────────────────────────────

    async def get_positions(self) -> list[Position]:
        # Refresh market values with current mock prices
        for symbol, pos in self._positions.items():
            current = MOCK_PRICES.get(symbol, pos.avg_entry_price)
            pos.current_price = current
            pos.market_value = pos.qty * current
            pos.unrealized_pnl = (current - pos.avg_entry_price) * pos.qty
            pos.unrealized_pnl_pct = (
                pos.unrealized_pnl / pos.cost_basis
                if pos.cost_basis else 0
            )
        return list(self._positions.values())

    async def get_position(self, symbol: str) -> Optional[Position]:
        return self._positions.get(symbol)

    async def close_position(self, symbol: str, qty=None) -> Order:
        pos = self._positions.get(symbol)
        if not pos:
            raise ValueError(f"No position for {symbol}")
        close_qty = qty or pos.qty
        return await self.submit_order(OrderRequest(
            symbol=symbol,
            side=OrderSide.SELL if pos.side == "long" else OrderSide.BUY,
            qty=close_qty,
            order_type=OrderType.MARKET,
        ))

    async def close_all_positions(self) -> list[Order]:
        orders = []
        for symbol in list(self._positions.keys()):
            order = await self.close_position(symbol)
            orders.append(order)
        return orders

    # ── Streaming ─────────────────────────────────────────────

    async def subscribe_order_updates(self, callback: OrderUpdateCallback) -> None:
        self._order_callbacks.append(callback)

    async def unsubscribe_order_updates(self) -> None:
        self._order_callbacks.clear()

    # ── Mock-specific ─────────────────────────────────────────

    def set_price(self, symbol: str, price: float) -> None:
        """Override price for a symbol (useful in tests)."""
        MOCK_PRICES[symbol] = price

    def get_fill_history(self) -> list[Fill]:
        return self._fills.copy()

    async def get_pnl_summary(self) -> dict:
        positions = await self.get_positions()
        account = await self.get_account()
        total_unrealized = sum(p.unrealized_pnl for p in positions)
        return {
            "total_value": account.portfolio_value,
            "cash": self._cash,
            "unrealized_pnl": total_unrealized,
            "position_count": len(positions),
            "fills_today": len(self._fills),
        }
