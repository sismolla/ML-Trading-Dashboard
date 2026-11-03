import pandas as pd
import numpy as np
import pandas_ta as ta
from tqdm import tqdm
import joblib

class SmartMoneyZones:
    def __init__(self, atr_period=14, ema_fast=9, ema_slow=21):
        self.order_blocks = []
        self.fvgs = []
        self.atr_period = atr_period
        self.ema_fast = ema_fast
        self.ema_slow = ema_slow

    def update_indicators(self, df):
        # Calculate technical indicators
        df['atr'] = ta.atr(df['high'], df['low'], df['close'], length=self.atr_period)
        df[f'ema_{self.ema_fast}'] = ta.ema(df['close'], length=self.ema_fast)
        df[f'ema_{self.ema_slow}'] = ta.ema(df['close'], length=self.ema_slow)
        return df

    def detect_order_blocks(self, df, start_idx, end_idx):
        for i in range(max(1, start_idx), end_idx):
            prev = df.iloc[i - 1]
            curr = df.iloc[i]

            bullish_ob = (prev['close'] < prev['open']) and \
                         (curr['close'] > curr['open']) and \
                         (curr['open'] < prev['close']) and \
                         (curr['close'] > prev['open'])

            bearish_ob = (prev['close'] > prev['open']) and \
                         (curr['close'] < curr['open']) and \
                         (curr['open'] > prev['close']) and \
                         (curr['close'] < prev['open'])

            if bullish_ob or bearish_ob:
                ob = {
                    'side': 'bullish' if bullish_ob else 'bearish',
                    'high': prev['high'],
                    'low': prev['low'],
                    'mid': (prev['high'] + prev['low']) / 2,
                    'start_idx': i - 1,
                    'age': 0,
                    'tap_count': 0,
                    'reaction_strength': 0,
                    'is_mitigated': False
                }
                self.order_blocks.append(ob)

    def detect_fvgs(self, df, start_idx, end_idx):
        for i in range(max(1, start_idx), min(len(df) - 1, end_idx)):
            prev = df.iloc[i - 1]
            curr = df.iloc[i]
            nxt = df.iloc[i + 1]

            if nxt['low'] > prev['high']:
                fvg = {
                    'side': 'bullish',
                    'high': prev['high'],
                    'low': curr['low'],
                    'mid': (prev['high'] + curr['low']) / 2,
                    'start_idx': i,
                    'age': 0,
                    'tap_count': 0,
                    'reaction_strength': 0,
                    'is_mitigated': False
                }
                self.fvgs.append(fvg)
            elif nxt['high'] < prev['low']:
                fvg = {
                    'side': 'bearish',
                    'high': curr['high'],
                    'low': prev['low'],
                    'mid': (curr['high'] + prev['low']) / 2,
                    'start_idx': i,
                    'age': 0,
                    'tap_count': 0,
                    'reaction_strength': 0,
                    'is_mitigated': False
                }
                self.fvgs.append(fvg)

    def price_in_zone(self, price, zone):
        return zone['low'] <= price <= zone['high']

    def update_zones(self, df, idx):
        if pd.isna(df.at[idx, 'atr']):
            return
            
        row = df.iloc[idx]
        price = row['close']
        atr = row['atr']
        volume = row['volume']
        volume_max = df['volume'].rolling(100).max().iloc[idx]
        
        body = abs(row['close'] - row['open'])
        range_ = row['high'] - row['low']
        body_ratio = body / range_ if range_ > 0 else 0
        volume_score = volume / volume_max if volume_max > 0 else 0

        for zone in self.order_blocks + self.fvgs:
            zone['age'] += 1
            
            # Check zone tap
            if self.price_in_zone(price, zone):
                zone['tap_count'] += 1
                zone['reaction_strength'] = max(
                    zone['reaction_strength'], 
                    body_ratio * volume_score
                )
            
            # Check zone mitigation with ATR-based threshold
            threshold = 0.5 * atr
            if zone['side'] == 'bullish':
                if price < zone['low'] - threshold:
                    zone['is_mitigated'] = True
            else:  # Bearish zone
                if price > zone['high'] + threshold:
                    zone['is_mitigated'] = True

    def detect_liquidity_sweep(self, df, idx, lookback=5):
        if idx < lookback or lookback <= 0:
            return 0
        highs = df['high'].iloc[idx - lookback: idx]
        lows = df['low'].iloc[idx - lookback: idx]
        curr = df.iloc[idx]
        return int(curr['high'] > highs.max() or curr['low'] < lows.min())

    def detect_break_of_structure(self, df, idx, lookback=10):
        if idx < lookback or lookback <= 0:
            return 0
        highs = df['high'].iloc[idx - lookback: idx]
        lows = df['low'].iloc[idx - lookback: idx]
        close = df.iloc[idx]['close']
        return int(close > highs.max() or close < lows.min())

    def get_trend_direction(self, df, idx):
        if idx < self.ema_slow or pd.isna(df.at[idx, f'ema_{self.ema_fast}']):
            return 0
        return 1 if df.at[idx, f'ema_{self.ema_fast}'] > df.at[idx, f'ema_{self.ema_slow}'] else -1
    
    def closest_zone(self, zones, price, atr):
        if not zones:
            return None
            
        # Find closest zone using volatility-scaled distance
        return min(
            zones,
            key=lambda z: min(
                abs(price - z['low']) / atr,
                abs(price - z['high']) / atr,
                abs(price - z['mid']) / atr
            )
        )


def create_features_labels(df, refresh_interval=500):
    """Sequential processing with state management"""
    # Initialize smart money detector
    smz = SmartMoneyZones()
    df = smz.update_indicators(df)
    
    features = []
    labels = []
    
    # Warm-up period for indicators
    start_idx = max(smz.atr_period, smz.ema_slow, 2)
    
    for i in tqdm(range(start_idx, len(df))):
        # Periodically refresh zones (not full reset)
        if i % refresh_interval == 0:
            smz.detect_order_blocks(df, i - refresh_interval, i)
            smz.detect_fvgs(df, i - refresh_interval, i)
        
        # Update all zones with current candle
        smz.update_zones(df, i)
        
        active_obs = [z for z in smz.order_blocks if not z['is_mitigated']]
        active_fvgs = [z for z in smz.fvgs if not z['is_mitigated']]
        
        # Get current market state
        price = df.iloc[i]['close']
        atr = df.at[i, 'atr']
        volume = df.iloc[i]['volume']
        volume_ma = df['volume'].rolling(20).mean().iloc[i]
        
        # Find most relevant zones
        ob = smz.closest_zone(active_obs, price, atr)
        fvg = smz.closest_zone(active_fvgs, price, atr)
        
        # Build features
        ob_feature = {
            'ob_strength': 0, 
            'ob_age': 999, 
            'ob_tap_count': 0, 
            'ob_reaction_strength': 0, 
            'ob_side': 0
        }
        if ob and volume > volume_ma * 0.7:  # Volume filter
            ob_feature = {
                'ob_strength': max(0, 1 - ob['age'] / 20),
                'ob_age': ob['age'],
                'ob_tap_count': ob['tap_count'],
                'ob_reaction_strength': ob['reaction_strength'],
                'ob_side': 1 if ob['side'] == 'bullish' else -1
            }

        fvg_feature = {
            'fvg_strength': 0, 
            'fvg_age': 999, 
            'fvg_tap_count': 0, 
            'fvg_reaction_strength': 0, 
            'fvg_side': 0
        }
        if fvg and volume > volume_ma * 0.7:  # Volume filter
            fvg_feature = {
                'fvg_strength': max(0, 1 - fvg['age'] / 20),
                'fvg_age': fvg['age'],
                'fvg_tap_count': fvg['tap_count'],
                'fvg_reaction_strength': fvg['reaction_strength'],
                'fvg_side': 1 if fvg['side'] == 'bullish' else -1
            }

        # Additional market features
        liquidity_sweep = smz.detect_liquidity_sweep(df, i)
        bos = smz.detect_break_of_structure(df, i)
        trend = smz.get_trend_direction(df, i)
        hour = df.iloc[i]['time'].hour
        session_london = int(7 <= hour <= 16)
        session_ny = int(12 <= hour <= 21)
        
        # Confluence scoring
        confluence = sum([
            ob_feature['ob_tap_count'] > 0,
            fvg_feature['fvg_tap_count'] > 0,
            liquidity_sweep,
            bos,
            session_london,
            session_ny,
            (trend > 0 and (ob_feature['ob_side'] > 0 or fvg_feature['fvg_side'] > 0)),
            (trend < 0 and (ob_feature['ob_side'] < 0 or fvg_feature['fvg_side'] < 0))
        ])
        
        entry = (ob_feature['ob_tap_count'] > 0 or fvg_feature['fvg_tap_count'] > 0) and \
                confluence >= 4 and \
                ((trend > 0 and (ob_feature['ob_side'] > 0 or fvg_feature['fvg_side'] > 0)) or \
                (trend < 0 and (ob_feature['ob_side'] < 0 or fvg_feature['fvg_side'] < 0)))
        
        # Dynamic labeling with volatility scaling
        label = 0
        if entry and i + 5 < len(df):
            future_price = df.iloc[i + 5]['close']
            price_move = (future_price - price) / price
            target = 0.5 * atr / price  # 0.5 ATR move
            
            if price_move > target:
                label = 1
            elif price_move < -target:
                label = -1

        # Compile features
        features.append({
            'time': df.iloc[i]['time'],
            'open' : df.iloc[i]['open'],
            'close' : df.iloc[i]['close'],
            'high' : df.iloc[i]['high'],
            'low' : df.iloc[i]['low'],
            'volume' : df.iloc[i]['volume'],
            **ob_feature,
            **fvg_feature,
            'liquidity_sweep': liquidity_sweep,
            'bos_confirmed': bos,
            'session_london': session_london,
            'session_ny': session_ny,
            'confluence_score': confluence,
            'trend': trend,
            'entry':entry,
            'vol_above_ma': int(volume > volume_ma),
            'atr_pct': atr / price
        })
        labels.append(label)

    return pd.DataFrame(features), pd.Series(labels)