# views.py
from django.views.generic import TemplateView
import pandas as pd
from .models import Prediction_values
from .main_model import ModelLearning 
import pickle
from datetime import datetime
import pytz,json
import plotly.graph_objects as go
from plotly.offline import plot

class FXDashboardView(TemplateView):
    template_name = 'profiteHandler/dashboard_view.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        import os
        filename = 'C:/Users/HP/Desktop/ml_dashboard/model_dashboard/profiteHandler/trained_model_finalisma.pkl'

        if not os.path.exists(filename):
            context['error'] = 'Model file not found'
            return context

        with open(filename, 'rb') as file:
            loaded_model = pickle.load(file)

        import MetaTrader5 as mt5
        models = ModelLearning(d1=mt5.TIMEFRAME_H4, symbol='XAUUSDm', num_bars=100000)
        df, X_new_data = models.main()

        if df is None or df.empty:
            context['error'] = 'Failed to retrieve data from MT5'
            return context
        
        
        last_row = df.iloc[[-1]].copy()
        prediction_features = last_row.drop(columns=['target'])

        # Ensure the model receives the correct input format
        last_row_prediction = loaded_model.predict(prediction_features)[0]  # Extract single value
        last_row_prediction_prob = loaded_model.predict_proba(prediction_features)[0]  # First row



        formatted_date = prediction_features.index[-1].strftime('%Y-%m-%d %H:%M')

        if formatted_date and last_row_prediction_prob is not None:
            Prediction_values.objects.create(
                index=formatted_date,
                predicted=int(last_row_prediction),
                predicted_prob=float(max(last_row_prediction_prob))  # e.g., probability of predicted class
            )
        else:
            print('Saving prediction failed!!')
            
        recent_pred_display = f"Predicted for {formatted_date}: {last_row_prediction}"


        predictions = loaded_model.predict(X_new_data)
        test_results = pd.DataFrame({'predicted_label': predictions}, index=X_new_data.index)

        shifted_preds = test_results['predicted_label'].shift(1).dropna()
        df_test_aligned = df.loc[shifted_preds.index]

        # Run strategy
        result_df = test_xauusd_strategy(
            df_test_aligned,
            shifted_preds,
            initial_capital=100,
            sl_pips=150,
            commission=0.5,
            tp_pips=400,
        )

        result_df.index = pd.to_datetime(result_df.index)

        # Plotly Candlestick Chart
        ohlc_data = result_df[['open', 'high', 'low', 'close','prediction','true','hit_sl']].tail(100).copy()
        ohlc_data['Date'] = result_df.index[-100:]

        candlestick = go.Figure(data=[
            go.Candlestick(
                x=ohlc_data['Date'],
                open=ohlc_data['open'],
                high=ohlc_data['high'],
                low=ohlc_data['low'],
                close=ohlc_data['close'],
                increasing_line_color='#50fa7b',
                decreasing_line_color='#ff5555'
            )
        ])

        # Add dots (e.g., where close > open)
        condition = ohlc_data['prediction'] == ohlc_data['true']
        candlestick.add_trace(
            go.Scatter(
                x=ohlc_data['Date'][condition],
                y=ohlc_data['high'][condition] + 2,  # Offset dots slightly above high
                mode='markers',
                marker=dict(color='cyan', size=8, symbol='circle'),
                name='Signal Dots'
            )
        )

        # 2. Stop-Loss hits (new condition)
        sl_condition = ohlc_data['hit_sl']  # Assuming this column exists
        candlestick.add_trace(
            go.Scatter(
                x=ohlc_data['Date'][sl_condition],
                y=ohlc_data['low'][sl_condition] - 2,  # Place below low
                mode='markers',
                marker=dict(color='orange', size=10, symbol='triangle-down'),
                name='Stop-Loss Hit'
            )
        )



        candlestick.update_layout(
            template='plotly_dark',
            title='Candlestick Chart (Last 100)',
            xaxis_rangeslider_visible=False
        )
        candlestick_div = plot(candlestick, output_type='div', include_plotlyjs=False)

        # Time-based profits
        utc_now = datetime.now(pytz.UTC)
        today = utc_now.date()
        today_mask = result_df.index.date == today

        this_week = utc_now.isocalendar()[1]
        this_year = utc_now.year
        this_month = utc_now.month

        weekly_mask = (result_df.index.isocalendar().week == this_week) & (result_df.index.isocalendar().year == this_year)
        monthly_mask = (result_df.index.month == this_month) & (result_df.index.year == this_year)

        today_profit = result_df.loc[today_mask, 'profit'].sum()
        weekly_profit = result_df.loc[weekly_mask, 'profit'].sum()
        monthly_profit = result_df.loc[monthly_mask, 'profit'].sum()

        # JSON OHLCV for JS fallback (optional if you're fully Plotly-based)
        ohlcv_data_for_js = result_df.tail(100).copy()
        ohlcv_data_for_js['Date'] = ohlcv_data_for_js.index.strftime('%Y-%m-%dT%H:%M:%S')

        ohlcv_json = json.dumps([
            {
                'Date': row['Date'],
                'open': row['open'],
                'high': row['high'],
                'low': row['low'],
                'close': row['close'],
            }
            for _, row in ohlcv_data_for_js.iterrows()
        ])

        context.update({
            'recent_pred':recent_pred_display,
            'today_profit': f'${round(today_profit, 2)}',
            'weekly': f"This Week ({this_year}-W{this_week}): ${round(weekly_profit, 2)}",
            'monthly': f"{this_year}-{this_month:02d}: ${round(monthly_profit, 2)}" ,          
            'equity': result_df['equity'].tail(100).tolist(),
            'candlestick_div': candlestick_div,
            'ohlcv_data': ohlcv_json, 
        })

        return context

def test_xauusd_strategy(
    df, 
    predictions, 
    initial_capital=100.0, 
    sl_pips=100, 
    tp_pips=150,   # ✅ NEW: take profit in pips (optional)
    spread_pips=3, 
    commission=0.07,    
    lot_size=0.01       
):
    capital = initial_capital
    equity_curve = []
    results = []

    pip_to_price_unit = 0.1 
    sl_price_diff = sl_pips * pip_to_price_unit
    tp_price_diff = tp_pips * pip_to_price_unit
    spread_price = spread_pips * pip_to_price_unit
    pip_value_per_lot = lot_size * 10 

    sl_count = 0
    tp_count = 0
    wrong_dir_count = 0 
    win_count = 0
    trade_count = 0

    for i in range(len(predictions) - 1):
        idx = predictions.index[i]
        next_idx = predictions.index[i + 1]

        pred = predictions.iloc[i]
        true = df.loc[idx, 'target']
        open_price = df.loc[next_idx, 'Open']
        high = df.loc[next_idx, 'High']
        low = df.loc[next_idx, 'Low']
        close = df.loc[next_idx, 'Close']

        entry_price = open_price + (spread_price / 2 if pred == 1 else -spread_price / 2)
        stop_loss_price = entry_price - sl_price_diff if pred == 1 else entry_price + sl_price_diff
        take_profit_price = entry_price + tp_price_diff if pred == 1 else entry_price - tp_price_diff

        hit_sl = False
        hit_tp = False
        direction_wrong = False
        outcome = ''
        exit_price = close

        # === Trade Management ===
        if pred == 1:  # Buy
            if low <= stop_loss_price and high >= take_profit_price:
                # SL and TP both hit; first hit wins. Assume worst-case: SL hit first.
                if low - stop_loss_price < take_profit_price - high:
                    exit_price = stop_loss_price
                    hit_sl = True
                else:
                    exit_price = take_profit_price
                    hit_tp = True
            elif low <= stop_loss_price:
                exit_price = stop_loss_price
                hit_sl = True
            elif high >= take_profit_price:
                exit_price = take_profit_price
                hit_tp = True
        else:  # Sell
            if high >= stop_loss_price and low <= take_profit_price:
                if high - stop_loss_price < take_profit_price - low:
                    exit_price = stop_loss_price
                    hit_sl = True
                else:
                    exit_price = take_profit_price
                    hit_tp = True
            elif high >= stop_loss_price:
                exit_price = stop_loss_price
                hit_sl = True
            elif low <= take_profit_price:
                exit_price = take_profit_price
                hit_tp = True

        # Direction check if neither SL nor TP was hit
        if not hit_sl and not hit_tp:
            if (pred == 1 and close < open_price) or (pred == 0 and close > open_price):
                direction_wrong = True

        # === Profit Calculation ===
        price_diff_raw = (exit_price - entry_price) if pred == 1 else (entry_price - exit_price)
        pips_moved = price_diff_raw / pip_to_price_unit 
        profit = pips_moved * pip_value_per_lot
        profit -= commission
        capital += profit
        equity_curve.append(capital)
        trade_count += 1

        # === Outcome Classification ===
        if hit_sl:
            outcome = 'SL Loss'
            sl_count += 1
        elif hit_tp:
            outcome = 'TP Hit'
            tp_count += 1
            win_count += 1
        elif direction_wrong:
            outcome = 'Wrong Direction'
            wrong_dir_count += 1
        else:
            outcome = 'Win'
            win_count += 1

        results.append({
            'index': next_idx,
            'initial_capital':initial_capital,
            'entry': round(entry_price, 3),
            'exit': round(exit_price, 3),
            'profit': round(profit, 2),
            'capital': round(capital, 2),
            'hit_sl': hit_sl,
            'hit_tp': hit_tp,
            'direction_wrong': direction_wrong,
            'true': 'Bullish' if true == 1 else 'Bearish',
            'prediction': 'Bullish' if pred == 1 else 'Bearish',
            'outcome': outcome,
            'close': close,
            'open': open_price,
            'high':high,
            'low':low,
            'pips_moved': round(pips_moved, 1),
            'lot_size': lot_size
        })

    # === Create Results DataFrame ===
    result_df = pd.DataFrame(results).set_index('index')
    result_df['equity'] = equity_curve
    if trade_count > 0:
        print(f"Win Rate             : {win_count / trade_count * 100:.2f}%")
    else:
        print("Win Rate             : N/A (No trades executed)")
    
    return result_df


