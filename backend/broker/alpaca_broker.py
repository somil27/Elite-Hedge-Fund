"""
Alpaca Broker Implementation
Full implementation of AbstractBroker using alpaca-py SDK.
Supports paper and live trading, REST + WebSocket streaming.
"""
from __future__ import annotations
import asyncio
import uuid
from datetime import datetime, timezone
from typing import Optional
import structlog

from broker.base import (
    AbstractBroker, OrderRequest, Order, OrderStatus, OrderSide,
    OrderType, TimeInForce, Position, AccountInfo, MarketClock,
    Fill, OrderUpdateCallback,
)
from core.config import settings
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

logger = structlog.get_logger()


def _to_alpaca_side(side: OrderSide):
    from alpaca.trading.enums import OrderSide as AlpacaSide
    return AlpacaSide.BUY if side == OrderSide.BUY else AlpacaSide.SELL


def _to_alpaca_tif(tif: TimeInForce):
    from alpaca.trading.enums import TimeInForce as AlpacaTIF
    mapping = {
        TimeInForce.DAY: AlpacaTIF.DAY,
        TimeInForce.GTC: AlpacaTIF.GTC,
        TimeInForce.IOC: AlpacaTIF.IOC,
        TimeInForce.FOK: AlpacaTIF.FOK,
        TimeInForce.OPG: AlpacaTIF.OPG,
        TimeInForce.CLS: AlpacaTIF.CLS,
    }
    return mapping.get(tif, AlpacaTIF.DAY)


def _parse_order_status(status_str: str) -> OrderStatus:
    mapping = {
        "new":              OrderStatus.SUBMITTED,
        "partially_filled": OrderStatus.PARTIAL,
        "filled":           OrderStatus.FILLED,
        "done_for_day":     OrderStatus.CANCELLED,
        "canceled":         OrderStatus.CANCELLED,
        "cancelled":        OrderStatus.CANCELLED,
        "expired":          OrderStatus.EXPIRED,
        "replaced":         OrderStatus.CANCELLED,
        "pending_cancel":   OrderStatus.SUBMITTED,
        "pending_replace":  OrderStatus.SUBMITTED,
        "held":             OrderStatus.SUBMITTED,
        "accepted":         OrderStatus.SUBMITTED,
        "pending_new":      OrderStatus.PENDING,
        "rejected":         OrderStatus.REJECTED,
    }
    return mapping.get(str(status_str).lower(), OrderStatus.PENDING)


def _alpaca_order_to_order(ao) -> Order:
    """Convert an alpaca-py Order object to our Order dataclass."""
    fills = []
    if hasattr(ao, "legs") and ao.legs:
        for leg in ao.legs:
            if leg.filled_avg_price:
                fills.append(Fill(
                    fill_id=str(uuid.uuid4()),
                    order_id=str(ao.id),
                    symbol=str(ao.symbol),
                    side=OrderSide.BUY if str(ao.side).lower() == "buy" else OrderSide.SELL,
                    qty=float(leg.filled_qty or 0),
                    price=float(leg.filled_avg_price),
                    timestamp=datetime.now(timezone.utc),
                ))

    return Order(
        order_id=str(ao.id),
        client_order_id=str(ao.client_order_id) if ao.client_order_id else None,
        symbol=str(ao.symbol),
        side=OrderSide.BUY if str(ao.side).lower() == "buy" else OrderSide.SELL,
        order_type=OrderType.MARKET if str(ao.type).lower() == "market" else OrderType.LIMIT,
        qty=float(ao.qty or 0),
        filled_qty=float(ao.filled_qty or 0),
        limit_price=float(ao.limit_price) if ao.limit_price else None,
        stop_price=float(ao.stop_price) if ao.stop_price else None,
        avg_fill_price=float(ao.filled_avg_price) if ao.filled_avg_price else None,
        status=_parse_order_status(str(ao.status)),
        submitted_at=ao.submitted_at,
        filled_at=ao.filled_at,
        cancelled_at=ao.canceled_at if hasattr(ao, "canceled_at") else None,
        fills=fills,
    )


def _alpaca_position_to_position(ap) -> Position:
    qty = float(ap.qty or 0)
    return Position(
        symbol=str(ap.symbol),
        qty=abs(qty),
        side="long" if qty > 0 else "short",
        avg_entry_price=float(ap.avg_entry_price or 0),
        current_price=float(ap.current_price or 0),
        market_value=float(ap.market_value or 0),
        unrealized_pnl=float(ap.unrealized_pl or 0),
        unrealized_pnl_pct=float(ap.unrealized_plpc or 0),
        cost_basis=float(ap.cost_basis or 0),
    )


class AlpacaBroker(AbstractBroker):
    """
    Full Alpaca broker: paper and live trading.
    Uses alpaca-py REST client + WebSocket streaming for order updates.
    """

    def __init__(self, paper: bool = True):
        self.paper = paper
        self._client = None
        self._stream = None
        self._stream_task: Optional[asyncio.Task] = None
        self._order_callbacks: list[OrderUpdateCallback] = []
        self._connected = False

    # ── Connection ────────────────────────────────────────────

    async def connect(self) -> None:
        if not settings.alpaca_api_key or not settings.alpaca_secret_key:
            raise RuntimeError(
                "ALPACA_API_KEY and ALPACA_SECRET_KEY must be set in .env"
            )
        def _init():
            from alpaca.trading.client import TradingClient
            return TradingClient(
                settings.alpaca_api_key,
                settings.alpaca_secret_key,
                paper=self.paper,
            )
        self._client = await asyncio.get_event_loop().run_in_executor(None, _init)
        self._connected = True
        logger.info("alpaca_connected", paper=self.paper)

    async def disconnect(self) -> None:
        if self._stream_task:
            self._stream_task.cancel()
            try:
                await self._stream_task
            except asyncio.CancelledError:
                pass
        self._connected = False
        logger.info("alpaca_disconnected")

    async def is_connected(self) -> bool:
        return self._connected and self._client is not None

    def _ensure_connected(self):
        if not self._client:
            raise RuntimeError("AlpacaBroker not connected. Call connect() first.")

    # ── Account ───────────────────────────────────────────────

    async def get_account(self) -> AccountInfo:
        self._ensure_connected()
        def _fetch():
            return self._client.get_account()
        acc = await asyncio.get_event_loop().run_in_executor(None, _fetch)
        return AccountInfo(
            account_id=str(acc.id),
            portfolio_value=float(acc.portfolio_value or 0),
            cash=float(acc.cash or 0),
            buying_power=float(acc.buying_power or 0),
            day_trade_count=int(acc.daytrade_count or 0),
            pattern_day_trader=bool(acc.pattern_day_trader),
            trading_blocked=bool(acc.trading_blocked),
            currency=str(acc.currency or "USD"),
            initial_margin=float(acc.initial_margin or 0),
            maintenance_margin=float(acc.maintenance_margin or 0),
            sma=float(acc.sma or 0),
        )

    async def get_market_clock(self) -> MarketClock:
        self._ensure_connected()
        def _fetch():
            return self._client.get_clock()
        clock = await asyncio.get_event_loop().run_in_executor(None, _fetch)
        return MarketClock(
            is_open=bool(clock.is_open),
            next_open=clock.next_open,
            next_close=clock.next_close,
        )

    # ── Orders ────────────────────────────────────────────────

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        retry=retry_if_exception_type(Exception),
        reraise=True,
    )
    async def submit_order(self, req: OrderRequest) -> Order:
        self._ensure_connected()

        def _submit():
            from alpaca.trading.requests import (
                MarketOrderRequest, LimitOrderRequest,
                StopOrderRequest, StopLimitOrderRequest,
            )

            side = _to_alpaca_side(req.side)
            tif  = _to_alpaca_tif(req.time_in_force)
            kwargs = dict(
                symbol=req.symbol,
                qty=req.qty,
                side=side,
                time_in_force=tif,
                client_order_id=req.client_order_id or str(uuid.uuid4()),
                extended_hours=req.extended_hours,
            )

            if req.order_type == OrderType.MARKET:
                order_req = MarketOrderRequest(**kwargs)
            elif req.order_type == OrderType.LIMIT:
                order_req = LimitOrderRequest(limit_price=req.limit_price, **kwargs)
            elif req.order_type == OrderType.STOP:
                order_req = StopOrderRequest(stop_price=req.stop_price, **kwargs)
            elif req.order_type == OrderType.STOP_LIMIT:
                order_req = StopLimitOrderRequest(
                    limit_price=req.limit_price,
                    stop_price=req.stop_price,
                    **kwargs,
                )
            else:
                order_req = MarketOrderRequest(**kwargs)

            return self._client.submit_order(order_req)

        raw = await asyncio.get_event_loop().run_in_executor(None, _submit)
        order = _alpaca_order_to_order(raw)
        logger.info("order_submitted",
                    order_id=order.order_id,
                    symbol=req.symbol,
                    side=req.side.value,
                    qty=req.qty,
                    type=req.order_type.value)
        return order

    async def get_order(self, order_id: str) -> Order:
        self._ensure_connected()
        def _fetch():
            return self._client.get_order_by_id(order_id)
        raw = await asyncio.get_event_loop().run_in_executor(None, _fetch)
        return _alpaca_order_to_order(raw)

    async def get_orders(
        self,
        status: Optional[str] = None,
        limit: int = 50,
    ) -> list[Order]:
        self._ensure_connected()
        def _fetch():
            from alpaca.trading.requests import GetOrdersRequest
            from alpaca.trading.enums import QueryOrderStatus
            req = GetOrdersRequest(
                status=QueryOrderStatus(status) if status else QueryOrderStatus.OPEN,
                limit=limit,
            )
            return self._client.get_orders(req)
        raws = await asyncio.get_event_loop().run_in_executor(None, _fetch)
        return [_alpaca_order_to_order(r) for r in raws]

    async def cancel_order(self, order_id: str) -> bool:
        self._ensure_connected()
        def _cancel():
            self._client.cancel_order_by_id(order_id)
        try:
            await asyncio.get_event_loop().run_in_executor(None, _cancel)
            logger.info("order_cancelled", order_id=order_id)
            return True
        except Exception as e:
            logger.warning("cancel_failed", order_id=order_id, error=str(e))
            return False

    async def cancel_all_orders(self) -> int:
        self._ensure_connected()
        def _cancel():
            return self._client.cancel_orders()
        results = await asyncio.get_event_loop().run_in_executor(None, _cancel)
        count = len(results) if results else 0
        logger.info("all_orders_cancelled", count=count)
        return count

    # ── Positions ─────────────────────────────────────────────

    async def get_positions(self) -> list[Position]:
        self._ensure_connected()
        def _fetch():
            return self._client.get_all_positions()
        raws = await asyncio.get_event_loop().run_in_executor(None, _fetch)
        return [_alpaca_position_to_position(p) for p in raws]

    async def get_position(self, symbol: str) -> Optional[Position]:
        self._ensure_connected()
        def _fetch():
            try:
                return self._client.get_open_position(symbol)
            except Exception:
                return None
        raw = await asyncio.get_event_loop().run_in_executor(None, _fetch)
        return _alpaca_position_to_position(raw) if raw else None

    async def close_position(
        self,
        symbol: str,
        qty: Optional[float] = None,
    ) -> Order:
        self._ensure_connected()
        def _close():
            from alpaca.trading.requests import ClosePositionRequest
            if qty:
                req = ClosePositionRequest(qty=str(qty))
                return self._client.close_position(symbol, close_options=req)
            return self._client.close_position(symbol)
        raw = await asyncio.get_event_loop().run_in_executor(None, _close)
        order = _alpaca_order_to_order(raw)
        logger.info("position_closed", symbol=symbol, qty=qty)
        return order

    async def close_all_positions(self) -> list[Order]:
        self._ensure_connected()
        def _close():
            return self._client.close_all_positions(cancel_orders=True)
        raws = await asyncio.get_event_loop().run_in_executor(None, _close)
        orders = []
        if raws:
            for r in raws:
                try:
                    orders.append(_alpaca_order_to_order(r.body))
                except Exception:
                    pass
        logger.info("all_positions_closed", count=len(orders))
        return orders

    # ── Streaming order updates ───────────────────────────────

    async def subscribe_order_updates(
        self,
        callback: OrderUpdateCallback,
    ) -> None:
        self._order_callbacks.append(callback)
        if self._stream_task is None:
            self._stream_task = asyncio.create_task(
                self._run_stream()
            )

    async def unsubscribe_order_updates(self) -> None:
        self._order_callbacks.clear()
        if self._stream_task:
            self._stream_task.cancel()
            self._stream_task = None

    async def _run_stream(self):
        """Run the Alpaca WebSocket trade update stream."""
        try:
            from alpaca.trading.stream import TradingStream
            stream = TradingStream(
                settings.alpaca_api_key,
                settings.alpaca_secret_key,
                paper=self.paper,
            )

            async def on_trade_update(data):
                try:
                    order = _alpaca_order_to_order(data.order)
                    logger.info("stream_order_update",
                                order_id=order.order_id,
                                status=order.status.value)
                    for cb in self._order_callbacks:
                        await cb(order)
                except Exception as e:
                    logger.error("stream_callback_error", error=str(e))

            stream.subscribe_trade_updates(on_trade_update)
            logger.info("alpaca_stream_started")
            await stream._run_forever()
        except asyncio.CancelledError:
            logger.info("alpaca_stream_cancelled")
        except Exception as e:
            logger.error("alpaca_stream_error", error=str(e))

    # ── Utility ───────────────────────────────────────────────

    async def wait_for_fill(
        self,
        order_id: str,
        timeout_seconds: float = 60.0,
        poll_interval: float = 1.5,
    ) -> Order:
        """Poll order status until filled or timeout."""
        deadline = asyncio.get_event_loop().time() + timeout_seconds
        while asyncio.get_event_loop().time() < deadline:
            order = await self.get_order(order_id)
            if order.is_terminal:
                logger.info("order_terminal",
                            order_id=order_id,
                            status=order.status.value,
                            fill_price=order.avg_fill_price)
                return order
            await asyncio.sleep(poll_interval)
        raise TimeoutError(
            f"Order {order_id} did not reach terminal state within {timeout_seconds}s"
        )
