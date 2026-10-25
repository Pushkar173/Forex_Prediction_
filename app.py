import streamlit as st
import pandas as pd
import yfinance as yf
import matplotlib.pyplot as plt
import numpy as np
from datetime import datetime, timezone
import time
import json
import secrets
import hashlib

st.set_page_config(page_title='ForexAI Chain - Predictor & Blockchain Ledger', layout='wide', page_icon='📈')

# ---------------------------------------------------------------------------
# Authentication Gate (Only authenticated users see the dashboard & predictions)
# ---------------------------------------------------------------------------
from auth import render_login_gate
render_login_gate()

st.title('📈 Forex Prediction Dashboard & Blockchain Audit Layer')

# ---------------------------------------------------------------------------
# Blockchain connection (cached so rerun reuses the same connection)
# ---------------------------------------------------------------------------

@st.cache_resource
def get_blockchain_ledger():
    """Return a Ledger instance connected to the blockchain."""
    try:
        from ledger import Ledger
        return Ledger()
    except Exception as e:
        st.warning(f"⚠️ Blockchain unavailable: {e}")
        return None

ledger = get_blockchain_ledger()

# Display chain status in sidebar
st.sidebar.header("Blockchain Audit Status")
if ledger is not None:
    try:
        chain_id = ledger.w3.eth.chain_id
        contract_addr = ledger._contract.address
        st.sidebar.success(f"🔗 Connected\n\n**Chain ID:** `{chain_id}`\n\n**Contract:** `{contract_addr[:10]}…{contract_addr[-6:]}`")
    except Exception:
        st.sidebar.info("🔗 Connected to Blockchain Ledger")
else:
    st.sidebar.warning("⚠️ Running in offline/unanchored mode")

# Sidebar for user input
st.sidebar.header("Forex Configuration")
symbol = st.sidebar.selectbox(
    "Select Currency Pair",
    ['EURUSD', 'GBPUSD', 'USDJPY', 'USDCHF', 'AUDUSD', 'USDCAD']
)

period = st.sidebar.selectbox(
    "Select Period",
    ['1mo', '3mo', '6mo', '1y', '2y']
)

# Load data function
@st.cache_data
def load_forex_data(symbol, period):
    try:
        ticker = f'{symbol}=X'
        data = yf.download(ticker, period=period, progress=False)
        if data is None or data.empty:
            return None
        if isinstance(data.columns, pd.MultiIndex):
            data.columns = [c[0] if isinstance(c, tuple) else c for c in data.columns]
        for col in ['Open', 'High', 'Low', 'Close', 'Volume']:
            if col in data.columns:
                data[col] = pd.to_numeric(data[col], errors='coerce')
        return data
    except Exception as e:
        st.error(f'Error loading data: {e}')
        return None

# Technical analysis functions
def calculate_rsi(prices, window=14):
    """Calculate RSI indicator"""
    delta = prices.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=window).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=window).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

def calculate_moving_averages(data, windows=[20, 50]):
    """Calculate moving averages"""
    for window in windows:
        data[f'MA{window}'] = data['Close'].rolling(window=window).mean()
    return data

# Load data
data = load_forex_data(symbol, period)

if data is not None and not data.empty:
    # Calculate technical indicators
    data = calculate_moving_averages(data)
    data['RSI'] = calculate_rsi(data['Close'])
    
    # Display current price info
    current_price = data['Close'].iloc[-1]
    previous_price = data['Close'].iloc[-2]
    change = current_price - previous_price
    change_pct = (change / previous_price) * 100
    
    col1, col2, col3 = st.columns(3)
    col1.metric(f'Current {symbol} Price', f'{float(current_price):.4f}')
    col2.metric('Change', f'{float(change):.4f}', f'{float(change_pct):.2f}%')
    col3.metric('RSI', f'{float(data["RSI"].iloc[-1]):.1f}')
    
    # Price chart with moving averages
    st.subheader('Price Chart with Moving Averages')
    fig, ax = plt.subplots(figsize=(12, 5))
    ax.plot(data.index, data['Close'], label='Close Price', linewidth=2, color='#1f77b4')
    if 'MA20' in data.columns:
        ax.plot(data.index, data['MA20'], label='MA20', linewidth=1.2, color='#ff7f0e', alpha=0.85)
    if 'MA50' in data.columns:
        ax.plot(data.index, data['MA50'], label='MA50', linewidth=1.2, color='#d62728', alpha=0.85)
    ax.set_title(f'{symbol} Price Chart ({period})', fontsize=14)
    ax.set_xlabel('Date')
    ax.set_ylabel('Exchange Rate')
    ax.legend(loc='best')
    ax.grid(True, alpha=0.3)
    st.pyplot(fig)
    
    # Technical indicators in columns
    st.subheader('Technical Indicators')
    col1, col2 = st.columns(2)
    
    with col1:
        st.write('**RSI (Relative Strength Index)**')
        fig, ax = plt.subplots(figsize=(10, 3.5))
        ax.plot(data.index, data['RSI'], color='#9467bd', linewidth=1.5)
        ax.axhline(70, color='r', linestyle='--', alpha=0.7, label='Overbought (70)')
        ax.axhline(30, color='g', linestyle='--', alpha=0.7, label='Oversold (30)')
        ax.axhline(50, color='gray', linestyle='-', alpha=0.4)
        ax.set_ylim(0, 100)
        ax.legend(loc='upper right')
        ax.grid(True, alpha=0.3)
        st.pyplot(fig)
    
    with col2:
        st.write('**Trading Volume**')
        fig, ax = plt.subplots(figsize=(10, 3.5))
        ax.plot(data.index, data['Volume'], color='#2ca02c', linewidth=1)
        ax.set_title('Volume')
        ax.grid(True, alpha=0.3)
        st.pyplot(fig)
    
    # Data summary
    st.subheader('Data Summary')
    col1, col2, col3, col4 = st.columns(4)
    col1.metric('Total Bars', len(data))
    col2.metric('Period High', f'{float(data["High"].max()):.4f}')
    col3.metric('Period Low', f'{float(data["Low"].min()):.4f}')
    col4.metric('Average Price', f'{float(data["Close"].mean()):.4f}')
    
    # ------------------------------------------------------------------
    # PREDICTION SECTION
    # ------------------------------------------------------------------
    st.markdown("---")
    st.subheader("🎯 Price Prediction & Blockchain Audit")
    
    prediction_col1, prediction_col2 = st.columns([1, 1])
    
    with prediction_col1:
        st.write("**Model & Pipeline Status:**")
        models_ready = False
        try:
            from src.models import ForexPredictor
            predictor = ForexPredictor()
            predictor.load_models()
            if predictor.models:
                models_ready = True
                st.success("✅ Models loaded and ready!")
                st.write(f"**Available models:** {', '.join(predictor.models.keys())}")
            else:
                st.warning("⚠️ No trained models found")
        except Exception:
            st.error("❌ Models not trained yet")

        st.info("""
        **Audit Trail Process:**
        1. Model features and prediction outputs are compiled into a canonical JSON signal record.
        2. A SHA-256 fingerprint is calculated and stored immutably on the Ethereum smart contract.
        3. Anyone can verify prediction authenticity without revealing raw confidential data.
        """)
        
        if st.button("🔄 Retrain Models Pipeline", key="train_btn"):
            with st.spinner("Training models and anchoring weights to blockchain..."):
                try:
                    from main import main as train_pipeline
                    train_pipeline()
                    st.success("Models trained and anchored successfully!")
                    time.sleep(1)
                    st.rerun()
                except Exception as train_err:
                    st.error(f"Error during training pipeline: {train_err}")

    with prediction_col2:
        st.write("**Generate Audited Prediction**")
        if st.button("🚀 Predict Next Move & Anchor on Chain", type="primary", use_container_width=True):
            try:
                from src.data_loader import ForexDataLoader
                from src.feature_engineering import FeatureEngineer
                from src.models import ForexPredictor
                from ledger import make_hash, hash_file
                import os

                with st.spinner('Calculating technical indicators, running inference, and anchoring signal...'):
                    loader = ForexDataLoader()
                    prediction_data = loader.download_data(symbol, period='6mo')
                    prediction_data = loader.calculate_technical_indicators(prediction_data)
                    prediction_data = prediction_data.dropna()
                    
                    if len(prediction_data) > 20:
                        engineer = FeatureEngineer()
                        features, _ = engineer.create_features(prediction_data, lookback=15, forecast_horizon=1)
                        
                        if len(features) > 0:
                            predictor = ForexPredictor()
                            predictor.load_models()
                            
                            if 'random_forest' in predictor.models:
                                latest_features = features[-1:].reshape(1, -1)
                                latest_features_scaled = engineer.scale_features(latest_features)
                                
                                prediction = predictor.models['random_forest'].predict(latest_features_scaled)[0]
                                probability = predictor.models['random_forest'].predict_proba(latest_features_scaled)[0]
                                
                                signal_direction = "UP" if prediction == 1 else "DOWN"
                                confidence_score = round(float(probability[1] if prediction == 1 else probability[0]), 4)

                                # Display Prediction Output
                                st.success("✅ Prediction Generated Successfully!")
                                if prediction == 1:
                                    st.balloons()
                                    st.markdown(f"### 🔼 **Direction: UP**")
                                else:
                                    st.markdown(f"### 🔽 **Direction: DOWN**")
                                
                                conf_col1, conf_col2 = st.columns(2)
                                conf_col1.metric("UP Probability", f"{probability[1]:.2%}")
                                conf_col2.metric("DOWN Probability", f"{probability[0]:.2%}")
                                st.progress(float(confidence_score))
                                
                                # Canonical JSON signal record as specified:
                                # (timestamp, pair, timeframe, model, signal, confidence, input_hash, nonce)
                                input_hash = hashlib.sha256(latest_features_scaled.tobytes()).hexdigest()
                                nonce = secrets.token_hex(16)
                                now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
                                
                                signal_record = {
                                    "timestamp": now_iso,
                                    "pair": symbol,
                                    "timeframe": period,
                                    "model": "random_forest",
                                    "signal": signal_direction,
                                    "confidence": confidence_score,
                                    "input_hash": input_hash,
                                    "nonce": nonce,
                                }
                                
                                signal_hash = make_hash(signal_record)
                                
                                # Anchor on blockchain
                                st.markdown("#### 🔗 Blockchain Audit Anchor")
                                if ledger is not None:
                                    try:
                                        info = ledger.anchor_signal(
                                            signal_hash,
                                            record=signal_record,
                                            nonce=nonce,
                                        )
                                        st.success(
                                            f"**Immutable On-Chain Anchor Confirmed!**  \n\n"
                                            f"• **Signal Hash:** `{signal_hash}`  \n"
                                            f"• **Transaction Hash:** `{info['tx_hash']}`  \n"
                                            f"• **Block Number:** `#{info['block_number']}`"
                                        )
                                    except Exception as chain_err:
                                        ledger.save_unanchored(
                                            signal_hash, "signal",
                                            record=signal_record, nonce=nonce,
                                        )
                                        st.warning(f"⚠️ Signal recorded locally; blockchain anchoring failed: {chain_err}")
                                        st.code(f"Signal Hash: {signal_hash}")
                                else:
                                    try:
                                        from ledger import _get_db
                                        db = _get_db()
                                        db.execute(
                                            "INSERT OR REPLACE INTO anchors "
                                            "(hash, kind, anchored, record_json, salt)"
                                            " VALUES (?, 'signal', 0, ?, ?)",
                                            (signal_hash, json.dumps(signal_record, sort_keys=True), nonce),
                                        )
                                        db.commit()
                                    except Exception:
                                        pass
                                    st.warning("⚠️ Blockchain ledger is not connected; signal record saved offline.")
                                    st.code(f"Signal Hash: {signal_hash}")

                                # Canonical JSON Record & Download
                                record_json_str = json.dumps(signal_record, indent=2, sort_keys=True)
                                with st.expander("📄 View Canonical Signal Record (JSON)"):
                                    st.code(record_json_str, language="json")
                                
                                st.download_button(
                                    label="💾 Download Signal Record JSON",
                                    data=record_json_str,
                                    file_name=f"signal_{symbol}_{now_iso[:10]}_{nonce[:6]}.json",
                                    mime="application/json",
                                    use_container_width=True
                                )
                            else:
                                st.warning("Random Forest model not found. Run 'python main.py' to train.")
                        else:
                            st.warning("Insufficient feature rows for prediction.")
                    else:
                        st.warning("Insufficient historical data downloaded for prediction.")
            except Exception as e:
                st.error(f"Prediction error: {e}")

    # Show recent data
    st.subheader('Recent Market Data')
    st.dataframe(data.tail(8).style.format({
        'Open': '{:.4f}', 'High': '{:.4f}', 'Low': '{:.4f}', 
        'Close': '{:.4f}', 'Volume': '{:.0f}'
    }), use_container_width=True)

    # ------------------------------------------------------------------
    # VERIFY A SIGNAL (Blockchain Audit Verification)
    # ------------------------------------------------------------------
    st.markdown("---")
    with st.expander("🔍 Verify a Signal or Model on Blockchain", expanded=False):
        st.write("Verify the authenticity, timestamp, and ownership of any Forex prediction signal or model hash against the immutable smart contract.")
        
        tab_hash, tab_upload = st.tabs(["Paste Hash", "Upload Signal JSON Record"])
        
        target_hash = ""
        uploaded_record_dict = None
        
        with tab_hash:
            pasted_hash = st.text_input(
                "Enter SHA-256 Hash",
                placeholder="e.g. 6f6cc25c6f5ac4e7efedbb5214b5c300fcb3ffedaed1f593eb10269595109408",
                key="verify_hash_input"
            )
            if pasted_hash:
                target_hash = pasted_hash.strip()
                
        with tab_upload:
            uploaded_file = st.file_uploader(
                "Upload Signal Record (.json)",
                type=["json"],
                key="verify_file_input"
            )
            if uploaded_file is not None:
                try:
                    from ledger import make_hash
                    file_contents = uploaded_file.read().decode('utf-8')
                    uploaded_record_dict = json.loads(file_contents)
                    computed_hash = make_hash(uploaded_record_dict)
                    st.success(f"Computed SHA-256 Hash from file: `{computed_hash}`")
                    target_hash = computed_hash
                    with st.expander("Uploaded Payload", expanded=False):
                        st.json(uploaded_record_dict)
                except Exception as file_err:
                    st.error(f"Error parsing uploaded JSON: {file_err}")

        verify_clicked = st.button("🔍 Verify on Blockchain", key="btn_run_verification", type="primary")

        if verify_clicked and target_hash:
            clean_h = target_hash.strip()
            if clean_h.startswith("0x") or clean_h.startswith("0X"):
                clean_h = clean_h[2:]
                
            if len(clean_h) != 64:
                st.error(f"❌ Invalid hash length: {len(clean_h)} characters (expected 64 hex characters).")
            elif ledger is None:
                st.error("❌ Blockchain connection unavailable – cannot verify on-chain.")
            else:
                try:
                    # Query on-chain smart contract
                    chain_result = ledger.verify(clean_h)
                    exists = chain_result["exists"]
                    kind = chain_result["kind"]
                    writer = chain_result["writer"]
                    raw_timestamp = chain_result["timestamp"]
                    
                    st.markdown("### 📋 Verification Results")
                    
                    if not exists:
                        st.error(
                            f"❌ **NOT FOUND ON BLOCKCHAIN**  \n\n"
                            f"The hash `{clean_h}` does not exist in the ForexLedger smart contract.  \n"
                            f"This indicates the record has never been anchored or has been altered."
                        )
                    else:
                        dt_str = datetime.fromtimestamp(raw_timestamp, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC") if raw_timestamp else "N/A"
                        
                        st.success(
                            f"✅ **AUTHENTIC & VERIFIED ON-CHAIN!**  \n\n"
                            f"• **Status:** Immutable record found on blockchain  \n"
                            f"• **Entry Kind:** `{kind.upper()}`  \n"
                            f"• **Writer Address:** `{writer}`  \n"
                            f"• **Block Timestamp:** `{raw_timestamp}` ({dt_str})  \n"
                            f"• **SHA-256 Hash:** `{clean_h}`"
                        )
                        
                        # Check local payload integrity if JSON record is available
                        record_to_check = uploaded_record_dict
                        if record_to_check is None:
                            stored = ledger.get_record(clean_h)
                            if stored and stored.get("record_json"):
                                try:
                                    record_to_check = json.loads(stored["record_json"])
                                except Exception:
                                    pass
                        
                        if record_to_check is not None:
                            from ledger import make_hash
                            recalculated = make_hash(record_to_check)
                            if recalculated.lower() == clean_h.lower():
                                st.info("🔒 **Data Integrity Check: PASSED** – Canonical JSON payload matches the on-chain SHA-256 hash perfectly.")
                                st.json(record_to_check)
                            else:
                                st.error("🚨 **Data Integrity Check: FAILED** – The payload data has been altered and does not match the on-chain hash!")

                except Exception as verify_err:
                    st.error(f"Verification execution error: {verify_err}")

else:
    st.error('Failed to load forex data. Please check internet connection or currency pair.')

# Information section
st.sidebar.markdown("---")
st.sidebar.header('System Architecture')
st.sidebar.info('''
**Forex Prediction & Blockchain Audit Layer**
- **Data Source:** Yahoo Finance real-time FX
- **ML Models:** Scikit-learn (Random Forest, Gradient Boosting, Logistic Regression)
- **Blockchain:** Ethereum / Ganache smart contract (`ForexLedger.sol`)
- **Audit Standard:** SHA-256 cryptographic commitments with canonical JSON serialization
''')