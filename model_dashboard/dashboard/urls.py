from django.urls import path
from .views import ModelLaunchView,get_logs,LogsView,evaluate_predictions,TradingDashboardView,note_api,SmartMoneyDashboardView

app_name = 'dashboard'

urlpatterns = [
    path('', ModelLaunchView.as_view(), name='dashboard'),
    path('logs/', LogsView.as_view(), name='logs'),
    path('logs/api/', get_logs, name='get_logs'),
    path('evaluate_predictions/', evaluate_predictions, name='evaluate_predictions'),
    path('dashboard/', TradingDashboardView.as_view(), name='trading_dashboard'),
    path('api/note/', note_api, name='note_api'),
    path('smc/', SmartMoneyDashboardView.as_view(), name='smc_dashboard'),

]