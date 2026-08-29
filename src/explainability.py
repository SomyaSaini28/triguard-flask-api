
import warnings
import numpy as np
import pandas as pd
import joblib

try:
    import shap
except ImportError as exc:
    raise ImportError("SHAP is required. Install dependencies from requirements.txt.") from exc

MODEL_PATH = "outputs/models/triguard_calibrated_model.pkl"

def _get_base_pipeline(calibrated_model):
    return calibrated_model.calibrated_classifiers_[0].estimator

def explain_single_case(case_dict, top_k=5):
    """
    Return the calibrated risk probability plus SHAP contributions
    from the underlying Random Forest.
    """
    model = joblib.load(MODEL_PATH)
    input_df = pd.DataFrame([case_dict])
    calibrated_probability = float(model.predict_proba(input_df)[0, 1])

    pipeline = _get_base_pipeline(model)
    preprocessor = pipeline.named_steps["preprocessor"]
    rf = pipeline.named_steps["model"]

    transformed = preprocessor.transform(input_df)
    feature_names = preprocessor.get_feature_names_out()

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        explainer = shap.TreeExplainer(rf)
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
        "risk_probability": calibrated_probability,
        "explanations": [
            {
                "feature": feature,
                "impact": float(impact),
                "direction": "increases risk" if impact > 0 else "reduces risk"
            }
            for feature, impact in ranked
        ]
    }
