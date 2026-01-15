from django.urls import path

from . import views

app_name = 'news'

urlpatterns = [
    path('', views.NewsDashboardView.as_view(), name='dashboard'),
    path('company/<slug:slug>/', views.CompanyNewsView.as_view(), name='company_news'),
    path('<int:pk>/toggle-read/', views.ToggleNewsReadView.as_view(), name='toggle_read'),
    path('<int:pk>/toggle-starred/', views.ToggleNewsStarredView.as_view(), name='toggle_starred'),
    path('refresh/<slug:slug>/', views.RefreshCompanyNewsView.as_view(), name='refresh'),
    path('mark-all-read/', views.MarkAllReadView.as_view(), name='mark_all_read'),
]
