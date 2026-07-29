"""
tools/broker.py — backward-compatibility shim.

All broker logic now lives in the `broker/` package.
This file re-exports the public functions that existing agent code calls,
so no other file needs to change.
"""
from broker.registry import get_portfolio_snapshot  # noqa: F401


async def execute_order(order: dict) -> dict:
    """Legacy wrapper — submits via the broker registry."""
    from broker import get_broker, OrderRequest, OrderSide, OrderType, TimeInForce

    symbol    = order.get("symbol", "AAPL")
    direction = order.get("direction", "long")
    qty       = float(order.get("qty", 1))
    otype     = order.get("order_type", "market")

    side = OrderSide.BUY if direction == "long" else OrderSide.SELL
    order_type = {
        "market":     OrderType.MARKET,
        "limit":      OrderType.LIMIT,
        "stop_limit": OrderType.STOP_LIMIT,
    }.get(otype, OrderType.MARKET)

    req = OrderRequest(
        symbol=symbol, side=side, qty=qty, order_type=order_type,
        limit_price=order.get("limit_price"),
        stop_price=order.get("stop_price"),
        time_in_force=TimeInForce.DAY,
        note="Legacy execute_order via tools/broker.py",
    )
    broker = await get_broker()
    placed = await broker.submit_order(req)
    return {"order_id": placed.order_id, "status": placed.status.value}


async def get_fill_report(order_id: str, order: dict) -> dict:
    """Legacy wrapper — polls broker for fill details."""
    from broker import get_broker
    broker = await get_broker()
    try:
        filled = await broker.wait_for_fill(order_id, timeout_seconds=30)
    except TimeoutError:
        filled = await broker.get_order(order_id)

    return {
        "order_id":       filled.order_id,
        "symbol":         order.get("symbol", filled.symbol),
        "direction":      order.get("direction", "long"),
        "qty_filled":     filled.filled_qty,
        "avg_fill_price": filled.avg_fill_price or 0.0,
        "slippage_bps":   filled.slippage_bps,
        "status":         filled.status.value,
        "fills": [
            {"fill_id": f.fill_id, "price": f.price, "qty": f.qty,
             "timestamp": f.timestamp.isoformat()}
            for f in filled.fills
        ],
    }
