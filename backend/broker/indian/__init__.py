"""
Indian Broker Package
Supports Zerodha (Kite Connect) and Upstox (v2 API).

Usage:
    from broker.indian.session_manager import get_indian_broker
    client = await get_indian_broker(user_id, "zerodha", conn)
    holdings = await client.get_holdings()
"""
from broker.indian.zerodha import ZerodhaBroker
from broker.indian.upstox  import UpstoxBroker
from broker.indian.base_indian import (
    IndianOrderRequest, IndianOrder, IndianPosition, Holding,
    MarketQuote, IndianFunds, Exchange, ProductType,
    InstrumentType, OrderVariety, Validity,
)
from broker.indian.session_manager import (
    get_indian_broker, save_broker_connection, invalidate_session,
)
from broker.indian.portfolio_analysis import analyse_portfolio, generate_stock_insight
from broker.indian.alert_engine import (
    check_and_fire_alerts, get_user_alerts,
    mark_alerts_read, start_alert_monitor,
)

__all__ = [
    "ZerodhaBroker", "UpstoxBroker",
    "IndianOrderRequest", "IndianOrder", "IndianPosition",
    "Holding", "MarketQuote", "IndianFunds",
    "Exchange", "ProductType", "InstrumentType",
    "OrderVariety", "Validity",
    "get_indian_broker", "save_broker_connection", "invalidate_session",
    "analyse_portfolio", "generate_stock_insight",
    "check_and_fire_alerts", "get_user_alerts",
    "mark_alerts_read", "start_alert_monitor",
]
