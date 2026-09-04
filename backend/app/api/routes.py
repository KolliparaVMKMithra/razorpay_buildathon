from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from app.db.database import AuditLog, ReviewQueueItem, SessionLocal, TransactionScore, get_db
from app.config import settings
from app.services.redis_store import redis_status
from app.services.stream_manager import stream_manager

router = APIRouter()


@router.get("/health")
def health():
    return {
        "status": "ok",
        "service": "ringwatch",
        "redis": redis_status(),
        "telegram_configured": bool(
            settings.telegram_bot_token.strip() and settings.telegram_chat_id.strip()
        ),
    }


@router.get("/metrics/offline")
def offline_metrics():
    import json
    from pathlib import Path

    path = Path(__file__).resolve().parents[3] / "ml" / "metrics_report.json"
    if not path.exists():
        raise HTTPException(404, "metrics_report.json not found — run ml/train.py first")
    return json.loads(path.read_text(encoding="utf-8"))


@router.get("/metrics/live")
def live_metrics():
    return {
        "session_id": stream_manager.session_id,
        "running": stream_manager.running,
        "history": stream_manager.metrics_history[-200:],
        **stream_manager._live_metrics,
    }


@router.get("/drift/current")
def drift_current():
    return stream_manager.get_drift()


@router.get("/audit/{transaction_id}")
def audit_transaction(transaction_id: str, db: Session = Depends(get_db)):
    txn = db.query(TransactionScore).filter_by(transaction_id=transaction_id).first()
    if not txn:
        raise HTTPException(404, "Transaction not found")
    logs = (
        db.query(AuditLog)
        .filter_by(transaction_id=transaction_id)
        .order_by(AuditLog.created_at)
        .all()
    )
    return {
        "transaction": {
            "transaction_id": txn.transaction_id,
            "timestamp": txn.timestamp.isoformat() if txn.timestamp else None,
            "amount_inr": txn.amount_inr,
            "payment_method": txn.payment_method,
            "shipping_city": txn.shipping_city,
            "device_id": txn.device_id,
            "ip_address": txn.ip_address,
            "shipping_address_id": txn.shipping_address_id,
            "risk_score": txn.risk_score,
            "threshold_used": txn.threshold_used,
            "decision_band": txn.decision_band,
            "reasons": txn.reasons,
            "model_version": txn.model_version,
            "is_fraud": txn.is_fraud,
            "cluster_type": txn.cluster_type,
        },
        "audit_trail": [
            {
                "action": l.action,
                "actor": l.actor,
                "details": l.details,
                "created_at": l.created_at.isoformat() if l.created_at else None,
            }
            for l in logs
        ],
    }


@router.get("/dashboard/summary")
def dashboard_summary(db: Session = Depends(get_db)):
    summary = stream_manager.get_dashboard_summary()
    pending = (
        db.query(ReviewQueueItem)
        .filter(ReviewQueueItem.status == "pending")
        .count()
    )
    summary["review_queue_size"] = pending
    summary["drift"] = stream_manager.get_drift()
    return summary


@router.get("/rings")
def get_rings():
    return stream_manager.get_ring_graph()


@router.get("/review-queue")
def review_queue(db: Session = Depends(get_db)):
    q = (
        db.query(ReviewQueueItem)
        .filter(ReviewQueueItem.status == "pending")
        .order_by(ReviewQueueItem.created_at.desc())
        .limit(100)
        .all()
    )
    return [
        {
            "transaction_id": i.transaction_id,
            "risk_score": i.risk_score,
            "threshold_used": i.threshold_used,
            "reasons": i.reasons,
            "status": i.status,
            "created_at": i.created_at.isoformat() if i.created_at else None,
        }
        for i in q
    ]


@router.post("/review-queue/{transaction_id}/approve")
def approve_review(transaction_id: str, db: Session = Depends(get_db)):
    item = db.query(ReviewQueueItem).filter_by(transaction_id=transaction_id).first()
    if not item:
        raise HTTPException(404, "Not in review queue")
    now = datetime.now(timezone.utc)
    item.status = "approved"
    item.resolved_at = now
    db.add(
        AuditLog(
            transaction_id=transaction_id,
            action="review_approved",
            actor="reviewer",
            details={"note": "Human approved — no auto-block executed"},
            created_at=now,
        )
    )
    db.commit()
    return {"status": "approved", "transaction_id": transaction_id}


@router.post("/review-queue/{transaction_id}/reject")
def reject_review(transaction_id: str, db: Session = Depends(get_db)):
    item = db.query(ReviewQueueItem).filter_by(transaction_id=transaction_id).first()
    if not item:
        raise HTTPException(404, "Not in review queue")
    now = datetime.now(timezone.utc)
    item.status = "rejected"
    item.resolved_at = now
    db.add(
        AuditLog(
            transaction_id=transaction_id,
            action="review_rejected",
            actor="reviewer",
            details={"note": "Human rejected — recommended hold maintained for audit"},
            created_at=now,
        )
    )
    db.commit()
    return {"status": "rejected", "transaction_id": transaction_id}


@router.get("/stream/status")
def stream_status():
    return {
        "running": stream_manager.running,
        "paused": stream_manager.paused,
        "session_id": stream_manager.session_id,
        "index": stream_manager._index,
        "total": len(stream_manager._rows),
        "ws_clients": len(stream_manager.clients),
        **stream_manager._live_metrics,
        "history": stream_manager.metrics_history[-200:],
    }


@router.post("/stream/start")
async def start_stream(
    filename: Optional[str] = None,
    speed: float = 10.0,
    db: Session = Depends(get_db),
):
    if stream_manager.running:
        stream_manager.running = False
        await asyncio.sleep(0.2)
    count = stream_manager.load_rows(filename)
    stream_manager.session_id = str(uuid4())[:8]
    stream_manager.speed = speed
    stream_manager.running = True
    stream_manager.paused = False
    stream_manager.reset(db)

    def db_factory():
        return SessionLocal()

    asyncio.create_task(stream_manager.run_stream(db_factory))
    return {
        "status": "started",
        "session_id": stream_manager.session_id,
        "transactions": count,
        "speed": speed,
        "file": filename or "default",
    }


@router.post("/stream/pause")
def pause_stream():
    stream_manager.paused = True
    return {"status": "paused"}


@router.post("/stream/resume")
def resume_stream():
    stream_manager.paused = False
    return {"status": "resumed"}


@router.post("/stream/reset")
def reset_stream(db: Session = Depends(get_db)):
    stream_manager.running = False
    stream_manager.reset(db)
    return {"status": "reset", "session_id": stream_manager.session_id}


@router.websocket("/ws/stream")
async def websocket_stream(websocket: WebSocket):
    await websocket.accept()
    stream_manager.clients.add(websocket)
    try:
        await websocket.send_json(
            {
                "type": "connected",
                "session_id": stream_manager.session_id,
                "metrics": stream_manager._live_metrics,
            }
        )
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        stream_manager.clients.discard(websocket)
