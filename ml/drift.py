"""
Population Stability Index (PSI) for feature drift monitoring.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from features import FEATURE_COLUMNS

PSI_DRIFT_THRESHOLD = 0.2


def _psi(expected: np.ndarray, actual: np.ndarray, bins: int = 10) -> float:
    """PSI between two distributions using quantile bins from expected."""
    expected = expected[~np.isnan(expected)]
    actual = actual[~np.isnan(actual)]
    if len(expected) < bins or len(actual) < bins:
        return 0.0
    breakpoints = np.percentile(expected, np.linspace(0, 100, bins + 1))
    breakpoints = np.unique(breakpoints)
    if len(breakpoints) < 2:
        return 0.0
    exp_counts, _ = np.histogram(expected, bins=breakpoints)
    act_counts, _ = np.histogram(actual, bins=breakpoints)
    exp_pct = exp_counts / max(exp_counts.sum(), 1)
    act_pct = act_counts / max(act_counts.sum(), 1)
    exp_pct = np.clip(exp_pct, 1e-4, 1.0)
    act_pct = np.clip(act_pct, 1e-4, 1.0)
    return float(np.sum((act_pct - exp_pct) * np.log(act_pct / exp_pct)))


def compute_psi_report(
    baseline_df: pd.DataFrame,
    current_df: pd.DataFrame,
    features: list[str] | None = None,
) -> dict:
    features = features or FEATURE_COLUMNS
    per_feature: dict[str, float] = {}
    for col in features:
        if col not in baseline_df.columns or col not in current_df.columns:
            continue
        per_feature[col] = _psi(
            baseline_df[col].astype(float).values,
            current_df[col].astype(float).values,
        )
    aggregate = float(np.mean(list(per_feature.values()))) if per_feature else 0.0
    drifting = [k for k, v in per_feature.items() if v > PSI_DRIFT_THRESHOLD]
    return {
        "aggregate_psi": aggregate,
        "per_feature_psi": per_feature,
        "drifting_features": drifting,
        "is_drifting": aggregate > PSI_DRIFT_THRESHOLD or len(drifting) > 0,
        "threshold": PSI_DRIFT_THRESHOLD,
    }


def save_baseline(path: Path, df: pd.DataFrame, features: list[str] | None = None) -> None:
    features = features or FEATURE_COLUMNS
    baseline = {col: df[col].astype(float).tolist() for col in features if col in df.columns}
    path.write_text(json.dumps(baseline))


def load_baseline(path: Path) -> pd.DataFrame:
    data = json.loads(path.read_text())
    return pd.DataFrame(data)
