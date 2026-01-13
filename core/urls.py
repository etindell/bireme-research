"""
URL configuration for core views.
"""
from django.urls import path

from . import views

urlpatterns = [
    path('', views.DashboardView.as_view(), name='dashboard'),
    path('api/activity/', views.ActivityDataView.as_view(), name='activity_data'),
    path('api/fix-imported-notes/', views.FixImportedNotesView.as_view(), name='fix_imported_notes'),
]
