"""
URL configuration for search app.
"""
from django.urls import path

from . import views

app_name = 'search'

urlpatterns = [
    path('', views.GlobalSearchView.as_view(), name='global'),
]
