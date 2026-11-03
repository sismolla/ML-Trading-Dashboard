from django.contrib import admin
from .models import Prediction

@admin.register(Prediction)
class PredictionAdmin(admin.ModelAdmin):
    list_display = ('symbol', 'timeframe', 'prediction_value', 'probability', 'predicted_at', 'predicted_for')
    list_filter = ('symbol', 'timeframe')
    search_fields = ('symbol',)
