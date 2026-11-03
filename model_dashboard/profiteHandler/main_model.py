import MetaTrader5 as mt5
import pandas as pd
import numpy as np
import sys

class ModelLearning:
    def __init__(self,d1, symbol="EURUSDm", num_bars=100000, chunk_size=100000,report=False):
        self.symbol = symbol
        self.num_bars = num_bars
        self.chunk_size = chunk_size
        self.data = pd.DataFrame()
        self.d1 = d1
        self.full_df = None        

        self.report = report

    def mt5_downloader(self,timeframe):

        if not mt5.initialize():
            print("❌ MT5 initialization failed.")
            sys.exit()
            return pd.DataFrame()
        

        if not mt5.symbol_select(self.symbol, True):
            print(f"❌ Symbol '{self.symbol}' not found or not visible in Market Watch.")
            mt5.shutdown()
            sys.exit()
            return pd.DataFrame()

        candles = mt5.copy_rates_from_pos(self.symbol, timeframe, 1, self.num_bars)

        if candles is None:
            print("❌ Failed to retrieve data.")
            mt5.shutdown()
            return pd.DataFrame()

        self.data = pd.DataFrame(candles)
        self.data['time'] = pd.to_datetime(self.data['time'], unit='s')
        self.data.drop(columns=['real_volume'], inplace=True)

        print(f"\n✅ Downloaded {len(self.data)} candles for {self.symbol} on {self.d1}.")

        mt5.shutdown()

        return self.data
    
    def change_header(self,df):
        df = df.rename(columns={'time': 'Time', 'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close', 'tick_volume': 'Volume'})
        return df

    def calculate_rsi(self,data, window=5):
        delta = data.diff()
        gain = delta.where(delta > 0, 0).rolling(window=window).mean()
        loss = -delta.where(delta < 0, 0).rolling(window=window).mean()
        rs = gain / loss
        return 100 - (100 / (1 + rs))

    def calculate_stochastic_d(self,df, k_window=14, d_window=3):
        low_min = df['Low'].rolling(window=k_window).min()
        high_max = df['High'].rolling(window=k_window).max()
        stochastic_k = 100 * ((df['Close'] - low_min) / (high_max - low_min))
        stochastic_d = stochastic_k.rolling(window=d_window).mean()
        return stochastic_d

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

        print('data engineering Done!!!!!')
        return df
    
    def detect_fvgs(self,df):
        df = df.copy()
        df['Bullish_FVG'] = False
        df['Bearish_FVG'] = False
        print('okay')
        
        for i in range(2, len(df)):
            # Bullish FVG condition (current high < previous low)
            if df['High'].iloc[i] < df['Low'].iloc[i-2]:
                df['Bullish_FVG'].iloc[i] = True

            
            # Bearish FVG condition (current low > previous high)
            if df['Low'].iloc[i] > df['High'].iloc[i-2]:
                df['Bearish_FVG'].iloc[i] = True

        print('Fair Value Gap Done!!!')
        return df
   
    def order_block_leak_free(self,df):
        df = df.copy()
        df['Bullish_OB'] = False
        df['Bearish_OB'] = False
        
        for i in range(2, len(df) - 2):
            # Bullish Order Block (bear candle followed by 2 bull candles)
            if (df['Close'].iloc[i] < df['Open'].iloc[i] and       # Current candle is bearish
                df['Close'].iloc[i+1] > df['Open'].iloc[i+1] and   # Next candle is bullish
                df['Close'].iloc[i+2] > df['Open'].iloc[i+2]):     # Following candle is bullish
                df.at[df.index[i], 'Bullish_OB'] = True
            
            if (df['Close'].iloc[i] > df['Open'].iloc[i] and       # Current candle is bullish
                df['Close'].iloc[i+1] < df['Open'].iloc[i+1] and   # Next candle is bearish
                df['Close'].iloc[i+2] < df['Open'].iloc[i+2]):     # Following candle is bearish
                df.at[df.index[i], 'Bearish_OB'] = True

        print('Order Block Done!!!')

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
        print('Liquidity Done!!!')
        return df
    
    def time_session(self,df):
        df['Time'] = df['Time'].dt.tz_localize('UTC')  

        df['Hour'] = df['Time'].dt.hour


        # Add market session flags
        df['Asian_Session'] = df['Hour'].between(0, 8)   # 00:00–08:59
        df['London_Session'] = df['Hour'].between(7, 15)  # 07:00–15:59
        df['NY_Session'] = df['Hour'].between(13, 21)    # 13:00–21:59
        print('Session Time Done!!!')
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

        # 2. VWAP
        df['VWAP'] = (df['Close'] * df['Volume']).cumsum() / df['Volume'].cumsum()

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

        print('Volume Indicator Successfully Added!!!')

        return df

    def save_new_data_to_csv(data, file_path='full_data.csv'):
        # `data` should be a list of dicts or a DataFrame
        df = pd.DataFrame(data)
        df.to_csv(file_path, index=False)  # This overwrites the existing file

    def model_verification(self,df):
        from sklearn.preprocessing import StandardScaler
        from sklearn.model_selection import train_test_split
        from sklearn.metrics import classification_report, accuracy_score
        from lightgbm import LGBMClassifier
        from catboost import CatBoostClassifier
        from xgboost import XGBClassifier
        import pandas as pd
        import numpy as np

        last_row = df.iloc[[-1]].copy()
        train_df = df.iloc[:-1].copy()
        
        X = train_df.drop(columns=['target'])
        y = train_df['target']
        X_pred = last_row.drop(columns=['target'])

        # Step 2: Train-test split
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.2, random_state=42, shuffle=False
        )

        # Step 3: Scale features
        scaler = StandardScaler()
        X_train_scaled = scaler.fit_transform(X_train)
        X_test_scaled = scaler.transform(X_test)
        X_pred_scaled = scaler.transform(X_pred)

        # --- Model Definitions ---
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
                n_jobs=-1
            ),
            'cat': CatBoostClassifier(
                iterations=50,
                learning_rate=0.05,
                depth=2,
                l2_leaf_reg=3,
                subsample=0.8,
                colsample_bylevel=0.7,
                random_seed=42,
                verbose=0,
                early_stopping_rounds=50,
                use_best_model=True,
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
            
            # Predict on test set for evaluation
            y_pred = model.predict(X_test_scaled)
            
            print(f"\n--- {name.upper()} Model Evaluation ---")
            print(f"Test Accuracy : {accuracy_score(y_test, y_pred):.4f}")
            print(f"Classification Report:\n{classification_report(y_test, y_pred)}")

            train_preds = model.predict(X_train_scaled)
            train_pred_classes = (train_preds > 0.5).astype(int)
            print("Train Accuracy:", accuracy_score(y_train, train_pred_classes))
            print(classification_report(y_train, train_pred_classes))
                        
            # Predict on last row for final prediction
            pred = model.predict(X_pred_scaled)[0]
            print(y_pred[int(len(y_pred)-5):])
            prob = model.predict_proba(X_pred_scaled)[0][1]
            last_row_predictions[name] = pred
            last_row_probabilities[name] = prob
            

        # --- Ensemble ---
        ensemble_prob = np.mean(list(last_row_probabilities.values()))
        ensemble_pred = int(ensemble_prob > 0.5)
        return ensemble_pred

        
    
    def Ensemble_model(self, df):
        from sklearn.preprocessing import StandardScaler
        from lightgbm import LGBMClassifier
        from catboost import CatBoostClassifier
        from xgboost import XGBClassifier
        import pandas as pd

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

        print(str(last_row))
        print("="*40)
        print("REAL-TIME ENSEMBLE PREDICTION")
        print("="*40)
        print("Class (based on 0.5 threshold):", int(last_predicted_prob > 0.5))
        return last_predicted_prob
    
    def df_add(self,df):
        
        train = df.copy()
        train['close_ma_ratio'] = train['Close'] / train['Close'].rolling(9).mean()
        train['range'] = train['High'] - train['Low']
        train['upper_wick'] = train['High'] - train[['Close', 'Open']].max(axis=1)
        train['lower_wick'] = train[['Close', 'Open']].min(axis=1) - train['Low']
        train['momentum_14'] = train['Close'].pct_change(10)
        train['momentum_5'] = train['Close'] - train['Close'].shift(5)
        train['range_ma_ratio'] = train['range'] / train['range'].rolling(14).mean()

        train['engulfing'] = (
            (train['Close'] > train['Open'].shift(1)) &
            (train['Open'] < train['Close'].shift(1))
        ).astype(int)


        return train
    
    def main(self):
        from .feauters import FeatureGenerator
        from sklearn.model_selection import train_test_split

        try:
            print("✅ initialing FeatureGenerator Started.....")
            fg = FeatureGenerator(t1=self.d1,symbol=self.symbol)
            fg.update()
            self.full_df = fg.get_full_buffer()
            self.full_df = self.df_add(self.full_df)
            
            self.full_df['target'] = (self.full_df['Close'].shift(-1) > self.full_df['Open'].shift(-1)).astype(int)


            train_df = self.full_df[:-1].dropna()

            # --- Split data into features and target ---
            features = train_df.drop(columns=['target'])
            target = train_df['target']

            X_train, X_test, y_train, y_test = train_test_split(
                features, target, test_size=0.15, shuffle=False
            )

            
            if self.full_df is not None:
                if len(str(self.full_df)) < 1000:
                    print(f"📊 Full data:\n{self.full_df.tail()}")
                else:
                    print(f"📊 Data sample:\n{self.full_df.tail()}")
                    print(f"🔢 Data shape: {getattr(self.full_df, 'shape', len(self.full_df))}")
            else:
                print('Data is None')
            if self.report:
                verify_pred = self.model_verification(self.full_df)
                print(f"✅ Verification Prediction complete. predicted value: {verify_pred}")
                prediction = self.Ensemble_model(self.full_df)
                print(f"✅ Prediction complete. predicted value: {prediction}")



        except Exception as e:
            print(f"🚨 Critical error in main(): {e}")
        finally:
            mt5.shutdown()

        return self.full_df,X_test


