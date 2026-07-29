from sqlalchemy import Column, String, Float, Boolean, DateTime, Text, ForeignKey, JSON, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.sql import func
from db.database import Base
import uuid


class TradeCycle(Base):
    __tablename__ = "trade_cycles"

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("uuid_generate_v4()"))
    mode = Column(String(20), nullable=False)
    status = Column(String(30), nullable=False, default="running")
    cio_mandate = Column(JSON, nullable=False)
    auto_mode = Column(Boolean, default=False)
    started_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)


from sqlalchemy.types import UserDefinedType

class Vector(UserDefinedType):
    def __init__(self, dimensions: int = 1536):
        self.dimensions = dimensions

    def get_col_spec(self, **kw):
        return f"vector({self.dimensions})"

class AgentMemory(Base):
    __tablename__ = "agent_memories"

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("uuid_generate_v4()"))
    agent_id = Column(String(50), nullable=False, index=True)
    cycle_id = Column(PGUUID(as_uuid=True), ForeignKey("trade_cycles.id"), nullable=True)
    memory_type = Column(String(20), nullable=False)
    # 'observation' | 'analysis' | 'reflection' | 'signal'
    content = Column(Text, nullable=False)
    embedding = Column(Vector(1536), nullable=True)
    importance_score = Column(Float, default=0.5)
    metadata_ = Column("metadata", JSON, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    expires_at = Column(DateTime(timezone=True), nullable=True)


class TradeOutcome(Base):
    __tablename__ = "trade_outcomes"

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("uuid_generate_v4()"))
    cycle_id = Column(PGUUID(as_uuid=True), ForeignKey("trade_cycles.id"), nullable=False)
    symbol = Column(String(20), nullable=False)
    direction = Column(String(10), nullable=False)
    entry_price = Column(Float, nullable=False)
    exit_price = Column(Float, nullable=True)
    qty = Column(Float, nullable=False)
    pnl_realized = Column(Float, nullable=True)
    pnl_pct = Column(Float, nullable=True)
    agent_signals = Column(JSON, nullable=False)
    human_decision = Column(String(20), nullable=True)
    close_reason = Column(String(50), nullable=True)
    opened_at = Column(DateTime(timezone=True), server_default=func.now())
    closed_at = Column(DateTime(timezone=True), nullable=True)


class HumanReview(Base):
    __tablename__ = "human_reviews"

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("uuid_generate_v4()"))
    cycle_id = Column(PGUUID(as_uuid=True), ForeignKey("trade_cycles.id"), nullable=False)
    proposal_data = Column(JSON, nullable=False)
    technical_data = Column(JSON, nullable=False)
    risk_data = Column(JSON, nullable=False)
    estimated_notional = Column(Float, nullable=False)
    status = Column(String(20), default="pending")   # pending | approved | rejected | resized | expired
    decision = Column(String(20), nullable=True)
    override_weight = Column(Float, nullable=True)
    notes = Column(Text, nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    decided_at = Column(DateTime(timezone=True), nullable=True)
