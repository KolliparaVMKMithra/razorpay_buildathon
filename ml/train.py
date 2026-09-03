#!/usr/bin/env python3
"""
Train RingWatch ensemble models and evaluate once on held-out test set.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import joblib
import lightgbm as lgb
import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.ensemble import IsolationForest
from sklearn.metrics import (
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import train_test_split

ML_DIR = Path(__file__).resolve().parent
ROOT = ML_DIR.parent
DATA_DIR = ROOT / "data"
MODEL_DIR = ML_DIR / "model"

sys.path.insert(0, str(ML_DIR))

from ensemble import (  # noqa: E402
    calibrate_iforest_scores,
    ensemble_score,
    save_iforest_calibration,
)
from drift import compute_psi_report, save_baseline  # noqa: E402
from explain import Explainer  # noqa: E402
from features import FEATURE_COLUMNS, SlidingWindowState, build_features_dataframe  # noqa: E402
from threshold import (  # noqa: E402
    calibrate_threshold_params,
    decision_band,
    dynamic_threshold,
    load_threshold_config,
    save_threshold_config,
)

MODEL_VERSION = "ringwatch-v1.0.0"


def load_data() -> tuple[pd.DataFrame, pd.DataFrame]:
    train = pd.read_csv(DATA_DIR / "transactions_train_v2.csv", parse_dates=["timestamp"])
    test = pd.read_csv(DATA_DIR / "transactions_test_HELDOUT_v2.csv", parse_dates=["timestamp"])
    return train, test


def prepare_features(train: pd.DataFrame, test: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    print("Building train features (chronological, no look-ahead)...")
    train_feat = build_features_dataframe(train)
    print("Building test features (fresh state, no train leakage in windows)...")
    test_feat = build_features_dataframe(test, state=SlidingWindowState())
    return train_feat, test_feat


def train_models(X_train: np.ndarray, y_train: np.ndarray):
    pos = max(int(y_train.sum()), 1)
    neg = max(int((y_train == 0).sum()), 1)
    scale_pos_weight = neg / pos

    xgb_model = xgb.XGBClassifier(
        n_estimators=200,
        max_depth=6,
        learning_rate=0.08,
        subsample=0.85,
        colsample_bytree=0.85,
        scale_pos_weight=scale_pos_weight,
        eval_metric="logloss",
        random_state=42,
        n_jobs=-1,
    )
    lgb_model = lgb.LGBMClassifier(
        n_estimators=200,
        max_depth=6,
        learning_rate=0.08,
        subsample=0.85,
        colsample_bytree=0.85,
        scale_pos_weight=scale_pos_weight,
        random_state=42,
        n_jobs=-1,
        verbose=-1,
    )
    iforest = IsolationForest(
        n_estimators=200,
        contamination=min(0.05, max(y_train.mean(), 0.01)),
        random_state=42,
        n_jobs=-1,
    )

    xgb_model.fit(X_train, y_train)
    lgb_model.fit(X_train, y_train)
    iforest.fit(X_train)

    return xgb_model, lgb_model, iforest


HARD_NEGATIVE_CLUSTERS = ["family", "hostel", "office", "cafe_wifi"]


def hard_negative_fp_rates(df: pd.DataFrame, flagged: np.ndarray, y_true: np.ndarray) -> dict:
    rates: dict[str, dict] = {}
    for ct in HARD_NEGATIVE_CLUSTERS:
        mask = (df["cluster_type"].values == ct) & (y_true == 0)
        n = int(mask.sum())
        if n == 0:
            continue
        fp = int(np.sum(flagged & mask))
        rates[ct] = {
            "legit_rows": n,
            "false_positives": fp,
            "fp_rate": round(fp / n, 4),
        }
    return rates


def evaluate_split(
    df: pd.DataFrame,
    risk_scores: np.ndarray,
    thresholds: np.ndarray,
    split_name: str,
) -> dict:
    y_true = df["is_fraud"].values
    flagged = risk_scores >= thresholds
    bands = [
        decision_band(float(s), float(t)) for s, t in zip(risk_scores, thresholds)
    ]

    tp = int(np.sum(flagged & (y_true == 1)))
    fp = int(np.sum(flagged & (y_true == 0)))
    fn = int(np.sum((~flagged) & (y_true == 1)))
    tn = int(np.sum((~flagged) & (y_true == 0)))

    fp_cost = float(df.loc[flagged & (y_true == 0), "amount_inr"].sum())
    fn_cost = float(df.loc[(~flagged) & (y_true == 1), "amount_inr"].sum())
    fraud_prevented = float(df.loc[flagged & (y_true == 1), "amount_inr"].sum())

    prec = precision_score(y_true, flagged, zero_division=0)
    rec = recall_score(y_true, flagged, zero_division=0)
    f1 = f1_score(y_true, flagged, zero_division=0)
    auc = roc_auc_score(y_true, risk_scores) if len(np.unique(y_true)) > 1 else 0.0

    fp_by_cluster: dict[str, dict] = {}
    if "cluster_type" in df.columns:
        fp_df = df[flagged & (y_true == 0)]
        for ct, grp in fp_df.groupby("cluster_type"):
            fp_by_cluster[ct] = {
                "count": int(len(grp)),
                "cost_inr": float(grp["amount_inr"].sum()),
            }

    fraud_types = {}
    if "cluster_type" in df.columns:
        fraud_df = df[y_true == 1]
        for ct, grp in fraud_df.groupby("cluster_type"):
            detected = int(np.sum(flagged[grp.index]))
            fraud_types[ct] = {
                "total": int(len(grp)),
                "detected": detected,
                "recall": detected / len(grp) if len(grp) else 0.0,
            }

    return {
        "split": split_name,
        "precision": round(prec, 4),
        "recall": round(rec, 4),
        "f1": round(f1, 4),
        "roc_auc": round(auc, 4),
        "confusion_matrix": {"tp": tp, "fp": fp, "fn": fn, "tn": tn},
        "false_positive_cost_inr": round(fp_cost, 2),
        "false_negative_cost_inr": round(fn_cost, 2),
        "fraud_prevented_inr": round(fraud_prevented, 2),
        "threshold_min": round(float(thresholds.min()), 4),
        "threshold_max": round(float(thresholds.max()), 4),
        "threshold_mean": round(float(thresholds.mean()), 4),
        "false_positives_by_cluster_type": fp_by_cluster,
        "hard_negative_fp_rates": hard_negative_fp_rates(df, flagged, y_true),
        "fraud_detection_by_cluster_type": fraud_types,
        "decision_bands": {
            "allow": int(bands.count("allow")),
            "review": int(bands.count("review")),
            "flagged": int(bands.count("flagged")),
        },
    }


def write_metrics_md(report: dict, path: Path) -> None:
    held = report["heldout_evaluation"]
    lines = [
        "# RingWatch Metrics Report",
        "",
        f"**Model version:** {report['model_version']}",
        f"**Generated:** {report['generated_at']}",
        "",
        "## Held-out evaluation (single run, no tuning on test)",
        "",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Precision | {held['precision']} |",
        f"| Recall | {held['recall']} |",
        f"| F1 | {held['f1']} |",
        f"| ROC-AUC | {held['roc_auc']} |",
        f"| False-positive cost (₹) | {held['false_positive_cost_inr']:,.2f} |",
        f"| Fraud prevented (₹) | {held['fraud_prevented_inr']:,.2f} |",
        f"| Dynamic threshold range | {held['threshold_min']} – {held['threshold_max']} |",
        "",
        "### Confusion matrix",
        f"- TP: {held['confusion_matrix']['tp']}, FP: {held['confusion_matrix']['fp']}",
        f"- FN: {held['confusion_matrix']['fn']}, TN: {held['confusion_matrix']['tn']}",
        "",
        "### False positives by hard-negative cluster",
        "",
    ]
    for ct, info in held.get("false_positives_by_cluster_type", {}).items():
        lines.append(f"- **{ct}**: {info['count']} FPs, ₹{info['cost_inr']:,.2f}")
    lines.extend(["", "### Hard-negative FP rates (held-out)", ""])
    for ct, info in held.get("hard_negative_fp_rates", {}).items():
        lines.append(f"- **{ct}**: {info['fp_rate']:.2%} ({info['false_positives']}/{info['legit_rows']})")
    lines.extend(["", "### Fraud detection by pattern (held-out)", ""])
    for ct, info in held.get("fraud_detection_by_cluster_type", {}).items():
        lines.append(f"- **{ct}**: {info['detected']}/{info['total']} detected (recall {info['recall']:.2%})")
    lines.extend(["", "### Known limitation", ""])
    lines.append(report.get("known_limitations", ""))
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    train, test = load_data()
    train_feat, test_feat = prepare_features(train, test)

    X = train_feat[FEATURE_COLUMNS].astype(float).values
    y = train_feat["is_fraud"].values

    X_tr, X_val, y_tr, y_val, idx_tr, idx_val = train_test_split(
        X, y, np.arange(len(y)), test_size=0.2, random_state=42, stratify=y
    )
    val_df = train_feat.iloc[idx_val].reset_index(drop=True)

    print("Training ensemble on train split...")
    xgb_m, lgb_m, iforest = train_models(X_tr, y_tr)
    val_if_cal = calibrate_iforest_scores(iforest, X_tr)

    print("Calibrating dynamic thresholds on validation split...")
    val_scores = ensemble_score(xgb_m, lgb_m, iforest, X_val, val_if_cal)
    val_feature_rows = [
        {k: float(row[k]) for k in FEATURE_COLUMNS}
        for _, row in val_df.iterrows()
    ]
    threshold_params = calibrate_threshold_params(
        y_val, val_scores, val_df["amount_inr"].values, val_feature_rows
    )
    save_threshold_config(MODEL_DIR / "threshold_config.json", threshold_params)
    load_threshold_config(MODEL_DIR / "threshold_config.json")

    print("Retraining on full training set...")
    xgb_m, lgb_m, iforest = train_models(X, y)
    if_cal = calibrate_iforest_scores(iforest, X)
    save_iforest_calibration(MODEL_DIR / "iforest_calibration.json", if_cal)

    joblib.dump(xgb_m, MODEL_DIR / "xgb_model.joblib")
    joblib.dump(lgb_m, MODEL_DIR / "lgb_model.joblib")
    joblib.dump(iforest, MODEL_DIR / "iforest_model.joblib")
    joblib.dump(FEATURE_COLUMNS, MODEL_DIR / "feature_columns.joblib")

    explainer = Explainer(xgb_m, FEATURE_COLUMNS)
    joblib.dump(explainer, MODEL_DIR / "explainer.joblib")

    print("Evaluating on held-out test set (single evaluation)...")
    X_test = test_feat[FEATURE_COLUMNS].astype(float).values
    test_scores = ensemble_score(xgb_m, lgb_m, iforest, X_test, if_cal)
    test_feature_rows = [
        {k: float(row[k]) for k in FEATURE_COLUMNS}
        for _, row in test_feat.iterrows()
    ]
    test_thresholds = np.array(
        [
            dynamic_threshold(float(a), f)
            for a, f in zip(test_feat["amount_inr"].values, test_feature_rows)
        ]
    )
    heldout_metrics = evaluate_split(test_feat, test_scores, test_thresholds, "heldout")

    train_scores = ensemble_score(xgb_m, lgb_m, iforest, X, if_cal)
    train_thresholds = np.array(
        [
            dynamic_threshold(float(a), f)
            for a, f in zip(
                train_feat["amount_inr"].values,
                [{k: float(row[k]) for k in FEATURE_COLUMNS} for _, row in train_feat.iterrows()],
            )
        ]
    )
    train_hard_negative_fp = hard_negative_fp_rates(
        train_feat, train_scores >= train_thresholds, y
    )

    # PSI baseline from train features
    save_baseline(MODEL_DIR / "feature_baseline.json", train_feat)
    psi_report = compute_psi_report(train_feat, test_feat)

    known_limitations = (
        "Held-out test contains only card_testing fraud (59/59 fraud rows). "
        "Stolen-card burst and structuring patterns exist only in training data; "
        "demo replay uses the full dataset to visualize all three ring types. "
        "Hard negatives (family/hostel/office/cafe_wifi) may cause false positives on shared devices."
    )

    report = {
        "model_version": MODEL_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "training_rows": len(train_feat),
        "heldout_rows": len(test_feat),
        "train_fraud_rate": round(float(train_feat["is_fraud"].mean()), 4),
        "heldout_fraud_rate": round(float(test_feat["is_fraud"].mean()), 4),
        "threshold_calibration": threshold_params,
        "heldout_evaluation": heldout_metrics,
        "train_hard_negative_fp_rates": train_hard_negative_fp,
        "psi_train_vs_heldout": psi_report,
        "known_limitations": known_limitations,
        "features_used": FEATURE_COLUMNS,
        "ensemble_weights": {"xgboost": 0.375, "lightgbm": 0.375, "isolation_forest": 0.25},
    }

    (ML_DIR / "metrics_report.json").write_text(json.dumps(report, indent=2))
    write_metrics_md(report, ML_DIR / "metrics_report.md")

    print("\n=== HELD-OUT RESULTS ===")
    print(json.dumps(heldout_metrics, indent=2))
    print(f"\nReports saved to {ML_DIR / 'metrics_report.json'}")


if __name__ == "__main__":
    main()
