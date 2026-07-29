"""
Indian broker unit tests.
These test the data parsers and business logic without hitting live APIs.

Run with:  pytest tests/test_indian_brokers.py -v
"""
import pytest
from datetime import datetime

from broker.indian.base_indian import (
    IndianOrderRequest, IndianOrder, IndianPosition, Holding,
    MarketQuote, IndianFunds, Exchange, ProductType, Validity,
    OrderVariety, MARKET_OPEN_IST, MARKET_CLOSE_IST,
)
from broker.indian.zerodha import ZerodhaBroker
from broker.indian.upstox  import UpstoxBroker
from broker.indian.alert_engine import _make_alert


# ── Data structure tests ──────────────────────────────────────

def test_holding_calculations():
    h = Holding(
        tradingsymbol="RELIANCE",
        exchange="NSE",
        isin="INE002A01018",
        quantity=10,
        average_price=2400.0,
        last_price=2600.0,
        close_price=2500.0,
    )
    assert h.current_value == 26000.0
    assert h.investment_value == 24000.0
    assert h.total_return_pct == pytest.approx(8.333, rel=1e-2)
    assert h.day_change == pytest.approx(100.0)
    assert h.day_change_pct == pytest.approx(4.0)


def test_holding_zero_avg_price():
    h = Holding(
        tradingsymbol="TCS", exchange="NSE", isin="",
        quantity=5, average_price=0.0, last_price=3500.0,
    )
    assert h.total_return_pct == 0.0   # no div-by-zero


def test_indian_position_side():
    long_pos = IndianPosition(
        exchange="NSE", tradingsymbol="INFY", product="MIS",
        quantity=50,
    )
    assert long_pos.side == "long"

    short_pos = IndianPosition(
        exchange="NSE", tradingsymbol="INFY", product="MIS",
        quantity=-20,
    )
    assert short_pos.side == "short"


def test_indian_position_change_pct():
    pos = IndianPosition(
        exchange="NSE", tradingsymbol="HDFC", product="CNC",
        quantity=10, last_price=1650.0, close_price=1600.0,
    )
    assert pos.change_pct == pytest.approx(3.125)


def test_indian_position_zero_close():
    pos = IndianPosition(
        exchange="NSE", tradingsymbol="HDFC", product="CNC",
        quantity=10, last_price=1650.0, close_price=0.0,
    )
    assert pos.change_pct == 0.0


def test_market_quote_fields():
    q = MarketQuote(
        instrument_token=738561,
        tradingsymbol="RELIANCE",
        last_price=2580.0,
        high=2610.0, low=2555.0,
        upper_circuit=2838.0, lower_circuit=2322.0,
        volume=1_250_000,
    )
    assert q.last_price == 2580.0
    assert q.upper_circuit == 2838.0


def test_instrument_full_symbol():
    from broker.indian.base_indian import Instrument
    inst = Instrument.equity("WIPRO", Exchange.NSE, token=969633)
    assert inst.full_symbol == "NSE:WIPRO"
    assert inst.lot_size == 1


def test_indian_funds():
    f = IndianFunds(
        available_cash=50000.0,
        available_margin=75000.0,
        used_margin=25000.0,
        net=100000.0,
    )
    assert f.available_cash == 50000.0
    assert f.net == 100000.0


# ── Order request construction ────────────────────────────────

def test_indian_order_request_defaults():
    req = IndianOrderRequest(
        exchange=Exchange.NSE,
        tradingsymbol="SBIN",
        transaction_type="BUY",
        quantity=100,
    )
    assert req.product == ProductType.CNC
    assert req.order_type == "MARKET"
    assert req.validity == Validity.DAY
    assert req.variety == OrderVariety.REGULAR
    assert req.price == 0.0
    assert req.trigger_price == 0.0


def test_indian_order_request_limit():
    req = IndianOrderRequest(
        exchange=Exchange.BSE,
        tradingsymbol="TATASTEEL",
        transaction_type="SELL",
        quantity=50,
        product=ProductType.MIS,
        order_type="LIMIT",
        price=125.50,
        validity=Validity.IOC,
    )
    assert req.product == ProductType.MIS
    assert req.price == 125.50
    assert req.validity == Validity.IOC


def test_indian_order_is_complete():
    complete = IndianOrder(
        order_id="123", exchange="NSE", tradingsymbol="RELIANCE",
        transaction_type="BUY", quantity=10,
        status="COMPLETE",
    )
    assert complete.is_complete is True

    open_order = IndianOrder(
        order_id="124", exchange="NSE", tradingsymbol="RELIANCE",
        transaction_type="BUY", quantity=10,
        status="OPEN",
    )
    assert open_order.is_complete is False


def test_indian_order_slippage():
    order = IndianOrder(
        order_id="125", exchange="NSE", tradingsymbol="TCS",
        transaction_type="BUY", quantity=5,
        price=3450.0, average_price=3452.76,
        status="COMPLETE",
    )
    expected_bps = abs(3452.76 - 3450.0) / 3450.0 * 10_000
    assert order.slippage_bps == pytest.approx(expected_bps, rel=1e-3)


def test_indian_order_zero_slippage_market():
    order = IndianOrder(
        order_id="126", exchange="NSE", tradingsymbol="HDFC",
        transaction_type="BUY", quantity=10,
        price=0.0, average_price=1640.0,   # market order
        status="COMPLETE",
    )
    assert order.slippage_bps == 0.0


# ── Zerodha parser tests (using raw dict data) ─────────────────

def _make_zerodha(token="test-token"):
    return ZerodhaBroker(api_key="testkey", api_secret="testsecret",
                         access_token=token)


def test_zerodha_parse_order():
    kite = _make_zerodha()
    raw = {
        "order_id": "221201000000000",
        "exchange": "NSE",
        "tradingsymbol": "INFY",
        "transaction_type": "BUY",
        "quantity": 50,
        "filled_quantity": 50,
        "pending_quantity": 0,
        "product": "CNC",
        "order_type": "MARKET",
        "price": 0.0,
        "trigger_price": 0.0,
        "average_price": 1523.45,
        "status": "COMPLETE",
        "status_message": "",
        "variety": "regular",
        "validity": "DAY",
        "tag": "alphadeskv1",
    }
    order = kite._parse_order(raw)
    assert order.order_id == "221201000000000"
    assert order.tradingsymbol == "INFY"
    assert order.average_price == 1523.45
    assert order.is_complete is True


def test_zerodha_parse_position():
    kite = _make_zerodha()
    raw = {
        "exchange": "NSE",
        "tradingsymbol": "NIFTY24JANFUT",
        "product": "NRML",
        "quantity": 50,
        "overnight_quantity": 50,
        "buy_quantity": 50,
        "sell_quantity": 0,
        "buy_price": 21750.0,
        "sell_price": 0.0,
        "last_price": 21890.0,
        "close_price": 21800.0,
        "pnl": 7000.0,
        "unrealised": 7000.0,
        "realised": 0.0,
        "multiplier": 50,
    }
    pos = kite._parse_position(raw)
    assert pos.tradingsymbol == "NIFTY24JANFUT"
    assert pos.quantity == 50
    assert pos.pnl == 7000.0
    assert pos.multiplier == 50


def test_zerodha_parse_holding():
    kite = _make_zerodha()
    raw = {
        "tradingsymbol": "HDFCBANK",
        "exchange": "NSE",
        "isin": "INE040A01034",
        "quantity": 25,
        "t1_quantity": 0,
        "average_price": 1580.0,
        "last_price": 1640.0,
        "close_price": 1625.0,
        "pnl": 1500.0,
    }
    holding = kite._parse_holding(raw)
    assert holding.tradingsymbol == "HDFCBANK"
    assert holding.quantity == 25
    assert holding.isin == "INE040A01034"
    assert holding.total_return_pct == pytest.approx(3.797, rel=1e-2)
    assert holding.day_change == pytest.approx(15.0)


# ── Upstox parser tests ───────────────────────────────────────

def _make_upstox():
    return UpstoxBroker(api_key="testkey", api_secret="testsecret",
                        redirect_uri="http://localhost/cb")


def test_upstox_parse_order_dict():
    upstox = _make_upstox()
    raw = {
        "order_id": "230801010101010",
        "exchange": "NSE",
        "trading_symbol": "RELIANCE",
        "transaction_type": "BUY",
        "quantity": 10,
        "filled_quantity": 10,
        "product": "D",
        "order_type": "MARKET",
        "price": 0.0,
        "trigger_price": 0.0,
        "average_price": 2583.50,
        "status": "complete",
        "status_message": "",
    }
    order = upstox._parse_order(raw)
    assert order.order_id == "230801010101010"
    assert order.tradingsymbol == "RELIANCE"
    assert order.status == "COMPLETE"
    assert order.average_price == 2583.50


def test_upstox_parse_position_dict():
    upstox = _make_upstox()
    raw = {
        "exchange": "NSE",
        "trading_symbol": "SBIN",
        "product": "I",
        "quantity": -100,
        "buy_quantity": 0,
        "sell_quantity": 100,
        "buy_price": 0.0,
        "sell_price": 620.50,
        "last_price": 615.0,
        "close_price": 618.0,
        "pnl": 550.0,
        "unrealised": 550.0,
        "realised": 0.0,
    }
    pos = upstox._parse_position(raw)
    assert pos.tradingsymbol == "SBIN"
    assert pos.quantity == -100
    assert pos.side == "short"
    assert pos.pnl == 550.0


def test_upstox_parse_holding_dict():
    upstox = _make_upstox()
    raw = {
        "trading_symbol": "WIPRO",
        "exchange": "NSE",
        "isin": "INE075A01022",
        "quantity": 200,
        "t1_quantity": 0,
        "average_price": 420.0,
        "last_price": 450.0,
        "close_price": 445.0,
        "pnl": 6000.0,
    }
    holding = upstox._parse_holding(raw)
    assert holding.tradingsymbol == "WIPRO"
    assert holding.quantity == 200
    assert holding.total_return_pct == pytest.approx(7.142, rel=1e-2)
    assert holding.day_change == pytest.approx(5.0)
    assert holding.day_change_pct == pytest.approx(1.123, rel=1e-2)


# ── Alert engine tests ────────────────────────────────────────

def test_make_alert_structure():
    alert = _make_alert(
        user_id="user-123",
        broker="zerodha",
        symbol="RELIANCE",
        alert_type="pnl_above",
        message="RELIANCE achieved +25% return!",
        threshold=25.0,
        meta={"return_pct": 26.5},
    )
    assert alert["user_id"] == "user-123"
    assert alert["broker"] == "zerodha"
    assert alert["symbol"] == "RELIANCE"
    assert alert["alert_type"] == "pnl_above"
    assert alert["threshold"] == 25.0
    assert alert["metadata"]["return_pct"] == 26.5
    assert not alert["is_read"]


def test_make_alert_circuit():
    alert = _make_alert(
        user_id="u1", broker="upstox", symbol="ADANI",
        alert_type="circuit_upper",
        message="ADANI hit upper circuit",
        threshold=3500.0,
    )
    assert alert["alert_type"] == "circuit_upper"
    assert alert["threshold"] == 3500.0


# ── Market hours tests ────────────────────────────────────────

def test_market_hours_constants():
    from datetime import time
    assert MARKET_OPEN_IST == time(9, 15)
    assert MARKET_CLOSE_IST == time(15, 30)


def test_zerodha_market_open_logic():
    """Test is_market_open returns a bool (actual value depends on time of test)."""
    kite = _make_zerodha()
    result = kite.is_market_open()
    assert isinstance(result, bool)


def test_upstox_market_open_logic():
    upstox = _make_upstox()
    result = upstox.is_market_open()
    assert isinstance(result, bool)


# ── Exchange mapping tests ────────────────────────────────────

def test_exchange_enum():
    assert Exchange.NSE.value == "NSE"
    assert Exchange.BSE.value == "BSE"
    assert Exchange.NFO.value == "NFO"
    assert Exchange.MCX.value == "MCX"


def test_product_type_enum():
    assert ProductType.CNC.value  == "CNC"
    assert ProductType.MIS.value  == "MIS"
    assert ProductType.NRML.value == "NRML"


def test_upstox_product_map():
    from broker.indian.upstox import PRODUCT_MAP
    assert PRODUCT_MAP["CNC"]  == "D"
    assert PRODUCT_MAP["MIS"]  == "I"
    assert PRODUCT_MAP["NRML"] == "M"


def test_upstox_exchange_map():
    from broker.indian.upstox import EXCHANGE_MAP
    assert EXCHANGE_MAP["NSE"] == "NSE_EQ"
    assert EXCHANGE_MAP["NFO"] == "NSE_FO"
    assert EXCHANGE_MAP["MCX"] == "MCX_FO"


# ── Token encryption tests ────────────────────────────────────

def test_token_encrypt_decrypt():
    """Round-trip encryption test."""
    from core.token_crypto import encrypt_token, decrypt_token
    original = "test-access-token-12345"
    encrypted = encrypt_token(original)
    assert encrypted != original
    decrypted = decrypt_token(encrypted)
    assert decrypted == original


def test_token_encryption_is_unique():
    """Each encryption produces different ciphertext (due to random nonce)."""
    from core.token_crypto import encrypt_token
    t = "same-token"
    enc1 = encrypt_token(t)
    enc2 = encrypt_token(t)
    # Nonce-based — should differ
    assert enc1 != enc2


def test_maybe_decrypt_none():
    from core.token_crypto import maybe_decrypt
    assert maybe_decrypt(None) is None


def test_maybe_decrypt_value():
    from core.token_crypto import encrypt_token, maybe_decrypt
    enc = encrypt_token("mytoken")
    assert maybe_decrypt(enc) == "mytoken"


# ── NSE holidays list ─────────────────────────────────────────

def test_nse_holidays_format():
    from broker.indian.base_indian import NSE_HOLIDAYS_2025
    assert len(NSE_HOLIDAYS_2025) > 0
    for holiday in NSE_HOLIDAYS_2025:
        # Must be YYYY-MM-DD format
        datetime.strptime(holiday, "%Y-%m-%d")


def test_republic_day_is_holiday():
    from broker.indian.base_indian import NSE_HOLIDAYS_2025
    assert "2025-01-26" in NSE_HOLIDAYS_2025


def test_independence_day_is_holiday():
    from broker.indian.base_indian import NSE_HOLIDAYS_2025
    assert "2025-08-15" in NSE_HOLIDAYS_2025
