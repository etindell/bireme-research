"""
URL configuration for todos app.
"""
from django.urls import path

from . import views

app_name = 'todos'

urlpatterns = [
    # Main todo list
    path('', views.TodoListView.as_view(), name='list'),

    # CRUD operations
    path('create/', views.TodoCreateView.as_view(), name='create'),
    path('<int:pk>/', views.TodoDetailView.as_view(), name='detail'),
    path('<int:pk>/edit/', views.TodoUpdateView.as_view(), name='update'),
    path('<int:pk>/delete/', views.TodoDeleteView.as_view(), name='delete'),

    # Toggle completion (HTMX)
    path('<int:pk>/toggle/', views.TodoToggleCompleteView.as_view(), name='toggle_complete'),

    # Complete with note
    path('<int:pk>/complete-with-note/', views.CompleteWithNoteView.as_view(), name='complete_with_note'),

    # Quick todo from company page (HTMX)
    path('quick/<slug:company_slug>/', views.QuickTodoCreateView.as_view(), name='quick_create'),

    # Company todos partial (HTMX)
    path('company/<slug:company_slug>/', views.CompanyTodosPartialView.as_view(), name='company_todos'),

    # Investor letter special views
    path('investor-letter/<int:pk>/', views.InvestorLetterTodoUpdateView.as_view(), name='investor_letter'),

    # Process watchlist quick-add
    path('quick-add/<int:pk>/process/', views.ProcessWatchlistQuickAddView.as_view(), name='process_quick_add'),
]
