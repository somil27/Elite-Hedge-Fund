"""
Indian Broker Session Manager
Manages authenticated broker instances per user.
Caches connected clients so we don't re-auth on every request.
"""
from __future__ import annotations
import asyncio
import json
from datetime import datetime
from typing import Optional, Union
import structlog

from core.token_crypto import decrypt_token
from broker.indian.zerodha import ZerodhaBroker
from broker.indian.upstox  import UpstoxBroker

logger = structlog.get_logger()

# In-memory client cache: {user_id: {broker: client}}
_sessions: dict[str, dict[str, Union[ZerodhaBroker, UpstoxBroker]]] = {}
_locks: dict[str, asyncio.Lock] = {}


async def get_indian_broker(
    user_id: str,
    broker: str,
    conn,                          # asyncpg connection
) -> Union[ZerodhaBroker, UpstoxBroker]:
    """
    Get or create an authenticated broker client for a user.
    broker: "zerodha" | "upstox"
    """
    cache_key = f"{user_id}:{broker}"
    if cache_key not in _locks:
        _locks[cache_key] = asyncio.Lock()

    async with _locks[cache_key]:
        # Return cached if present
        if user_id in _sessions and broker in _sessions[user_id]:
            client = _sessions[user_id][broker]
            return client

        # Load from DB
        row = await conn.fetchrow("""
            SELECT access_token_enc, refresh_token_enc, token_expiry,
                   metadata, broker_user_id
            FROM user_broker_connections
            WHERE user_id = $1::uuid AND broker = $2 AND is_active = true
        """, user_id, broker)

        if not row:
            raise ValueError(
                f"No active {broker} connection for user {user_id}. "
                "Please connect your broker account first."
            )

        access_token = decrypt_token(row["access_token_enc"])
        meta         = row["metadata"] or {}
        if isinstance(meta, str):
            try:
                meta = json.loads(meta)
            except Exception:
                meta = {}

        if broker == "zerodha":
            from core.config import settings
            api_key    = meta.get("api_key") or getattr(settings, "zerodha_api_key", "")
            api_secret = meta.get("api_secret") or getattr(settings, "zerodha_api_secret", "")
            client = ZerodhaBroker(
                api_key=api_key,
                api_secret=api_secret,
                access_token=access_token,
            )
        elif broker == "upstox":
            from core.config import settings
            api_key     = meta.get("api_key") or getattr(settings, "upstox_api_key", "")
            api_secret  = meta.get("api_secret") or getattr(settings, "upstox_api_secret", "")
            redirect    = meta.get("redirect_uri") or getattr(settings, "upstox_redirect_uri", "")
            client = UpstoxBroker(
                api_key=api_key,
                api_secret=api_secret,
                redirect_uri=redirect,
                access_token=access_token,
            )
        else:
            raise ValueError(f"Unknown Indian broker: {broker}")

        try:
            await client.connect()
        except Exception as e:
            err_str = str(e)
            if "401" in err_str or "unauthorized" in err_str.lower() or "invalid token" in err_str.lower() or "udapi100050" in err_str.lower():
                raise ValueError(
                    f"Your {broker.upper()} login session has expired or is invalid. "
                    f"Please reconnect your broker account in the dashboard."
                ) from e
            raise e
            
        _sessions.setdefault(user_id, {})[broker] = client

        # Update last_synced
        await conn.execute("""
            UPDATE user_broker_connections
            SET last_synced = now()
            WHERE user_id = $1::uuid AND broker = $2
        """, user_id, broker)

        logger.info("indian_broker_session_created",
                    user=user_id, broker=broker)
        return client


def invalidate_session(user_id: str, broker: str) -> None:
    """Remove cached session (e.g., after token expiry or disconnect)."""
    if user_id in _sessions and broker in _sessions[user_id]:
        del _sessions[user_id][broker]
        logger.info("session_invalidated", user=user_id, broker=broker)


async def save_broker_connection(
    conn,
    user_id: str,
    broker: str,
    access_token: str,
    broker_user_id: str = "",
    broker_user_name: str = "",
    meta: dict = None,
    token_expiry: Optional[datetime] = None,
) -> None:
    """Persist or update a broker connection after successful OAuth."""
    from core.token_crypto import encrypt_token
    import uuid
    enc_token = encrypt_token(access_token)
    conn_id = str(uuid.uuid4())

    await conn.execute("""
        INSERT INTO user_broker_connections
            (id, user_id, broker, broker_user_id, broker_user_name,
             access_token_enc, token_expiry, metadata, is_active, connected_at)
        VALUES ($1::uuid, $2::uuid, $3, $4, $5, $6, $7, $8, true, now())
        ON CONFLICT (user_id, broker)
        DO UPDATE SET
            access_token_enc  = EXCLUDED.access_token_enc,
            broker_user_id    = EXCLUDED.broker_user_id,
            broker_user_name  = EXCLUDED.broker_user_name,
            token_expiry      = EXCLUDED.token_expiry,
            metadata          = EXCLUDED.metadata,
            is_active         = true,
            connected_at      = now()
    """,
        conn_id,
        user_id,
        broker,
        broker_user_id,
        broker_user_name,
        enc_token,
        token_expiry,
        __import__("json").dumps(meta or {}),
    )
    # Invalidate stale cache entry
    invalidate_session(user_id, broker)
    logger.info("broker_connection_saved", user=user_id, broker=broker)
