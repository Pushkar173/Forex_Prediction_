import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, confusion_matrix, classification_report

class ModelEvaluator:
    def __init__(self):
        pass

    def evaluate_model(self, model, X_test, y_test):
        """Evaluate a model and return comprehensive performance metrics"""
        y_pred = model.predict(X_test)
        metrics = {
            'accuracy': float(accuracy_score(y_test, y_pred)),
            'precision': float(precision_score(y_test, y_pred, zero_division=0)),
            'recall': float(recall_score(y_test, y_pred, zero_division=0)),
            'f1_score': float(f1_score(y_test, y_pred, zero_division=0)),
            'confusion_matrix': confusion_matrix(y_test, y_pred).tolist(),
            'report': classification_report(y_test, y_pred, output_dict=True, zero_division=0)
        }
        return metrics

    def print_summary(self, model_name, metrics):
        """Print concise metrics summary to console"""
        print(f"\n--- Evaluation for {model_name} ---")
        print(f"Accuracy : {metrics['accuracy']:.4f}")
        print(f"Precision: {metrics['precision']:.4f}")
        print(f"Recall   : {metrics['recall']:.4f}")
        print(f"F1 Score : {metrics['f1_score']:.4f}")
