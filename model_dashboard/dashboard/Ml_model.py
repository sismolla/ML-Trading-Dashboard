import MetaTrader5 as mt5
import pandas as pd
import numpy as np
import sys

class ModelLearning:
    def __init__(self,d1,d2,d3,log, timeframe1=None, timeframe2=None,floor_time = None, symbol="EURUSDm", num_bars=100000, chunk_size=100000,report=False):
        self.symbol = symbol
        self.num_bars = num_bars
        self.chunk_size = chunk_size
        self.timeframe1 = timeframe1
        self.timeframe2 = timeframe2
        self.data = pd.DataFrame()
        self.floor_time = floor_time
        self.d1 = d1
        self.d2 = d2
        self.d3 = d3
        self.full_df = None
        self.log = log
        self.report = report

    def mt5_downloader(self, timeframe):
        self.timeframe = timeframe

        if not mt5.initialize():
            self.log("❌ MT5 initialization failed.")
            mt5.shutdown()
            return pd.DataFrame()


        if not mt5.symbol_select(self.symbol, True):
            self.log(f"❌ Symbol '{self.symbol}' not found or not visible in Market Watch.")
            mt5.shutdown()
            return pd.DataFrame()

        candles = mt5.copy_rates_from_pos(self.symbol, timeframe, 1, self.num_bars)

        if candles is None:
            self.log("❌ Failed to retrieve data.")
            mt5.shutdown()
            return pd.DataFrame()

        self.data = pd.DataFrame(candles)
        self.data['time'] = pd.to_datetime(self.data['time'], unit='s')
        self.data.drop(columns=['real_volume'], inplace=True)

        print(f"\n✅ Downloaded {len(self.data)} candles for {self.symbol} on {timeframe}.")

        mt5.shutdown()

        return self.data
    
    def change_header(self,df):
        df = df.rename(columns={'time': 'Time', 'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close', 'tick_volume': 'Volume'})
        return df

    def calculate_rsi(self,data, window=5):
        delta = data.diff()
        gain = delta.where(delta > 0, 0).rolling(window=window).mean()
        loss = -delta.where(delta < 0, 0).rolling(window=window).mean()
        rs = gain / loss.replace(0, np.nan)  # Avoid division by zero
        return 100 - (100 / (1 + rs))

    def calculate_stochastic_d(self,df, k_window=14, d_window=3):
        low_min = df['Low'].rolling(window=k_window).min()
        high_max = df['High'].rolling(window=k_window).max()
        stochastic_k = 100 * ((df['Close'] - low_min) / (high_max - low_min))
        stochastic_d = stochastic_k.rolling(window=d_window).mean()
        return stochastic_d

    def add_indicators(self,df, timeframe):
        df = df.copy()
        
        # Technical Indicators
        df['EMA_12'] = df['Close'].ewm(span=12, adjust=False).mean()
        df['EMA_26'] = df['Close'].ewm(span=26, adjust=False).mean()
        df['MACD'] = df['EMA_12'] - df['EMA_26']
        
        # RSI
        df['RSI'] = self.calculate_rsi(df['Close'], window=14)
        
        # ATR
        df['Prev_Close'] = df['Close'].shift(1)
        df['TR'] = pd.concat([
            (df['High'] - df['Low']),
            (df['High'] - df['Prev_Close']).abs(),
            (df['Low'] - df['Prev_Close']).abs()
        ], axis=1).max(axis=1)
        df['ATR'] = df['TR'].rolling(window=14).mean()
        df.drop(columns=['Prev_Close'], inplace=True)
        
        # Volume SMA
        df['Volume_SMA_24'] = df['Volume'].rolling(window=24).mean()

        # Stochastic D
        df['Stochastic_D'] = self.calculate_stochastic_d(df, k_window=14, d_window=14)

        # Drop raw EMAs (optional)
        df.drop(columns=['EMA_12', 'EMA_26'], inplace=True)
        
        # Floor time to DAILY for merging with daily candles
        df['Time_floor'] = df['Time'].dt.floor(self.floor_time)

        # Feature columns to aggregate
        features = ['MACD', 'RSI', 'ATR', 'TR', 'Volume_SMA_24', 'Stochastic_D']

        # Aggregate features per daily floor
        agg_df = df.groupby('Time_floor')[features].agg({
            'MACD': 'last',
            'RSI': 'last',
            'ATR': 'mean',
            'TR': 'mean',
            'Volume_SMA_24': 'last',
            'Stochastic_D': 'last',
        }).reset_index().rename(columns={'Time_floor': 'Time'})

        # Add suffix to columns
        suffix = f'_{timeframe.lower()}'
        agg_df.columns = ['Time'] + [col + suffix for col in agg_df.columns[1:]]

        return agg_df
    
    def data_agg(self, df, df15, df30, timeframe1:str, timeframe2:str):
        df['Time'] = pd.to_datetime(df['Time'])         # Daily
        df15['Time'] = pd.to_datetime(df15['Time'])     # 1H
        df30['Time'] = pd.to_datetime(df30['Time'])     # 4H

        # Ensure numeric
        def numeric_data(df):
            cols = ['Open', 'High', 'Low', 'Close', 'Volume']
            for col in cols:
                df[col] = pd.to_numeric(df[col], errors='coerce')
            return df

        df = numeric_data(df)
        df15 = numeric_data(df15)
        df30 = numeric_data(df30)

        # Generate features
        features_1h = self.add_indicators(df15, timeframe=timeframe1)
        features_4h = self.add_indicators(df30, timeframe=timeframe2)

        # Floor times to daily (align all to same day)
        df['Time_floor'] = df['Time'].dt.floor(self.floor_time)

        features_1h['Time_floor'] = features_1h['Time'].dt.floor(self.floor_time)
        features_4h['Time_floor'] = features_4h['Time'].dt.floor(self.floor_time)

        # Merge based on floored time
        df = df.merge(features_1h, on='Time_floor', how='left', suffixes=('', f'_{timeframe1}'))
        df = df.merge(features_4h, on='Time_floor', how='left', suffixes=('', f'_{timeframe2}'))

        # Shift merged features to prevent future leakage
        for col in df.columns:
            if col.endswith(f'_{timeframe1}') or col.endswith(f'_{timeframe2}'):
                df[col] = df[col].shift(1)

        # Clean up
        df.drop(columns=['Time_floor'], inplace=True)

        self.log(f'✅ Aggregation with {timeframe1}min and {timeframe2}min done!')

        return df

    def data_feature_eng(self, df):
        # Moving Averages
        df['SMA_15'] = df['Close'].rolling(window=15).mean()
        df['SMA_30'] = df['Close'].rolling(window=30).mean()
        df['SMA_60'] = df['Close'].rolling(window=60).mean()
        df['EMA_15'] = df['Close'].ewm(span=15, adjust=False).mean()
        df['EMA_30'] = df['Close'].ewm(span=30, adjust=False).mean()



        df['RSI'] = self.calculate_rsi(df['Close'])

        # MACD
        df['EMA_12'] = df['Close'].ewm(span=12, adjust=False).mean()
        df['EMA_26'] = df['Close'].ewm(span=26, adjust=False).mean()
        df['MACD'] = df['EMA_12'] - df['EMA_26']
        df['MACD_signal'] = df['MACD'].ewm(span=9, adjust=False).mean()
        df.drop(columns=['EMA_12','EMA_26'], inplace=True)

        # Bollinger Bands
        std = df['Close'].rolling(window=30).std()
        df['BB_upper'] = df['SMA_30'] + (std * 2)
        df['BB_lower'] = df['SMA_30'] - (std * 2)

        # ATR
        df['Prev_Close'] = df['Close'].shift(1)
        df['TR'] = np.maximum(
            df['High'] - df['Low'],
            np.abs(df['High'] - df['Prev_Close']),
            np.abs(df['Low'] - df['Prev_Close'])
        )
        df['ATR'] = df['TR'].rolling(window=14).mean()

        df.drop(columns=['Prev_Close'], inplace=True)

        # Volume-based
        df['Volume_SMA_15'] = df['Volume'].rolling(window=15).mean()
        df['Volume_SMA_30'] = df['Volume'].rolling(window=30).mean()

        # Clean missing rows
        df.dropna(inplace=True)

        self.log('data engineering Done!!!!!')
        return df
    
    def detect_fvgs(self,df):
        df = df.copy()
        df['Bullish_FVG'] = False
        df['Bearish_FVG'] = False

        # Vectorized approach for better performance
        df['Bullish_FVG'] = df['High'] < df['Low'].shift(2)
        df['Bearish_FVG'] = df['Low'] > df['High'].shift(2)

        self.log('Fair Value Gap Done!!!')
        return df
   
    def order_block_leak_free(self,df):
        df = df.copy()
        df['Bullish_OB'] = False
        df['Bearish_OB'] = False

        # Vectorized approach - mark current candle as OB if pattern occurred in past
        bear_candle = df['Close'] < df['Open']
        bull_candle = df['Close'] > df['Open']

        # Bullish OB: current candle is bullish, preceded by bear candle and bullish candle
        df['Bullish_OB'] = bull_candle & bear_candle.shift(1) & bull_candle.shift(2)

        # Bearish OB: current candle is bearish, preceded by bull candle and bearish candle
        df['Bearish_OB'] = bear_candle & bull_candle.shift(1) & bear_candle.shift(2)

        self.log('Order Block Done!!!')

        return df
    
    def liquidity(self,df):
        df['Liquidity_High'] = np.where(
        (df['High'].shift(1) > df['High'].shift(2)) & 
        (df['High'].shift(1) > df['High']),
        True,
        False)

        df['Liquidity_Low'] = np.where(
            (df['Low'].shift(1) < df['Low'].shift(2)) & 
            (df['Low'].shift(1) < df['Low']),
            True,
            False
        )
        self.log('Liquidity Done!!!')
        return df
    
    def time_session(self,df):
        df['Time'] = df['Time'].dt.tz_localize('UTC')  

        df['Hour'] = df['Time'].dt.hour


        # Add market session flags
        df['Asian_Session'] = df['Hour'].between(0, 8)   # 00:00–08:59
        df['London_Session'] = df['Hour'].between(7, 15)  # 07:00–15:59
        df['NY_Session'] = df['Hour'].between(13, 21)    # 13:00–21:59
        self.log('Session Time Done!!!')
        return df
    
    def add_volume_indicators(self,df):
        import ta
        from ta.volume import MFIIndicator
        df.set_index("Time", inplace=True)
        df = df.copy()
        df['psar'] = ta.trend.PSARIndicator(high=df['High'], low=df['Low'], close=df['Close']).psar()

        # 1. On-Balance Volume (OBV)
        obv = [0]
        for i in range(1, len(df)):
            if df['Close'][i] > df['Close'][i-1]:
                obv.append(obv[-1] + df['Volume'][i])
            elif df['Close'][i] < df['Close'][i-1]:
                obv.append(obv[-1] - df['Volume'][i])
            else:
                obv.append(obv[-1])
        df['OBV'] = obv

        # 2. VWAP (handle division by zero)
        volume_cumsum = df['Volume'].cumsum()
        df['VWAP'] = (df['Close'] * df['Volume']).cumsum() / volume_cumsum.replace(0, np.nan)

        # 3. Accumulation/Distribution Line (A/D Line)
        clv = ((df['Close'] - df['Low']) - (df['High'] - df['Close'])) / (df['High'] - df['Low'])
        clv = clv.replace([np.inf, -np.inf], 0).fillna(0)
        df['AD_Line'] = (clv * df['Volume']).cumsum()

        # 4. Chaikin Money Flow (CMF)
        df['CMF'] = (clv * df['Volume']).rolling(window=20).sum() / df['Volume'].rolling(window=20).sum()

        # 5. Price-Volume Trend (PVT)
        pvt = [0]
        for i in range(1, len(df)):
            change = (df['Close'][i] - df['Close'][i-1]) / df['Close'][i-1]
            pvt.append(pvt[-1] + df['Volume'][i] * change)
        df['PVT'] = pvt

        # 6. Money Flow Index (MFI)
        mfi = MFIIndicator(high=df['High'], low=df['Low'], close=df['Close'], volume=df['Volume'], window=14)
        df['MFI'] = mfi.money_flow_index()

        self.log('Volume Indicator Successfully Added!!!')

        return df

    def save_new_data_to_csv(data, file_path='full_data.csv'):
        # `data` should be a list of dicts or a DataFrame
        df = pd.DataFrame(data)
        df.to_csv(file_path, index=False)  # This overwrites the existing file

    def model_verification(self, df):
        from sklearn.preprocessing import StandardScaler
        from sklearn.model_selection import train_test_split
        from sklearn.metrics import classification_report, accuracy_score
        from lightgbm import LGBMClassifier
        from catboost import CatBoostClassifier
        from xgboost import XGBClassifier
        import numpy as np

        # --- Step 1: Feature Engineering for CRT Strategy ---
        df = df.copy()
        df['body_size'] = df['Close'] - df['Open']
        df['range'] = df['High'] - df['Low']
        df['body_ratio'] = df['body_size'] / df['range']
        df['upper_wick'] = df['High'] - df[['Close', 'Open']].max(axis=1)
        df['lower_wick'] = df[['Close', 'Open']].min(axis=1) - df['Low']
        
        # --- Step 2: Separate prediction row ---
        last_row = df.iloc[[-1]].copy()
        train_df = df.iloc[:-1].copy()

        X = train_df.drop(columns=['target'])
        y = train_df['target']
        X_pred = last_row.drop(columns=['target'])

        # --- Step 3: Train-test split ---
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.2, random_state=42, shuffle=False
        )

        # --- Step 4: Scale Features ---
        scaler = StandardScaler()
        X_train_scaled = scaler.fit_transform(X_train)
        X_test_scaled = scaler.transform(X_test)
        X_pred_scaled = scaler.transform(X_pred)

        # --- Step 5: Models ---
        models = {
            'lgb': LGBMClassifier(
                n_estimators=50,
                learning_rate=0.05,
                max_depth=2,
                reg_alpha=0.3,
                reg_lambda=0.5,
                subsample=0.85,
                colsample_bytree=0.7,
                random_state=42,
                n_jobs=-1,

            ),
            'cat': CatBoostClassifier(
                iterations=50,
                learning_rate=0.05,
                depth=4,
                l2_leaf_reg=3,
                subsample=0.8,
                colsample_bylevel=0.7,
                random_seed=42,
                verbose=0,
                eval_metric='Logloss',
                loss_function='Logloss'
            ),
            'xgb': XGBClassifier(
                n_estimators=50,
                learning_rate=0.05,
                max_depth=2,
                subsample=0.85,
                colsample_bytree=0.7,
                gamma=1,
                min_child_weight=3,
                reg_alpha=0.3,
                reg_lambda=1,
                scale_pos_weight=1,
                eval_metric='logloss',
                use_label_encoder=False,
                random_state=42,
                n_jobs=-1,
                tree_method='hist'
            )
        }

        last_row_predictions = {}
        last_row_probabilities = {}

        for name, model in models.items():
            if name == 'cat':
                model.fit(X_train_scaled, y_train, eval_set=(X_test_scaled, y_test), verbose=False)
            else:
                model.fit(X_train_scaled, y_train)
            
            y_pred = model.predict(X_test_scaled)
            
            self.log(f"\n--- {name.upper()} Model Evaluation ---")
            self.log(f"Test Accuracy : {accuracy_score(y_test, y_pred):.4f}")
            self.log(f"Classification Report:\n{classification_report(y_test, y_pred)}")

            train_preds = model.predict(X_train_scaled)
            train_pred_classes = (train_preds > 0.5).astype(int)
            self.log(f'"Train Accuracy:" {accuracy_score(y_train, train_pred_classes)}')
            self.log(f'"Classification Report: " {classification_report(y_train, train_pred_classes)}')
                        
            pred = model.predict(X_pred_scaled)[0]
            prob = model.predict_proba(X_pred_scaled)[0][1]
            last_row_predictions[name] = pred
            last_row_probabilities[name] = prob

        # --- Ensemble ---
        ensemble_prob = np.mean(list(last_row_probabilities.values()))
        ensemble_pred = int(ensemble_prob > 0.5)
        self.log(f"\nEnsemble Prediction at {last_row.index} is: {ensemble_pred}  | Prob: {ensemble_prob:.4f}")

    def Ensemble_model(self, df):
        from sklearn.preprocessing import StandardScaler
        from lightgbm import LGBMClassifier
        from catboost import CatBoostClassifier
        from xgboost import XGBClassifier
        import pandas as pd

        
        # --- Feature Engineering ---
        df['body_size'] = df['Close'] - df['Open']
        df['range'] = df['High'] - df['Low']
        df['body_ratio']= df['body_size'] / df['range']
        df['upper_wick'] = df['High'] - df[['Close', 'Open']].max(axis=1)
        df['lower_wick'] = df[['Close', 'Open']].min(axis=1) - df['Low']
        df['returns'] = df['Close'].pct_change()
        df['volatility_5'] = df['returns'].rolling(5).std()
        df['momentum_10'] = df['Close'].pct_change(10)
        df['log_return'] = np.log(df['Close'] / df['Close'].shift(1))
        df['rolling_vol'] = df['log_return'].rolling(10).std()
        df['momentum_5'] = df['Close'] - df['Close'].shift(5)
        df['close_ma_ratio'] = df['Close'] / df['Close'].rolling(20).mean()
        df['range_ma_ratio'] = df['range'] / df['range'].rolling(20).mean()
        df['engulfing'] = (
            (df['Close'] > df['Open'].shift(1)) &
            (df['Open'] < df['Close'].shift(1))
        ).astype(int)

        df['bos'] = (df['High'] > df['High'].shift(1)) & (df['Low'] > df['Low'].shift(1))  # Break of structure
        df['trend_up'] = (df['Close'] > df['Close'].rolling(3).mean())  # basic trend direction
        df['consolidating'] = df['range'].rolling(5).std() < df['range'].rolling(5).mean() * 0.5  # low volatility = range
        df['change_of_character'] = (df['bos'] != df['bos'].shift(1)).astype(int)  # sudden shift
            
        for col in ['bos', 'trend_up', 'consolidating', 'change_of_character']:
            df[col] = df[col].astype(int)


        df.dropna(inplace=True)


        df.drop(columns=[f'Time_{self.timeframe1}' , f'Time_{self.timeframe2}'],inplace=True)

            # Create binary classification target
        df['target'] = (df['Close'].shift(-1) > df['Open'].shift(-1)).astype(int)

        # Prepare training and prediction data
        last_row = df.iloc[[-1]].copy()
        train_df = df[:-1].dropna()  # Ensure no NaNs

        features = train_df.drop(columns=['target'])
        target = train_df['target']
        prediction_features = last_row.drop(columns=['target'])

        # Ensure numeric data
        assert all(pd.api.types.is_numeric_dtype(features[col]) for col in features.columns), "Only numeric features allowed."

        # Feature scaling
        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(features)
        prediction_scaled = scaler.transform(prediction_features)

        # Define models
        models = {
            'lgb': LGBMClassifier(
                n_estimators=50,
                learning_rate=0.02,
                max_depth=2,
                reg_alpha=0.3,
                reg_lambda=0.5,
                subsample=0.85,
                colsample_bytree=0.7,
                random_state=42,
                n_jobs=-1
            ),
            'cat': CatBoostClassifier(
                iterations=50,
                learning_rate=0.01,
                depth=2,
                l2_leaf_reg=3,
                subsample=0.8,
                colsample_bylevel=0.7,
                random_seed=42,
                verbose=0,
                eval_metric='Logloss',
                loss_function='Logloss'
            ),
            'xgb': XGBClassifier(
                n_estimators=50,
                learning_rate=0.02,
                max_depth=2,
                subsample=0.85,
                colsample_bytree=0.7,
                gamma=1,
                min_child_weight=3,
                reg_alpha=0.3,
                reg_lambda=1,
                scale_pos_weight=1,
                eval_metric='logloss',
                use_label_encoder=False,
                random_state=42,
                n_jobs=-1,
                tree_method='hist'
            )
        }

        # Train models on full data
        # Train and predict
        last_predicted_probs = []
        for name, model in models.items():
            model.fit(X_scaled, target)
            prob = model.predict_proba(prediction_scaled)[:, 1][0]
            last_predicted_probs.append(prob)

        # Ensemble result
        last_predicted_prob = sum(last_predicted_probs) / len(last_predicted_probs)

        self.log(f'{str(last_row)}')
        self.log("="*40)
        self.log("REAL-TIME ENSEMBLE PREDICTION")
        self.log("="*40)
        self.log(f"Class (based on 0.5 threshold) at {last_row.index} is:, {int(last_predicted_prob > 0.5)}")
        return last_predicted_prob

    def main(self):
        from .FeautureHandeler import FeatureGenerator
        try:
            self.log("✅ initialing FeatureGenerator Started.....")
            fg = FeatureGenerator(t1=self.d1, t2=self.d2, t3=self.d3,floor_time = self.floor_time, symbol=self.symbol, timeframe1=self.timeframe1, timeframe2=self.timeframe2,log = self.log)
            fg.update()
            self.full_df = fg.get_full_buffer()
            
            if self.full_df is not None:
                if len(str(self.full_df)) < 1000:
                    self.log(f"📊 Full data:\n{self.full_df.tail()}")
                else:
                    print(f"📊 Data sample:\n{self.full_df.shape()}")
                    self.log(f"🔢 Data shape: {getattr(self.full_df, 'shape', len(self.full_df))}")
            else:
                self.log('Data is None')
            
            prediction = self.Ensemble_model(self.full_df)
            self.log(f"✅ Prediction complete. predicted value: {prediction}")

            if self.report:
                self.model_verification(self.full_df)
        except Exception as e:
            self.log(f"🚨 Critical error in main(): {e}")
        finally:
            mt5.shutdown()

        return prediction


