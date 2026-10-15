# orders/urls.py
from django.urls import path
from . import api_views
from . import views

app_name = "orders"

urlpatterns = [
   path("", views.order_dashboard, name="order_list")
   ,path("analytics/", views.analytics_dashboard, name="analytics_dashboard_html"),


    # Analytics API
    path("api/analytics/dashboard/", api_views.analytics_dashboard, name="analytics_dashboard"),
    path("api/analytics/daily-revenue/", api_views.daily_revenue, name="daily_revenue"),
    path("api/analytics/hourly-today/", api_views.hourly_today, name="hourly_today"),
    path("api/analytics/status-breakdown/", api_views.status_breakdown, name="status_breakdown"),
    path("api/analytics/top-items/", api_views.top_items, name="top_items"),
]