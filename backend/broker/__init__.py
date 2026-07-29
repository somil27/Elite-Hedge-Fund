"""
Broker package — abstract interface + concrete implementations.

Public API (what agents import):
    from broker import get_broker, get_portfolio_snapshot
    from broker import OrderRequest, OrderSide, OrderType, AlgoConfig

Brokers available:
    AlpacaBroker  — paper + live via alpaca-py
    IBKRBroker    — live via ib_insync (requires TWS)
    MockBroker    — deterministic fills, no API keys
"""
from broker.base import (
    AbstractBroker,
    OrderRequest,
    Order,
    OrderStatus,
    OrderSide,
    OrderType,
    TimeInForce,
    Position,
    AccountInfo,
    MarketClock,
    Fill,
)
from broker.execution_algos import AlgoConfig, AlgoResult, ExecutionAlgoEngine
from broker.registry import get_broker, get_portfolio_snapshot, reset_broker

__all__ = [
    "AbstractBroker",
    "OrderRequest", "Order", "OrderStatus", "OrderSide",
    "OrderType", "TimeInForce", "Position", "AccountInfo",
    "MarketClock", "Fill",
    "AlgoConfig", "AlgoResult", "ExecutionAlgoEngine",
    "get_broker", "get_portfolio_snapshot", "reset_broker",
]
