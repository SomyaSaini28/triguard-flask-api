# TriGuard Model V2

Model V2 is a retained experimental model version. The deployed Flask API serves the V3 artifact by default.

## Changes
- Removes `safety_stock_gap` from the ML feature set because it is deterministically derived from `current_stock_days`.
- Uses Random Forest + isotonic probability calibration.
- Uses a prototype classification threshold of 0.35, selected as the maximum-F1 candidate on the fixed holdout split.
- Keeps operational triage thresholds separate from the binary classification threshold.
- Supports SHAP explanations using the underlying Random Forest.
- Stores model metadata alongside the model artifact.

## V2 metrics on the fixed synthetic holdout
- Accuracy: 0.665
- Precision: 0.524
- Recall: 0.692
- F1: 0.596
- ROC-AUC: 0.729
- Brier score: 0.197

These results are prototype results on synthetic data and are not evidence of real-world clinical or operational performance.

## Run locally
```bash
python src/train_model_v2.py
flask --app api.main:app run --port 8000
```
