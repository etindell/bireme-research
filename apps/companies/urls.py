"""
URL configuration for companies app.
"""
from django.urls import path

from . import views

app_name = 'companies'

urlpatterns = [
    path('', views.CompanyListView.as_view(), name='list'),
    path('create/', views.CompanyCreateView.as_view(), name='create'),
    path('<slug:slug>/', views.CompanyDetailView.as_view(), name='detail'),
    path('<slug:slug>/edit/', views.CompanyUpdateView.as_view(), name='update'),
    path('<slug:slug>/delete/', views.CompanyDeleteView.as_view(), name='delete'),
    path('<slug:slug>/status/', views.CompanyStatusUpdateView.as_view(), name='status_update'),
]
