"""
Cost-sensitive dynamic per-transaction thresholds.
Fitted on train validation only — never on held-out test.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from features import ring_signal

# Defaults — overwritten by train.py calibration
AMOUNT_SCALE = 25_000.0
RING_PENALTY = 0.30
BASE_HIGH = 0.82
BASE_LOW = 0.28
HARD_BLOCK_FLOOR = 0.92
REVIEW_BAND_TOP = 0.85


def dynamic_threshold(amount_inr: float, features: dict[str, float]) -> float:
    """
    Higher amount → lower threshold (missed fraud costs more).
    High ring signal → lower threshold (card-testing bursts even at low ₹).
    """
    ring = ring_signal(features)
    amount_factor = np.clip(amount_inr / AMOUNT_SCALE, 0.0, 1.0)
    threshold = BASE_HIGH - 0.40 * amount_factor - RING_PENALTY * ring
    return float(np.clip(threshold, BASE_LOW, BASE_HIGH))


def decision_band(risk_score: float, threshold: float) -> str:
    if risk_score >= HARD_BLOCK_FLOOR:
        return "flagged"
    if risk_score >= threshold:
        return "review"
    return "allow"


def calibrate_threshold_params(
    y_true: np.ndarray,
    risk_scores: np.ndarray,
    amounts: np.ndarray,
    feature_rows: list[dict[str, float]],
    amount_scales: list[float] | None = None,
    ring_penalties: list[float] | None = None,
) -> dict:
    """Grid search on validation set to minimize cost-weighted errors."""
    global AMOUNT_SCALE, RING_PENALTY, BASE_HIGH, BASE_LOW
    amount_scales = amount_scales or [15_000, 20_000, 25_000, 30_000, 40_000]
    ring_penalties = ring_penalties or [0.20, 0.25, 0.30, 0.35, 0.40]

    best_cost = float("inf")
    best_params: dict = {}

    legit_mask = y_true == 0
    avg_legit = float(np.mean(amounts[legit_mask])) if legit_mask.any() else 500.0

    for ascale in amount_scales:
        for rpen in ring_penalties:
            AMOUNT_SCALE = ascale
            RING_PENALTY = rpen
            thresholds = np.array(
                [dynamic_threshold(float(a), f) for a, f in zip(amounts, feature_rows)]
            )
            flagged = risk_scores >= thresholds
            tp = int(np.sum(flagged & (y_true == 1)))
            fp = int(np.sum(flagged & (y_true == 0)))
            fn = int(np.sum((~flagged) & (y_true == 1)))
            fp_cost = float(np.sum(amounts[flagged & (y_true == 0)]))
            fn_cost = float(np.sum(amounts[(~flagged) & (y_true == 1)]))
            cost = fp_cost + fn_cost
            if cost < best_cost:
                best_cost = cost
                best_params = {
                    "amount_scale": ascale,
                    "ring_penalty": rpen,
                    "base_high": BASE_HIGH,
                    "base_low": BASE_LOW,
                    "hard_block_floor": HARD_BLOCK_FLOOR,
                    "val_fp_cost_inr": fp_cost,
                    "val_fn_cost_inr": fn_cost,
                    "val_precision": tp / (tp + fp) if (tp + fp) else 0.0,
                    "val_recall": tp / (tp + fn) if (tp + fn) else 0.0,
                    "threshold_min": float(np.min(thresholds)),
                    "threshold_max": float(np.max(thresholds)),
                    "threshold_mean": float(np.mean(thresholds)),
                    "avg_legit_amount_inr": avg_legit,
                }

    AMOUNT_SCALE = best_params["amount_scale"]
    RING_PENALTY = best_params["ring_penalty"]
    return best_params


def save_threshold_config(path: Path, params: dict) -> None:
    path.write_text(json.dumps(params, indent=2))


def load_threshold_config(path: Path) -> dict:
    global AMOUNT_SCALE, RING_PENALTY, BASE_HIGH, BASE_LOW, HARD_BLOCK_FLOOR
    params = json.loads(path.read_text())
    AMOUNT_SCALE = params.get("amount_scale", AMOUNT_SCALE)
    RING_PENALTY = params.get("ring_penalty", RING_PENALTY)
    BASE_HIGH = params.get("base_high", BASE_HIGH)
    BASE_LOW = params.get("base_low", BASE_LOW)
    HARD_BLOCK_FLOOR = params.get("hard_block_floor", HARD_BLOCK_FLOOR)
    return params
