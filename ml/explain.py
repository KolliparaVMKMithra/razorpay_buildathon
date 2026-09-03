"""
Request-time SHAP explanations in plain English.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import shap

from features import FEATURE_COLUMNS, THRESHOLDS_INR

REASON_TEMPLATES: dict[str, str] = {
    "txn_count_by_device_5min": "{v:.0f} transactions from this device in the last 5 minutes",
    "txn_count_by_device_15min": "{v:.0f} transactions from this device in the last 15 minutes",
    "txn_count_by_ip_5min": "{v:.0f} transactions from this IP in the last 5 minutes",
    "distinct_users_per_address_60min": "{v:.0f} different users shipping to this address in the last hour",
    "distinct_users_per_device_5min": "{v:.0f} different users on this device in the last 5 minutes",
    "amount_distance_to_threshold": "amount near regulatory review threshold",
    "is_new_device_for_user": "first time this device is seen for this user",
    "is_new_ip_for_user": "first time this IP is seen for this user",
    "is_odd_hour": "transaction occurred during odd hours (midnight–6am)",
    "hour_of_day": "transaction at hour {v:.0f} local time",
}


def _format_feature_reason(name: str, value: float, row: dict[str, Any] | None = None) -> str:
    if name == "amount_distance_to_threshold":
        amount = float(row.get("amount_inr", 0)) if row else abs(value)
        thr = min(THRESHOLDS_INR, key=lambda t: abs(amount - t))
        pct = abs(value) / thr * 100
        if value < 0:
            return f"amount is {pct:.1f}% below the Rs.{thr:,} review threshold"
        if value > 0:
            return f"amount is {pct:.1f}% above the Rs.{thr:,} review threshold"
        return ""
    if name in ("is_new_device_for_user", "is_new_ip_for_user", "is_odd_hour"):
        if value >= 0.5:
            return REASON_TEMPLATES.get(name, f"{name}={value}")
        return ""
    if name in REASON_TEMPLATES:
        return REASON_TEMPLATES[name].format(v=value)
    return f"{name.replace('_', ' ')}: {value:.2f}"


class Explainer:
    def __init__(self, model, feature_names: list[str] | None = None):
        self.model = model
        self.feature_names = feature_names or FEATURE_COLUMNS
        self._explainer = shap.TreeExplainer(model)

    def top_reasons(
        self,
        X: np.ndarray,
        row: dict[str, Any] | None = None,
        k: int = 3,
    ) -> list[str]:
        shap_vals = self._explainer.shap_values(X)
        if isinstance(shap_vals, list):
            shap_vals = shap_vals[1] if len(shap_vals) > 1 else shap_vals[0]
        sv = shap_vals[0] if shap_vals.ndim > 1 else shap_vals
        feat_vals = X[0] if X.ndim > 1 else X
        order = np.argsort(np.abs(sv))[::-1]
        reasons: list[str] = []
        for idx in order:
            fname = self.feature_names[idx]
            val = float(feat_vals[idx])
            text = _format_feature_reason(fname, val, row)
            if text and text not in reasons:
                reasons.append(text)
            if len(reasons) >= k:
                break
        if not reasons:
            reasons = ["Elevated ensemble fraud risk score based on transaction pattern"]
        return reasons[:k]
