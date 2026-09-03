from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Float,
    Integer,
    String,
    Text,
    create_engine,
)
from sqlalchemy.orm import declarative_base, sessionmaker

from app.config import settings

engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class TransactionScore(Base):
    __tablename__ = "transaction_scores"

    id = Column(Integer, primary_key=True, autoincrement=True)
    transaction_id = Column(String(64), unique=True, index=True, nullable=False)
    timestamp = Column(DateTime, nullable=False)
    user_id = Column(String(64))
    device_id = Column(String(64), index=True)
    ip_address = Column(String(64), index=True)
    amount_inr = Column(Float)
    payment_method = Column(String(32))
    merchant_category = Column(String(64))
    shipping_city = Column(String(64))
    shipping_address_id = Column(String(64), index=True)
    is_fraud = Column(Integer)  # ground truth, not shown to detector
    cluster_type = Column(String(64))

    risk_score = Column(Float)
    threshold_used = Column(Float)
    decision_band = Column(String(16))  # allow | review | flagged
    flagged = Column(Boolean, default=False)
    reasons = Column(JSON)
    model_version = Column(String(32))
    session_id = Column(String(64), index=True)
    scored_at = Column(DateTime)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    transaction_id = Column(String(64), index=True, nullable=False)
    action = Column(String(32))  # scored | review_approved | review_rejected
    actor = Column(String(64), default="system")
    details = Column(JSON)
    created_at = Column(DateTime)


class ReviewQueueItem(Base):
    __tablename__ = "review_queue"

    id = Column(Integer, primary_key=True, autoincrement=True)
    transaction_id = Column(String(64), unique=True, index=True)
    risk_score = Column(Float)
    threshold_used = Column(Float)
    reasons = Column(JSON)
    status = Column(String(16), default="pending")  # pending | approved | rejected
    session_id = Column(String(64), index=True)
    created_at = Column(DateTime)
    resolved_at = Column(DateTime, nullable=True)


class DriftSnapshot(Base):
    __tablename__ = "drift_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(64), index=True)
    aggregate_psi = Column(Float)
    per_feature_psi = Column(JSON)
    is_drifting = Column(Boolean)
    created_at = Column(DateTime)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    Base.metadata.create_all(bind=engine)
