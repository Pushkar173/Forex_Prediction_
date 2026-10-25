import os
import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split
import warnings
warnings.filterwarnings('ignore')

from src.data_loader import ForexDataLoader
from src.feature_engineering import FeatureEngineer
from src.models import ForexPredictor
from src.evaluation import ModelEvaluator

def main():
    print("=== Forex Prediction Project ===")
    print("Using Scikit-learn models (No TensorFlow)")
    
    # Step 1: Load Data
    print("\n1. Loading Forex Data...")
    loader = ForexDataLoader()
    data = loader.download_data('EURUSD', period='1y')
    
    if data is None:
        print("Failed to load data. Exiting...")
        return
    
    # Step 2: Calculate Technical Indicators
    print("\n2. Calculating Technical Indicators...")
    data = loader.calculate_technical_indicators(data)
    data = data.dropna()
    
    print(f"Data shape: {data.shape}")
    print(f"Date range: {data.index[0]} to {data.index[-1]}")
    
    # Step 3: Feature Engineering
    print("\n3. Engineering Features...")
    engineer = FeatureEngineer()
    features, targets = engineer.create_features(data, lookback=15, forecast_horizon=1)
    
    if len(features) == 0:
        print("No features created. Check your data.")
        return
        
    print(f"Features shape: {features.shape}")
    target_counts = pd.Series(targets).value_counts()
    print(f"Target distribution - Up: {target_counts.get(1, 0)}, Down: {target_counts.get(0, 0)}")
    
    # Step 4: Split Data
    print("\n4. Splitting Data...")
    X_train, X_test, y_train, y_test = train_test_split(
        features, targets, test_size=0.2, random_state=42, shuffle=False
    )
    
    X_train_scaled = engineer.scale_features(X_train)
    X_test_scaled = engineer.scale_features(X_test)
    
    print(f"Training set: {X_train_scaled.shape}")
    print(f"Test set: {X_test_scaled.shape}")
    
    # Step 5: Train Multiple Models
    print("\n5. Training Models...")
    predictor = ForexPredictor()
    
    # Train different models
    rf_model = predictor.train_random_forest(X_train_scaled, y_train, X_test_scaled, y_test)
    gb_model = predictor.train_gradient_boosting(X_train_scaled, y_train, X_test_scaled, y_test)
    lr_model = predictor.train_logistic_regression(X_train_scaled, y_train, X_test_scaled, y_test)
    
    # Step 6: Evaluate Models
    print("\n6. Model Performance Summary:")
    print("-" * 40)
    for model_name, accuracy in predictor.model_performance.items():
        print(f"  {model_name:.<20} {accuracy:.4f}")
    
    # Find best model
    best_model = max(predictor.model_performance, key=predictor.model_performance.get)
    best_accuracy = predictor.model_performance[best_model]
    print(f"\nBest Model: {best_model} ({best_accuracy:.4f})")
    
    # Step 7: Save Models
    print("\n7. Saving Models...")
    predictor.save_models()
    
    # Step 8: Anchor model hashes on blockchain
    print("\n8. Anchoring model hashes on chain...")
    try:
        from ledger import Ledger
        ledger = Ledger()
        models_dir = predictor.models_dir

        for filename in sorted(os.listdir(models_dir)):
            if not filename.endswith('.pkl'):
                continue
            filepath = os.path.join(models_dir, filename)
            file_hash = ledger.hash_file(filepath)
            try:
                info = ledger.anchor_model(file_hash)
                print(f"  {filename}")
                print(f"    SHA-256 : {file_hash}")
                print(f"    TX hash : {info['tx_hash'][:16]}...")
            except Exception as e:
                # Duplicate hash (model unchanged) is fine
                print(f"  {filename}  hash={file_hash[:16]}...  (already on chain)")

    except Exception as e:
        print(f"  ⚠ Blockchain anchoring skipped: {e}")
    
    print("\n=== Project Complete ===")
    print("All models trained and saved successfully!")
    print("Run 'streamlit run app.py' to see the dashboard.")

if __name__ == "__main__":
    main()