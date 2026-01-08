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

    # Company detail routes
    path('<slug:slug>/', views.CompanyDetailView.as_view(), name='detail'),
    path('<slug:slug>/edit/', views.CompanyUpdateView.as_view(), name='update'),
    path('<slug:slug>/delete/', views.CompanyDeleteView.as_view(), name='delete'),
    path('<slug:slug>/status/', views.CompanyStatusUpdateView.as_view(), name='status_update'),

    # Valuation routes
    path('<slug:slug>/valuation/', views.CompanyValuationCreateView.as_view(), name='valuation_create'),
    path('<slug:slug>/valuation/<int:pk>/', views.CompanyValuationUpdateView.as_view(), name='valuation_update'),
    path('valuation/<int:pk>/refresh-price/', views.RefreshStockPriceView.as_view(), name='refresh_price'),
]
