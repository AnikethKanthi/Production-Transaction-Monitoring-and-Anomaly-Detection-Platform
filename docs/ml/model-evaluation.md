# Model evaluation

The committed `isolation_forest.v1` artifact is a scikit-learn Isolation Forest pipeline with deterministic seed 42, 250 estimators, and `transaction_features.v1` input order. Training used 2,000 synthetic normal rows; 200 labeled synthetic anomalies were held out from fitting and used for separation reporting. The training range is 2025-01-01 through 2025-01-08 UTC.

The recorded evaluation reports mean normal score `-0.103665`, mean anomalous score `0.269015`, mean lift `0.372680`, and pairwise anomaly-score separation rate `1.0`. Scores are negative `decision_function`, so larger values are more anomalous. These results demonstrate deterministic synthetic separation, not real-world fraud performance.

Threshold selection uses a separate 2,400-row labeled synthetic dataset and fixed seed 20261026. The selected inclusive threshold is `0.229602043777838`. On the 1,200-row holdout it recorded precision `1.0`, recall `0.666667`, F1 `0.8`, and an alert rate of `6.6667%`. All 40 false negatives were subtle takeover scenarios; the selected run recorded no false positives. See [threshold strategy](threshold-strategy.md) for methodology and limitations.

Reproduce training with `python scripts/train_model.py` and threshold evaluation with `python scripts/evaluate_threshold.py` after installing `apps/api[dev,ml]`. Compare artifact and dataset hashes, metadata, reports, and score charts before accepting a rerun. Do not overwrite a deployed model in place or infer production quality from synthetic metrics.
