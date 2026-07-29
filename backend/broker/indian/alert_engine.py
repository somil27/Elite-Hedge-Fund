"""
Alert Engine for Indian Portfolios
Monitors holdings and positions, fires alerts for:
  - Price crossing user-defined thresholds
  - Upper/lower circuit filters hit
  - P&L targets or stop-loss thresholds
  - Volume spikes
  - AI-generated insight alerts
"""
from __future__ import annotations
import asyncio
import json
import uuid
from datetime import datetime, timezone
from typing import Union
import structlog

from broker.indian.zerodha import ZerodhaBroker
from broker.indian.upstox  import UpstoxBroker

logger = structlog.get_logger()


# ─────────────────────────────────────────────
# Alert type definitions
# ─────────────────────────────────────────────

ALERT_TYPES = {
    "price_above":      "Price crossed above target",
    "price_below":      "Price dropped below threshold",
    "pnl_above":        "P&L target achieved",
    "pnl_below":        "Stop-loss threshold breached",
    "circuit_upper":    "Upper circuit filter hit — trading halted",
    "circuit_lower":    "Lower circuit filter hit — trading halted",
    "volume_spike":     "Unusual volume activity detected",
    "day_loss":         "Portfolio day loss exceeded threshold",
    "ai_insight":       "AI-generated portfolio insight",
}


async def check_and_fire_alerts(
    user_id: str,
    broker: str,
    broker_client: Union[ZerodhaBroker, UpstoxBroker],
    conn,
    user_alert_config: dict = None,
) -> list[dict]:
    """
    Run all alert checks for a user's portfolio.
    Writes triggered alerts to DB and returns list of new alerts.
    user_alert_config: optional per-user thresholds from DB/preferences.
    """
    cfg = user_alert_config or {}
    new_alerts = []

    try:
        holdings  = await broker_client.get_holdings()
        positions_raw = await broker_client.get_positions()
        positions = (positions_raw.get("net", [])
                     if isinstance(positions_raw, dict) else positions_raw)
    except Exception as e:
        logger.error("alert_data_fetch_error", user=user_id, error=str(e))
        return []

    # ── Get live quotes for all holding symbols ────────────────
    symbols = [f"NSE:{h.tradingsymbol}" for h in holdings]
    quotes  = {}
    if symbols and hasattr(broker_client, "get_quote"):
        try:
            quotes = await broker_client.get_quote(symbols[:50])  # API limit
        except Exception as e:
            logger.warning("quote_fetch_error", error=str(e))

    # ── Holdings checks ───────────────────────────────────────
    for h in holdings:
        quote_key = f"NSE:{h.tradingsymbol}"
        q = quotes.get(quote_key)

        # Circuit filter alert
        if q:
            ltp = q.last_price
            if q.upper_circuit and ltp >= q.upper_circuit * 0.999:
                new_alerts.append(_make_alert(
                    user_id, broker, h.tradingsymbol,
                    "circuit_upper",
                    f"{h.tradingsymbol} has hit its UPPER CIRCUIT at ₹{q.upper_circuit:.2f}. "
                    f"Trading is halted for buying.",
                    threshold=q.upper_circuit,
                    meta={"ltp": ltp, "circuit": q.upper_circuit},
                ))
            if q.lower_circuit and ltp <= q.lower_circuit * 1.001:
                new_alerts.append(_make_alert(
                    user_id, broker, h.tradingsymbol,
                    "circuit_lower",
                    f"{h.tradingsymbol} has hit its LOWER CIRCUIT at ₹{q.lower_circuit:.2f}. "
                    f"Trading is halted for selling.",
                    threshold=q.lower_circuit,
                    meta={"ltp": ltp, "circuit": q.lower_circuit},
                ))

        # P&L stop-loss alert (default: -15% from average)
        stop_pct = cfg.get(f"{h.tradingsymbol}_stop_pct", -15.0)
        if h.total_return_pct <= stop_pct:
            new_alerts.append(_make_alert(
                user_id, broker, h.tradingsymbol,
                "pnl_below",
                f"{h.tradingsymbol}: Loss of {h.total_return_pct:.1f}% from avg buy price "
                f"₹{h.average_price:.2f}. Consider reviewing your stop-loss.",
                threshold=stop_pct,
                meta={"return_pct": h.total_return_pct, "avg_price": h.average_price},
            ))

        # P&L target alert (default: +25% from average)
        target_pct = cfg.get(f"{h.tradingsymbol}_target_pct", 25.0)
        if h.total_return_pct >= target_pct:
            new_alerts.append(_make_alert(
                user_id, broker, h.tradingsymbol,
                "pnl_above",
                f"🎯 {h.tradingsymbol} has achieved +{h.total_return_pct:.1f}% return! "
                f"Consider booking partial profits.",
                threshold=target_pct,
                meta={"return_pct": h.total_return_pct, "target_pct": target_pct},
            ))

        # Volume spike via quote
        if q and q.volume:
            # Rough heuristic: if volume > 3x average (we estimate avg from OHLCV)
            pass  # Full impl requires historical avg volume

        # Custom price-above threshold
        if q and h.tradingsymbol in cfg.get("price_above", {}):
            target = cfg["price_above"][h.tradingsymbol]
            if q.last_price >= target:
                new_alerts.append(_make_alert(
                    user_id, broker, h.tradingsymbol,
                    "price_above",
                    f"{h.tradingsymbol} crossed ₹{target:.2f} — now at ₹{q.last_price:.2f}.",
                    threshold=target,
                ))

        # Custom price-below threshold
        if q and h.tradingsymbol in cfg.get("price_below", {}):
            floor = cfg["price_below"][h.tradingsymbol]
            if q.last_price <= floor:
                new_alerts.append(_make_alert(
                    user_id, broker, h.tradingsymbol,
                    "price_below",
                    f"⚠️ {h.tradingsymbol} dropped below ₹{floor:.2f} — now at ₹{q.last_price:.2f}.",
                    threshold=floor,
                ))

    # ── Intraday position checks ──────────────────────────────
    for pos in positions:
        if pos.quantity == 0:
            continue
        # MIS positions must be squared off by 3:20 PM IST
        if pos.product == "MIS":
            import pytz
            ist = pytz.timezone("Asia/Kolkata")
            now_ist = datetime.now(ist)
            if now_ist.hour == 15 and now_ist.minute >= 10:
                new_alerts.append(_make_alert(
                    user_id, broker, pos.tradingsymbol,
                    "price_below",
                    f"⚠️ MIS position in {pos.tradingsymbol} will be auto-squared off at 3:20 PM. "
                    f"Current P&L: ₹{pos.pnl:+.2f}",
                    meta={"pnl": pos.pnl, "qty": pos.quantity},
                ))

        # Intraday stop-loss
        if pos.pnl < -5000:   # ₹5000 loss alert (configurable)
            threshold = cfg.get("intraday_loss_limit", -5000)
            if pos.pnl < threshold:
                new_alerts.append(_make_alert(
                    user_id, broker, pos.tradingsymbol,
                    "pnl_below",
                    f"Intraday loss on {pos.tradingsymbol} exceeded ₹{abs(threshold):,.0f}. "
                    f"Current loss: ₹{pos.pnl:,.2f}",
                    threshold=threshold,
                ))

    # ── Deduplicate: skip alerts already fired in last 1 hour ──
    new_alerts = await _deduplicate_alerts(conn, user_id, new_alerts)

    # ── Persist alerts to DB ──────────────────────────────────
    for alert in new_alerts:
        await _save_alert(conn, alert)

    if new_alerts:
        logger.info("alerts_fired", user=user_id, count=len(new_alerts))

    return new_alerts


def _make_alert(
    user_id: str,
    broker: str,
    symbol: str,
    alert_type: str,
    message: str,
    threshold: float = None,
    meta: dict = None,
) -> dict:
    return {
        "user_id":    user_id,
        "broker":     broker,
        "symbol":     symbol,
        "alert_type": alert_type,
        "threshold":  threshold,
        "message":    message,
        "is_read":    False,
        "triggered_at": datetime.now(timezone.utc).isoformat(),
        "metadata":   meta or {},
    }


async def _deduplicate_alerts(conn, user_id: str, alerts: list[dict]) -> list[dict]:
    """Filter out alerts for same symbol+type fired in the last hour."""
    if not alerts:
        return []
    rows = await conn.fetch("""
        SELECT symbol, alert_type FROM portfolio_alerts
        WHERE user_id = $1::uuid
          AND triggered_at > now() - interval '1 hour'
    """, user_id)
    fired = {(r["symbol"], r["alert_type"]) for r in rows}
    return [a for a in alerts
            if (a["symbol"], a["alert_type"]) not in fired]


async def _save_alert(conn, alert: dict) -> None:
    alert_uuid = str(uuid.uuid4())
    await conn.execute("""
        INSERT INTO portfolio_alerts
            (id, user_id, broker, symbol, alert_type, threshold, message, metadata)
        VALUES ($1::uuid, $2::uuid, $3, $4, $5, $6, $7, $8)
    """,
        alert_uuid,
        alert["user_id"], alert["broker"], alert["symbol"],
        alert["alert_type"], alert["threshold"], alert["message"],
        json.dumps(alert.get("metadata", {})),
    )


async def get_user_alerts(
    conn,
    user_id: str,
    unread_only: bool = False,
    limit: int = 50,
) -> list[dict]:
    """Fetch portfolio alerts for a user."""
    where = "AND is_read = false" if unread_only else ""
    rows = await conn.fetch(f"""
        SELECT id::text, broker, symbol, alert_type, threshold,
               message, is_read, triggered_at, metadata
        FROM portfolio_alerts
        WHERE user_id = $1::uuid {where}
        ORDER BY triggered_at DESC
        LIMIT $2
    """, user_id, limit)
    results = []
    for r in rows:
        d = dict(r)
        meta = d.get("metadata")
        if isinstance(meta, str):
            try:
                d["metadata"] = json.loads(meta)
            except Exception:
                d["metadata"] = {}
        elif meta is None:
            d["metadata"] = {}
        results.append(d)
    return results


async def mark_alerts_read(conn, user_id: str, alert_ids: list[str]) -> int:
    """Mark specific alerts as read."""
    result = await conn.execute("""
        UPDATE portfolio_alerts
        SET is_read = true
        WHERE user_id = $1::uuid
          AND id = ANY($2::uuid[])
    """, user_id, alert_ids)
    return int(result.split()[-1])


async def start_alert_monitor(
    user_id: str,
    broker: str,
    broker_client,
    db_factory,
    interval_seconds: int = 60,
) -> None:
    """
    Background loop that runs alert checks on a schedule.
    Call as: asyncio.create_task(start_alert_monitor(...))
    """
    logger.info("alert_monitor_started", user=user_id, broker=broker,
                interval=interval_seconds)
    while True:
        try:
            conn = await db_factory()
            try:
                await check_and_fire_alerts(user_id, broker, broker_client, conn)
            finally:
                await conn.close()
        except Exception as e:
            logger.error("alert_monitor_error", user=user_id, error=str(e))
        await asyncio.sleep(interval_seconds)
