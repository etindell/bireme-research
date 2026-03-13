from django.urls import path
from . import views

app_name = 'prospects'

urlpatterns = [
    path('', views.ProspectListView.as_view(), name='list'),
    path('create/', views.ProspectCreateView.as_view(), name='create'),
    path('<int:pk>/', views.ProspectDetailView.as_view(), name='detail'),
    path('<int:pk>/edit/', views.ProspectUpdateView.as_view(), name='edit'),
    path('<int:pk>/note/', views.AddProspectNoteView.as_view(), name='add_note'),
    path('<int:pk>/sync/', views.SyncProspectView.as_view(), name='sync'),
]
