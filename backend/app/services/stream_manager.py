from __future__ import annotations

import json
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sqlalchemy.orm import Session

from app.config import settings
from app.db.database import AuditLog, DriftSnapshot, ReviewQueueItem, TransactionScore
from app.ml_bridge import FEATURE_COLUMNS, compute_psi_report, load_baseline
from app.services.scorer import Scorer
from app.services.redis_store import record_event, redis_status
from app.services.telegram import send_telegram_alert


def _json_safe(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    if isinstance(value, (np.integer, np.floating)):
        return float(value)
    if isinstance(value, np.bool_):
        return bool(value)
    return value


class StreamManager:
    def __init__(self) -> None:
        self.scorer = Scorer()
        self.session_id: str | None = None
        self.running = False
        self.paused = False
        self.speed = 10.0
        self.clients: set = set()
        self.feature_buffer: list[dict] = []
        self.metrics_history: list[dict] = []
        self._task = None
        self._rows: list[dict] = []
        self._index = 0
        self._live_metrics = {
            "precision": 0.0,
            "recall": 0.0,
            "f1": 0.0,
            "fraud_prevented_inr": 0.0,
            "false_positive_cost_inr": 0.0,
            "processed": 0,
            "tp": 0,
            "fp": 0,
            "fn": 0,
            "tn": 0,
        }
        self.flagged_txns: list[str] = []
        self.ring_nodes: dict[str, dict] = {}
        self.ring_edges: list[dict] = []
        self.decision_counts = {"allow": 0, "review": 0, "flagged": 0}
        self.pattern_counts: dict[str, int] = defaultdict(int)
        self.entity_stats: dict[str, dict] = {}
        self.recent_high_risk: list[dict] = []
        self.session_fraud_total = 0
        self.session_fraud_caught = 0
        self.total_volume_inr = 0.0
        self.flagged_volume_inr = 0.0

    def get_dashboard_summary(self) -> dict:
        entities = []
        for key, s in self.entity_stats.items():
            entities.append(
                {
                    "key": key,
                    "type": s["type"],
                    "id": s["id"],
                    "txn_count": s["txn_count"],
                    "user_count": len(s["users"]),
                    "total_inr": round(s["total_inr"], 2),
                    "max_risk": round(s["max_risk"], 4),
                    "patterns": sorted(s["patterns"]),
                }
            )
        entities.sort(key=lambda e: (-e["max_risk"], -e["txn_count"]))

        m = self._live_metrics
        fraud_rate = (
            round(self.session_fraud_caught / self.session_fraud_total, 4)
            if self.session_fraud_total
            else 0.0
        )
        return {
            "session_id": self.session_id,
            "running": self.running,
            "processed": m["processed"],
            "decision_counts": dict(self.decision_counts),
            "pattern_counts": dict(self.pattern_counts),
            "confusion": {"tp": m["tp"], "fp": m["fp"], "fn": m["fn"], "tn": m["tn"]},
            "precision": m["precision"],
            "recall": m["recall"],
            "f1": m["f1"],
            "fraud_prevented_inr": m["fraud_prevented_inr"],
            "false_positive_cost_inr": m["false_positive_cost_inr"],
            "total_volume_inr": round(self.total_volume_inr, 2),
            "flagged_volume_inr": round(self.flagged_volume_inr, 2),
            "session_fraud_total": self.session_fraud_total,
            "session_fraud_caught": self.session_fraud_caught,
            "session_fraud_rate": fraud_rate,
            "top_entities": entities[:20],
            "recent_high_risk": self.recent_high_risk[-30:],
            "flagged_count": len(self.flagged_txns),
        }

    def _track_session_analytics(self, row: dict, result: dict) -> None:
        band = result["decision_band"]
        self.decision_counts[band] = self.decision_counts.get(band, 0) + 1
        amount = float(row.get("amount_inr", 0))
        self.total_volume_inr += amount
        if band in ("review", "flagged"):
            self.flagged_volume_inr += amount

        is_fraud = int(row.get("is_fraud", 0))
        if is_fraud:
            self.session_fraud_total += 1
            if band in ("review", "flagged"):
                self.session_fraud_caught += 1
                ctype = row.get("cluster_type") or "unknown"
                if ctype.startswith("fraud_"):
                    self.pattern_counts[ctype] += 1

        if band in ("review", "flagged"):
            entry = {
                "transaction_id": row["transaction_id"],
                "amount_inr": amount,
                "risk_score": result["risk_score"],
                "threshold_used": result["threshold_used"],
                "decision_band": band,
                "reasons": result["reasons"],
                "device_id": row["device_id"],
                "ip_address": row["ip_address"],
                "shipping_address_id": row["shipping_address_id"],
                "is_fraud": is_fraud,
                "cluster_type": row.get("cluster_type"),
                "timestamp": row["timestamp"].isoformat()
                if hasattr(row["timestamp"], "isoformat")
                else str(row["timestamp"]),
            }
            self.recent_high_risk.append(entry)
            if len(self.recent_high_risk) > 50:
                self.recent_high_risk = self.recent_high_risk[-50:]

            for etype, eid, key in [
                ("device", row["device_id"], f"device:{row['device_id']}"),
                ("ip", row["ip_address"], f"ip:{row['ip_address']}"),
                ("address", row["shipping_address_id"], f"addr:{row['shipping_address_id']}"),
            ]:
                if key not in self.entity_stats:
                    self.entity_stats[key] = {
                        "type": etype,
                        "id": eid,
                        "txn_count": 0,
                        "users": set(),
                        "total_inr": 0.0,
                        "max_risk": 0.0,
                        "patterns": set(),
                    }
                s = self.entity_stats[key]
                s["txn_count"] += 1
                s["users"].add(row["user_id"])
                s["total_inr"] += amount
                s["max_risk"] = max(s["max_risk"], result["risk_score"])
                ctype = row.get("cluster_type")
                if ctype and ctype.startswith("fraud_"):
                    s["patterns"].add(ctype)

    def _data_path(self, filename: str | None = None) -> Path:
        data_dir = Path(settings.data_dir)
        if not data_dir.is_absolute():
            data_dir = Path(__file__).resolve().parents[2] / data_dir
        return data_dir / (filename or settings.stream_default_file)

    def load_rows(self, filename: str | None = None) -> int:
        path = self._data_path(filename)
        df = pd.read_csv(path, parse_dates=["timestamp"])
        df = df.sort_values("timestamp")
        self._rows = df.to_dict(orient="records")
        for r in self._rows:
            if hasattr(r["timestamp"], "to_pydatetime"):
                r["timestamp"] = r["timestamp"].to_pydatetime()
        return len(self._rows)

    def reset(self, db: Session) -> None:
        self.scorer.reset()
        self._index = 0
        self.feature_buffer.clear()
        self.metrics_history.clear()
        self.flagged_txns.clear()
        self.ring_nodes.clear()
        self.ring_edges.clear()
        self.decision_counts = {"allow": 0, "review": 0, "flagged": 0}
        self.pattern_counts.clear()
        self.entity_stats.clear()
        self.recent_high_risk.clear()
        self.session_fraud_total = 0
        self.session_fraud_caught = 0
        self.total_volume_inr = 0.0
        self.flagged_volume_inr = 0.0
        self._live_metrics = {
            "precision": 0.0,
            "recall": 0.0,
            "f1": 0.0,
            "fraud_prevented_inr": 0.0,
            "false_positive_cost_inr": 0.0,
            "processed": 0,
            "tp": 0,
            "fp": 0,
            "fn": 0,
            "tn": 0,
        }
        db.query(ReviewQueueItem).filter(ReviewQueueItem.status == "pending").delete(
            synchronize_session=False
        )
        db.commit()

    def _update_live_metrics(self, row: dict, result: dict) -> None:
        y = int(row.get("is_fraud", 0))
        flagged = result["decision_band"] in ("review", "flagged")
        m = self._live_metrics
        m["processed"] += 1
        amount = float(row.get("amount_inr", 0))
        if flagged and y == 1:
            m["tp"] += 1
            m["fraud_prevented_inr"] += amount
        elif flagged and y == 0:
            m["fp"] += 1
            m["false_positive_cost_inr"] += amount
        elif not flagged and y == 1:
            m["fn"] += 1
        else:
            m["tn"] += 1
        prec_denom = m["tp"] + m["fp"]
        rec_denom = m["tp"] + m["fn"]
        m["precision"] = round(m["tp"] / prec_denom, 4) if prec_denom else 0.0
        m["recall"] = round(m["tp"] / rec_denom, 4) if rec_denom else 0.0
        p, r = m["precision"], m["recall"]
        m["f1"] = round(2 * p * r / (p + r), 4) if (p + r) else 0.0
        self.metrics_history.append(
            {
                "processed": m["processed"],
                "precision": m["precision"],
                "recall": m["recall"],
                "f1": m["f1"],
            }
        )

    def _update_ring_graph(self, row: dict, result: dict) -> None:
        if not result["flagged"]:
            return
        txn_id = row["transaction_id"]
        self.flagged_txns.append(txn_id)
        entities = {
            f"device:{row['device_id']}": {"type": "device", "id": row["device_id"]},
            f"ip:{row['ip_address']}": {"type": "ip", "id": row["ip_address"]},
            f"addr:{row['shipping_address_id']}": {"type": "address", "id": row["shipping_address_id"]},
            f"user:{row['user_id']}": {"type": "user", "id": row["user_id"]},
        }
        for key, node in entities.items():
            node["risk"] = max(node.get("risk", 0), result["risk_score"])
            node["flagged"] = True
            self.ring_nodes[key] = node
        keys = list(entities.keys())
        for i in range(len(keys)):
            for j in range(i + 1, len(keys)):
                self.ring_edges.append(
                    {"source": keys[i], "target": keys[j], "transaction_id": txn_id}
                )

    def _persist(self, db: Session, row: dict, result: dict) -> None:
        now = datetime.now(timezone.utc)
        existing = db.query(TransactionScore).filter_by(transaction_id=row["transaction_id"]).first()
        if existing:
            record = existing
        else:
            record = TransactionScore(transaction_id=row["transaction_id"])
            db.add(record)
        record.timestamp = row["timestamp"]
        record.user_id = row["user_id"]
        record.device_id = row["device_id"]
        record.ip_address = row["ip_address"]
        record.amount_inr = float(row["amount_inr"])
        record.payment_method = row.get("payment_method")
        record.merchant_category = row.get("merchant_category")
        record.shipping_city = row.get("shipping_city")
        record.shipping_address_id = row["shipping_address_id"]
        record.is_fraud = int(row.get("is_fraud", 0))
        record.cluster_type = row.get("cluster_type")
        record.risk_score = result["risk_score"]
        record.threshold_used = result["threshold_used"]
        record.decision_band = result["decision_band"]
        record.flagged = result["flagged"]
        record.reasons = result["reasons"]
        record.model_version = result["model_version"]
        record.session_id = self.session_id
        record.scored_at = now
        db.add(
            AuditLog(
                transaction_id=row["transaction_id"],
                action="scored",
                actor="system",
                details={
                    "risk_score": result["risk_score"],
                    "threshold_used": result["threshold_used"],
                    "decision_band": result["decision_band"],
                    "reasons": result["reasons"],
                    "model_version": result["model_version"],
                },
                created_at=now,
            )
        )
        if result["decision_band"] == "review":
            item = db.query(ReviewQueueItem).filter_by(transaction_id=row["transaction_id"]).first()
            if item:
                item.risk_score = result["risk_score"]
                item.threshold_used = result["threshold_used"]
                item.reasons = result["reasons"]
                item.status = "pending"
                item.session_id = self.session_id
                item.created_at = now
                item.resolved_at = None
            else:
                db.add(
                    ReviewQueueItem(
                        transaction_id=row["transaction_id"],
                        risk_score=result["risk_score"],
                        threshold_used=result["threshold_used"],
                        reasons=result["reasons"],
                        status="pending",
                        session_id=self.session_id,
                        created_at=now,
                    )
                )
        db.commit()

    async def _broadcast(self, message: dict) -> None:
        dead = set()
        for ws in self.clients:
            try:
                await ws.send_json(message)
            except Exception:
                dead.add(ws)
        self.clients -= dead

    def get_drift(self) -> dict:
        if len(self.feature_buffer) < 50:
            return {"aggregate_psi": 0.0, "per_feature_psi": {}, "is_drifting": False, "threshold": 0.2}
        baseline_path = Path(settings.model_dir) / "feature_baseline.json"
        if not baseline_path.is_absolute():
            baseline_path = Path(__file__).resolve().parents[2] / baseline_path
        baseline = load_baseline(baseline_path)
        current = pd.DataFrame(self.feature_buffer[-500:])
        return compute_psi_report(baseline, current)

    async def run_stream(self, db_factory) -> None:
        import asyncio
        import logging

        logger = logging.getLogger(__name__)
        try:
            while self.running and self._index < len(self._rows):
                while self.paused and self.running:
                    await asyncio.sleep(0.1)
                if not self.running:
                    break
                row = self._rows[self._index]
                self._index += 1
                try:
                    result = self.scorer.score_transaction(row)
                except Exception as exc:
                    logger.exception("Failed to score transaction %s", row.get("transaction_id"))
                    await self._broadcast(
                        {
                            "type": "error",
                            "message": str(exc),
                            "transaction_id": row.get("transaction_id"),
                        }
                    )
                    continue
                self.feature_buffer.append(result["features"])
                ts = row["timestamp"]
                record_event(f"rw:device:{row['device_id']}", row["user_id"], ts)
                record_event(f"rw:ip:{row['ip_address']}", row["user_id"], ts)
                record_event(f"rw:addr:{row['shipping_address_id']}", row["user_id"], ts)

                self._update_live_metrics(row, result)
                self._track_session_analytics(row, result)
                self._update_ring_graph(row, result)

                msg = _json_safe(
                    {
                        "type": "transaction",
                        "session_id": self.session_id,
                        "payload": {
                            **result,
                            "ground_truth_fraud": int(row.get("is_fraud", 0)),
                            "cluster_type": row.get("cluster_type"),
                        },
                        "metrics": self._live_metrics,
                    }
                )
                await self._broadcast(msg)

                db = db_factory()
                try:
                    self._persist(db, row, result)
                except Exception as exc:
                    logger.exception("Failed to persist transaction %s", row.get("transaction_id"))
                    db.rollback()
                    await self._broadcast(
                        {
                            "type": "warning",
                            "message": f"Audit persist failed: {exc}",
                            "transaction_id": row.get("transaction_id"),
                        }
                    )
                finally:
                    db.close()

                if result["decision_band"] in ("review", "flagged"):
                    await send_telegram_alert(result)

                if self._index % 100 == 0:
                    drift = self.get_drift()
                    await self._broadcast({"type": "drift", "payload": drift, "session_id": self.session_id})

                await asyncio.sleep(1.0 / max(self.speed, 0.1))
        finally:
            self.running = False
            await self._broadcast(
                {"type": "stream_complete", "session_id": self.session_id, "metrics": self._live_metrics}
            )


stream_manager = StreamManager()
