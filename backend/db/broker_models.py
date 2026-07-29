"""
ORM models for broker_orders and order_fills tables.
Extend the existing db/models.py.
"""
from sqlalchemy import Column, String, Float, DateTime, Text, ForeignKey, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.sql import func
from db.database import Base
import uuid


class BrokerOrder(Base):
    __tablename__ = "broker_orders"

    id              = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("uuid_generate_v4()"))
    broker_order_id = Column(String(100), nullable=False, unique=True)
    cycle_id        = Column(PGUUID(as_uuid=True), ForeignKey("trade_cycles.id"), nullable=True)
    symbol          = Column(String(20), nullable=False)
    side            = Column(String(10), nullable=False)
    order_type      = Column(String(20), nullable=False)
    qty             = Column(Float, nullable=False)
    filled_qty      = Column(Float, default=0)
    limit_price     = Column(Float, nullable=True)
    stop_price      = Column(Float, nullable=True)
    avg_fill_price  = Column(Float, nullable=True)
    status          = Column(String(20), default="pending")
    algo            = Column(String(20), nullable=True)
    slippage_bps    = Column(Float, nullable=True)
    source          = Column(String(20), default="agent")   # agent | manual | stop_loss
    time_in_force   = Column(String(10), default="day")
    reject_reason   = Column(Text, nullable=True)
    submitted_at    = Column(DateTime(timezone=True), server_default=func.now())
    filled_at       = Column(DateTime(timezone=True), nullable=True)
    cancelled_at    = Column(DateTime(timezone=True), nullable=True)


class OrderFill(Base):
    __tablename__ = "order_fills"

    id              = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("uuid_generate_v4()"))
    broker_order_id = Column(String(100), ForeignKey("broker_orders.broker_order_id"), nullable=False)
    fill_id         = Column(String(100), nullable=False, unique=True)
    symbol          = Column(String(20), nullable=False)
    side            = Column(String(10), nullable=False)
    qty             = Column(Float, nullable=False)
    price           = Column(Float, nullable=False)
    commission      = Column(Float, default=0)
    filled_at       = Column(DateTime(timezone=True), server_default=func.now())
