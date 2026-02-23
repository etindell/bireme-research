"""
URL configuration for events app.
"""
from django.urls import path
from . import views

app_name = 'events'

urlpatterns = [
    # Event CRUD
    path('', views.EventListView.as_view(), name='list'),
    path('create/', views.EventCreateView.as_view(), name='create'),
    path('<int:pk>/', views.EventDetailView.as_view(), name='detail'),
    path('<int:pk>/edit/', views.EventUpdateView.as_view(), name='update'),
    path('<int:pk>/delete/', views.EventDeleteView.as_view(), name='delete'),

    # Screenshot upload & guest confirmation
    path('<int:pk>/upload-screenshot/', views.UploadScreenshotView.as_view(), name='upload_screenshot'),
    path('<int:pk>/confirm-guests/<int:screenshot_pk>/', views.ConfirmGuestsView.as_view(), name='confirm_guests'),

    # Guest management
    path('<int:pk>/add-guest/', views.AddGuestView.as_view(), name='add_guest'),
    path('<int:pk>/remove-guest/<int:guest_pk>/', views.RemoveGuestView.as_view(), name='remove_guest'),

    # Poll date management
    path('<int:pk>/add-date/', views.AddEventDateView.as_view(), name='add_date'),
    path('<int:pk>/remove-date/<int:date_pk>/', views.RemoveEventDateView.as_view(), name='remove_date'),

    # Email generation & sending
    path('<int:pk>/generate-emails/', views.GenerateEmailsView.as_view(), name='generate_emails'),
    path('<int:pk>/preview-email/<int:guest_pk>/', views.PreviewEmailView.as_view(), name='preview_email'),
    path('<int:pk>/send-emails/', views.SendEmailsView.as_view(), name='send_emails'),

    # RSVP dashboard (authenticated)
    path('<int:pk>/rsvp-dashboard/', views.RsvpDashboardView.as_view(), name='rsvp_dashboard'),

    # Public RSVP (no auth required)
    path('rsvp/<uuid:token>/', views.RsvpPublicView.as_view(), name='rsvp_public'),
]
