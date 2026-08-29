
import os
import json
import joblib
import pandas as pd

from sklearn.model_selection import train_test_split
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder
from sklearn.ensemble import RandomForestClassifier
from sklearn.calibration import CalibratedClassifierCV
from sklearn.metrics import (
    accuracy_score, precision_score, recall_score, f1_score,
    roc_auc_score, brier_score_loss
)

DATA_PATH = "data/processed/supply_chain_cases.csv"
MODEL_PATH = "outputs/models/triguard_model_v2.pkl"
METADATA_PATH = "outputs/models/triguard_model_v2_metadata.json"
TARGET = "disruption_within_7d"
OPERATING_THRESHOLD = 0.35

df = pd.read_csv(DATA_PATH)

feature_columns = [
    c for c in df.columns
    if c not in ["case_id", TARGET, "safety_stock_gap"]
]
X = df[feature_columns]
y = df[TARGET]

categorical_cols = ["medicine_name", "supplier_id", "destination_facility"]
numeric_cols = [c for c in feature_columns if c not in categorical_cols]

preprocessor = ColumnTransformer([
    ("cat", OneHotEncoder(handle_unknown="ignore"), categorical_cols),
    ("num", "passthrough", numeric_cols)
])

base_pipeline = Pipeline([
    ("preprocessor", preprocessor),
    ("model", RandomForestClassifier(
        n_estimators=200,
        max_depth=8,
        min_samples_split=10,
        min_samples_leaf=4,
        class_weight="balanced",
        random_state=42,
        n_jobs=-1
    ))
])

X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.20, random_state=42, stratify=y
)

model = CalibratedClassifierCV(
    estimator=base_pipeline,
    method="isotonic",
    cv=3
)
model.fit(X_train, y_train)

probs = model.predict_proba(X_test)[:, 1]
preds = (probs >= OPERATING_THRESHOLD).astype(int)

metadata = {
    "model_version": "v2",
    "feature_columns": feature_columns,
    "removed_features": ["safety_stock_gap"],
    "calibration": "isotonic",
    "cv_folds": 3,
    "operating_threshold": OPERATING_THRESHOLD,
    "threshold_note": (
        "Selected as the maximum-F1 candidate on the fixed prototype holdout. "
        "Must be revalidated on real operational data before deployment."
    ),
    "metrics": {
        "accuracy": float(accuracy_score(y_test, preds)),
        "precision": float(precision_score(y_test, preds, zero_division=0)),
        "recall": float(recall_score(y_test, preds, zero_division=0)),
        "f1": float(f1_score(y_test, preds, zero_division=0)),
        "roc_auc": float(roc_auc_score(y_test, probs)),
        "brier_score": float(brier_score_loss(y_test, probs))
    }
}

os.makedirs("outputs/models", exist_ok=True)
joblib.dump(model, MODEL_PATH)

with open(METADATA_PATH, "w") as f:
    json.dump(metadata, f, indent=2)

print("TriGuard Model V2 trained successfully.")
print(json.dumps(metadata, indent=2))
