"""
Indian Market Base Types
NSE/BSE specific enums, data structures, and the abstract Indian broker interface.
Extends the global broker base with India-specific concepts.
"""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from datetime import datetime, time
from typing import Optional


# ─────────────────────────────────────────────
# Indian Market Enums
# ─────────────────────────────────────────────

class Exchange(str, Enum):
    NSE  = "NSE"   # National Stock Exchange
    BSE  = "BSE"   # Bombay Stock Exchange
    NFO  = "NFO"   # NSE Futures & Options
    BFO  = "BFO"   # BSE Futures & Options
    CDS  = "CDS"   # Currency Derivatives
    MCX  = "MCX"   # Multi Commodity Exchange


class ProductType(str, Enum):
    CNC   = "CNC"    # Cash and Carry (delivery, equity)
    MIS   = "MIS"    # Margin Intraday Square-off (intraday)
    NRML  = "NRML"   # Normal (F&O overnight)
    CO    = "CO"     # Cover Order (with stop-loss)
    BO    = "BO"     # Bracket Order (entry + stop + target)


class InstrumentType(str, Enum):
    EQ      = "EQ"       # Equity
    FUT     = "FUT"      # Futures
    CE      = "CE"       # Call Option
    PE      = "PE"       # Put Option
    ETF     = "ETF"      # Exchange Traded Fund
    INDEX   = "INDEX"    # Index (NIFTY, SENSEX)


class OrderVariety(str, Enum):
    REGULAR  = "regular"
    AMO      = "amo"      # After Market Order
    CO       = "co"       # Cover Order
    BO       = "bo"       # Bracket Order


class Validity(str, Enum):
    DAY   = "DAY"
    IOC   = "IOC"    # Immediate or Cancel
    TTL   = "TTL"    # Time To Live (minutes)


# ─────────────────────────────────────────────
# Indian Instrument
# ─────────────────────────────────────────────

@dataclass
class Instrument:
    """Uniquely identifies a tradeable instrument on Indian exchanges."""
    exchange:        Exchange
    tradingsymbol:   str               # e.g. "RELIANCE", "NIFTY23DECFUT"
    instrument_token: int              # broker-assigned numeric token
    instrument_type: InstrumentType   = InstrumentType.EQ
    lot_size:        int               = 1
    tick_size:       float             = 0.05
    expiry:          Optional[datetime] = None    # for F&O
    strike:          Optional[float]   = None     # for options
    segment:         str               = "NSE"

    @property
    def full_symbol(self) -> str:
        return f"{self.exchange.value}:{self.tradingsymbol}"

    @classmethod
    def equity(cls, symbol: str, exchange: Exchange = Exchange.NSE,
               token: int = 0) -> "Instrument":
        return cls(exchange=exchange, tradingsymbol=symbol,
                   instrument_token=token)


# ─────────────────────────────────────────────
# Indian Order Request
# ─────────────────────────────────────────────

@dataclass
class IndianOrderRequest:
    """
    India-specific order request.
    Covers equity CNC/MIS and F&O NRML orders.
    """
    exchange:        Exchange
    tradingsymbol:   str
    transaction_type: str              # "BUY" | "SELL"
    quantity:        int               # always whole numbers in India
    product:         ProductType       = ProductType.CNC
    order_type:      str               = "MARKET"  # MARKET|LIMIT|SL|SL-M
    price:           float             = 0.0       # for LIMIT orders
    trigger_price:   float             = 0.0       # for SL orders
    validity:        Validity          = Validity.DAY
    variety:         OrderVariety      = OrderVariety.REGULAR
    disclosed_quantity: int            = 0         # iceberg qty
    tag:             str               = ""        # optional label


# ─────────────────────────────────────────────
# Indian Order (response)
# ─────────────────────────────────────────────

@dataclass
class IndianOrder:
    order_id:        str
    exchange:        str
    tradingsymbol:   str
    transaction_type: str
    quantity:        int
    filled_quantity: int               = 0
    pending_quantity: int              = 0
    product:         str               = "CNC"
    order_type:      str               = "MARKET"
    price:           float             = 0.0
    trigger_price:   float             = 0.0
    average_price:   float             = 0.0
    status:          str               = "OPEN"
    status_message:  str               = ""
    order_timestamp: Optional[datetime] = None
    exchange_timestamp: Optional[datetime] = None
    variety:         str               = "regular"
    validity:        str               = "DAY"
    tag:             str               = ""

    @property
    def is_complete(self) -> bool:
        return self.status in ("COMPLETE", "CANCELLED", "REJECTED")

    @property
    def slippage_bps(self) -> float:
        if self.price > 0 and self.average_price > 0:
            return abs(self.average_price - self.price) / self.price * 10_000
        return 0.0


# ─────────────────────────────────────────────
# Indian Position
# ─────────────────────────────────────────────

@dataclass
class IndianPosition:
    exchange:        str
    tradingsymbol:   str
    product:         str
    quantity:        int               # net qty (positive=long, negative=short)
    overnight_quantity: int            = 0
    buy_quantity:    int               = 0
    sell_quantity:   int               = 0
    buy_price:       float             = 0.0
    sell_price:      float             = 0.0
    last_price:      float             = 0.0
    close_price:     float             = 0.0       # prev day close
    pnl:             float             = 0.0
    unrealised:      float             = 0.0
    realised:        float             = 0.0
    multiplier:      int               = 1         # lot size for F&O

    @property
    def side(self) -> str:
        return "long" if self.quantity >= 0 else "short"

    @property
    def change_pct(self) -> float:
        if self.close_price > 0:
            return (self.last_price - self.close_price) / self.close_price * 100
        return 0.0


# ─────────────────────────────────────────────
# Indian Holdings (delivery portfolio)
# ─────────────────────────────────────────────

@dataclass
class Holding:
    """Long-term delivery holding (CNC, T+1 settled)."""
    tradingsymbol:   str
    exchange:        str
    isin:            str               # ISIN code
    quantity:        int
    t1_quantity:     int               = 0         # T+1 unsettled qty
    average_price:   float             = 0.0
    last_price:      float             = 0.0
    close_price:     float             = 0.0
    pnl:             float             = 0.0
    day_change:      float             = 0.0
    day_change_pct:  float             = 0.0

    def __post_init__(self):
        if self.close_price > 0:
            if not self.day_change:
                self.day_change = self.last_price - self.close_price
            if not self.day_change_pct:
                self.day_change_pct = (self.last_price - self.close_price) / self.close_price * 100

    @property
    def current_value(self) -> float:
        return self.quantity * self.last_price

    @property
    def investment_value(self) -> float:
        return self.quantity * self.average_price

    @property
    def total_return_pct(self) -> float:
        if self.average_price > 0:
            return (self.last_price - self.average_price) / self.average_price * 100
        return 0.0


# ─────────────────────────────────────────────
# Market Quote
# ─────────────────────────────────────────────

@dataclass
class MarketQuote:
    instrument_token: int
    tradingsymbol:   str
    last_price:      float
    open:            float             = 0.0
    high:            float             = 0.0
    low:             float             = 0.0
    close:           float             = 0.0
    volume:          int               = 0
    oi:              int               = 0         # open interest (F&O)
    upper_circuit:   float             = 0.0
    lower_circuit:   float             = 0.0
    change:          float             = 0.0
    change_pct:      float             = 0.0
    bid:             float             = 0.0
    ask:             float             = 0.0
    timestamp:       Optional[datetime] = None


# ─────────────────────────────────────────────
# Indian Funds / Margin
# ─────────────────────────────────────────────

@dataclass
class IndianFunds:
    """Account funds / available margin breakdown."""
    available_cash:      float = 0.0
    available_intraday:  float = 0.0
    available_margin:    float = 0.0
    used_margin:         float = 0.0
    collateral:          float = 0.0
    net:                 float = 0.0
    payin:               float = 0.0
    payout:              float = 0.0


# ─────────────────────────────────────────────
# Market Schedule (IST)
# ─────────────────────────────────────────────

MARKET_OPEN_IST  = time(9, 15)
MARKET_CLOSE_IST = time(15, 30)
PRE_OPEN_IST     = time(9, 0)
POST_CLOSE_IST   = time(15, 40)

NSE_HOLIDAYS_2025 = [
    "2025-01-26",  # Republic Day
    "2025-03-14",  # Holi
    "2025-04-14",  # Dr. Ambedkar Jayanti / Ram Navami
    "2025-04-18",  # Good Friday
    "2025-05-01",  # Maharashtra Day
    "2025-08-15",  # Independence Day
    "2025-10-02",  # Gandhi Jayanti
    "2025-10-20",  # Diwali Laxmi Pujan (tentative)
    "2025-10-21",  # Diwali Balipratipada (tentative)
    "2025-11-05",  # Gurunanak Jayanti
    "2025-12-25",  # Christmas
]
