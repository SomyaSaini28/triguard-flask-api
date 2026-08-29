import pandas as pd
import joblib

MODEL_PATH = "outputs/models/triguard_calibrated_model.pkl"

def assign_triage(risk, criticality, stock_days):
    if risk >= 0.75 and criticality >= 4 and stock_days <= 5:
        return "INTERVENE NOW"
    elif risk >= 0.60:
        return "ESCALATE TO PLANNER"
    elif risk >= 0.35:
        return "REVIEW"
    else:
        return "MONITOR"

def load_model():
    model = joblib.load(MODEL_PATH)
    return model

def predict_single_case(case_dict):
    """
    case_dict = dictionary containing one supply chain case
    """
    model = load_model()

    input_df = pd.DataFrame([case_dict])

    risk_probability = model.predict_proba(input_df)[:, 1][0]
    predicted_label = int(risk_probability >= 0.5)

    criticality = case_dict["medicine_criticality"]
    stock_days = case_dict["current_stock_days"]

    triage_action = assign_triage(risk_probability, criticality, stock_days)

    result = {
        "predicted_label": predicted_label,
        "risk_probability": round(float(risk_probability), 4),
        "triage_action": triage_action
    }

    return result


if __name__ == "__main__":
    sample_case = {
        "medicine_name": "Insulin",
        "medicine_criticality": 5,
        "cold_chain_required": 1,
        "supplier_id": "S2",
        "destination_facility": "District Hospital Jaipur",
        "supplier_on_time_rate": 0.68,
        "supplier_fill_rate": 0.72,
        "lead_time_days": 8,
        "lead_time_variability": 4.5,
        "route_delay_days": 3.8,
        "weather_risk_score": 8,
        "demand_spike_factor": 1.4,
        "current_stock_days": 3,
        "warehouse_utilization": 88,
        "safety_stock_gap": 5
    }

    prediction = predict_single_case(sample_case)
    print("Prediction Result:")
    print(prediction)