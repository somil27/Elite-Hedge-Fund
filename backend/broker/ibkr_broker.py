"""
Interactive Brokers Broker Stub
Implements AbstractBroker using ib_insync.
Requires: pip install ib_insync
Requires: TWS or IB Gateway running locally on port 7497 (paper) or 7496 (live).

To activate:
1. Install ib_insync: pip install ib_insync
2. Start TWS or IB Gateway
3. Enable API access in TWS: File → Global Config → API → Enable ActiveX and Socket Clients
4. Set BROKER=ibkr in .env
"""
from __future__ import annotations
import asyncio
from datetime import datetime, timezone
from typing import Optional
import structlog

from broker.base import (
    AbstractBroker, OrderRequest, Order, OrderStatus, OrderSide,
    OrderType, Position, AccountInfo, MarketClock,
    OrderUpdateCallback,
)

logger = structlog.get_logger()

# TWS connection defaults
TWS_HOST = "127.0.0.1"
TWS_PAPER_PORT = 7497
TWS_LIVE_PORT  = 7496
CLIENT_ID = 1


class IBKRBroker(AbstractBroker):
    """
    Interactive Brokers broker via ib_insync.
    Supports equities, options, futures, forex.
    """

    def __init__(self, paper: bool = True):
        self.paper = paper
        self._port = TWS_PAPER_PORT if paper else TWS_LIVE_PORT
        self._ib = None
        self._connected = False
        self._order_callbacks: list[OrderUpdateCallback] = []

    # ── Connection ────────────────────────────────────────────

    async def connect(self) -> None:
        try:
            import ib_insync as ibi
            self._ib = ibi.IB()
            await self._ib.connectAsync(
                TWS_HOST, self._port, clientId=CLIENT_ID
            )
            self._ib.orderStatusEvent += self._on_order_status
            self._connected = True
            logger.info("ibkr_connected", paper=self.paper, port=self._port)
        except ImportError:
            raise ImportError(
                "ib_insync not installed. Run: pip install ib_insync"
            )
        except Exception as e:
            raise RuntimeError(f"IBKR connection failed: {e}")

    async def disconnect(self) -> None:
        if self._ib and self._ib.isConnected():
            self._ib.disconnect()
        self._connected = False
        logger.info("ibkr_disconnected")

    async def is_connected(self) -> bool:
        return self._connected and self._ib is not None and self._ib.isConnected()

    def _ensure_connected(self):
        if not self._ib or not self._ib.isConnected():
            raise RuntimeError("IBKRBroker not connected.")

    # ── Account ───────────────────────────────────────────────

    async def get_account(self) -> AccountInfo:
        self._ensure_connected()
        summary = await self._ib.accountSummaryAsync()
        vals = {item.tag: float(item.value)
                for item in summary if item.currency == "USD"}
        return AccountInfo(
            account_id=self._ib.managedAccounts()[0],
            portfolio_value=vals.get("NetLiquidation", 0),
            cash=vals.get("CashBalance", 0),
            buying_power=vals.get("BuyingPower", 0),
            initial_margin=vals.get("InitMarginReq", 0),
            maintenance_margin=vals.get("MaintMarginReq", 0),
        )

    async def get_market_clock(self) -> MarketClock:
        # IB doesn't expose a simple clock endpoint — derive from trading hours
        from datetime import datetime, timezone, timedelta
        now = datetime.now(timezone.utc)
        # Approximate: NYSE 9:30–16:00 ET (14:30–21:00 UTC)
        et_offset = timedelta(hours=-4)   # EDT
        now_et = now + et_offset
        market_open = now_et.replace(hour=9, minute=30, second=0, microsecond=0)
        market_close = now_et.replace(hour=16, minute=0, second=0, microsecond=0)
        is_open = (market_open <= now_et <= market_close
                   and now_et.weekday() < 5)
        return MarketClock(
            is_open=is_open,
            next_open=market_open if not is_open else market_open + timedelta(days=1),
            next_close=market_close,
        )

    # ── Orders ────────────────────────────────────────────────

    async def submit_order(self, req: OrderRequest) -> Order:
        self._ensure_connected()
        import ib_insync as ibi

        contract = ibi.Stock(req.symbol, "SMART", "USD")
        await self._ib.qualifyContractsAsync(contract)

        if req.order_type == OrderType.MARKET:
            ib_order = ibi.MarketOrder(
                action="BUY" if req.side == OrderSide.BUY else "SELL",
                totalQuantity=req.qty,
            )
        elif req.order_type == OrderType.LIMIT:
            ib_order = ibi.LimitOrder(
                action="BUY" if req.side == OrderSide.BUY else "SELL",
                totalQuantity=req.qty,
                lmtPrice=req.limit_price,
            )
        elif req.order_type == OrderType.STOP:
            ib_order = ibi.StopOrder(
                action="BUY" if req.side == OrderSide.BUY else "SELL",
                totalQuantity=req.qty,
                stopPrice=req.stop_price,
            )
        else:
            ib_order = ibi.MarketOrder(
                action="BUY" if req.side == OrderSide.BUY else "SELL",
                totalQuantity=req.qty,
            )

        trade = self._ib.placeOrder(contract, ib_order)
        logger.info("ibkr_order_placed",
                    symbol=req.symbol, side=req.side.value, qty=req.qty)

        return Order(
            order_id=str(trade.order.orderId),
            client_order_id=req.client_order_id,
            symbol=req.symbol,
            side=req.side,
            order_type=req.order_type,
            qty=req.qty,
            status=OrderStatus.SUBMITTED,
            submitted_at=datetime.now(timezone.utc),
        )

    async def get_order(self, order_id: str) -> Order:
        self._ensure_connected()
        trades = self._ib.trades()
        for trade in trades:
            if str(trade.order.orderId) == order_id:
                return self._ib_trade_to_order(trade)
        raise ValueError(f"Order {order_id} not found")

    async def get_orders(self, status=None, limit=50) -> list[Order]:
        self._ensure_connected()
        trades = self._ib.trades()
        return [self._ib_trade_to_order(t) for t in trades[:limit]]

    async def cancel_order(self, order_id: str) -> bool:
        self._ensure_connected()
        trades = self._ib.trades()
        for trade in trades:
            if str(trade.order.orderId) == order_id:
                self._ib.cancelOrder(trade.order)
                logger.info("ibkr_order_cancelled", order_id=order_id)
                return True
        return False

    async def cancel_all_orders(self) -> int:
        self._ensure_connected()
        trades = self._ib.trades()
        count = 0
        for trade in trades:
            if trade.orderStatus.status not in ("Filled", "Cancelled"):
                self._ib.cancelOrder(trade.order)
                count += 1
        return count

    # ── Positions ─────────────────────────────────────────────

    async def get_positions(self) -> list[Position]:
        self._ensure_connected()
        positions = await self._ib.reqPositionsAsync()
        result = []
        for pos in positions:
            result.append(Position(
                symbol=pos.contract.symbol,
                qty=abs(pos.position),
                side="long" if pos.position > 0 else "short",
                avg_entry_price=pos.avgCost,
                current_price=pos.avgCost,   # requires market data subscription
                market_value=abs(pos.position) * pos.avgCost,
                unrealized_pnl=0,
                unrealized_pnl_pct=0,
                cost_basis=abs(pos.position) * pos.avgCost,
            ))
        return result

    async def get_position(self, symbol: str) -> Optional[Position]:
        positions = await self.get_positions()
        return next((p for p in positions if p.symbol == symbol), None)

    async def close_position(self, symbol: str, qty=None) -> Order:
        pos = await self.get_position(symbol)
        if not pos:
            raise ValueError(f"No open position for {symbol}")
        close_qty = qty or pos.qty
        side = OrderSide.SELL if pos.side == "long" else OrderSide.BUY
        return await self.submit_order(OrderRequest(
            symbol=symbol, side=side, qty=close_qty,
            order_type=OrderType.MARKET,
        ))

    async def close_all_positions(self) -> list[Order]:
        positions = await self.get_positions()
        orders = []
        for pos in positions:
            order = await self.close_position(pos.symbol)
            orders.append(order)
        return orders

    # ── Streaming ─────────────────────────────────────────────

    async def subscribe_order_updates(self, callback: OrderUpdateCallback) -> None:
        self._order_callbacks.append(callback)

    async def unsubscribe_order_updates(self) -> None:
        self._order_callbacks.clear()

    def _on_order_status(self, trade):
        """IB order status event handler — fires callbacks."""
        order = self._ib_trade_to_order(trade)
        for cb in self._order_callbacks:
            asyncio.ensure_future(cb(order))

    # ── Internal ──────────────────────────────────────────────

    def _ib_trade_to_order(self, trade) -> Order:
        status_map = {
            "Submitted":        OrderStatus.SUBMITTED,
            "PreSubmitted":     OrderStatus.SUBMITTED,
            "Filled":           OrderStatus.FILLED,
            "PartiallyFilled":  OrderStatus.PARTIAL,
            "Cancelled":        OrderStatus.CANCELLED,
            "Inactive":         OrderStatus.CANCELLED,
        }
        status = status_map.get(
            trade.orderStatus.status, OrderStatus.PENDING
        )
        return Order(
            order_id=str(trade.order.orderId),
            client_order_id=None,
            symbol=trade.contract.symbol,
            side=OrderSide.BUY if trade.order.action == "BUY" else OrderSide.SELL,
            order_type=OrderType.MARKET,
            qty=float(trade.order.totalQuantity),
            filled_qty=float(trade.orderStatus.filled),
            avg_fill_price=float(trade.orderStatus.avgFillPrice) or None,
            status=status,
            submitted_at=datetime.now(timezone.utc),
        )
