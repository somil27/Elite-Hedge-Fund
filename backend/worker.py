import asyncio
import json
import redis.asyncio as redis
from celery import Celery
from core.config import settings

# Initialize Celery app
celery_app = Celery(
    "trading_worker",
    broker=settings.redis_url,
    backend=settings.redis_url
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
)

async def _publish_to_redis(message: dict):
    # Using a short-lived connection just for publishing
    client = redis.from_url(settings.redis_url)
    await client.publish("trading_updates", json.dumps(message))
    await client.aclose()

async def async_run_cycle(cycle_id: str, initial_state: dict):
    from graph.trading_graph import trading_graph
    from db.database import AsyncSessionLocal
    from db.models import HumanReview
    
    try:
        await _publish_to_redis({
            "event": "cycle_started", 
            "cycle_id": cycle_id,
            "mode": initial_state.get("mode")
        })

        result = await trading_graph.ainvoke(initial_state)

        await _publish_to_redis({
            "event": "cycle_update",
            "cycle_id": cycle_id,
            "status": result.get("final_status"),
            "awaiting_human": result.get("awaiting_human", False),
            "symbol": result.get("order", {}).get("symbol") if result.get("order") else None,
        })

        if result.get("awaiting_human"):
            # Persist human review to DB
            async with AsyncSessionLocal() as db:
                review = HumanReview(
                    cycle_id=cycle_id,
                    proposal_data=result.get("trade_proposal"),
                    technical_data=result.get("technical_assessment"),
                    risk_data=result.get("risk_assessment"),
                    estimated_notional=result.get("order", {}).get("qty", 0) * result.get("order", {}).get("limit_price", 0)
                )
                db.add(review)
                await db.commit()
                
    except Exception as e:
        import traceback
        await _publish_to_redis({
            "event": "cycle_error",
            "cycle_id": cycle_id,
            "error": str(e)
        })
        print(f"Error in cycle {cycle_id}: {e}")
        traceback.print_exc()


@celery_app.task(name="worker.run_cycle_task")
def run_cycle_task(cycle_id: str, initial_state: dict):
    """
    Synchronous Celery task wrapper that runs the async trading cycle.
    """
    asyncio.run(async_run_cycle(cycle_id, initial_state))
