import pandas as pd
import numpy as np
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, confusion_matrix

def evaluate_thresholds(y_true, probabilities, thresholds=None):
    if thresholds is None:
        thresholds = np.arange(0.25, 0.61, 0.05)

    rows = []
    for threshold in thresholds:
        preds = (probabilities >= threshold).astype(int)
        tn, fp, fn, tp = confusion_matrix(y_true, preds).ravel()
        rows.append({
            "threshold": round(float(threshold), 2),
            "accuracy": accuracy_score(y_true, preds),
            "precision": precision_score(y_true, preds, zero_division=0),
            "recall": recall_score(y_true, preds, zero_division=0),
            "f1": f1_score(y_true, preds, zero_division=0),
            "false_negatives": int(fn),
            "false_positives": int(fp),
        })
    return pd.DataFrame(rows)
