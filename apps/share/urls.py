"""
URL configuration for share app.
Public views that don't require authentication.
"""
from django.urls import path

from . import views

app_name = 'share'

urlpatterns = [
    path('<str:token>/', views.SharedNoteView.as_view(), name='view'),
    path('<str:token>/comment/', views.SharedNoteCommentView.as_view(), name='comment'),
]
