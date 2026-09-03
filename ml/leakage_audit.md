# RingWatch Data Leakage Audit

**Date:** 2026-09-03  
**Auditor:** Automated + manual review during Phase 1 build  
**Dataset:** `transactions_train_v2.csv`, `transactions_test_HELDOUT_v2.csv`

## Purpose

Verify every feature and label used in training/scoring is knowable **at the moment the transaction is scored**, before any post-payment outcome (shipment, refund, chargeback, return).

## Available columns in source data

| Column | Available at score time? | Used in model? | Notes |
|--------|--------------------------|----------------|-------|
| `transaction_id` | Yes | No (identifier only) | |
| `timestamp` | Yes | Yes (derived: hour, day, windows) | |
| `user_id` | Yes | No direct; used for first-seen flags | |
| `device_id` | Yes | Via rolling counts | |
| `ip_address` | Yes | Via rolling counts | |
| `amount_inr` | Yes | Yes | |
| `payment_method` | Yes | Yes (one-hot) | |
| `merchant_category` | Yes | **Rejected** — marginal lift, kept model simpler | |
| `shipping_city` | Yes | **Rejected** — high cardinality, not ring-specific | |
| `shipping_address_id` | Yes | Via `distinct_users_per_address_60min` | |
| `is_fraud` | **No** (label) | Target only, never a feature | |
| `cluster_type` | **No** (ground-truth metadata) | **Rejected** — would be label leakage in production | Used post-hoc for FP analysis only |

## Features considered and accepted

| Feature | Leakage risk | Mitigation |
|---------|--------------|------------|
| `txn_count_by_device_5min` | Look-ahead if future txns included | Only events with `timestamp < current` in sliding window |
| `txn_count_by_device_15min` | Same | Same |
| `txn_count_by_ip_5min` | Same | Same |
| `distinct_users_per_address_60min` | Same | Count distinct users in prior 60min only |
| `distinct_users_per_device_5min` | Same | Added for card-testing ring signal |
| `amount_distance_to_threshold` | None | Computed from current amount only |
| `amount_inr_log` | None | Current transaction |
| `is_new_device_for_user` | Look-ahead if future pairs included | Updated **after** feature compute |
| `is_new_ip_for_user` | Same | Same |
| `hour_of_day`, `is_odd_hour`, `day_of_week` | None | From transaction timestamp |
| Payment method one-hots | None | Known at checkout |

## Features explicitly rejected

| Candidate | Reason rejected |
|-----------|-----------------|
| `cluster_type` | Oracle label — not available in production |
| `merchant_category` | Available but excluded to reduce overfit; can add in v2 |
| `shipping_city` | Geographic prior not needed for ring detection |
| Post-transaction outcomes (shipped, returned, refunded) | **Not present in CSV** — N/A |
| Future transaction counts within same burst | Would require look-ahead |
| Global fraud rate / label statistics | Target leakage |

## Train/test split leakage checks

| Check | Result |
|-------|--------|
| Transaction ID overlap train ∩ test | **0** — PASS |
| Test timestamps after train max | **Yes** (test starts 42s after train ends) — PASS |
| `cluster_type` used as feature | **No** — PASS |
| Threshold calibration on held-out | **No** — calibrated on train validation split only — PASS |
| Test feature windows include train history | **No** — fresh `SlidingWindowState()` for test — PASS |

## Second-pass review (post-shipment columns)

Unlike e-commerce RTO datasets, this payment fraud dataset has **no** post-order columns (delivery status, return initiated, etc.). No columns were found that become knowable only after shipment.

## Conclusion

**No leakage detected** in the accepted feature set. Offline metrics on `transactions_test_HELDOUT_v2.csv` are reported once without test-set tuning.

## Residual risks (documented honestly)

1. **Synthetic data** — patterns are planted; real fraud may be noisier.
2. **Held-out fraud composition** — test set contains only `fraud_card_testing`; metrics do not measure stolen-card or structuring recall.
3. **IP non-overlap train→test** — `is_new_ip_for_user` behaves differently across splits (expected drift, monitored via PSI).
