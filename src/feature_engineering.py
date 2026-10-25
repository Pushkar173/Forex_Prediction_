import os
import joblib
import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler

class FeatureEngineer:
    def __init__(self, scaler_path='models/scaler.pkl'):
        self.scaler_path = scaler_path
        self.scaler = StandardScaler()
        self.is_fitted = False
        
        # Load scaler if already trained and saved
        if os.path.exists(self.scaler_path):
            try:
                self.scaler = joblib.load(self.scaler_path)
                self.is_fitted = True
            except Exception:
                self.is_fitted = False

    def create_features(self, data, lookback=15, forecast_horizon=1):
        """
        Transform raw indicator dataframe into windowed features and binary classification targets.
        Target: 1 if future close > current close, else 0.
        """
        if data is None or len(data) < lookback:
            return np.array([]), np.array([])

        df = data.copy()
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]

        candidate_cols = [
            'Close', 'Open', 'High', 'Low', 'Volume',
            'MA20', 'MA50', 'RSI', 'MACD', 'MACD_Signal',
            'BB_Upper', 'BB_Lower', 'Return', 'Volatility'
        ]
        feature_cols = [col for col in candidate_cols if col in df.columns]

        if not feature_cols:
            feature_cols = df.select_dtypes(include=[np.number]).columns.tolist()

        data_values = df[feature_cols].ffill().bfill().values
        close_values = df['Close'].values

        n_samples = len(df)
        features_list = []
        targets_list = []

        for i in range(lookback - 1, n_samples):
            # Window of past lookback days flattened into 1D feature vector
            window = data_values[i - lookback + 1 : i + 1].flatten()
            features_list.append(window)

            # Binary target: 1 for UP, 0 for DOWN
            if i + forecast_horizon < n_samples:
                target = 1 if close_values[i + forecast_horizon] > close_values[i] else 0
            else:
                # Latest row where future is not yet observed (used for inference)
                target = 1 if (i > 0 and close_values[i] > close_values[i - 1]) else 0
            targets_list.append(target)

        features = np.array(features_list, dtype=np.float32)
        targets = np.array(targets_list, dtype=np.int32)

        return features, targets

    def scale_features(self, features):
        """
        Scale features using StandardScaler.
        Fits scaler on training data, or transforms using previously fitted scaler.
        """
        features_arr = np.asarray(features, dtype=np.float32)
        if features_arr.ndim == 1:
            features_arr = features_arr.reshape(1, -1)

        if not self.is_fitted:
            scaled = self.scaler.fit_transform(features_arr)
            self.is_fitted = True
            os.makedirs(os.path.dirname(self.scaler_path), exist_ok=True)
            try:
                joblib.dump(self.scaler, self.scaler_path)
            except Exception as e:
                print(f"Warning: Could not save scaler to {self.scaler_path}: {e}")
            return scaled
        else:
            try:
                return self.scaler.transform(features_arr)
            except Exception:
                # Fallback if dimensions changed
                return self.scaler.fit_transform(features_arr)
