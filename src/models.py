import os
import joblib
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score

class ForexPredictor:
    def __init__(self, models_dir='models'):
        self.models_dir = models_dir
        self.models = {}
        self.model_performance = {}

    def train_random_forest(self, X_train, y_train, X_test, y_test):
        """Train Random Forest classifier"""
        rf = RandomForestClassifier(n_estimators=100, max_depth=10, random_state=42)
        rf.fit(X_train, y_train)
        y_pred = rf.predict(X_test)
        acc = accuracy_score(y_test, y_pred)
        
        self.models['random_forest'] = rf
        self.model_performance['random_forest'] = acc
        return rf

    def train_gradient_boosting(self, X_train, y_train, X_test, y_test):
        """Train Gradient Boosting classifier"""
        gb = GradientBoostingClassifier(n_estimators=100, learning_rate=0.05, max_depth=4, random_state=42)
        gb.fit(X_train, y_train)
        y_pred = gb.predict(X_test)
        acc = accuracy_score(y_test, y_pred)
        
        self.models['gradient_boosting'] = gb
        self.model_performance['gradient_boosting'] = acc
        return gb

    def train_logistic_regression(self, X_train, y_train, X_test, y_test):
        """Train Logistic Regression classifier"""
        lr = LogisticRegression(max_iter=1000, random_state=42)
        lr.fit(X_train, y_train)
        y_pred = lr.predict(X_test)
        acc = accuracy_score(y_test, y_pred)
        
        self.models['logistic_regression'] = lr
        self.model_performance['logistic_regression'] = acc
        return lr

    def save_models(self, path=None):
        """Save all trained models and performance metrics"""
        target_dir = path if path is not None else self.models_dir
        os.makedirs(target_dir, exist_ok=True)
        
        # Save individual models and complete dictionary
        for name, model in self.models.items():
            joblib.dump(model, os.path.join(target_dir, f"{name}.pkl"))
        
        joblib.dump(self.models, os.path.join(target_dir, "models.pkl"))
        joblib.dump(self.model_performance, os.path.join(target_dir, "performance.pkl"))
        print(f"Models successfully saved to {target_dir}/")

    def load_models(self, path=None):
        """Load trained models from directory"""
        target_dir = path if path is not None else self.models_dir
        if not os.path.exists(target_dir):
            return self.models

        # Try loading all models dictionary
        models_dict_path = os.path.join(target_dir, "models.pkl")
        if os.path.exists(models_dict_path):
            try:
                self.models = joblib.load(models_dict_path)
            except Exception:
                self.models = {}

        # Also load individual models if not present
        for name in ['random_forest', 'gradient_boosting', 'logistic_regression']:
            indiv_path = os.path.join(target_dir, f"{name}.pkl")
            if os.path.exists(indiv_path) and name not in self.models:
                try:
                    self.models[name] = joblib.load(indiv_path)
                except Exception:
                    pass

        # Load performance metrics if available
        perf_path = os.path.join(target_dir, "performance.pkl")
        if os.path.exists(perf_path):
            try:
                self.model_performance = joblib.load(perf_path)
            except Exception:
                pass

        return self.models
