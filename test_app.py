import streamlit as st
import pandas as pd
import yfinance as yf

st.title('Forex Test App')
st.write('If you can see this, Streamlit is working!')

# Test data download
try:
    data = yf.download('EURUSD=X', period='1mo')
    st.write(f'Data downloaded successfully! Shape: {data.shape}')
    st.write('First few rows:')
    st.dataframe(data.head())
except Exception as e:
    st.error(f'Error: {e}')