import threading
import uuid
from django.http import JsonResponse
from django.views.generic import FormView
from django.urls import reverse
from django.shortcuts import redirect, render
from django.views import View
from django.core.cache import cache
import MetaTrader5 as mt5
from django.db import transaction
from django.utils import timezone
from .forms import ModelLaunchForm
from .models import Prediction
from datetime import datetime, timedelta
from .Ml_model import ModelLearning
from django.views.generic import TemplateView
from django.db.models import Count, Q
import plotly.express as px
from plotly.offline import plot
import pandas as pd

def model_runner(job_id, params):
    cache.set(job_id, [], timeout=86400)
    
    def log(msg):
        print(str(msg), flush=True)
        current_logs = cache.get(job_id, [])
        updated_logs = current_logs + [msg]
        cache.set(job_id, updated_logs, timeout=86400)
    
    try:
        log(f"🚀 Launching model for symbol: {params['symbol']}")
        log(f"the model is based on : {params['floor_time'],params['timeframe1'],params['timeframe2'],}")

        # Pass the log function to ModelLearning
        model = ModelLearning(
            d1=params['d1'],
            d2=params['d2'],
            d3=params['d3'],
            log=log,
            floor_time=params['floor_time'],
            timeframe1=params['timeframe1'],
            timeframe2=params['timeframe2'],
            symbol=params['symbol'],
            num_bars=params['num_bars'],
            report = True
        )

        log("✅ Model initialized successfully.")
        log(f'floor_time to: {params["floor_time"]}')
        prediction = model.main()
        log("🎯 Model finished running.")

        value = 'Buy' if prediction > 0.5 else 'Sell'
        save_prediction(symbol=params['symbol'], value=value,prob=prediction,timeframe_str=params['floor_time'])

    except Exception as e:
        log(f"❌ Error running model: {str(e)}")

        
class ModelLaunchView(FormView):
    template_name = 'dashboard.html'
    form_class = ModelLaunchForm

    
    SYMBOL_CHOICES = [
        ('ETHUSDm', 'ETH/USD'),
        ('XAUUSDm', 'Gold/USD'),
        ('USDJPYm', 'USD/JPY'),
        ('USDCHFm', 'USD/CHF'),

    ]

    TIMEFRAME_CHOICES = [
        ('TIMEFRAME_D1', 'D1'),
        ('TIMEFRAME_H4', 'H4'),
        ('TIMEFRAME_H1', 'H1'),
        ('TIMEFRAME_M30', 'M30'),
        ('TIMEFRAME_M15', 'M15'),
    ]

    FLOOR_TIME_CHOICES = [
        ('1d', '1 Day'),
        ('4h', '4 Hours'),
        ('2h', '2 Hours'),
        ('1h', '1 Hour'),
    ]

    FEATURE_TIMEFRAMES = [
        ('4h', '4 Hours'),
        ('2h', '2 Hours'),
        ('1h', '1 Hour'),
        ('30min', '30 Minutes'),
        ('15min', '15 Minutes'),
    ]



    def form_valid(self, form):
        MT5_TIMEFRAMES = {
            "TIMEFRAME_M1": mt5.TIMEFRAME_M1,
            "TIMEFRAME_M5": mt5.TIMEFRAME_M5,
            "TIMEFRAME_M15": mt5.TIMEFRAME_M15,
            "TIMEFRAME_M30": mt5.TIMEFRAME_M30,
            "TIMEFRAME_H1": mt5.TIMEFRAME_H1,
            "TIMEFRAME_H2": mt5.TIMEFRAME_H2,
            "TIMEFRAME_H4": mt5.TIMEFRAME_H4,
            "TIMEFRAME_D1": mt5.TIMEFRAME_D1,
        }
        params = {
            'symbol': form.cleaned_data['symbol'],
            'd1': MT5_TIMEFRAMES[form.cleaned_data['d1']],
            'd2': MT5_TIMEFRAMES[form.cleaned_data['d2']],
            'd3': MT5_TIMEFRAMES[form.cleaned_data['d3']],
            'floor_time': form.cleaned_data['floor_time'],
            'timeframe1': form.cleaned_data['timeframe1'],
            'timeframe2': form.cleaned_data['timeframe2'],
            'num_bars': form.cleaned_data['num_bars'],
        }

        job_id = uuid.uuid4().hex
        thread = threading.Thread(target=model_runner, args=(job_id, params))
        thread.daemon = True
        thread.start()

        return redirect(f"{reverse('dashboard:logs')}?job_id={job_id}&symbol={params['symbol']}")
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from .forms import SYMBOL_CHOICES, TIMEFRAME_CHOICES, FLOOR_TIME_CHOICES, FEATURE_TIMEFRAMES
        context.update({
            'SYMBOL_CHOICES': SYMBOL_CHOICES,
            'TIMEFRAME_CHOICES': TIMEFRAME_CHOICES,
            'FLOOR_TIME_CHOICES': FLOOR_TIME_CHOICES,
            'FEATURE_TIMEFRAMES': FEATURE_TIMEFRAMES
        })
        return context
        

def get_logs(request):
    job_id = request.GET.get('job_id')
    logs = cache.get(job_id, [])
    return JsonResponse({'logs': logs})

class LogsView(View):
    def get(self, request):
        job_id = request.GET.get('job_id')
        symbol = request.GET.get('symbol', 'N/A')
        return render(request, 'logs.html', {'job_id': job_id, 'symbol': symbol})
    
def get_next_candle_open(now: datetime, timeframe: str) -> datetime:
    # Round 'now' down to the nearest hour
    base_time = now.replace(minute=0, second=0, microsecond=0)
    
    # Timeframe to duration in hours
    timeframe_durations = {
        '1h': 1,
        '2h': 2,
        '4h': 4,
        '1d': 24,
    }

    hours = timeframe_durations.get(timeframe)
    if hours is None:
        raise ValueError(f"Unsupported timeframe: {timeframe}")

    if hours < 24:
        # Find how many hours have passed since last valid candle open
        offset = base_time.hour % hours
        last_candle_open = base_time - timedelta(hours=offset)
        next_candle_open = last_candle_open + timedelta(hours=hours)
    else:
        # For daily candles, next candle is at midnight
        if base_time.hour == 0:
            next_candle_open = base_time + timedelta(days=1)
        else:
            next_candle_open = base_time.replace(hour=0) + timedelta(days=1)

    return next_candle_open

def save_prediction(symbol, value, prob, timeframe_str):
    now = datetime.now()

    predicted_for = get_next_candle_open(now, timeframe_str)

    Prediction.objects.create(
        symbol=symbol,
        timeframe=timeframe_str,
        predicted_at=now,
        predicted_for=predicted_for,
        prediction_value=value,
        probability=prob,
        evaluated=False,  # Mark as not yet evaluated
        result=None       # No result yet
    )

    
from datetime import datetime, timedelta

from django.http import JsonResponse
from django.db import transaction
from .models import Prediction
import MetaTrader5 as mt5
from datetime import timedelta, datetime

from datetime import timedelta
import pytz



def evaluate_predictions(request):
    if not mt5.initialize():
        return JsonResponse({'error': 'Could not connect to MT5'}, status=500)

    try:
        now_utc = datetime.now()

        tf_map = {
            '1h': (mt5.TIMEFRAME_H1, timedelta(hours=1)),
            '2h': (mt5.TIMEFRAME_H2, timedelta(hours=2)),
            '4h': (mt5.TIMEFRAME_H4, timedelta(hours=4)),
            '1d': (mt5.TIMEFRAME_D1, timedelta(days=1)),
        }

        pending_preds = Prediction.objects.filter(evaluated=False).order_by('predicted_for')
        if not pending_preds.exists():
            return JsonResponse({'message': 'No pending predictions to evaluate'})

        results = []
        skipped = []

        with transaction.atomic():
            for pred in pending_preds:
                tf_data = tf_map.get(pred.timeframe)
                if not tf_data:
                    skipped.append({
                        'id': pred.id,
                        'reason': f"Unsupported timeframe: {pred.timeframe}"
                    })
                    continue

                mt5_tf, duration = tf_data

                # predicted_for_utc = pred.predicted_for.astimezone(pytz.UTC)

                candle_close_time = pred.predicted_for.replace(tzinfo=None)

                # Skip if candle not yet closed
                if now_utc < candle_close_time:
                    skipped.append({
                        'id': pred.id,
                        'reason': f"Candle not yet closed (closes at {candle_close_time}, predicted for: {pred.predicted_for})"
                    })
                    continue

                # Fetch candle data at predicted_for time
                rates = mt5.copy_rates_from(pred.symbol, mt5_tf, pred.predicted_for, 1)
                if not rates or len(rates) == 0:
                    results.append({
                        'id': pred.id,
                        'status': 'error',
                        'error': 'No candle data found for time',
                        'symbol': pred.symbol
                    })
                    continue

                rate = rates[0]
                open_price = rate['open']
                close_price = rate['close']
                actual_direction = 'Buy' if close_price > open_price else 'Sell'
                result = 'Win' if actual_direction == pred.prediction_value else 'Loss'

                pred.actual_open = open_price
                pred.actual_close = close_price
                pred.result = result
                pred.evaluated = True
                pred.evaluated_at = now_utc
                pred.save()

                results.append({
                    'id': pred.id,
                    'result': result,
                    'symbol': pred.symbol,
                    'predicted_direction': pred.prediction_value,
                    'actual_direction': actual_direction,
                    'open': open_price,
                    'close': close_price
                })

        return redirect('dashboard:trading_dashboard')

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

    finally:
        mt5.shutdown()


# views.py

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
import os
from pathlib import Path

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# Define path to your note file (make sure this folder is writable)
NOTE_FILE_PATH = os.path.join(BASE_DIR, 'note/note.txt')

@csrf_exempt
def note_api(request):
    if request.method == 'GET':
        try:
            with open(NOTE_FILE_PATH, 'r', encoding='utf-8') as f:
                note = f.read()
        except FileNotFoundError:
            note = ''  # Return empty if no note saved yet
        return JsonResponse({'note': note})

    elif request.method == 'POST':
        note_text = request.POST.get('note', '')
        with open(NOTE_FILE_PATH, 'w', encoding='utf-8') as f:
            f.write(note_text)
        return JsonResponse({'status': 'success'})



class TradingDashboardView(TemplateView):
    template_name = 'trading_dashboard.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        predictions = Prediction.objects.all().order_by('-predicted_for')[:11]
        
        from datetime import datetime

        recent_predictions = []
        for pred in predictions:
            now = datetime.now()  # Naive datetime

            predicted_for_naive = pred.predicted_for.replace(tzinfo=None)

            if predicted_for_naive > now:
                remaining = predicted_for_naive - now

                total_seconds = int(remaining.total_seconds())
                hours, remainder = divmod(total_seconds, 3600)
                minutes, seconds = divmod(remainder, 60)
                pred.time_remaining = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
                pred.expired = False
            else:
                pred.expired = True
                pred.time_remaining = "Expired"

            recent_predictions.append(pred)

        

        performance_data = self.get_performance_metrics()
        
        context['win_loss_chart'] = self.create_win_loss_chart()
        context['timeframe_chart'] = self.create_timeframe_chart()
        context['probability_chart'] = self.create_probability_chart()
        context['recent_predictions'] = recent_predictions
        context['symbol_matrix'] = self.create_symbol_matrix()
        
        context['metrics'] = {
            'win_rate': performance_data['win_rate'],
            'recent_accuracy': performance_data['recent_accuracy'],
            'best_symbol': performance_data['best_symbol'],
            'hot_timeframe': performance_data['hot_timeframe'],
        }
    
        return context
    def get_performance_metrics(self):
        total = Prediction.objects.filter(evaluated=True).count()
        wins = Prediction.objects.filter(evaluated=True, result='Win').count()
        win_rate = (wins / total * 100) if total > 0 else 0

        recent = Prediction.objects.filter(
            evaluated=True,
            predicted_for__gte=timezone.now() - timedelta(days=7)
        )
        recent_wins = recent.filter(result='Win').count()
        recent_accuracy = (recent_wins / recent.count() * 100) if recent.count() > 0 else 0
        
        best_symbol = Prediction.objects.filter(evaluated=True) \
            .values('symbol') \
            .annotate(win_count=Count('result', filter=Q(result='Win'))) \
            .order_by('-win_count') \
            .first()

        hot_timeframe = Prediction.objects.filter(evaluated=True) \
            .values('timeframe') \
            .annotate(win_count=Count('result', filter=Q(result='Win'))) \
            .order_by('-win_count') \
            .first()
        
        return {
            'win_rate': round(win_rate, 1),
            'recent_accuracy': round(recent_accuracy, 1),
            'best_symbol': best_symbol['symbol'] if best_symbol else 'N/A',
            'hot_timeframe': hot_timeframe['timeframe'] if hot_timeframe else 'N/A'
        }

    def create_win_loss_chart(self):
        data = list(Prediction.objects.filter(evaluated=True)
                    .values('result')
                    .annotate(count=Count('result')))
        if not data:
            return None

        df = pd.DataFrame(data)
        fig = px.pie(df, values='count', names='result',
                    title='Win/Loss Distribution',
                    color='result',
                    color_discrete_map={'Win': '#10B981', 'Loss': '#EF4444'})
        
        fig.update_layout(
            template='plotly_dark',
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)',
            font_color='white'
        )
        
        return plot(fig, output_type='div', include_plotlyjs=False)

    def create_timeframe_chart(self):
        data = list(Prediction.objects.filter(evaluated=True)
                    .values('timeframe', 'result')
                    .annotate(count=Count('result')))
        if not data:
            return None

        df = pd.DataFrame(data)
        fig = px.bar(df, x='timeframe', y='count', color='result',
                    title='Performance by Timeframe',
                    barmode='group',
                    color_discrete_map={'Win': '#10B981', 'Loss': '#EF4444'})
        
        fig.update_layout(
            template='plotly_dark',
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)',
            font_color='white'
        )
        
        return plot(fig, output_type='div', include_plotlyjs=False)

    def create_probability_chart(self):
        data = list(Prediction.objects.filter(evaluated=True)
                    .values('probability', 'result'))
        if not data:
            return None

        df = pd.DataFrame(data)
        fig = px.histogram(df, x='probability', color='result',
                        title='Probability Distribution',
                        nbins=20,
                        color_discrete_map={'Win': '#10B981', 'Loss': '#EF4444'})
        
        fig.update_layout(
            template='plotly_dark',
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)',
            font_color='white'
        )
        
        return plot(fig, output_type='div', include_plotlyjs=False)


    def create_symbol_matrix(self):
        symbols = Prediction.objects.values_list('symbol', flat=True).distinct()
        timeframes = Prediction.objects.values_list('timeframe', flat=True).distinct()
        
        matrix = []
        for symbol in symbols:
            row = {'symbol': symbol}
            for tf in timeframes:
                stats = Prediction.objects.filter(
                    symbol=symbol,
                    timeframe=tf,
                    evaluated=True
                ).aggregate(
                    total=Count('id'),
                    wins=Count('id', filter=Q(result='Win'))
                )
                total = stats['total'] or 0
                wins = stats['wins'] or 0
                win_rate = round(wins / total * 100, 1) if total else 0
                row[tf] = {
                    'total': total,
                    'wins': wins,
                    'win_rate': win_rate
                }
            matrix.append(row)
        
        return matrix


from .SmartMoneyZones import create_features_labels
import sys
import numpy as np

class SmartMoneyDashboardView(TemplateView):
    template_name = 'smc_dashboard.html'

    from datetime import datetime

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Load latest market data
        data = self.get_15m_data()
        if data.empty:
            context['error'] = 'Failed to fetch data from MT5.'
            return context

        # Generate features and labels
        features_df, labels = create_features_labels(data)
        if features_df.empty:
            context['error'] = 'No feature data generated.'
            return context

        last = features_df.iloc[-1]

        entries = []
        horizontal_lines = []

        for i in range(len(labels)):
            label_val = labels.iloc[i]
            row = features_df.iloc[i]

            # Get scalar time
            time_val = row['time']
            if isinstance(time_val, (pd.Series, list, np.ndarray)):
                time_val = time_val.iloc[0] if isinstance(time_val, pd.Series) else time_val[0]
            time_val = pd.to_datetime(time_val).to_pydatetime()

            # Get scalar price
            price_val = row['close']
            if isinstance(price_val, (pd.Series, list, np.ndarray)):
                price_val = price_val.iloc[0] if isinstance(price_val, pd.Series) else price_val[0]
            price_val = float(price_val)

            # Save horizontal line if label = 1
            if label_val == 1:
                horizontal_lines.append({'time': time_val, 'price': price_val})

            # Save entry if label ≠ 0
            if label_val != 0:
                entries.append({
                    'time': time_val,
                    'price': price_val,
                    'confluence': float(row['confluence_score']),
                    'bos': bool(row['bos_confirmed']),
                    'trend': row['trend']
                })

        # Filter entries from today only
        today = datetime.utcnow().date()
        daily_entries = entries[int(len(entries)-5):]

        context.update({
            'trend': last['trend'],
            'entry':last['entry'],
            'liquidity_sweep': last['liquidity_sweep'],
            'bos': last['bos_confirmed'],
            'confluence': last['confluence_score'],
            'ob_side': 'Bullish' if last['ob_side'] == 1 else 'Bearish' if last['ob_side'] == -1 else 'None',
            'fvg_side': 'Bullish' if last['fvg_side'] == 1 else 'Bearish' if last['fvg_side'] == -1 else 'None',
            'volume': last['vol_above_ma'],
            'atr_pct': round(float(last['atr_pct']) * 100, 2),
            'session_london': last['session_london'],
            'session_ny': last['session_ny'],
            'entries': daily_entries,
        })

        return context


    def get_15m_data(self):
        timeframe = mt5.TIMEFRAME_M15
        symbol = 'XAUUSDm'
        num_bars = 1200

        if not mt5.initialize():
            print("❌ MT5 initialization failed.")
            sys.exit()
            return pd.DataFrame()

        if not mt5.symbol_select(symbol, True):
            print(f"❌ Symbol '{symbol}' not found or not visible in Market Watch.")
            mt5.shutdown()
            sys.exit()
            return pd.DataFrame()

        candles = mt5.copy_rates_from_pos(symbol, timeframe, 1, num_bars)
        if candles is None:
            print("❌ Failed to retrieve data.")
            mt5.shutdown()
            return pd.DataFrame()

        data = pd.DataFrame(candles)
        data['time'] = pd.to_datetime(data['time'], unit='s')
        data = data.rename(columns={ 'tick_volume': 'volume'})
        data.drop(columns=['real_volume'], inplace=True)
        mt5.shutdown()
        return data

