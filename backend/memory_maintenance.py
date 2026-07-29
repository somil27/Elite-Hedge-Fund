"""
Memory maintenance job — prunes expired memories and decays importance scores.
Run periodically (daily recommended):
    python memory_maintenance.py
Or schedule via APScheduler / cron.
"""
import asyncio
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from dotenv import load_dotenv
load_dotenv()

import structlog
logger = structlog.get_logger()


async def prune_expired_memories(conn) -> int:
    """Delete memories past their expiry date."""
    result = await conn.execute("""
        DELETE FROM agent_memories
        WHERE expires_at IS NOT NULL AND expires_at < now()
    """)
    count = int(result.split()[-1]) if result else 0
    logger.info("expired_memories_pruned", count=count)
    return count


async def decay_importance_scores(conn) -> int:
    """
    Reduce importance of old memories that haven't been linked to outcomes.
    Memories older than 30 days lose 10% importance per run.
    Floor at 0.1 so they remain retrievable but deprioritized.
    """
    result = await conn.execute("""
        UPDATE agent_memories
        SET importance_score = GREATEST(0.1, importance_score * 0.90)
        WHERE created_at < now() - interval '30 days'
          AND memory_type IN ('observation', 'signal')
          AND importance_score > 0.1
    """)
    count = int(result.split()[-1]) if result else 0
    logger.info("importance_decayed", count=count)
    return count


async def close_stale_cycles(conn) -> int:
    """Mark cycles that have been running for more than 2 hours as failed."""
    result = await conn.execute("""
        UPDATE trade_cycles
        SET status = 'failed', completed_at = now()
        WHERE status IN ('running', 'awaiting_human')
          AND started_at < now() - interval '2 hours'
    """)
    count = int(result.split()[-1]) if result else 0
    if count:
        logger.warning("stale_cycles_closed", count=count)
    return count


async def expire_human_reviews(conn) -> int:
    """Expire pending human reviews that have passed their deadline."""
    result = await conn.execute("""
        UPDATE human_reviews
        SET status = 'expired'
        WHERE status = 'pending'
          AND expires_at < now()
    """)
    count = int(result.split()[-1]) if result else 0
    if count:
        logger.info("reviews_expired", count=count)
    return count


async def print_memory_stats(conn):
    """Print a summary of memory usage."""
    rows = await conn.fetch("""
        SELECT
            agent_id,
            memory_type,
            COUNT(*) as count,
            ROUND(AVG(importance_score)::numeric, 3) as avg_importance
        FROM agent_memories
        GROUP BY agent_id, memory_type
        ORDER BY agent_id, memory_type
    """)
    print("\nMemory Store Summary:")
    print(f"{'Agent':<25} {'Type':<15} {'Count':>6} {'Avg Importance':>15}")
    print("-" * 65)
    for r in rows:
        print(f"{r['agent_id']:<25} {r['memory_type']:<15} {r['count']:>6} {r['avg_importance']:>15}")

    total = await conn.fetchval("SELECT COUNT(*) FROM agent_memories")
    print(f"\nTotal memories: {total}")


async def main():
    from db.database import get_raw_connection
    conn = await get_raw_connection()
    try:
        print("Running memory maintenance…")
        await prune_expired_memories(conn)
        await decay_importance_scores(conn)
        await close_stale_cycles(conn)
        await expire_human_reviews(conn)
        await print_memory_stats(conn)
        print("\nDone.")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
