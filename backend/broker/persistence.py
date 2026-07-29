"""
Broker persistence service.
Every order submitted and fill received is recorded to the DB for audit.
The execution agent calls this after each algo run.
"""
from __future__ import annotations
import uuid
from datetime import datetime, timezone
from typing import Optional
import asyncpg
import structlog

from broker.base import Order
from broker.execution_algos import AlgoResult

logger = structlog.get_logger()


async def save_broker_order(
    conn: asyncpg.Connection,
    order: Order,
    cycle_id: Optional[str] = None,
    algo: Optional[str] = None,
    source: str = "agent",
) -> str:
    """Persist a submitted order to broker_orders. Returns the broker_order_id."""
    order_uuid = str(uuid.uuid4())
    await conn.execute("""
        INSERT INTO broker_orders (
            id, broker_order_id, cycle_id, symbol, side, order_type,
            qty, filled_qty, limit_price, stop_price, avg_fill_price,
            status, algo, slippage_bps, source, time_in_force,
            reject_reason, submitted_at, filled_at, cancelled_at
        ) VALUES (
            $1::uuid, $2, $3::uuid, $4, $5, $6,
            $7, $8, $9, $10, $11,
            $12, $13, $14, $15, $16,
            $17, $18, $19, $20
        )
        ON CONFLICT (broker_order_id) DO UPDATE SET
            filled_qty     = EXCLUDED.filled_qty,
            avg_fill_price = EXCLUDED.avg_fill_price,
            status         = EXCLUDED.status,
            slippage_bps   = EXCLUDED.slippage_bps,
            filled_at      = EXCLUDED.filled_at,
            cancelled_at   = EXCLUDED.cancelled_at
    """,
        order_uuid,
        order.order_id,
        cycle_id,
        order.symbol,
        order.side.value,
        order.order_type.value,
        order.qty,
        order.filled_qty,
        order.limit_price,
        order.stop_price,
        order.avg_fill_price,
        order.status.value,
        algo,
        order.slippage_bps if order.slippage_bps else None,
        source,
        "day",                   # default TIF
        order.reject_reason,
        order.submitted_at or datetime.now(timezone.utc),
        order.filled_at,
        order.cancelled_at,
    )
    logger.debug("broker_order_saved", order_id=order.order_id, status=order.status.value)
    return order.order_id


async def save_fills(
    conn: asyncpg.Connection,
    order: Order,
) -> int:
    """Persist individual fill events. Returns count saved."""
    count = 0
    for fill in order.fills:
        try:
            fill_uuid = str(uuid.uuid4())
            await conn.execute("""
                INSERT INTO order_fills (
                    id, broker_order_id, fill_id, symbol, side,
                    qty, price, commission, filled_at
                ) VALUES ($1::uuid, $2, $3, $4, $5, $6, $7, $8, $9)
                ON CONFLICT (fill_id) DO NOTHING
            """,
                fill_uuid,
                fill.order_id,
                fill.fill_id,
                fill.symbol,
                fill.side.value,
                fill.qty,
                fill.price,
                fill.commission,
                fill.timestamp,
            )
            count += 1
        except Exception as e:
            logger.warning("fill_save_error", fill_id=fill.fill_id, error=str(e))
    return count


async def save_algo_result(
    conn: asyncpg.Connection,
    result: AlgoResult,
    cycle_id: Optional[str] = None,
) -> None:
    """
    Persist the complete result of an execution algorithm run:
    saves a synthetic BrokerOrder row and all individual fills.
    """

    synthetic_order_uuid = str(uuid.uuid4())
    synthetic_id = f"ALGO-{cycle_id[:8] if cycle_id else 'NOCYCLE'}-{result.symbol}"

    # Upsert the algo order summary
    await conn.execute("""
        INSERT INTO broker_orders (
            id, broker_order_id, cycle_id, symbol, side, order_type,
            qty, filled_qty, avg_fill_price, status, algo,
            slippage_bps, source, submitted_at, filled_at
        ) VALUES (
            $1::uuid, $2, $3::uuid, $4, $5, 'market',
            $6, $7, $8, $9, $10,
            $11, 'agent', now(), now()
        )
        ON CONFLICT (broker_order_id) DO UPDATE SET
            filled_qty     = EXCLUDED.filled_qty,
            avg_fill_price = EXCLUDED.avg_fill_price,
            status         = EXCLUDED.status,
            slippage_bps   = EXCLUDED.slippage_bps,
            filled_at      = now()
    """,
        synthetic_order_uuid,
        synthetic_id,
        cycle_id,
        result.symbol,
        result.side,
        result.total_qty,
        result.filled_qty,
        result.avg_fill_price,
        result.status,
        result.algo,
        result.slippage_bps,
    )

    # Save individual fills
    for fill in result.fills:
        try:
            fill_uuid = str(uuid.uuid4())
            await conn.execute("""
                INSERT INTO order_fills (
                    id, broker_order_id, fill_id, symbol, side,
                    qty, price, commission, filled_at
                ) VALUES ($1::uuid, $2, $3, $4, $5, $6, $7, $8, $9)
                ON CONFLICT (fill_id) DO NOTHING
            """,
                fill_uuid,
                synthetic_id,
                fill.fill_id,
                fill.symbol,
                fill.side.value,
                fill.qty,
                fill.price,
                fill.commission,
                fill.timestamp,
            )
        except Exception as e:
            logger.warning("algo_fill_save_error", error=str(e))

    logger.info("algo_result_persisted",
                symbol=result.symbol, algo=result.algo,
                fills=len(result.fills), fill_rate=result.fill_rate)


async def get_order_history(
    conn: asyncpg.Connection,
    symbol: Optional[str] = None,
    limit: int = 50,
) -> list[dict]:
    """Fetch order history from DB for the dashboard."""
    where = "WHERE symbol = $1" if symbol else ""
    params = [symbol, limit] if symbol else [limit]
    limit_param = "$2" if symbol else "$1"

    rows = await conn.fetch(f"""
        SELECT
            bo.broker_order_id,
            bo.cycle_id::text,
            bo.symbol,
            bo.side,
            bo.order_type,
            bo.qty,
            bo.filled_qty,
            bo.avg_fill_price,
            bo.status,
            bo.algo,
            bo.slippage_bps,
            bo.source,
            bo.submitted_at,
            bo.filled_at,
            COALESCE(
                json_agg(
                    json_build_object(
                        'fill_id', f.fill_id,
                        'qty', f.qty,
                        'price', f.price,
                        'commission', f.commission,
                        'filled_at', f.filled_at
                    )
                ) FILTER (WHERE f.fill_id IS NOT NULL),
                '[]'
            ) AS fills
        FROM broker_orders bo
        LEFT JOIN order_fills f ON f.broker_order_id = bo.broker_order_id
        {where}
        GROUP BY bo.broker_order_id
        ORDER BY bo.submitted_at DESC
        LIMIT {limit_param}
    """, *params)

    return [dict(r) for r in rows]
