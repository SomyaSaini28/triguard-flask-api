import pandas as pd
import numpy as np

DATA_PATH = "data/processed/supply_chain_cases.csv"
TARGET = "disruption_within_7d"

df = pd.read_csv(DATA_PATH)

print("Shape:", df.shape)
print("Missing values:", int(df.isna().sum().sum()))
print("Duplicate rows:", int(df.duplicated().sum()))
print("Duplicate case IDs:", int(df["case_id"].duplicated().sum()))
print("\nTarget distribution (%):")
print((df[TARGET].value_counts(normalize=True).sort_index() * 100).round(2))

expected_gap = (8 - df["current_stock_days"]).clip(lower=0)
print("\nSafety stock gap fully derived from current stock days:",
      bool((expected_gap == df["safety_stock_gap"]).all()))

corr = (
    df.select_dtypes(include=np.number)
      .corr(numeric_only=True)[TARGET]
      .drop(TARGET)
      .sort_values(key=abs, ascending=False)
)
print("\nNumeric feature correlations with target:")
print(corr.round(3))
