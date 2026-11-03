# forms.py
from django import forms

SYMBOL_CHOICES = [
    ('ETHUSDm', 'ETH/USD'),
    ('XAUUSDm', 'Gold/USD'),
    ('USDJPYm', 'USD/JPY'),
    ('USDCHFm', 'USD/CHF'),

    # Add more symbols as needed
]

TIMEFRAME_CHOICES = [
    ('TIMEFRAME_D1', 'D1'),
    ('TIMEFRAME_H4', 'H4'),
    ('TIMEFRAME_H1', 'H1'),
    ('TIMEFRAME_H2', 'H2'),
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

class ModelLaunchForm(forms.Form):
    symbol = forms.ChoiceField(choices=SYMBOL_CHOICES)
    floor_time = forms.ChoiceField(choices=FLOOR_TIME_CHOICES)
    d1 = forms.ChoiceField(choices=TIMEFRAME_CHOICES)
    d2 = forms.ChoiceField(choices=TIMEFRAME_CHOICES)
    d3 = forms.ChoiceField(choices=TIMEFRAME_CHOICES)
    timeframe1 = forms.ChoiceField(choices=FEATURE_TIMEFRAMES)
    timeframe2 = forms.ChoiceField(choices=FEATURE_TIMEFRAMES)
    num_bars = forms.IntegerField(min_value=10000, max_value=200000, initial=100000)
