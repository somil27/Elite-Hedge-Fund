from sqlalchemy import Column, String, Float, Boolean, DateTime, Text, ForeignKey, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID, JSONB
from sqlalchemy.sql import func
from db.database import Base
import uuid


class User(Base):
    __tablename__ = "users"
    id              = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("uuid_generate_v4()"))
    email           = Column(String(255), nullable=False, unique=True)
    hashed_password = Column(String(255), nullable=False)
    name            = Column(String(255), nullable=True)
    created_at      = Column(DateTime(timezone=True), server_default=func.now())
    last_login      = Column(DateTime(timezone=True), nullable=True)
    is_active       = Column(Boolean, default=True)


class UserBrokerConnection(Base):
    __tablename__ = "user_broker_connections"
    id                = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("uuid_generate_v4()"))
    user_id           = Column(PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    broker            = Column(String(20), nullable=False)   # zerodha|upstox|alpaca
    broker_user_id    = Column(String(100), nullable=True)
    broker_user_name  = Column(String(255), nullable=True)
    access_token_enc  = Column(Text, nullable=True)
    refresh_token_enc = Column(Text, nullable=True)
    token_expiry      = Column(DateTime(timezone=True), nullable=True)
    is_active         = Column(Boolean, default=True)
    connected_at      = Column(DateTime(timezone=True), server_default=func.now())
    last_synced       = Column(DateTime(timezone=True), nullable=True)
    metadata_         = Column("metadata", JSONB, default=dict)


class PortfolioSnapshot(Base):
    __tablename__ = "portfolio_snapshots"
    id              = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("uuid_generate_v4()"))
    user_id         = Column(PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    broker          = Column(String(20), nullable=False)
    total_value     = Column(Float, nullable=False)
    cash            = Column(Float, nullable=False)
    invested_value  = Column(Float, nullable=False)
    day_pnl         = Column(Float, default=0)
    overall_pnl     = Column(Float, default=0)
    overall_pnl_pct = Column(Float, default=0)
    holdings_json   = Column(JSONB, default=list)
    positions_json  = Column(JSONB, default=list)
    snapped_at      = Column(DateTime(timezone=True), server_default=func.now())


class PortfolioAlert(Base):
    __tablename__ = "portfolio_alerts"
    id           = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("uuid_generate_v4()"))
    user_id      = Column(PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    broker       = Column(String(20), nullable=False)
    symbol       = Column(String(50), nullable=False)
    alert_type   = Column(String(30), nullable=False)
    threshold    = Column(Float, nullable=True)
    message      = Column(Text, nullable=False)
    is_read      = Column(Boolean, default=False)
    triggered_at = Column(DateTime(timezone=True), server_default=func.now())
    metadata_    = Column("metadata", JSONB, default=dict)
