"""Train a reproducible V3 artifact with provenance and integrity metadata.

Run from the repository root:
    python src/train_model_v3.py
"""

from __future__ import annotations

import hashlib
import json
import platform
from datetime import UTC, datetime
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.calibration import CalibratedClassifierCV
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, brier_score_loss, f1_score, precision_score, recall_score, roc_auc_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = PROJECT_ROOT / "data/processed/supply_chain_cases.csv"
MODEL_PATH = PROJECT_ROOT / "outputs/models/triguard_model_v3.pkl"
METADATA_PATH = PROJECT_ROOT / "outputs/models/triguard_model_v3_metadata.json"
TARGET = "disruption_within_7d"
OPERATING_THRESHOLD = 0.35
RANDOM_STATE = 42


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1_048_576), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    dataframe = pd.read_csv(DATA_PATH)
    feature_columns = [column for column in dataframe.columns if column not in {"case_id", TARGET, "safety_stock_gap"}]
    categorical_columns = ["medicine_name", "supplier_id", "destination_facility"]
    numeric_columns = [column for column in feature_columns if column not in categorical_columns]
    x_values, y_values = dataframe[feature_columns], dataframe[TARGET]
    x_train, x_test, y_train, y_test = train_test_split(
        x_values, y_values, test_size=0.20, random_state=RANDOM_STATE, stratify=y_values
    )
    preprocessor = ColumnTransformer([
        ("cat", OneHotEncoder(handle_unknown="ignore"), categorical_columns),
        ("num", "passthrough", numeric_columns),
    ])
    base_pipeline = Pipeline([
        ("preprocessor", preprocessor),
        ("model", RandomForestClassifier(
            n_estimators=300, max_depth=8, min_samples_split=10, min_samples_leaf=4,
            class_weight="balanced", random_state=RANDOM_STATE, n_jobs=-1,
        )),
    ])
    model = CalibratedClassifierCV(estimator=base_pipeline, method="isotonic", cv=3)
    model.fit(x_train, y_train)
    probabilities = model.predict_proba(x_test)[:, 1]
    predictions = (probabilities >= OPERATING_THRESHOLD).astype(int)

    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, MODEL_PATH)
    metadata = {
        "schema_version": "1.0",
        "model_version": "v3",
        "model_type": "Calibrated Random Forest",
        "feature_columns": feature_columns,
        "removed_features": ["safety_stock_gap"],
        "calibration": "isotonic",
        "cv_folds": 3,
        "operating_threshold": OPERATING_THRESHOLD,
        "training_data": {
            "source": "data/processed/supply_chain_cases.csv",
            "rows": int(len(dataframe)),
            "target": TARGET,
            "data_kind": "synthetic prototype data",
            "sha256": sha256(DATA_PATH),
        },
        "reproducibility": {
            "random_state": RANDOM_STATE,
            "train_test_split": {"test_size": 0.20, "stratified": True},
            "python_version": platform.python_version(),
            "numpy_version": np.__version__,
            "scikit_learn_version": sklearn.__version__,
            "trained_at_utc": datetime.now(UTC).isoformat(),
        },
        "metrics": {
            "accuracy": float(accuracy_score(y_test, predictions)),
            "precision": float(precision_score(y_test, predictions, zero_division=0)),
            "recall": float(recall_score(y_test, predictions, zero_division=0)),
            "f1": float(f1_score(y_test, predictions, zero_division=0)),
            "roc_auc": float(roc_auc_score(y_test, probabilities)),
            "brier_score": float(brier_score_loss(y_test, probabilities)),
        },
        "artifact_sha256": sha256(MODEL_PATH),
        "deployment_note": "Validate on local operational outcomes before use in production decisions.",
    }
    METADATA_PATH.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    print(f"Created {MODEL_PATH.name} with SHA-256 {metadata['artifact_sha256']}")
    print(json.dumps(metadata["metrics"], indent=2))


if __name__ == "__main__":
    main()
