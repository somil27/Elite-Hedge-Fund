"""
FastAPI application — REST API for the trading system.
"""
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, HTTPException, BackgroundTasks, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import asyncio
import json
from prometheus_client import make_asgi_app

from core.config import settings
from db.database import engine
from db.models import Base, TradeCycle, HumanReview
from db.database import AsyncSessionLocal
from graph.trading_graph import trading_graph
from broker.registry import get_portfolio_snapshot
from api.broker_router import router as broker_router
from api.indian_router import router as indian_router
from api.phase12_router import router as phase12_router
from api.auth_router import router as auth_router
import structlog

logger = structlog.get_logger()

# WebSocket connections for live updates
ws_clients: list[WebSocket] = []


from sqlalchemy import text

import redis.asyncio as redis

redis_listener_task = None

async def listen_to_redis_broadcasts():
    try:
        r = redis.from_url(settings.redis_url)
        pubsub = r.pubsub()
        await pubsub.subscribe("trading_updates")
        async for message in pubsub.listen():
            if message["type"] == "message":
                data = json.loads(message["data"])
                await broadcast(data)
    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.error("redis_listener_error", error=str(e))
    finally:
        if 'pubsub' in locals():
            await pubsub.unsubscribe("trading_updates")
        if 'r' in locals():
            await r.aclose()

@asynccontextmanager
async def lifespan(app: FastAPI):
    global redis_listener_task
    # Create tables (use Alembic in production)
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.execute(text('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"'))
        
        # Check if the existing embedding column is a JSON type from a previous run
        try:
            result = await conn.execute(text("""
                SELECT data_type FROM information_schema.columns 
                WHERE table_name = 'agent_memories' AND column_name = 'embedding'
            """))
            row = result.fetchone()
            if row and row[0] in ('json', 'jsonb', 'user-defined'):
                if row[0] in ('json', 'jsonb'):
                    logger.info("dropping_agent_memories_table_to_convert_to_vector")
                    await conn.execute(text("DROP TABLE agent_memories CASCADE"))
        except Exception as e:
            logger.warning("check_embedding_column_failed", error=str(e))
            
        await conn.run_sync(Base.metadata.create_all)
    
    redis_listener_task = asyncio.create_task(listen_to_redis_broadcasts())
    logger.info("app_startup")
    yield
    if redis_listener_task:
        redis_listener_task.cancel()
    await engine.dispose()
    logger.info("app_shutdown")


app = FastAPI(
    title="AlphaDesk",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=".*",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(broker_router, tags=["Broker"])
app.include_router(indian_router, tags=["Indian Market"])
app.include_router(phase12_router, tags=["Phase12"])
app.include_router(auth_router, prefix="/api/auth", tags=["Authentication"])

# Prometheus Metrics
metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)


# ── Request/Response Models ──────────────────────────────

class StartCycleRequest(BaseModel):
    mode: str = "short_term"      # short_term | long_term
    auto_mode: bool = False
    market: str = "us"            # "us" | "india"
    indian_broker: str = "zerodha"  # "zerodha" | "upstox" (ignored when market="us")
    user_id: str = "00000000-0000-0000-0000-000000000001"  # for indian broker auth
    portfolio_id: Optional[str] = None
    strategy: Optional[str] = None
    capital_budget: Optional[float] = None


class HumanDecisionRequest(BaseModel):
    decision: str  # approved | rejected | resized
    override_weight: Optional[float] = None
    notes: Optional[str] = None


# ── Active cycles store (in-memory for demo; use Redis in prod) ──
active_cycles: dict[str, dict] = {}


async def broadcast(event: dict):
    """Send event to all WebSocket clients."""
    msg = json.dumps(event)
    disconnected = []
    for ws in ws_clients:
        try:
            await ws.send_text(msg)
        except Exception:
            disconnected.append(ws)
    for ws in disconnected:
        ws_clients.remove(ws)


async def run_cycle_background(cycle_id: str, initial_state: dict):
    """Run the trading graph in the background."""
    try:
        await broadcast({"event": "cycle_started", "cycle_id": cycle_id,
                         "mode": initial_state.get("mode")})

        result = await trading_graph.ainvoke(initial_state)
        active_cycles[cycle_id] = result

        await broadcast({
            "event": "cycle_update",
            "cycle_id": cycle_id,
            "status": result.get("final_status"),
            "awaiting_human": result.get("awaiting_human", False),
            "symbol": result.get("order", {}).get("symbol") if result.get("order") else None,
        })

        if result.get("awaiting_human"):
            # Persist human review to DB
            async with AsyncSessionLocal() as db:
                review_req = result.get("review_request", {})
                review = HumanReview(
                    id=uuid.UUID(review_req.get("request_id", str(uuid.uuid4()))),
                    cycle_id=uuid.UUID(cycle_id),
                    proposal_data=review_req.get("proposal", {}),
                    technical_data=review_req.get("technical", {}),
                    risk_data=review_req.get("risk", {}),
                    estimated_notional=review_req.get("estimated_notional", 0),
                    status="pending",
                    expires_at=datetime.fromisoformat(
                        review_req.get("expires_at", datetime.utcnow().isoformat())
                    ),
                )
                db.add(review)
                await db.commit()

        logger.info("cycle_complete", cycle_id=cycle_id,
                    status=result.get("final_status"))
    except Exception as e:
        logger.error("cycle_error", cycle_id=cycle_id, error=str(e))
        await broadcast({"event": "cycle_error", "cycle_id": cycle_id, "error": str(e)})


# ── Endpoints ────────────────────────────────────────────

@app.post("/api/cycles/start")
async def start_cycle(req: StartCycleRequest, background_tasks: BackgroundTasks):
    """Start a new trading cycle using BackgroundTasks."""
    cycle_id = str(uuid.uuid4())

    # Persist cycle to DB
    async with AsyncSessionLocal() as db:
        cycle = TradeCycle(
            id=uuid.UUID(cycle_id),
            mode=req.mode,
            status="running",
            cio_mandate={"portfolio_id": req.portfolio_id} if req.portfolio_id else {},
            auto_mode=req.auto_mode,
        )
        db.add(cycle)
        await db.commit()

    initial_state = {
        "cycle_id":        cycle_id,
        "mode":            req.mode,
        "auto_mode":       req.auto_mode,
        "market":          req.market,
        "indian_broker":   req.indian_broker,
        "user_id":         req.user_id,
        "portfolio_id":    req.portfolio_id,
        "strategy_override": req.strategy,
        "capital_budget":  req.capital_budget,
        "mandate":         {},
        "fundamentals":    [],
        "quant_signals":   [],
        "proposals":       [],
        "technical_assessments": [],
        "risk_assessments":      [],
        "compliance_flags":      [],
        "errors":          [],
        "final_status":    "running",
        "past_similar_trades": [],
        "agent_reflections":   {},
        "regime_history":      [],
        "portfolio_snapshot":  {},
    }

    background_tasks.add_task(run_cycle_background, cycle_id, initial_state)
    
    return {"cycle_id": cycle_id, "status": "started", "mode": req.mode, "market": req.market}


@app.get("/api/cycles/{cycle_id}")
async def get_cycle(cycle_id: str):
    """Get current state of a cycle."""
    state = active_cycles.get(cycle_id)
    if not state:
        async with AsyncSessionLocal() as db:
            from sqlalchemy import select
            result = await db.execute(
                select(TradeCycle).where(TradeCycle.id == uuid.UUID(cycle_id))
            )
            cycle = result.scalar_one_or_none()
            if not cycle:
                raise HTTPException(404, "Cycle not found")
            return {
                "cycle_id": str(cycle.id),
                "mode": cycle.mode,
                "status": cycle.status,
                "auto_mode": cycle.auto_mode,
                "started_at": cycle.started_at.isoformat() if cycle.started_at else None,
            }
    return {
        "cycle_id": cycle_id,
        "mode": state.get("mode"),
        "status": state.get("final_status"),
        "mandate": state.get("mandate"),
        "market_intel": state.get("market_intel"),
        "proposals": state.get("proposals", []),
        "risk_assessments": state.get("risk_assessments", []),
        "execution_report": state.get("execution_report"),
        "awaiting_human": state.get("awaiting_human", False),
        "review_request": state.get("review_request"),
        "compliance_flags": state.get("compliance_flags", []),
        "errors": state.get("errors", []),
    }


@app.get("/api/cycles")
async def list_cycles(limit: int = 20):
    """List recent trading cycles."""
    async with AsyncSessionLocal() as db:
        from sqlalchemy import select
        result = await db.execute(
            select(TradeCycle).order_by(TradeCycle.started_at.desc()).limit(limit)
        )
        cycles = result.scalars().all()
        return [
            {
                "cycle_id": str(c.id),
                "mode": c.mode,
                "status": c.status,
                "auto_mode": c.auto_mode,
                "started_at": c.started_at.isoformat() if c.started_at else None,
                "completed_at": c.completed_at.isoformat() if c.completed_at else None,
            }
            for c in cycles
        ]


@app.get("/api/cycles/{cycle_id}/review")
async def get_pending_review(cycle_id: str):
    """Get the pending human review for a cycle."""
    async with AsyncSessionLocal() as db:
        from sqlalchemy import select
        result = await db.execute(
            select(HumanReview)
            .where(HumanReview.cycle_id == uuid.UUID(cycle_id))
            .where(HumanReview.status == "pending")
        )
        review = result.scalar_one_or_none()
        if not review:
            raise HTTPException(404, "No pending review")
        return {
            "review_id": str(review.id),
            "cycle_id": cycle_id,
            "proposal": review.proposal_data,
            "technical": review.technical_data,
            "risk": review.risk_data,
            "estimated_notional": review.estimated_notional,
            "expires_at": review.expires_at.isoformat(),
            "status": review.status,
        }


@app.post("/api/cycles/{cycle_id}/decide")
async def submit_human_decision(
    cycle_id: str,
    req: HumanDecisionRequest,
    background_tasks: BackgroundTasks,
):
    """Submit a human approval/rejection decision."""
    state = active_cycles.get(cycle_id)
    if not state:
        raise HTTPException(404, "Cycle not in active state")
    if not state.get("awaiting_human"):
        raise HTTPException(400, "Cycle is not awaiting human decision")

    # Update DB review record
    async with AsyncSessionLocal() as db:
        from sqlalchemy import select
        result = await db.execute(
            select(HumanReview)
            .where(HumanReview.cycle_id == uuid.UUID(cycle_id))
            .where(HumanReview.status == "pending")
        )
        review = result.scalar_one_or_none()
        if review:
            review.status = req.decision
            review.decision = req.decision
            review.override_weight = req.override_weight
            review.notes = req.notes
            review.decided_at = datetime.utcnow()
            await db.commit()

    # Inject decision into state and resume graph
    state["human_decision"] = {
        "decision": req.decision,
        "override_weight": req.override_weight,
        "notes": req.notes,
        "decided_by": "human",
        "cycle_id": cycle_id,
    }
    state["awaiting_human"] = False

    if req.decision in ("approved", "resized"):
        background_tasks.add_task(resume_after_human, cycle_id, state)
    else:
        state["final_status"] = "rejected"
        await broadcast({"event": "cycle_update", "cycle_id": cycle_id,
                         "status": "rejected"})

    return {"status": "decision_recorded", "decision": req.decision}


async def resume_after_human(cycle_id: str, state: dict):
    """Resume the graph from execution after human approves."""
    from agents.execution import ExecutionAgent
    from agents.post_trade import ComplianceAgent, PortfolioMonitorAgent, ReportingAgent
    from db.database import get_raw_connection

    conn = await get_raw_connection()
    try:
        exec_agent = ExecutionAgent()
        exec_result = await exec_agent.run(state, conn)
        state.update(exec_result)

        results = await asyncio.gather(
            ComplianceAgent().run(state, conn),
            PortfolioMonitorAgent().run(state, conn),
            ReportingAgent().run(state, conn),
            return_exceptions=True,
        )
        for r in results:
            if not isinstance(r, Exception):
                state.update(r)

        active_cycles[cycle_id] = state
        await broadcast({
            "event": "cycle_update",
            "cycle_id": cycle_id,
            "status": state.get("final_status"),
            "execution_report": state.get("execution_report"),
        })
    finally:
        await conn.close()


@app.get("/api/portfolio")
async def get_portfolio():
    """Get current portfolio snapshot from broker."""
    return await get_portfolio_snapshot()


@app.get("/api/trades")
async def list_trades(limit: int = 50):
    """List completed trade outcomes."""
    async with AsyncSessionLocal() as db:
        from sqlalchemy import select
        from db.models import TradeOutcome
        result = await db.execute(
            select(TradeOutcome).order_by(TradeOutcome.opened_at.desc()).limit(limit)
        )
        trades = result.scalars().all()
        return [
            {
                "id": str(t.id),
                "cycle_id": str(t.cycle_id),
                "symbol": t.symbol,
                "direction": t.direction,
                "entry_price": t.entry_price,
                "exit_price": t.exit_price,
                "qty": t.qty,
                "pnl_realized": t.pnl_realized,
                "pnl_pct": t.pnl_pct,
                "human_decision": t.human_decision,
                "close_reason": t.close_reason,
                "opened_at": t.opened_at.isoformat() if t.opened_at else None,
                "closed_at": t.closed_at.isoformat() if t.closed_at else None,
            }
            for t in trades
        ]


@app.get("/api/health")
async def health():
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat()}


@app.get("/api/provider")
async def get_provider():
    """Returns which LLM provider and models are active."""
    from core.llm import detect_provider, MODEL_MAP
    try:
        provider = detect_provider()
        models   = MODEL_MAP.get(provider, {})
        return {
            "provider":     provider,
            "strong_model": models.get("strong"),
            "fast_model":   models.get("fast"),
            "embed_model":  models.get("embed"),
            "has_native_embeddings": models.get("embed") is not None,
        }
    except RuntimeError as e:
        return {"error": str(e), "provider": None}


# ── WebSocket ────────────────────────────────────────────

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    ws_clients.append(websocket)
    try:
        while True:
            await websocket.receive_text()   # keep alive
    except WebSocketDisconnect:
        ws_clients.remove(websocket)
