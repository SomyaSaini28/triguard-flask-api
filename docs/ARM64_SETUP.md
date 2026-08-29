# Windows ARM64 local setup

TriGuard's Flask API can run locally on Windows ARM64 without the optional SHAP analysis tooling.

## Core environment
Recommended:
- Python 3.12
- scikit-learn 1.9.x
- pandas
- numpy
- joblib
- Flask

## SHAP
SHAP is only used by the optional analysis scripts; it is not required by the serving API.

If SHAP is unavailable, the application still supports:
- calibrated disruption probability
- binary disruption classification
- operational triage
- recommendations

This is useful on Windows ARM64 systems where SHAP/Numba/llvmlite wheels may not be available.

## Run
```powershell
$env:TRIGUARD_ENV = "development"
$env:TRIGUARD_API_KEY = "local-development-key"
flask --app api.main:app run --port 8000 --debug
```
