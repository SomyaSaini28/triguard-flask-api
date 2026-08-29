import pandas as pd
import numpy as np
import os

np.random.seed(42)

# -----------------------------
# CONFIG
# -----------------------------
N = 2000

medicines = [
    ("Insulin", 5, 1),
    ("Amoxicillin", 4, 0),
    ("Ceftriaxone", 4, 0),
    ("ORS", 3, 0),
    ("Oxytocin", 5, 0),
    ("Rabies Vaccine", 5, 1),
    ("Pentavalent Vaccine", 5, 1),
    ("Paracetamol Injection", 3, 0),
    ("Salbutamol", 4, 0),
    ("Iron Folic Acid", 2, 0),
    ("Anti-snake Venom", 5, 1),
    ("Adrenaline Injection", 5, 0)
]

suppliers = [f"S{i}" for i in range(1, 11)]
facilities = [
    "District Hospital Jaipur",
    "CHC Bikaner",
    "PHC Sikar",
    "Medical College Kota",
    "District Hospital Ajmer",
    "CHC Udaipur",
    "PHC Alwar",
    "District Hospital Jodhpur"
]

rows = []

for i in range(N):
    med_name, criticality, cold_chain = medicines[np.random.randint(0, len(medicines))]
    
    supplier_id = np.random.choice(suppliers)
    destination = np.random.choice(facilities)
    
    supplier_on_time_rate = np.clip(np.random.normal(0.82, 0.12), 0.4, 0.99)
    supplier_fill_rate = np.clip(np.random.normal(0.86, 0.10), 0.5, 1.0)
    lead_time_days = np.random.randint(2, 12)
    lead_time_variability = np.clip(np.random.normal(2.5, 1.5), 0, 8)
    route_delay_days = np.clip(np.random.normal(1.5, 1.8), 0, 10)
    weather_risk_score = np.random.randint(0, 11)   # 0-10
    demand_spike_factor = np.clip(np.random.normal(1.0, 0.35), 0.5, 2.5)
    current_stock_days = np.random.randint(1, 25)
    warehouse_utilization = np.random.randint(50, 101)
    
    # Safety stock gap = how far below ideal buffer we are
    safety_stock_gap = max(0, 8 - current_stock_days)

    # Hidden risk score logic (for synthetic label generation)
    risk_score = 0
    
    if supplier_on_time_rate < 0.75:
        risk_score += 2
    if supplier_fill_rate < 0.8:
        risk_score += 2
    if lead_time_variability > 4:
        risk_score += 1
    if route_delay_days > 3:
        risk_score += 2
    if weather_risk_score > 6:
        risk_score += 1
    if demand_spike_factor > 1.3:
        risk_score += 1
    if current_stock_days < 5:
        risk_score += 3
    if criticality >= 4:
        risk_score += 1
    if cold_chain == 1 and route_delay_days > 2:
        risk_score += 2
    if warehouse_utilization > 90:
        risk_score += 1

    # Convert risk score to label with some randomness
    disruption_prob = min(0.05 + risk_score * 0.08, 0.95)
    disruption_within_7d = np.random.binomial(1, disruption_prob)

    rows.append({
        "case_id": f"C{i+1}",
        "medicine_name": med_name,
        "medicine_criticality": criticality,
        "cold_chain_required": cold_chain,
        "supplier_id": supplier_id,
        "destination_facility": destination,
        "supplier_on_time_rate": round(supplier_on_time_rate, 3),
        "supplier_fill_rate": round(supplier_fill_rate, 3),
        "lead_time_days": lead_time_days,
        "lead_time_variability": round(lead_time_variability, 2),
        "route_delay_days": round(route_delay_days, 2),
        "weather_risk_score": weather_risk_score,
        "demand_spike_factor": round(demand_spike_factor, 2),
        "current_stock_days": current_stock_days,
        "warehouse_utilization": warehouse_utilization,
        "safety_stock_gap": safety_stock_gap,
        "disruption_within_7d": disruption_within_7d
    })

df = pd.DataFrame(rows)

os.makedirs("data/processed", exist_ok=True)
df.to_csv("data/processed/supply_chain_cases.csv", index=False)

print("Dataset generated successfully!")
print(df.head())
print("\nSaved to: data/processed/supply_chain_cases.csv")
print("\nClass distribution:")
print(df["disruption_within_7d"].value_counts(normalize=True))