from django.urls import path
from .views import FXDashboardView

app_name = 'fx_dashboard'

urlpatterns = [

    path('fx_dashboard/', FXDashboardView.as_view(), name='fx-dashboard'),



]    


