"""
URL configuration for export app.
"""
from django.urls import path

from . import views

app_name = 'export'

urlpatterns = [
    path('company/<slug:slug>.pdf', views.CompanyPDFView.as_view(), name='company_pdf'),
]
