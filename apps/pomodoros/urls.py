"""
URL configuration for pomodoros app.
"""
from django.urls import path
from . import views

app_name = 'pomodoros'

urlpatterns = [
    path('', views.PomodoroPageView.as_view(), name='timer'),
    path('start/', views.PomodoroStartView.as_view(), name='start'),
    path('<int:pk>/complete/', views.PomodoroCompleteView.as_view(), name='complete'),
    path('<int:pk>/focus/', views.PomodoroFocusResponseView.as_view(), name='focus'),
    path('<int:pk>/cancel/', views.PomodoroCancelView.as_view(), name='cancel'),
    path('weekly-data/', views.PomodoroWeeklyDataView.as_view(), name='weekly_data'),
]
