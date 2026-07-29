"""
Memory service — handles all read/write to agent_memories via pgvector.
Uses the universal LLM router for embeddings (works with any provider).
"""
import json
import uuid
from datetime import datetime, timedelta
import asyncpg
from core.llm import embed as llm_embed
import structlog

logger = structlog.get_logger()


async def embed(text: str) -> list[float]:
    """Generate embedding using the active LLM provider."""
    return await llm_embed(text)


async def write_memory(
    conn: asyncpg.Connection,
    agent_id: str,
    memory_type: str,
    content: str,
    metadata: dict = None,
    cycle_id: str = None,
    importance_score: float = 0.5,
    expires_in_hours: int = None,
) -> str:
    """Write a memory for an agent. Returns the memory UUID."""
    embedding     = await embed(content)
    embedding_str = "[" + ",".join(str(x) for x in embedding) + "]"
    expires_at    = None
    if expires_in_hours:
        expires_at = datetime.utcnow() + timedelta(hours=expires_in_hours)

    memory_id = str(uuid.uuid4())
    row = await conn.fetchrow("""
        INSERT INTO agent_memories
            (id, agent_id, cycle_id, memory_type, content, embedding,
             importance_score, metadata, expires_at)
        VALUES ($1::uuid, $2, $3::uuid, $4, $5, $6::vector, $7, $8, $9)
        RETURNING id::text
    """,
        memory_id, agent_id, cycle_id, memory_type, content,
        embedding_str, importance_score,
        json.dumps(metadata or {}), expires_at,
    )
    return row["id"]


async def retrieve_memories(
    conn: asyncpg.Connection,
    agent_id: str,
    query: str,
    memory_types: list[str] = None,
    limit: int = 8,
    min_importance: float = 0.2,
) -> list[dict]:
    """Semantic search over an agent's memories."""
    embedding     = await embed(query)
    embedding_str = "[" + ",".join(str(x) for x in embedding) + "]"
    types_filter  = memory_types or ["observation", "analysis", "reflection", "signal"]

    rows = await conn.fetch("""
        SELECT
            id::text,
            content,
            memory_type,
            importance_score,
            metadata,
            created_at,
            1 - (embedding <=> $3::vector) AS similarity
        FROM agent_memories
        WHERE agent_id = $1
          AND memory_type = ANY($2)
          AND importance_score >= $4
          AND (expires_at IS NULL OR expires_at > now())
        ORDER BY embedding <=> $3::vector
        LIMIT $5
    """, agent_id, types_filter, embedding_str, min_importance, limit)

    return [dict(r) for r in rows]


async def write_reflection(
    conn: asyncpg.Connection,
    agent_id: str,
    cycle_id: str,
    trade_outcome: dict,
) -> None:
    """Post-trade reflection: agent generates a lesson from the outcome."""
    pnl_pct    = trade_outcome.get("pnl_pct", 0) or 0
    importance = min(0.9, 0.5 + abs(pnl_pct) * 2)
    outcome_sign = "profitable" if pnl_pct > 0 else "loss-making"

    content = (
        f"Trade reflection [{outcome_sign}]: {trade_outcome.get('symbol')} "
        f"{trade_outcome.get('direction')} @ {trade_outcome.get('entry_price', 0):.2f}, "
        f"closed @ {trade_outcome.get('exit_price', 'open')}, "
        f"P&L: {pnl_pct:.2%}. "
        f"Close reason: {trade_outcome.get('close_reason', 'unknown')}. "
        f"Agent signals at entry: {json.dumps(trade_outcome.get('agent_signals', {}))}"
    )

    await write_memory(
        conn, agent_id, "reflection", content,
        metadata={"trade_outcome": trade_outcome},
        cycle_id=cycle_id,
        importance_score=importance,
    )
    logger.info("reflection_written", agent=agent_id, symbol=trade_outcome.get("symbol"))


async def get_portfolio_context(conn: asyncpg.Connection) -> list[dict]:
    """Retrieve recent regime observations for CIO context."""
    rows = await conn.fetch("""
        SELECT content, memory_type, metadata, created_at
        FROM agent_memories
        WHERE agent_id = 'market_intelligence'
          AND memory_type = 'observation'
          AND created_at > now() - interval '7 days'
        ORDER BY created_at DESC
        LIMIT 5
    """)
    return [dict(r) for r in rows]
