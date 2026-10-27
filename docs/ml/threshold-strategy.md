# Threshold selection: anomaly_threshold.v1

Run `python scripts/evaluate_threshold.py` from the repository root after installing
`pip install -e "apps/api[dev,ml]"`. This evaluates the saved model without retraining it.
The versioned `.threshold.json` sidecar binds the threshold to the model version, SHA-256,
feature version, evaluation version, seed, dataset hash, and library versions.

## Dataset and split

`threshold_evaluation.v1` has 2,400 labeled synthetic transactions, including 240 anomalies.
Seed 20261026 and February 2025 event dates distinguish it from January training data.
Scenario labels are generated independently of model scores. Normal cases include legitimate
large travel purchases; anomalies include subtle account takeovers that resemble normal
purchases, so some classification errors are expected. These are synthetic feature vectors,
not reconstructed production account histories. Country and payment method are independent
evaluation attributes, not model inputs. The stratified 50/50 calibration/holdout split uses
the same fixed seed and preserves 10% anomaly prevalence in each split.

## Selection and comparator

Scores are negative `decision_function`: higher is more anomalous. An alert candidate is
`score >= threshold`. Evaluate every distinct calibration score and an all-negative cutoff.
Select the highest calibration F1 under a 15% calibration alert budget. Tie-break by higher
precision, then the higher threshold. The budget is a provisional synthetic operating target,
not a measured staffing limit. No holdout labels participate in threshold selection.

Precision is TP/(TP+FP), recall is TP/(TP+FN), and F1 is their harmonic mean. Undefined
precision/recall/F1 are zero. Alert rate is (TP+FP)/N, and alerts per 10,000 equal rate times
10,000. The holdout alert rate can exceed the calibration budget. It is a scenario estimate
at 10% synthetic prevalence, not a production-volume forecast.

## Error review and segmentation

The recorded run selects **0.229602043777838**. On the 1,200-row holdout, precision is
1.0, recall is 0.666667, and F1 is 0.8: 80 true positives, zero false positives, and 40
false negatives. All 40 misses are subtle account takeovers. There are no selected-cutoff
false positives to inspect in this run. At the baseline zero cutoff there were 173 false
positives and 33 false negatives, with F1 0.457895 and 260 alerts. Raising the cutoff
reduces alerts to 80 (6.6667%, about 667 per 10,000) at the cost of seven additional misses.
This tradeoff maximizes calibration F1 under the stated alert budget; it does not establish
production performance or guarantee the absence of future false positives.

The versioned `.threshold-report.json` contains the baseline cutoff at zero, selected-cutoff
holdout metrics, calibration metrics, and country/payment segment comparisons. FP/FN counts
by scenario and ten deterministic examples per error class support review. The generated
`data/processed/threshold_evaluation.v1.errors.csv` lists every holdout error with its score,
features, segment, scenario, and label. The `.threshold-sweep.json` records all candidates.

False positives from legitimate large travel purchases indicate that contextual novelty can
look risky. False negatives from subtle takeovers show the limits of the current features;
lowering the threshold raises alert volume and does not replace additional identity signals.
Segment thresholds are fit on calibration rows only and evaluated on holdout rows. Retain
the global threshold: small synthetic segment samples with artificially assigned attributes
do not justify production-specific overrides. Revisit with representative labeled data and
explicit per-segment minimum support and alert-capacity targets.

## Deployment and reproducibility

The threshold evaluation produces a candidate sidecar. The worker's `anomaly_alert.v1`
policy now loads that sidecar through `ALERT_THRESHOLD_PATH`, verifies the model hash,
feature version and comparator, and applies it to persisted alerts. The metrics service's
positive-score anomaly definition remains separate. See `alert-policies.md` for severity
bands and activation behavior. Fallback scores never qualify as model alerts.
Reruns in the recorded environment reproduce dataset, split, sweep, metrics, reviews, and
configuration byte for byte. Timing and current timestamps are intentionally excluded.
