
import json
import joblib
import pandas as pd

MODEL_PATH = "outputs/models/triguard_model_v2.pkl"
METADATA_PATH = "outputs/models/triguard_model_v2_metadata.json"

def load_v2():
    model = joblib.load(MODEL_PATH)
    with open(METADATA_PATH) as f:
        metadata = json.load(f)
    return model, metadata

def assign_triage(risk, criticality, stock_days):
    """
    Operational triage remains distinct from the binary disruption threshold.
    It combines probability with medicine criticality and stock cover.
    """
    if risk >= 0.75 and criticality >= 4 and stock_days <= 5:
        return "INTERVENE NOW"
    if risk >= 0.60:
        return "ESCALATE TO PLANNER"
    if risk >= 0.35:
        return "REVIEW"
    return "MONITOR"

def predict_single_case_v2(case_dict):
    model, metadata = load_v2()

    # V2 intentionally excludes safety_stock_gap from the ML feature set.
    model_input = {
        key: value
        for key, value in case_dict.items()
        if key in metadata["feature_columns"]
    }

    input_df = pd.DataFrame([model_input], columns=metadata["feature_columns"])
    probability = float(model.predict_proba(input_df)[0, 1])

    threshold = float(metadata["operating_threshold"])
    predicted_label = int(probability >= threshold)

    triage = assign_triage(
        probability,
        case_dict["medicine_criticality"],
        case_dict["current_stock_days"]
    )

    return {
        "model_version": metadata["model_version"],
        "predicted_label": predicted_label,
        "risk_probability": round(probability, 4),
        "classification_threshold": threshold,
        "triage_action": triage
    }
