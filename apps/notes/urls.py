"""
URL configuration for notes app.
"""
from django.urls import path

from . import views

app_name = 'notes'

urlpatterns = [
    path('', views.NoteListView.as_view(), name='list'),
    path('create/', views.NoteCreateView.as_view(), name='create'),
    path('<int:pk>/', views.NoteDetailView.as_view(), name='detail'),
    path('<int:pk>/edit/', views.NoteUpdateView.as_view(), name='update'),
    path('<int:pk>/delete/', views.NoteDeleteView.as_view(), name='delete'),
    path('<int:pk>/toggle-collapse/', views.NoteToggleCollapseView.as_view(), name='toggle_collapse'),
    path('<int:pk>/toggle-pin/', views.NoteTogglePinView.as_view(), name='toggle_pin'),
]
