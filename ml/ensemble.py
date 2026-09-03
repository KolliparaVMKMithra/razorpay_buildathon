"""Shared ensemble scoring with fixed Isolation Forest calibration."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np


def calibrate_iforest_scores(iforest, X: np.ndarray) -> dict[str, float]:
    """Fit-time bounds using train distribution (percentiles for robustness)."""
    raw = -iforest.score_samples(X)
    return {
        "raw_p01": float(np.percentile(raw, 1)),
        "raw_p99": float(np.percentile(raw, 99)),
        "raw_min": float(raw.min()),
        "raw_max": float(raw.max()),
    }


def normalize_iforest(raw_scores: np.ndarray, raw_min: float, raw_max: float) -> np.ndarray:
    span = raw_max - raw_min
    if span < 1e-9:
        return np.zeros_like(raw_scores, dtype=float)
    return np.clip((raw_scores - raw_min) / span, 0.0, 1.0)


def ensemble_score(
    xgb_m,
    lgb_m,
    iforest,
    X: np.ndarray,
    if_cal: dict[str, float],
    *,
    supervised_weight: float = 0.75,
) -> np.ndarray:
    p_xgb = xgb_m.predict_proba(X)[:, 1]
    p_lgb = lgb_m.predict_proba(X)[:, 1]
    supervised = 0.5 * p_xgb + 0.5 * p_lgb
    raw_if = -iforest.score_samples(X)
    if_norm = normalize_iforest(
        raw_if,
        if_cal.get("raw_p01", if_cal["raw_min"]),
        if_cal.get("raw_p99", if_cal["raw_max"]),
    )
    if_weight = 1.0 - supervised_weight
    return supervised_weight * supervised + if_weight * if_norm


def save_iforest_calibration(path: Path, cal: dict[str, float]) -> None:
    path.write_text(json.dumps(cal, indent=2), encoding="utf-8")


def load_iforest_calibration(path: Path) -> dict[str, float]:
    return json.loads(path.read_text(encoding="utf-8"))
