"""
Abstract Broker Interface
Every broker (Alpaca, IBKR, etc.) implements this contract.
Agents always talk to this interface — never directly to a broker SDK.
"""
from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, Callable, Awaitable
import asyncio


# ─────────────────────────────────────────────
# Enums
# ─────────────────────────────────────────────

class OrderSide(str, Enum):
    BUY  = "buy"
    SELL = "sell"


class OrderType(str, Enum):
    MARKET     = "market"
    LIMIT      = "limit"
    STOP       = "stop"
    STOP_LIMIT = "stop_limit"


class OrderStatus(str, Enum):
    PENDING    = "pending"
    SUBMITTED  = "submitted"
    PARTIAL    = "partial"
    FILLED     = "filled"
    CANCELLED  = "cancelled"
    REJECTED   = "rejected"
    EXPIRED    = "expired"


class TimeInForce(str, Enum):
    DAY = "day"
    GTC = "gtc"   # Good-Till-Cancelled
    IOC = "ioc"   # Immediate-Or-Cancel
    FOK = "fok"   # Fill-Or-Kill
    OPG = "opg"   # At-Open
    CLS = "cls"   # At-Close


class AssetClass(str, Enum):
    EQUITY = "equity"
    OPTION = "option"
    CRYPTO = "crypto"
    FOREX  = "forex"


# ─────────────────────────────────────────────
# Data classes
# ─────────────────────────────────────────────

@dataclass
class OrderRequest:
    """Unified order request — broker-agnostic."""
    symbol:        str
    side:          OrderSide
    qty:           float
    order_type:    OrderType         = OrderType.MARKET
    limit_price:   Optional[float]   = None
    stop_price:    Optional[float]   = None
    time_in_force: TimeInForce       = TimeInForce.DAY
    client_order_id: Optional[str]   = None   # idempotency key
    extended_hours:  bool            = False
    asset_class:   AssetClass        = AssetClass.EQUITY
    # Execution algo metadata (informational for broker-side algos)
    algo:          str               = "market"   # vwap|twap|aggressive|passive
    note:          str               = ""


@dataclass
class Fill:
    """A single partial or full fill event."""
    fill_id:    str
    order_id:   str
    symbol:     str
    side:       OrderSide
    qty:        float
    price:      float
    timestamp:  datetime
    commission: float = 0.0


@dataclass
class Order:
    """Live order state returned by the broker."""
    order_id:        str
    client_order_id: Optional[str]
    symbol:          str
    side:            OrderSide
    order_type:      OrderType
    qty:             float
    filled_qty:      float           = 0.0
    limit_price:     Optional[float] = None
    stop_price:      Optional[float] = None
    avg_fill_price:  Optional[float] = None
    status:          OrderStatus     = OrderStatus.PENDING
    submitted_at:    Optional[datetime] = None
    filled_at:       Optional[datetime] = None
    cancelled_at:    Optional[datetime] = None
    fills:           list[Fill]      = field(default_factory=list)
    reject_reason:   Optional[str]   = None

    @property
    def slippage_bps(self) -> float:
        """Basis points slippage vs limit/arrival price."""
        if not self.avg_fill_price:
            return 0.0
        ref = self.limit_price or self.avg_fill_price
        if ref == 0:
            return 0.0
        return abs(self.avg_fill_price - ref) / ref * 10_000

    @property
    def is_terminal(self) -> bool:
        return self.status in (
            OrderStatus.FILLED, OrderStatus.CANCELLED,
            OrderStatus.REJECTED, OrderStatus.EXPIRED,
        )

    @property
    def notional(self) -> float:
        price = self.avg_fill_price or self.limit_price or 0
        return self.filled_qty * price


@dataclass
class Position:
    """Current open position."""
    symbol:              str
    qty:                 float
    side:                str          # "long" | "short"
    avg_entry_price:     float
    current_price:       float
    market_value:        float
    unrealized_pnl:      float
    unrealized_pnl_pct:  float
    cost_basis:          float


@dataclass
class AccountInfo:
    """Broker account summary."""
    account_id:       str
    portfolio_value:  float
    cash:             float
    buying_power:     float
    day_trade_count:  int            = 0
    pattern_day_trader: bool         = False
    trading_blocked:  bool           = False
    currency:         str            = "USD"
    # Risk metrics
    initial_margin:   float          = 0.0
    maintenance_margin: float        = 0.0
    sma:              float          = 0.0   # Special Memorandum Account


@dataclass
class MarketClock:
    is_open:      bool
    next_open:    datetime
    next_close:   datetime
    timezone:     str = "America/New_York"


# ─────────────────────────────────────────────
# Callback type
# ─────────────────────────────────────────────
OrderUpdateCallback = Callable[[Order], Awaitable[None]]


# ─────────────────────────────────────────────
# Abstract Broker
# ─────────────────────────────────────────────
class AbstractBroker(ABC):
    """
    All brokers implement this interface.
    Methods are async throughout for non-blocking I/O.
    """

    # ── Connection ────────────────────────────
    @abstractmethod
    async def connect(self) -> None:
        """Initialise connection / authenticate."""
        ...

    @abstractmethod
    async def disconnect(self) -> None:
        """Cleanly close connections."""
        ...

    @abstractmethod
    async def is_connected(self) -> bool:
        ...

    # ── Account ──────────────────────────────
    @abstractmethod
    async def get_account(self) -> AccountInfo:
        ...

    @abstractmethod
    async def get_market_clock(self) -> MarketClock:
        ...

    # ── Orders ───────────────────────────────
    @abstractmethod
    async def submit_order(self, req: OrderRequest) -> Order:
        """Submit a new order. Returns immediately with pending Order."""
        ...

    @abstractmethod
    async def get_order(self, order_id: str) -> Order:
        ...

    @abstractmethod
    async def get_orders(
        self,
        status: Optional[str] = None,
        limit: int = 50,
    ) -> list[Order]:
        ...

    @abstractmethod
    async def cancel_order(self, order_id: str) -> bool:
        """Returns True if successfully cancelled."""
        ...

    @abstractmethod
    async def cancel_all_orders(self) -> int:
        """Cancel all open orders. Returns count cancelled."""
        ...

    # ── Positions ────────────────────────────
    @abstractmethod
    async def get_positions(self) -> list[Position]:
        ...

    @abstractmethod
    async def get_position(self, symbol: str) -> Optional[Position]:
        ...

    @abstractmethod
    async def close_position(
        self,
        symbol: str,
        qty: Optional[float] = None,   # None = close full position
    ) -> Order:
        ...

    @abstractmethod
    async def close_all_positions(self) -> list[Order]:
        ...

    # ── Streaming ────────────────────────────
    @abstractmethod
    async def subscribe_order_updates(
        self,
        callback: OrderUpdateCallback,
    ) -> None:
        """Start streaming order updates. Calls callback on each update."""
        ...

    @abstractmethod
    async def unsubscribe_order_updates(self) -> None:
        ...

    # ── Utility ──────────────────────────────
    async def wait_for_fill(
        self,
        order_id: str,
        timeout_seconds: float = 60.0,
        poll_interval: float = 1.0,
    ) -> Order:
        """
        Poll until order reaches terminal state or timeout.
        Override with streaming implementation if available.
        """
        deadline = asyncio.get_event_loop().time() + timeout_seconds
        while asyncio.get_event_loop().time() < deadline:
            order = await self.get_order(order_id)
            if order.is_terminal:
                return order
            await asyncio.sleep(poll_interval)
        raise TimeoutError(
            f"Order {order_id} did not fill within {timeout_seconds}s"
        )
