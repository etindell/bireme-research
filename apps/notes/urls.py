"""
URL configuration for notes app.
"""
from django.urls import path

from . import views

app_name = 'notes'

urlpatterns = [
    path('', views.NoteListView.as_view(), name='list'),
    path('create/', views.NoteCreateView.as_view(), name='create'),
    path('import/', views.NoteImportView.as_view(), name='import'),
    path('upload-image/', views.NoteImageUploadView.as_view(), name='upload_image'),
    path('bulk-delete/', views.NoteBulkDeleteView.as_view(), name='bulk_delete'),
    path('<int:pk>/', views.NoteDetailView.as_view(), name='detail'),
    path('<int:pk>/edit/', views.NoteUpdateView.as_view(), name='update'),
    path('<int:pk>/delete/', views.NoteDeleteView.as_view(), name='delete'),
    path('<int:pk>/toggle-collapse/', views.NoteToggleCollapseView.as_view(), name='toggle_collapse'),
    path('<int:pk>/toggle-pin/', views.NoteTogglePinView.as_view(), name='toggle_pin'),
    path('<int:pk>/create-todo/', views.NoteCreateTodoView.as_view(), name='create_todo'),
    # Share management
    path('<int:pk>/share/', views.NoteShareCreateView.as_view(), name='share_create'),
    path('<int:pk>/share/<int:share_pk>/toggle/', views.NoteShareToggleView.as_view(), name='share_toggle'),
    path('<int:pk>/share/<int:share_pk>/delete/', views.NoteShareDeleteView.as_view(), name='share_delete'),
    path('<int:pk>/share-panel/', views.NoteSharePanelView.as_view(), name='share_panel'),
]
