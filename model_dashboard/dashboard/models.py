from django.db import models

TIMEFRAME_CHOICES = [
    ('1h', '1 Hour'),
    ('2h', '2 Hour'),
    ('4h', '4 Hours'),
    ('1d', '1 Day'),
]

class Prediction(models.Model):
    symbol = models.CharField(max_length=20)
    timeframe = models.CharField(max_length=10, choices=TIMEFRAME_CHOICES)
    predicted_at = models.DateTimeField()
    predicted_for = models.DateTimeField()
    prediction_value = models.CharField(max_length=10)  # e.g. 'Buy' or 'Sell'
    probability = models.FloatField()
    
    # Actual candle data (to be filled later)
    actual_open = models.FloatField(null=True, blank=True)
    actual_close = models.FloatField(null=True, blank=True)
    
    evaluated = models.BooleanField(default=False)
    result = models.CharField(max_length=10, null=True, blank=True)  # 'Win' or 'Loss'
    
    def __str__(self):
        return f"{self.symbol} {self.timeframe} @ {self.predicted_for}"
