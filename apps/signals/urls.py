"""
URL configuration for the Signals app.
"""
from django.urls import path
from apps.signals import views

app_name = 'signals'

urlpatterns = [
    path('', views.SignalIndexView.as_view(), name='index'),
    path('<slug:company_slug>/', views.CompanySignalDetailView.as_view(), name='company_detail'),
    path('<slug:company_slug>/sync/', views.SyncSignalView.as_view(), name='sync'),
    path('<slug:company_slug>/card/', views.CompanySignalCardView.as_view(), name='company_card'),
    path('observation/<int:pk>/exclude/', views.ExcludeObservationView.as_view(), name='exclude'),
    path('observation/<int:pk>/include/', views.IncludeObservationView.as_view(), name='include'),
]
