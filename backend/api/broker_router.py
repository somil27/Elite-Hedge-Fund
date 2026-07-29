"""
Broker API Router
Full REST endpoints for the frontend to interact with the broker directly:
  - Account info
  - Live positions
  - Order management (list, cancel)
  - Market clock
  - Manual order placement
"""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from broker import get_broker, get_portfolio_snapshot, OrderRequest, OrderSide, OrderType, TimeInForce
from db.database import get_raw_connection
import structlog

logger = structlog.get_logger()
router = APIRouter(prefix="/api/broker", tags=["broker"])


# ── Request models ───────────────────────────────────────────

class ManualOrderRequest(BaseModel):
    symbol:       str
    side:         str              # buy | sell
    qty:          float
    order_type:   str = "market"   # market | limit | stop | stop_limit
    limit_price:  Optional[float] = None
    stop_price:   Optional[float] = None
    time_in_force: str = "day"    # day | gtc | ioc | fok
    extended_hours: bool = False
    note:         str = "Manual order via dashboard"


# ── Account ──────────────────────────────────────────────────

@router.get("/account")
async def get_account():
    """Get full broker account details."""
    broker = await get_broker()
    try:
        account = await broker.get_account()
        return {
            "account_id":         account.account_id,
            "portfolio_value":    account.portfolio_value,
            "cash":               account.cash,
            "buying_power":       account.buying_power,
            "day_trade_count":    account.day_trade_count,
            "pattern_day_trader": account.pattern_day_trader,
            "trading_blocked":    account.trading_blocked,
            "currency":           account.currency,
            "initial_margin":     account.initial_margin,
            "maintenance_margin": account.maintenance_margin,
        }
    except Exception as e:
        raise HTTPException(500, f"Broker error: {e}")


@router.get("/clock")
async def get_market_clock():
    """Get current market clock (open/closed, next open/close times)."""
    broker = await get_broker()
    try:
        clock = await broker.get_market_clock()
        return {
            "is_open":    clock.is_open,
            "next_open":  clock.next_open.isoformat(),
            "next_close": clock.next_close.isoformat(),
            "timezone":   clock.timezone,
            "timestamp":  datetime.utcnow().isoformat(),
        }
    except Exception as e:
        raise HTTPException(500, f"Broker error: {e}")


@router.get("/portfolio")
async def get_portfolio():
    """Get portfolio snapshot: value, cash, positions."""
    try:
        return await get_portfolio_snapshot()
    except Exception as e:
        raise HTTPException(500, f"Broker error: {e}")


# ── Positions ────────────────────────────────────────────────

@router.get("/positions")
async def list_positions():
    """List all open positions."""
    broker = await get_broker()
    try:
        positions = await broker.get_positions()
        return [
            {
                "symbol":             p.symbol,
                "qty":                p.qty,
                "side":               p.side,
                "avg_entry_price":    p.avg_entry_price,
                "current_price":      p.current_price,
                "market_value":       p.market_value,
                "unrealized_pnl":     p.unrealized_pnl,
                "unrealized_pnl_pct": p.unrealized_pnl_pct,
                "cost_basis":         p.cost_basis,
            }
            for p in positions
        ]
    except Exception as e:
        raise HTTPException(500, f"Broker error: {e}")


@router.get("/positions/{symbol}")
async def get_position(symbol: str):
    """Get a specific open position."""
    broker = await get_broker()
    try:
        pos = await broker.get_position(symbol.upper())
        if not pos:
            raise HTTPException(404, f"No open position for {symbol}")
        return {
            "symbol":             pos.symbol,
            "qty":                pos.qty,
            "side":               pos.side,
            "avg_entry_price":    pos.avg_entry_price,
            "current_price":      pos.current_price,
            "market_value":       pos.market_value,
            "unrealized_pnl":     pos.unrealized_pnl,
            "unrealized_pnl_pct": pos.unrealized_pnl_pct,
            "cost_basis":         pos.cost_basis,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Broker error: {e}")


@router.delete("/positions/{symbol}")
async def close_position(symbol: str, qty: Optional[float] = Query(None)):
    """Close a position (full or partial)."""
    broker = await get_broker()
    try:
        order = await broker.close_position(symbol.upper(), qty)
        logger.info("position_closed_via_api", symbol=symbol, qty=qty)
        return {
            "order_id":   order.order_id,
            "symbol":     order.symbol,
            "status":     order.status.value,
            "qty":        order.qty,
        }
    except ValueError as e:
        raise HTTPException(404, str(e))
    except Exception as e:
        raise HTTPException(500, f"Broker error: {e}")


@router.delete("/positions")
async def close_all_positions():
    """Close all open positions."""
    broker = await get_broker()
    try:
        orders = await broker.close_all_positions()
        logger.warning("all_positions_closed_via_api", count=len(orders))
        return {
            "closed": len(orders),
            "orders": [{"order_id": o.order_id, "symbol": o.symbol} for o in orders],
        }
    except Exception as e:
        raise HTTPException(500, f"Broker error: {e}")


# ── Orders ───────────────────────────────────────────────────

@router.get("/orders")
async def list_orders(status: str = Query("open", description="open | closed | all")):
    """List orders by status."""
    broker = await get_broker()
    try:
        orders = await broker.get_orders(status=status, limit=100)
        return [
            {
                "order_id":        o.order_id,
                "symbol":          o.symbol,
                "side":            o.side.value,
                "order_type":      o.order_type.value,
                "qty":             o.qty,
                "filled_qty":      o.filled_qty,
                "limit_price":     o.limit_price,
                "stop_price":      o.stop_price,
                "avg_fill_price":  o.avg_fill_price,
                "status":          o.status.value,
                "submitted_at":    o.submitted_at.isoformat() if o.submitted_at else None,
                "filled_at":       o.filled_at.isoformat() if o.filled_at else None,
                "slippage_bps":    o.slippage_bps,
            }
            for o in orders
        ]
    except Exception as e:
        raise HTTPException(500, f"Broker error: {e}")


@router.get("/orders/{order_id}")
async def get_order(order_id: str):
    """Get a specific order by ID."""
    broker = await get_broker()
    try:
        o = await broker.get_order(order_id)
        return {
            "order_id":       o.order_id,
            "symbol":         o.symbol,
            "side":           o.side.value,
            "order_type":     o.order_type.value,
            "qty":            o.qty,
            "filled_qty":     o.filled_qty,
            "limit_price":    o.limit_price,
            "avg_fill_price": o.avg_fill_price,
            "status":         o.status.value,
            "submitted_at":   o.submitted_at.isoformat() if o.submitted_at else None,
            "filled_at":      o.filled_at.isoformat() if o.filled_at else None,
            "fills":          [
                {"fill_id": f.fill_id, "qty": f.qty,
                 "price": f.price, "timestamp": f.timestamp.isoformat()}
                for f in o.fills
            ],
            "slippage_bps":   o.slippage_bps,
            "reject_reason":  o.reject_reason,
        }
    except ValueError as e:
        raise HTTPException(404, str(e))
    except Exception as e:
        raise HTTPException(500, f"Broker error: {e}")


@router.post("/orders")
async def place_manual_order(req: ManualOrderRequest):
    """
    Place a manual order directly (bypasses the agent pipeline).
    Useful for: hedging, manual intervention, emergency exits.
    """
    broker = await get_broker()

    side_map       = {"buy": OrderSide.BUY, "sell": OrderSide.SELL}
    type_map       = {
        "market":     OrderType.MARKET,
        "limit":      OrderType.LIMIT,
        "stop":       OrderType.STOP,
        "stop_limit": OrderType.STOP_LIMIT,
    }
    tif_map        = {
        "day": TimeInForce.DAY, "gtc": TimeInForce.GTC,
        "ioc": TimeInForce.IOC, "fok": TimeInForce.FOK,
    }

    side = side_map.get(req.side.lower())
    if not side:
        raise HTTPException(400, f"Invalid side: {req.side}")

    order_req = OrderRequest(
        symbol=req.symbol.upper(),
        side=side,
        qty=req.qty,
        order_type=type_map.get(req.order_type, OrderType.MARKET),
        limit_price=req.limit_price,
        stop_price=req.stop_price,
        time_in_force=tif_map.get(req.time_in_force, TimeInForce.DAY),
        extended_hours=req.extended_hours,
        note=req.note,
    )

    try:
        order = await broker.submit_order(order_req)
        logger.info("manual_order_placed",
                    symbol=req.symbol, side=req.side, qty=req.qty)
        return {
            "order_id":       order.order_id,
            "symbol":         order.symbol,
            "side":           order.side.value,
            "qty":            order.qty,
            "status":         order.status.value,
            "submitted_at":   order.submitted_at.isoformat() if order.submitted_at else None,
        }
    except Exception as e:
        raise HTTPException(500, f"Order placement failed: {e}")


@router.delete("/orders/{order_id}")
async def cancel_order(order_id: str):
    """Cancel a specific open order."""
    broker = await get_broker()
    try:
        success = await broker.cancel_order(order_id)
        if not success:
            raise HTTPException(404, f"Order {order_id} not found or already terminal")
        return {"cancelled": True, "order_id": order_id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Broker error: {e}")


@router.delete("/orders")
async def cancel_all_orders():
    """Cancel all open orders."""
    broker = await get_broker()
    try:
        count = await broker.cancel_all_orders()
        logger.warning("all_orders_cancelled_via_api", count=count)
        return {"cancelled": count}
    except Exception as e:
        raise HTTPException(500, f"Broker error: {e}")


# ── Order history from DB ────────────────────────────────────

@router.get("/history")
async def get_order_history(
    symbol: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
):
    """
    Order history from the local database.
    Includes fills, slippage, and algo details for every executed order.
    """
    from broker.persistence import get_order_history
    conn = await get_raw_connection()
    try:
        rows = await get_order_history(conn, symbol=symbol, limit=limit)
        return [
            {
                **{k: (v.isoformat() if hasattr(v, 'isoformat') else v)
                   for k, v in row.items()
                   if k not in ('fills',)},
                "fills": row.get("fills", []),
            }
            for row in rows
        ]
    finally:
        await conn.close()


@router.get("/history/{order_id}/fills")
async def get_order_fills(order_id: str):
    """Get all fills for a specific order from the DB."""
    conn = await get_raw_connection()
    try:
        rows = await conn.fetch("""
            SELECT fill_id, symbol, side, qty, price, commission, filled_at
            FROM order_fills
            WHERE broker_order_id = $1
            ORDER BY filled_at
        """, order_id)
        return [dict(r) for r in rows]
    finally:
        await conn.close()
