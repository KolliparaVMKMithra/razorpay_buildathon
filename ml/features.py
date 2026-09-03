"""
RingWatch feature engineering — strict no-look-ahead.
Each transaction's features use only data with timestamp strictly before it.
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

import numpy as np
import pandas as pd

THRESHOLDS_INR = (10_000, 50_000)

FEATURE_COLUMNS = [
    "txn_count_by_device_5min",
    "txn_count_by_device_15min",
    "txn_count_by_ip_5min",
    "distinct_users_per_address_60min",
    "distinct_users_per_device_5min",
    "amount_distance_to_threshold",
    "amount_inr_log",
    "is_new_device_for_user",
    "is_new_ip_for_user",
    "hour_of_day",
    "is_odd_hour",
    "day_of_week",
    "payment_method_card",
    "payment_method_upi",
    "payment_method_wallet",
    "payment_method_netbanking",
]

CATEGORICAL_ENCODINGS: dict[str, list[str]] = {}


def amount_distance_to_threshold(amount: float) -> float:
    """Signed distance to nearest regulatory-style threshold (₹10k / ₹50k). Negative = below."""
    distances = [amount - t for t in THRESHOLDS_INR]
    idx = int(np.argmin(np.abs(distances)))
    return float(distances[idx])


def _parse_ts(ts: Any) -> datetime:
    if isinstance(ts, datetime):
        return ts
    return pd.to_datetime(ts).to_pydatetime()


@dataclass
class SlidingWindowState:
    """In-memory state for rolling window features (batch replay or Redis-backed live)."""

    device_events: dict[str, deque] = field(default_factory=lambda: defaultdict(deque))
    ip_events: dict[str, deque] = field(default_factory=lambda: defaultdict(deque))
    address_events: dict[str, deque] = field(default_factory=lambda: defaultdict(deque))
    user_devices: dict[str, set] = field(default_factory=lambda: defaultdict(set))
    user_ips: dict[str, set] = field(default_factory=lambda: defaultdict(set))

    def _prune(self, dq: deque, cutoff: datetime) -> None:
        while dq and dq[0][0] <= cutoff:
            dq.popleft()

    def compute_features(self, row: dict[str, Any]) -> dict[str, float]:
        ts = _parse_ts(row["timestamp"])
        device = str(row["device_id"])
        ip = str(row["ip_address"])
        address = str(row["shipping_address_id"])
        user = str(row["user_id"])
        amount = float(row["amount_inr"])

        cut_5 = ts - timedelta(minutes=5)
        cut_15 = ts - timedelta(minutes=15)
        cut_60 = ts - timedelta(minutes=60)

        for dq in (self.device_events[device], self.ip_events[ip], self.address_events[address]):
            self._prune(dq, cut_60)

        dev_5 = sum(1 for t, _ in self.device_events[device] if t > cut_5)
        dev_15 = sum(1 for t, _ in self.device_events[device] if t > cut_15)
        ip_5 = sum(1 for t, _ in self.ip_events[ip] if t > cut_5)
        addr_users = {u for t, u in self.address_events[address] if t > cut_60}
        dev_users = {u for t, u in self.device_events[device] if t > cut_5}

        is_new_device = 0.0 if device in self.user_devices[user] else 1.0
        is_new_ip = 0.0 if ip in self.user_ips[user] else 1.0

        pm = str(row.get("payment_method", "")).lower()
        features = {
            "txn_count_by_device_5min": float(dev_5),
            "txn_count_by_device_15min": float(dev_15),
            "txn_count_by_ip_5min": float(ip_5),
            "distinct_users_per_address_60min": float(len(addr_users)),
            "distinct_users_per_device_5min": float(len(dev_users)),
            "amount_distance_to_threshold": amount_distance_to_threshold(amount),
            "amount_inr_log": float(np.log1p(amount)),
            "is_new_device_for_user": is_new_device,
            "is_new_ip_for_user": is_new_ip,
            "hour_of_day": float(ts.hour),
            "is_odd_hour": 1.0 if 0 <= ts.hour <= 5 else 0.0,
            "day_of_week": float(ts.weekday()),
            "payment_method_card": 1.0 if pm == "card" else 0.0,
            "payment_method_upi": 1.0 if pm == "upi" else 0.0,
            "payment_method_wallet": 1.0 if pm == "wallet" else 0.0,
            "payment_method_netbanking": 1.0 if pm == "netbanking" else 0.0,
        }

        self.device_events[device].append((ts, user))
        self.ip_events[ip].append((ts, user))
        self.address_events[address].append((ts, user))
        self.user_devices[user].add(device)
        self.user_ips[user].add(ip)

        return features

    def reset(self) -> None:
        self.device_events.clear()
        self.ip_events.clear()
        self.address_events.clear()
        self.user_devices.clear()
        self.user_ips.clear()


def build_features_dataframe(df: pd.DataFrame, state: SlidingWindowState | None = None) -> pd.DataFrame:
    """Compute features for all rows in chronological order."""
    work = df.sort_values("timestamp").reset_index(drop=True)
    state = state or SlidingWindowState()
    rows: list[dict[str, float]] = []
    for _, row in work.iterrows():
        rows.append(state.compute_features(row.to_dict()))
    feat_df = pd.DataFrame(rows)
    return pd.concat([work.reset_index(drop=True), feat_df], axis=1)


def ring_signal(features: dict[str, float]) -> float:
    """0-1 signal for coordinated ring activity (used in dynamic thresholding)."""
    dev5 = features.get("txn_count_by_device_5min", 0)
    ip5 = features.get("txn_count_by_ip_5min", 0)
    addr_users = features.get("distinct_users_per_address_60min", 0)
    dev_users = features.get("distinct_users_per_device_5min", 0)
    score = (
        min(dev5 / 15.0, 1.0) * 0.35
        + min(ip5 / 15.0, 1.0) * 0.25
        + min(addr_users / 10.0, 1.0) * 0.25
        + min(dev_users / 10.0, 1.0) * 0.15
    )
    return float(np.clip(score, 0.0, 1.0))
