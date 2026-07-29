"""
Indian Broker API Router
Endpoints for Zerodha and Upstox:
  - OAuth connect/callback
  - Portfolio (holdings + positions + funds)
  - Orders (place, modify, cancel, history)
  - AI portfolio analysis
  - Alerts management
"""
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from db.database import get_raw_connection
from broker.indian.session_manager import (
    get_indian_broker, save_broker_connection, invalidate_session,
)
from broker.indian.base_indian import (
    IndianOrderRequest, Exchange, ProductType, Validity, OrderVariety,
)
from broker.indian.portfolio_analysis import analyse_portfolio, generate_stock_insight
from broker.indian.alert_engine import (
    check_and_fire_alerts, get_user_alerts, mark_alerts_read,
)
from core.config import settings
import structlog

logger = structlog.get_logger()
router = APIRouter(prefix="/api/india", tags=["indian-brokers"])

# ── demo user (replace with real auth middleware) ─────────────
DEMO_USER_ID = "00000000-0000-0000-0000-000000000001"


# ── Request models ────────────────────────────────────────────

class PlaceOrderBody(BaseModel):
    exchange:         str              # NSE | BSE | NFO
    tradingsymbol:    str
    transaction_type: str              # BUY | SELL
    quantity:         int
    product:          str = "CNC"      # CNC | MIS | NRML
    order_type:       str = "MARKET"   # MARKET | LIMIT | SL | SL-M
    price:            float = 0.0
    trigger_price:    float = 0.0
    validity:         str = "DAY"
    variety:          str = "regular"
    tag:              str = ""


class ModifyOrderBody(BaseModel):
    quantity:      Optional[int]   = None
    price:         Optional[float] = None
    trigger_price: Optional[float] = None
    order_type:    Optional[str]   = None
    validity:      Optional[str]   = None


class MarkReadBody(BaseModel):
    alert_ids: list[str]


class ConnectTokenBody(BaseModel):
    """For direct token injection (testing / manual connect)."""
    access_token: str
    broker_user_id:   str = ""
    broker_user_name: str = ""


# ═══════════════════════════════════════════════════
# OAuth flows
# ═══════════════════════════════════════════════════

@router.get("/zerodha/login")
async def zerodha_login(user_id: str = DEMO_USER_ID):
    """Redirect user to Zerodha OAuth login page."""
    from broker.indian.zerodha import ZerodhaBroker
    api_key = getattr(settings, "zerodha_api_key", "")
    if not api_key:
        raise HTTPException(400, "ZERODHA_API_KEY not configured in .env")
    kite = ZerodhaBroker(api_key=api_key, api_secret="")
    login_url = kite.get_login_url()
    return RedirectResponse(url=login_url)


@router.get("/zerodha/callback")
async def zerodha_callback(request_token: str, action: str = "login", status: str = "success"):
    """
    Zerodha OAuth callback.
    Zerodha redirects here with ?request_token=XXX after user logs in.
    """
    if status != "success":
        raise HTTPException(400, "Zerodha login was not successful")

    from broker.indian.zerodha import ZerodhaBroker
    api_key    = getattr(settings, "zerodha_api_key", "")
    api_secret = getattr(settings, "zerodha_api_secret", "")
    kite = ZerodhaBroker(api_key=api_key, api_secret=api_secret)

    access_token = await kite.exchange_token(request_token)
    await kite.connect()
    profile = await kite.get_profile()

    conn = await get_raw_connection()
    try:
        await _ensure_demo_user(conn)
        await save_broker_connection(
            conn,
            user_id=DEMO_USER_ID,
            broker="zerodha",
            access_token=access_token,
            broker_user_id=profile.get("user_id", ""),
            broker_user_name=profile.get("user_name", ""),
            meta={"api_key": api_key, "api_secret": api_secret},
            token_expiry=datetime.now(timezone.utc).replace(
                hour=3, minute=30, second=0
            ) + timedelta(days=1),
        )
        logger.info("zerodha_oauth_complete", user=profile.get("user_name"))
    finally:
        await conn.close()

    return {
        "status": "connected",
        "broker": "zerodha",
        "user_name": profile.get("user_name"),
        "message": "Zerodha connected successfully. You can now trade."
    }


@router.post("/zerodha/connect")
async def zerodha_connect_direct(body: ConnectTokenBody):
    """
    Connect Zerodha with a pre-obtained access token.
    Useful for testing or when your app handles the OAuth redirect separately.
    """
    from broker.indian.zerodha import ZerodhaBroker
    api_key    = getattr(settings, "zerodha_api_key", "")
    api_secret = getattr(settings, "zerodha_api_secret", "")
    kite = ZerodhaBroker(api_key=api_key, api_secret=api_secret,
                         access_token=body.access_token)
    await kite.connect()
    profile = await kite.get_profile()

    conn = await get_raw_connection()
    try:
        await _ensure_demo_user(conn)
        await save_broker_connection(
            conn, DEMO_USER_ID, "zerodha", body.access_token,
            broker_user_id=body.broker_user_id or profile.get("user_id", ""),
            broker_user_name=body.broker_user_name or profile.get("user_name", ""),
            meta={"api_key": api_key, "api_secret": api_secret},
        )
    finally:
        await conn.close()

    return {"status": "connected", "broker": "zerodha",
            "user": profile.get("user_name")}


@router.get("/upstox/login")
async def upstox_login(user_id: str = DEMO_USER_ID):
    """Redirect user to Upstox OAuth2 login page."""
    from broker.indian.upstox import UpstoxBroker
    print("---------------------------------------------",settings)
    api_key      = getattr(settings, "upstox_api_key", "")
    redirect_uri = getattr(settings, "upstox_redirect_uri", "")
    if not api_key:
        raise HTTPException(400, "UPSTOX_API_KEY not configured in .env")
    client = UpstoxBroker(api_key=api_key, api_secret="", redirect_uri=redirect_uri)
    login_url = client.get_login_url(state=user_id)
    return RedirectResponse(url=login_url)


@router.get("/upstox/callback")
async def upstox_callback(code: str, state: str = DEMO_USER_ID):
    """Upstox OAuth2 callback — exchanges auth code for access token."""
    from broker.indian.upstox import UpstoxBroker
    print(settings)
    api_key      = getattr(settings, "upstox_api_key", "")
    api_secret   = getattr(settings, "upstox_api_secret", "")
    redirect_uri = getattr(settings, "upstox_redirect_uri", "")

    client = UpstoxBroker(api_key=api_key, api_secret=api_secret,
                          redirect_uri=redirect_uri)
    access_token = await client.exchange_code(code)
    await client.connect()
    profile = await client.get_profile()

    conn = await get_raw_connection()
    try:
        await _ensure_demo_user(conn)
        await save_broker_connection(
            conn, state, "upstox", access_token,
            broker_user_id=profile.get("user_id", ""),
            broker_user_name=profile.get("name", ""),
            meta={"api_key": api_key, "api_secret": api_secret,
                  "redirect_uri": redirect_uri},
            token_expiry=datetime.now(timezone.utc).replace(
                hour=22, minute=0, second=0) + timedelta(days=1),
        )
        logger.info("upstox_oauth_complete", user=profile.get("name"))
    finally:
        await conn.close()

    return {"status": "connected", "broker": "upstox",
            "user_name": profile.get("name"),
            "message": "Upstox connected successfully."}


@router.post("/upstox/connect")
async def upstox_connect_direct(body: ConnectTokenBody):
    """Connect Upstox with a pre-obtained access token."""
    from broker.indian.upstox import UpstoxBroker
    api_key      = getattr(settings, "upstox_api_key", "")
    api_secret   = getattr(settings, "upstox_api_secret", "")
    redirect_uri = getattr(settings, "upstox_redirect_uri", "")
    client = UpstoxBroker(api_key=api_key, api_secret=api_secret,
                          redirect_uri=redirect_uri,
                          access_token=body.access_token)
    await client.connect()
    profile = await client.get_profile()

    conn = await get_raw_connection()
    try:
        await _ensure_demo_user(conn)
        await save_broker_connection(
            conn, DEMO_USER_ID, "upstox", body.access_token,
            broker_user_id=body.broker_user_id or profile.get("user_id", ""),
            broker_user_name=body.broker_user_name or profile.get("name", ""),
            meta={"api_key": api_key, "api_secret": api_secret,
                  "redirect_uri": redirect_uri},
        )
    finally:
        await conn.close()

    return {"status": "connected", "broker": "upstox",
            "user": profile.get("name")}


@router.get("/connections")
async def list_connections():
    """List all broker connections for the current user."""
    conn = await get_raw_connection()
    try:
        rows = await conn.fetch("""
            SELECT broker, broker_user_id, broker_user_name,
                   is_active, connected_at, last_synced, token_expiry
            FROM user_broker_connections
            WHERE user_id = $1::uuid
            ORDER BY connected_at DESC
        """, DEMO_USER_ID)
        return [
            {
                **{k: (v.isoformat() if hasattr(v, "isoformat") else v)
                   for k, v in dict(r).items()
                   if k not in ("access_token_enc", "refresh_token_enc")},
            }
            for r in rows
        ]
    finally:
        await conn.close()


@router.delete("/connections/{broker}")
async def disconnect_broker(broker: str):
    """Disconnect a broker account."""
    conn = await get_raw_connection()
    try:
        await conn.execute("""
            UPDATE user_broker_connections SET is_active = false
            WHERE user_id = $1::uuid AND broker = $2
        """, DEMO_USER_ID, broker)
        invalidate_session(DEMO_USER_ID, broker)
        return {"status": "disconnected", "broker": broker}
    finally:
        await conn.close()


# ═══════════════════════════════════════════════════
# Portfolio endpoints
# ═══════════════════════════════════════════════════

@router.get("/{broker}/portfolio")
async def get_portfolio(broker: str):
    """Full portfolio: holdings + positions + funds."""
    conn = await get_raw_connection()
    try:
        client = await get_indian_broker(DEMO_USER_ID, broker, conn)
        funds    = await client.get_funds()
        holdings = await client.get_holdings()
        positions_raw = await client.get_positions()
        positions = (positions_raw.get("net", [])
                     if isinstance(positions_raw, dict) else positions_raw)

        total_investment = sum(h.investment_value for h in holdings)
        total_current    = sum(h.current_value for h in holdings)
        total_pnl        = sum(h.pnl for h in holdings)
        day_pnl          = sum(h.quantity * h.day_change for h in holdings)

        return {
            "broker": broker,
            "funds": {
                "available_cash":     funds.available_cash,
                "available_margin":   funds.available_margin,
                "used_margin":        funds.used_margin,
                "net":                funds.net,
                "collateral":         funds.collateral,
            },
            "summary": {
                "total_investment":   total_investment,
                "total_current_value": total_current,
                "total_pnl":          total_pnl,
                "total_pnl_pct":      (total_pnl / total_investment * 100)
                                       if total_investment else 0,
                "day_pnl":            day_pnl,
                "holdings_count":     len(holdings),
                "positions_count":    len([p for p in positions if p.quantity != 0]),
            },
            "holdings": [
                {
                    "symbol":          h.tradingsymbol,
                    "exchange":        h.exchange,
                    "isin":            h.isin,
                    "quantity":        h.quantity,
                    "t1_quantity":     h.t1_quantity,
                    "avg_price":       h.average_price,
                    "ltp":             h.last_price,
                    "current_value":   h.current_value,
                    "investment":      h.investment_value,
                    "pnl":             h.pnl,
                    "pnl_pct":         h.total_return_pct,
                    "day_change":      h.day_change,
                    "day_change_pct":  h.day_change_pct,
                }
                for h in holdings
            ],
            "positions": [
                {
                    "symbol":      p.tradingsymbol,
                    "exchange":    p.exchange,
                    "product":     p.product,
                    "quantity":    p.quantity,
                    "side":        p.side,
                    "buy_price":   p.buy_price,
                    "sell_price":  p.sell_price,
                    "ltp":         p.last_price,
                    "pnl":         p.pnl,
                    "unrealised":  p.unrealised,
                    "realised":    p.realised,
                    "change_pct":  p.change_pct,
                }
                for p in positions if p.quantity != 0
            ],
        }
    finally:
        await conn.close()


@router.get("/{broker}/holdings")
async def get_holdings(broker: str):
    conn = await get_raw_connection()
    try:
        client   = await get_indian_broker(DEMO_USER_ID, broker, conn)
        holdings = await client.get_holdings()
        return [vars(h) for h in holdings]
    finally:
        await conn.close()


@router.get("/{broker}/positions")
async def get_positions(broker: str):
    conn = await get_raw_connection()
    try:
        client = await get_indian_broker(DEMO_USER_ID, broker, conn)
        positions_raw = await client.get_positions()
        if isinstance(positions_raw, dict):
            return {
                "net": [vars(p) for p in positions_raw.get("net", [])],
                "day": [vars(p) for p in positions_raw.get("day", [])],
            }
        return [vars(p) for p in positions_raw]
    finally:
        await conn.close()


@router.get("/{broker}/funds")
async def get_funds(broker: str):
    conn = await get_raw_connection()
    try:
        client = await get_indian_broker(DEMO_USER_ID, broker, conn)
        funds  = await client.get_funds()
        return vars(funds)
    finally:
        await conn.close()


# ═══════════════════════════════════════════════════
# Orders
# ═══════════════════════════════════════════════════

@router.get("/{broker}/orders")
async def list_orders(broker: str):
    conn = await get_raw_connection()
    try:
        client = await get_indian_broker(DEMO_USER_ID, broker, conn)
        orders = await client.get_orders()
        return [vars(o) for o in orders]
    finally:
        await conn.close()


@router.post("/{broker}/orders")
async def place_order(broker: str, body: PlaceOrderBody):
    conn = await get_raw_connection()
    try:
        client = await get_indian_broker(DEMO_USER_ID, broker, conn)
        req = IndianOrderRequest(
            exchange=Exchange(body.exchange),
            tradingsymbol=body.tradingsymbol.upper(),
            transaction_type=body.transaction_type.upper(),
            quantity=body.quantity,
            product=ProductType(body.product),
            order_type=body.order_type.upper(),
            price=body.price,
            trigger_price=body.trigger_price,
            validity=Validity(body.validity),
            variety=OrderVariety(body.variety),
            tag=body.tag or "alphadeskv1",
        )

        # Check market hours
        if not client.is_market_open():
            if req.variety != OrderVariety.AMO:
                raise HTTPException(
                    400,
                    "Market is closed. Use variety='amo' for After Market Orders."
                )

        order_id = await client.place_order(req)
        logger.info("indian_order_placed", broker=broker,
                    symbol=body.tradingsymbol, order_id=order_id)
        return {"order_id": order_id, "status": "placed",
                "symbol": body.tradingsymbol, "broker": broker}
    except ValueError as e:
        raise HTTPException(400, str(e))
    finally:
        await conn.close()


@router.put("/{broker}/orders/{order_id}")
async def modify_order(broker: str, order_id: str, body: ModifyOrderBody):
    conn = await get_raw_connection()
    try:
        client = await get_indian_broker(DEMO_USER_ID, broker, conn)
        new_id = await client.modify_order(
            order_id=order_id,
            quantity=body.quantity,
            price=body.price,
            trigger_price=body.trigger_price,
            order_type=body.order_type,
            validity=body.validity,
        )
        return {"order_id": new_id, "status": "modified"}
    finally:
        await conn.close()


@router.delete("/{broker}/orders/{order_id}")
async def cancel_order(broker: str, order_id: str):
    conn = await get_raw_connection()
    try:
        client = await get_indian_broker(DEMO_USER_ID, broker, conn)
        cancelled_id = await client.cancel_order(order_id)
        return {"order_id": cancelled_id, "status": "cancelled"}
    finally:
        await conn.close()


@router.get("/{broker}/orders/{order_id}/trades")
async def get_order_trades(broker: str, order_id: str):
    """Get individual fills for an order."""
    conn = await get_raw_connection()
    try:
        client = await get_indian_broker(DEMO_USER_ID, broker, conn)
        trades = await client.get_order_trades(order_id)
        return trades
    finally:
        await conn.close()


# ═══════════════════════════════════════════════════
# Market Data
# ═══════════════════════════════════════════════════

@router.get("/{broker}/quote")
async def get_quote(broker: str, symbols: str = Query(...,
    description="Comma-separated: NSE:RELIANCE,BSE:500325")):
    """Get live quotes for symbols."""
    conn = await get_raw_connection()
    try:
        client = await get_indian_broker(DEMO_USER_ID, broker, conn)
        syms_list = [s.strip() for s in symbols.split(",")]
        quotes = await client.get_quote(syms_list)
        return {k: vars(v) for k, v in quotes.items()}
    finally:
        await conn.close()


@router.get("/{broker}/market/open")
async def market_status(broker: str):
    """Check if market is currently open."""
    conn = await get_raw_connection()
    try:
        client = await get_indian_broker(DEMO_USER_ID, broker, conn)
        return {
            "is_open": client.is_market_open(),
            "broker":  broker,
            "market":  "NSE/BSE",
            "timezone": "Asia/Kolkata",
        }
    finally:
        await conn.close()


# ═══════════════════════════════════════════════════
# AI Portfolio Analysis
# ═══════════════════════════════════════════════════

@router.get("/{broker}/analysis")
async def portfolio_analysis(
    broker: str,
    type: str = Query("full",
        description="full | risk | diversification | rebalance | pnl"),
):
    """Run AI portfolio analysis using Claude."""
    conn = await get_raw_connection()
    try:
        client = await get_indian_broker(DEMO_USER_ID, broker, conn)
        result = await analyse_portfolio(client, analysis_type=type)
        return result
    finally:
        await conn.close()


@router.get("/{broker}/analysis/{symbol}")
async def stock_insight(broker: str, symbol: str,
                        exchange: str = Query("NSE")):
    """Get deep AI analysis of a specific stock in your portfolio."""
    conn = await get_raw_connection()
    try:
        client = await get_indian_broker(DEMO_USER_ID, broker, conn)
        result = await generate_stock_insight(client, symbol.upper(), exchange)
        return result
    finally:
        await conn.close()


# ═══════════════════════════════════════════════════
# Alerts
# ═══════════════════════════════════════════════════

@router.get("/{broker}/alerts")
async def get_alerts(broker: str, unread_only: bool = Query(False)):
    """Get portfolio alerts for the current user."""
    conn = await get_raw_connection()
    try:
        alerts = await get_user_alerts(conn, DEMO_USER_ID,
                                       unread_only=unread_only)
        return alerts
    finally:
        await conn.close()


@router.post("/{broker}/alerts/check")
async def trigger_alert_check(broker: str):
    """Manually trigger an alert check for the portfolio."""
    conn = await get_raw_connection()
    try:
        client = await get_indian_broker(DEMO_USER_ID, broker, conn)
        alerts = await check_and_fire_alerts(
            DEMO_USER_ID, broker, client, conn
        )
        return {
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "new_alerts": len(alerts),
            "alerts": alerts,
        }
    finally:
        await conn.close()


@router.post("/{broker}/alerts/read")
async def mark_read(broker: str, body: MarkReadBody):
    """Mark alerts as read."""
    conn = await get_raw_connection()
    try:
        count = await mark_alerts_read(conn, DEMO_USER_ID, body.alert_ids)
        return {"marked_read": count}
    finally:
        await conn.close()


# ═══════════════════════════════════════════════════
# GTT (Zerodha-only)
# ═══════════════════════════════════════════════════

@router.get("/zerodha/gtt")
async def list_gtts():
    """List all GTT (Good-Till-Triggered) orders."""
    conn = await get_raw_connection()
    try:
        client = await get_indian_broker(DEMO_USER_ID, "zerodha", conn)
        return await client.get_gtts()
    finally:
        await conn.close()


@router.delete("/zerodha/gtt/{gtt_id}")
async def delete_gtt(gtt_id: int):
    """Delete a GTT order."""
    conn = await get_raw_connection()
    try:
        client = await get_indian_broker(DEMO_USER_ID, "zerodha", conn)
        result = await client.delete_gtt(gtt_id)
        return result
    finally:
        await conn.close()


# ═══════════════════════════════════════════════════
# Portfolio Snapshot (history for charting)
# ═══════════════════════════════════════════════════

@router.post("/{broker}/snapshot")
async def save_snapshot(broker: str):
    """Save a portfolio snapshot for historical charting."""
    conn = await get_raw_connection()
    try:
        client   = await get_indian_broker(DEMO_USER_ID, broker, conn)
        holdings = await client.get_holdings()
        funds    = await client.get_funds()
        positions_raw = await client.get_positions()
        positions = (positions_raw.get("net", [])
                     if isinstance(positions_raw, dict) else positions_raw)

        invested = sum(h.investment_value for h in holdings)
        current  = sum(h.current_value for h in holdings)
        pnl      = current - invested
        day_pnl  = sum(h.quantity * h.day_change for h in holdings)

        snapshot_id = str(uuid.uuid4())
        await conn.execute("""
            INSERT INTO portfolio_snapshots
                (id, user_id, broker, total_value, cash, invested_value,
                 day_pnl, overall_pnl, overall_pnl_pct,
                 holdings_json, positions_json)
            VALUES ($1::uuid, $2::uuid, $3, $4, $5, $6, $7, $8, $9, $10, $11)
        """,
            snapshot_id,
            DEMO_USER_ID, broker,
            current + funds.available_cash,
            funds.available_cash,
            invested,
            day_pnl,
            pnl,
            (pnl / invested * 100) if invested else 0,
            __import__("json").dumps([vars(h) for h in holdings]),
            __import__("json").dumps([vars(p) for p in positions]),
        )
        return {"status": "saved", "total_value": current + funds.available_cash}
    finally:
        await conn.close()


@router.get("/{broker}/snapshot/history")
async def get_snapshot_history(broker: str, days: int = Query(30, le=365)):
    """Get portfolio value history for charting."""
    conn = await get_raw_connection()
    try:
        rows = await conn.fetch("""
            SELECT total_value, cash, invested_value,
                   day_pnl, overall_pnl, overall_pnl_pct, snapped_at
            FROM portfolio_snapshots
            WHERE user_id = $1::uuid AND broker = $2
              AND snapped_at > now() - ($3 || ' days')::interval
            ORDER BY snapped_at
        """, DEMO_USER_ID, broker, str(days))
        return [
            {**dict(r), "snapped_at": r["snapped_at"].isoformat()}
            for r in rows
        ]
    finally:
        await conn.close()


# ═══════════════════════════════════════════════════
# Internal helpers
# ═══════════════════════════════════════════════════

async def _ensure_demo_user(conn) -> None:
    """Create demo user row if it doesn't exist."""
    await conn.execute("""
        INSERT INTO users (id, email, name)
        VALUES ($1::uuid, 'demo@alphadeskv1.ai', 'Demo User')
        ON CONFLICT (email) DO NOTHING
    """, DEMO_USER_ID)
