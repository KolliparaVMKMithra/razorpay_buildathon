# RingWatch Metrics Report

**Model version:** ringwatch-v1.0.0
**Generated:** 2026-09-03T10:41:26.809351+00:00

## Held-out evaluation (single run, no tuning on test)

| Metric | Value |
|--------|-------|
| Precision | 0.8103 |
| Recall | 0.7966 |
| F1 | 0.8034 |
| ROC-AUC | 0.979 |
| False-positive cost (₹) | 83,734.05 |
| Fraud prevented (₹) | 1,357.44 |
| Dynamic threshold range | 0.42 – 0.8198 |

### Confusion matrix
- TP: 47, FP: 11
- FN: 12, TN: 3841

### False positives by hard-negative cluster

- **cafe_wifi**: 1 FPs, ₹87.32
- **independent**: 10 FPs, ₹83,646.73

### Fraud detection by pattern (held-out)

- **fraud_card_testing**: 47/59 detected (recall 79.66%)

### Known limitation

Held-out test contains only card_testing fraud (59/59 fraud rows). Stolen-card burst and structuring patterns exist only in training data; demo replay uses the full dataset to visualize all three ring types. Hard negatives (family/hostel/office/cafe_wifi) may cause false positives on shared devices.