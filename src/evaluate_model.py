
import os
import json
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from sklearn.model_selection import train_test_split
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder
from sklearn.ensemble import RandomForestClassifier
from sklearn.calibration import CalibratedClassifierCV, calibration_curve
from sklearn.metrics import (
    accuracy_score, precision_score, recall_score, f1_score,
    roc_auc_score, brier_score_loss, confusion_matrix,
    classification_report
)

DATA_PATH = "data/processed/supply_chain_cases.csv"
OUT_DIR = "outputs/evaluation"
os.makedirs(OUT_DIR, exist_ok=True)

df = pd.read_csv(DATA_PATH)
target = "disruption_within_7d"

X = df.drop(columns=["case_id", target])
y = df[target]

categorical_cols = ["medicine_name", "supplier_id", "destination_facility"]
numeric_cols = [c for c in X.columns if c not in categorical_cols]

preprocessor = ColumnTransformer(
    transformers=[
        ("cat", OneHotEncoder(handle_unknown="ignore"), categorical_cols),
        ("num", "passthrough", numeric_cols),
    ]
)

rf = RandomForestClassifier(
    n_estimators=200,
    max_depth=8,
    min_samples_split=10,
    min_samples_leaf=4,
    class_weight="balanced",
    random_state=42,
    n_jobs=-1,
)

raw_pipeline = Pipeline([
    ("preprocessor", preprocessor),
    ("model", rf),
])

X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.20, random_state=42, stratify=y
)

# Raw Random Forest
raw_pipeline.fit(X_train, y_train)
raw_probs = raw_pipeline.predict_proba(X_test)[:, 1]
raw_preds = (raw_probs >= 0.5).astype(int)

# Calibrated Random Forest
calibrated = CalibratedClassifierCV(
    estimator=raw_pipeline,
    method="isotonic",
    cv=3
)
calibrated.fit(X_train, y_train)
cal_probs = calibrated.predict_proba(X_test)[:, 1]
cal_preds = (cal_probs >= 0.5).astype(int)

def metrics(y_true, preds, probs):
    return {
        "accuracy": float(accuracy_score(y_true, preds)),
        "precision": float(precision_score(y_true, preds, zero_division=0)),
        "recall": float(recall_score(y_true, preds, zero_division=0)),
        "f1": float(f1_score(y_true, preds, zero_division=0)),
        "roc_auc": float(roc_auc_score(y_true, probs)),
        "brier_score": float(brier_score_loss(y_true, probs)),
    }

raw_metrics = metrics(y_test, raw_preds, raw_probs)
cal_metrics = metrics(y_test, cal_preds, cal_probs)

comparison = pd.DataFrame(
    [raw_metrics, cal_metrics],
    index=["Random Forest (raw)", "Random Forest + Isotonic Calibration"]
)
comparison.to_csv(os.path.join(OUT_DIR, "metrics_comparison.csv"))

with open(os.path.join(OUT_DIR, "metrics.json"), "w") as f:
    json.dump(
        {"raw_random_forest": raw_metrics,
         "calibrated_random_forest": cal_metrics},
        f, indent=2
    )

with open(os.path.join(OUT_DIR, "classification_report.txt"), "w") as f:
    f.write("RAW RANDOM FOREST\n")
    f.write(classification_report(y_test, raw_preds, digits=4))
    f.write("\nCALIBRATED RANDOM FOREST\n")
    f.write(classification_report(y_test, cal_preds, digits=4))

# Confusion matrix for calibrated model
cm = confusion_matrix(y_test, cal_preds)
fig, ax = plt.subplots(figsize=(5, 4))
im = ax.imshow(cm)
ax.set_title("TriGuard — Calibrated Model Confusion Matrix")
ax.set_xlabel("Predicted label")
ax.set_ylabel("Actual label")
ax.set_xticks([0, 1], ["No disruption", "Disruption"])
ax.set_yticks([0, 1], ["No disruption", "Disruption"])
for i in range(2):
    for j in range(2):
        ax.text(j, i, cm[i, j], ha="center", va="center")
fig.colorbar(im, ax=ax)
fig.tight_layout()
fig.savefig(os.path.join(OUT_DIR, "confusion_matrix.png"), dpi=180)
plt.close(fig)

# Calibration curve
raw_frac, raw_mean = calibration_curve(y_test, raw_probs, n_bins=8, strategy="quantile")
cal_frac, cal_mean = calibration_curve(y_test, cal_probs, n_bins=8, strategy="quantile")

fig, ax = plt.subplots(figsize=(6, 5))
ax.plot([0, 1], [0, 1], linestyle="--", label="Perfect calibration")
ax.plot(raw_mean, raw_frac, marker="o", label="Random Forest (raw)")
ax.plot(cal_mean, cal_frac, marker="o", label="Isotonic calibrated")
ax.set_title("TriGuard — Probability Calibration")
ax.set_xlabel("Mean predicted probability")
ax.set_ylabel("Observed frequency")
ax.legend()
fig.tight_layout()
fig.savefig(os.path.join(OUT_DIR, "calibration_curve.png"), dpi=180)
plt.close(fig)

print("\n=== TriGuard Evaluation ===")
print(comparison.round(4))
print("\nConfusion matrix (calibrated):")
print(cm)
print(f"\nSaved evaluation outputs to: {OUT_DIR}")
