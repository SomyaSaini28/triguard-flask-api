
import json
import warnings
import joblib
import numpy as np
import pandas as pd
import shap

MODEL_PATH = "outputs/models/triguard_model_v2.pkl"
METADATA_PATH = "outputs/models/triguard_model_v2_metadata.json"

def explain_single_case_v2(case_dict, top_k=5):
    model = joblib.load(MODEL_PATH)
    with open(METADATA_PATH) as f:
        metadata = json.load(f)

    model_input = {
        key: value
        for key, value in case_dict.items()
        if key in metadata["feature_columns"]
    }
    input_df = pd.DataFrame([model_input], columns=metadata["feature_columns"])

    calibrated_probability = float(model.predict_proba(input_df)[0, 1])

    pipeline = model.calibrated_classifiers_[0].estimator
    preprocessor = pipeline.named_steps["preprocessor"]
    forest = pipeline.named_steps["model"]

    transformed = preprocessor.transform(input_df)
    feature_names = preprocessor.get_feature_names_out()

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        explainer = shap.TreeExplainer(forest)
        shap_values = explainer.shap_values(transformed)

    if isinstance(shap_values, list):
        values = np.asarray(shap_values[1])[0]
    else:
        arr = np.asarray(shap_values)
        if arr.ndim == 3:
            values = arr[0, :, 1]
        elif arr.ndim == 2:
            values = arr[0]
        else:
            values = arr.reshape(-1)

    original_columns = list(input_df.columns)
    contributions = {col: 0.0 for col in original_columns}

    for name, value in zip(feature_names, values):
        stripped = name.split("__", 1)[-1]
        for col in original_columns:
            if stripped == col or stripped.startswith(col + "_"):
                contributions[col] += float(value)
                break

    ranked = sorted(
        contributions.items(),
        key=lambda item: abs(item[1]),
        reverse=True
    )[:top_k]

    return {
        "model_version": metadata["model_version"],
        "risk_probability": round(calibrated_probability, 4),
        "explanations": [
            {
                "feature": feature,
                "impact": round(float(impact), 6),
                "direction": "increases risk" if impact > 0 else "reduces risk"
            }
            for feature, impact in ranked
        ]
    }
