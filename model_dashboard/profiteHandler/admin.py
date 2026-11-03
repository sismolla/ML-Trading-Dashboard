from django.contrib import admin
from .models import Prediction_values

@admin.register(Prediction_values)
class Prediction_valueAdmin(admin.ModelAdmin):
    list_display = (
        'index','predicted','predicted_prob'
    )
    list_filter = ('index','predicted','predicted_prob')
# Register your models here.
