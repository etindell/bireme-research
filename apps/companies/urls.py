"""
URL configuration for companies app.
"""
from django.urls import path

from . import views

app_name = 'companies'

urlpatterns = [
    # Company list and create
    path('', views.CompanyListView.as_view(), name='list'),
    path('create/', views.CompanyCreateView.as_view(), name='create'),

    # IRR Leaderboard
    path('leaderboard/', views.IRRLeaderboardView.as_view(), name='irr_leaderboard'),
    path('leaderboard/refresh-prices/', views.RefreshAllPricesView.as_view(), name='refresh_all_prices'),

    # Watchlist
    path('watchlist/refresh-prices/', views.RefreshWatchlistPricesView.as_view(), name='refresh_watchlist_prices'),
    path('<slug:slug>/upgrade-to-on-deck/', views.UpgradeToOnDeckView.as_view(), name='upgrade_to_on_deck'),

    # General refresh
    path('refresh-data/', views.RefreshCompanyPricesView.as_view(), name='refresh_company_data'),

    # Company detail routes
    path('<slug:slug>/', views.CompanyDetailView.as_view(), name='detail'),
    path('<slug:slug>/edit/', views.CompanyUpdateView.as_view(), name='update'),
    path('<slug:slug>/delete/', views.CompanyDeleteView.as_view(), name='delete'),
    path('<slug:slug>/status/', views.CompanyStatusUpdateView.as_view(), name='status_update'),
    path('<slug:slug>/generate-summary/', views.GenerateSummaryView.as_view(), name='generate_summary'),
    path('<slug:slug>/key-questions/', views.UpdateKeyQuestionsView.as_view(), name='update_key_questions'),
    path('<slug:slug>/forecast-history/', views.ForecastHistoryAPIView.as_view(), name='forecast_history'),

    # Valuation routes
    path('<slug:slug>/valuation/', views.CompanyValuationCreateView.as_view(), name='valuation_create'),
    path('<slug:slug>/valuation/<int:pk>/', views.CompanyValuationUpdateView.as_view(), name='valuation_update'),
    path('valuation/<int:pk>/refresh-price/', views.RefreshStockPriceView.as_view(), name='refresh_price'),
]
