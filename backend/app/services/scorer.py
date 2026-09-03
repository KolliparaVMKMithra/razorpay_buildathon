from __future__ import annotations

from pathlib import Path
from typing import Any

import joblib
import numpy as np

from app.config import settings
from app.ml_bridge import (
    FEATURE_COLUMNS,
    SlidingWindowState,
    decision_band,
    dynamic_threshold,
    load_threshold_config,
    ring_signal,
)
from app.services.ensemble_scorer import EnsembleScorer

MODEL_VERSION = "ringwatch-v1.0.0"


class Scorer:
    def __init__(self) -> None:
        model_dir = Path(settings.model_dir)
        if not model_dir.is_absolute():
            model_dir = Path(__file__).resolve().parents[2] / model_dir
        self.model_dir = model_dir
        self.ensemble = EnsembleScorer(model_dir)
        self.explainer = joblib.load(model_dir / "explainer.joblib")
        load_threshold_config(model_dir / "threshold_config.json")
        self.state = SlidingWindowState()
        self.device_flag_history: dict[str, int] = {}

    def reset(self) -> None:
        self.state.reset()
        self.device_flag_history.clear()

    def score_transaction(self, row: dict[str, Any]) -> dict[str, Any]:
        features = self.state.compute_features(row)
        X = np.array([[features[c] for c in FEATURE_COLUMNS]], dtype=float)
        risk = self.ensemble.score(X)
        threshold = dynamic_threshold(float(row["amount_inr"]), features)
        band = decision_band(risk, threshold)
        flagged = band in ("review", "flagged")
        reasons = self.explainer.top_reasons(X, {**row, **features}, k=3)

        device = str(row["device_id"])
        if flagged:
            self.device_flag_history[device] = self.device_flag_history.get(device, 0) + 1
        prior_flags = self.device_flag_history.get(device, 0)

        return {
            "transaction": row,
            "features": features,
            "risk_score": round(risk, 4),
            "threshold_used": round(threshold, 4),
            "decision_band": band,
            "flagged": flagged,
            "reasons": reasons,
            "model_version": MODEL_VERSION,
            "ring_signal": round(ring_signal(features), 4),
            "device_prior_flags": prior_flags,
            "network_note": (
                f"This device has {prior_flags} prior flagged transaction(s) in this session"
                if prior_flags
                else "No prior flagged activity on this device in this session"
            ),
        }
