import pandas as pd
import MetaTrader5 as mt5
from .main_model import ModelLearning

class FeatureGenerator:
    def __init__(self, symbol, t1,window_size=100000):
        self.buffer = pd.DataFrame()
        self.window_size = window_size
        self.symbol = symbol        
        self.t1 = t1

        try:
            self.data = ModelLearning(d1=self.t1, symbol=self.symbol)

        except TypeError as e:
            raise ValueError(f"ModelLearning instantiation failed: {e}")

        try:
            self.df_h1 = self.data.change_header(self.data.mt5_downloader(self.t1))

            self.buffer = self.build_features(self.df_h1)
            self.buffer.dropna(inplace=True)
        except Exception as e:
            raise RuntimeError(f"Error initializing FeatureGenerator: {e}")

    def build_features(self,df):
        df = self.data.data_feature_eng(df)
        df = self.data.detect_fvgs(df)
        df = self.data.order_block_leak_free(df)
        df = self.data.liquidity(df)
        df = self.data.time_session(df)
        df = self.data.add_volume_indicators(df)
        df.dropna(inplace=True)

        binary_cols = [
            'Bullish_FVG', 'Bearish_FVG', 'Bullish_OB', 'Bearish_OB',
            'Liquidity_High', 'Liquidity_Low', 'Asian_Session',
            'London_Session', 'NY_Session'
        ]
        df[binary_cols] = df[binary_cols].astype(int)
        return df
    
    def update(self):
        if self.buffer.empty:
            latest_time = pd.Timestamp.now() - pd.Timedelta(days=7)
        else:
            latest_time = self.buffer.index[-1]

        try:
            full_h1 = self.data.change_header(self.data.mt5_downloader(self.t1))
        except Exception as e:
            print(f"Error during {self.t1} download: {e}")
            return pd.DataFrame()

        if latest_time not in full_h1.index:
            print("Warning: Time discontinuity detected")
            new_h1 = full_h1.iloc[-100:]
        else:
            idx = full_h1.index.get_loc(latest_time)
            start_idx = max(0, idx - 10)
            new_h1 = full_h1.iloc[start_idx:]

        try:
            new_features = self.build_features(new_h1)
            if not self.buffer.empty:
                new_features = new_features[new_features.index > latest_time]

            if new_features.empty:
                print("No new candles since last update")
                return self.buffer.iloc[-1:] if not self.buffer.empty else pd.DataFrame()

            self.buffer = pd.concat([self.buffer, new_features])
            self.buffer = self.buffer[~self.buffer.index.duplicated(keep='last')]
            self.buffer.sort_index(inplace=True)

            if len(self.buffer) > self.window_size:
                self.buffer = self.buffer.iloc[-self.window_size:]

            return self.buffer.iloc[-1:]

        except Exception as e:
            print(f"Error during feature update: {e}")
            return pd.DataFrame()

    def get_full_buffer(self):
        return self.buffer.copy()
