from __future__ import annotations

import json
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

ML_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ML_DIR))

from ensemble import ensemble_score, load_iforest_calibration  # noqa: E402
from features import FEATURE_COLUMNS, SlidingWindowState, build_features_dataframe  # noqa: E402
from threshold import decision_band, dynamic_threshold, load_threshold_config  # noqa: E402

MODEL_DIR = ML_DIR / "model"
DATA_DIR = ML_DIR.parent / "data"


def main() -> None:
    load_threshold_config(MODEL_DIR / "threshold_config.json")
    if_cal = load_iforest_calibration(MODEL_DIR / "iforest_calibration.json")
    xgb = joblib.load(MODEL_DIR / "xgb_model.joblib")
    lgb_m = joblib.load(MODEL_DIR / "lgb_model.joblib")
    iforest = joblib.load(MODEL_DIR / "iforest_model.joblib")

    df = pd.read_csv(DATA_DIR / "transactions_full_with_labels_v2.csv", parse_dates=["timestamp"])
    feat = build_features_dataframe(df, state=SlidingWindowState())
    X = feat[FEATURE_COLUMNS].astype(float).values
    scores = ensemble_score(xgb, lgb_m, iforest, X, if_cal)

    thresholds = np.array(
        [
            dynamic_threshold(float(a), {k: float(row[k]) for k in FEATURE_COLUMNS})
            for a, (_, row) in zip(feat["amount_inr"].values, feat.iterrows())
        ]
    )
    bands = [decision_band(float(s), float(t)) for s, t in zip(scores, thresholds)]
    flagged = np.array([b in ("review", "flagged") for b in bands])

    print("=== RingWatch score sanity check (single-row path via batch features) ===")
    print(f"rows: {len(scores)}")
    print(f"risk min/max/std: {scores.min():.4f} / {scores.max():.4f} / {scores.std():.4f}")
    print(f"unique @3dp: {len(set(np.round(scores, 3)))}")
    print(f"allowed  p50/p90: {np.percentile(scores[~flagged], 50):.4f} / {np.percentile(scores[~flagged], 90):.4f}")
    print(f"flagged  p50/p90: {np.percentile(scores[flagged], 50):.4f} / {np.percentile(scores[flagged], 90):.4f}")
    print(f"count at exactly 0.750: {int(np.sum(np.abs(scores - 0.75) < 1e-4))}")
    print(f"count at exactly 0.000: {int(np.sum(np.abs(scores) < 1e-4))}")
    print("bands:", {b: bands.count(b) for b in set(bands)})


if __name__ == "__main__":
    main()
