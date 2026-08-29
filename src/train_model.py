import pandas as pd
import numpy as np
import os
import joblib

from sklearn.model_selection import train_test_split
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder
from sklearn.metrics import classification_report, roc_auc_score
from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import RandomForestClassifier

# -----------------------------
# LOAD DATA
# -----------------------------
df = pd.read_csv("data/processed/supply_chain_cases.csv")

target = "disruption_within_7d"

X = df.drop(columns=["case_id", target])
y = df[target]

categorical_cols = ["medicine_name", "supplier_id", "destination_facility"]
numeric_cols = [col for col in X.columns if col not in categorical_cols]

preprocessor = ColumnTransformer(
    transformers=[
        ("cat", OneHotEncoder(handle_unknown="ignore"), categorical_cols),
        ("num", "passthrough", numeric_cols)
    ]
)

# -----------------------------
# BASE MODEL
# -----------------------------
base_model = RandomForestClassifier(
    n_estimators=200,
    max_depth=8,
    min_samples_split=10,
    min_samples_leaf=4,
    class_weight="balanced",
    random_state=42,
    n_jobs=-1
)

pipeline = Pipeline([
    ("preprocessor", preprocessor),
    ("model", base_model)
])

# -----------------------------
# TRAIN / TEST SPLIT
# -----------------------------
X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=42, stratify=y
)

# -----------------------------
# CALIBRATED MODEL
# PS2 ke liye calibration important hai
# -----------------------------
calibrated_model = CalibratedClassifierCV(
    estimator=pipeline,
    method="isotonic",
    cv=3
)

calibrated_model.fit(X_train, y_train)

# -----------------------------
# PREDICTIONS
# -----------------------------
preds = calibrated_model.predict(X_test)
probs = calibrated_model.predict_proba(X_test)[:, 1]

print("Classification Report:")
print(classification_report(y_test, preds))

print("ROC-AUC:", roc_auc_score(y_test, probs))

# -----------------------------
# SAVE MODEL
# -----------------------------
os.makedirs("outputs/models", exist_ok=True)
os.makedirs("outputs/predictions", exist_ok=True)

joblib.dump(calibrated_model, "outputs/models/triguard_calibrated_model.pkl")

# -----------------------------
# SAVE SAMPLE PREDICTIONS
# -----------------------------
results = X_test.copy()
results["actual_label"] = y_test.values
results["predicted_label"] = preds
results["risk_probability"] = probs

# -----------------------------
# TRIAGE RULES
# -----------------------------
def assign_triage(row):
    risk = row["risk_probability"]
    criticality = row["medicine_criticality"]
    stock_days = row["current_stock_days"]

    if risk >= 0.75 and criticality >= 4 and stock_days <= 5:
        return "INTERVENE NOW"
    elif risk >= 0.60:
        return "ESCALATE TO PLANNER"
    elif risk >= 0.35:
        return "REVIEW"
    else:
        return "MONITOR"

results["triage_action"] = results.apply(assign_triage, axis=1)

results.to_csv("outputs/predictions/sample_predictions.csv", index=False)

print("\nModel saved to outputs/models/triguard_calibrated_model.pkl")
print("Predictions saved to outputs/predictions/sample_predictions.csv")
print("\nSample triage output:")
print(results[["medicine_name", "destination_facility", "risk_probability", "triage_action"]].head(10))