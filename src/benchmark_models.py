
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier
from sklearn.calibration import CalibratedClassifierCV
from sklearn.metrics import (
    accuracy_score, precision_score, recall_score, f1_score,
    roc_auc_score, brier_score_loss
)

df = pd.read_csv("data/processed/supply_chain_cases.csv")
target = "disruption_within_7d"
X = df.drop(columns=["case_id", target])
y = df[target]

categorical_cols = ["medicine_name", "supplier_id", "destination_facility"]
numeric_cols = [c for c in X.columns if c not in categorical_cols]

X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=42, stratify=y
)

def preprocessor(scale_numeric=False):
    num = StandardScaler() if scale_numeric else "passthrough"
    return ColumnTransformer([
        ("cat", OneHotEncoder(handle_unknown="ignore"), categorical_cols),
        ("num", num, numeric_cols)
    ])

models = {
    "Logistic Regression": Pipeline([
        ("preprocessor", preprocessor(True)),
        ("model", LogisticRegression(
            max_iter=2000, class_weight="balanced", random_state=42
        ))
    ]),
    "Random Forest": Pipeline([
        ("preprocessor", preprocessor(False)),
        ("model", RandomForestClassifier(
            n_estimators=200, max_depth=8, min_samples_split=10,
            min_samples_leaf=4, class_weight="balanced",
            random_state=42, n_jobs=-1
        ))
    ]),
}

rf_cal = Pipeline([
    ("preprocessor", preprocessor(False)),
    ("model", RandomForestClassifier(
        n_estimators=200, max_depth=8, min_samples_split=10,
        min_samples_leaf=4, class_weight="balanced",
        random_state=42, n_jobs=-1
    ))
])
models["Calibrated RF (Isotonic)"] = CalibratedClassifierCV(
    estimator=rf_cal, method="isotonic", cv=3
)

rows = []
for name, model in models.items():
    model.fit(X_train, y_train)
    probs = model.predict_proba(X_test)[:, 1]
    preds = (probs >= 0.5).astype(int)
    rows.append({
        "model": name,
        "accuracy": accuracy_score(y_test, preds),
        "precision": precision_score(y_test, preds, zero_division=0),
        "recall": recall_score(y_test, preds, zero_division=0),
        "f1": f1_score(y_test, preds, zero_division=0),
        "roc_auc": roc_auc_score(y_test, probs),
        "brier_score": brier_score_loss(y_test, probs)
    })

results = pd.DataFrame(rows).set_index("model")
print(results.round(4))
results.to_csv("outputs/evaluation/model_benchmark.csv")
