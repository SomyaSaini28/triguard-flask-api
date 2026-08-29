"""TriGuard feature-ablation experiment.
Re-run the Phase 6 comparison using the same split/model settings documented in outputs/evaluation/feature_ablation.csv.
Finding: safety_stock_gap is redundant with current_stock_days and can be removed from the ML feature set.
Keep medicine_criticality and cold_chain_required: removing all three derived/redundant fields reduced ROC-AUC.
"""\n