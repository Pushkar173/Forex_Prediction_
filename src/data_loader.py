import pandas as pd
import numpy as np
import yfinance as yf

class ForexDataLoader:
    def __init__(self):
        pass

    def download_data(self, symbol, period='1y', interval='1d'):
        """
        Download historical forex data using Yahoo Finance.
        Handles ticker formatting and flattens MultiIndex columns.
        """
        try:
            ticker = symbol if symbol.endswith('=X') else f"{symbol}=X"
            data = yf.download(ticker, period=period, interval=interval, progress=False)
            
            if data is None or data.empty:
                return None
            
            # Flatten multi-level columns if present (common in modern yfinance)
            if isinstance(data.columns, pd.MultiIndex):
                data.columns = [c[0] if isinstance(c, tuple) else c for c in data.columns]
                
            # Clean and coerce standard columns
            for col in ['Open', 'High', 'Low', 'Close', 'Volume']:
                if col in data.columns:
                    data[col] = pd.to_numeric(data[col], errors='coerce')
                    
            data = data.dropna(subset=['Close'])
            if data.empty:
                return None
            return data
        except Exception as e:
            print(f"Error downloading data for {symbol}: {e}")
            return None

    def calculate_technical_indicators(self, data):
        """
        Calculate technical indicators for model features and analysis:
        - Moving Averages (MA20, MA50)
        - RSI (Relative Strength Index)
        - MACD and Signal
        - Bollinger Bands
        - Return and Volatility
        """
        if data is None or data.empty:
            return data

        df = data.copy()
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]

        close = df['Close']

        # Moving Averages
        df['MA20'] = close.rolling(window=20).mean()
        df['MA50'] = close.rolling(window=50).mean()

        # RSI (14 period)
        delta = close.diff()
        gain = delta.where(delta > 0, 0.0).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0.0)).rolling(window=14).mean()
        rs = gain / (loss.replace(0, 1e-10))
        df['RSI'] = 100.0 - (100.0 / (1.0 + rs))

        # MACD (12, 26, 9)
        ema12 = close.ewm(span=12, adjust=False).mean()
        ema26 = close.ewm(span=26, adjust=False).mean()
        df['MACD'] = ema12 - ema26
        df['MACD_Signal'] = df['MACD'].ewm(span=9, adjust=False).mean()

        # Bollinger Bands (20 period, 2 std)
        bb_middle = close.rolling(window=20).mean()
        bb_std = close.rolling(window=20).std()
        df['BB_Upper'] = bb_middle + (2 * bb_std)
        df['BB_Lower'] = bb_middle - (2 * bb_std)

        # Returns and Volatility
        df['Return'] = close.pct_change()
        df['Volatility'] = df['Return'].rolling(window=10).std()

        return df
