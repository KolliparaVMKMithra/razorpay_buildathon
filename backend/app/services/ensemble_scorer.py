from __future__ import annotations

import json
import sys
from pathlib import Path

import joblib
import numpy as np

from app.config import settings
from app.ml_bridge import FEATURE_COLUMNS

ML_DIR = Path(__file__).resolve().parents[2] / "ml"
if str(ML_DIR) not in sys.path:
    sys.path.insert(0, str(ML_DIR))

from ensemble import ensemble_score, load_iforest_calibration  # noqa: E402


class EnsembleScorer:
    """Loads models once and scores with fixed IF calibration bounds."""

    def __init__(self, model_dir: Path | None = None) -> None:
        model_dir = model_dir or Path(settings.model_dir)
        if not model_dir.is_absolute():
            model_dir = Path(__file__).resolve().parents[2] / model_dir
        self.model_dir = model_dir
        self.xgb = joblib.load(model_dir / "xgb_model.joblib")
        self.lgb = joblib.load(model_dir / "lgb_model.joblib")
        self.iforest = joblib.load(model_dir / "iforest_model.joblib")
        cal_path = model_dir / "iforest_calibration.json"
        if not cal_path.exists():
            raise FileNotFoundError(
                f"{cal_path} missing — run ml/train.py to generate IF calibration bounds"
            )
        self.if_cal = load_iforest_calibration(cal_path)

    def score(self, X: np.ndarray) -> float:
        return float(ensemble_score(self.xgb, self.lgb, self.iforest, X, self.if_cal)[0])
