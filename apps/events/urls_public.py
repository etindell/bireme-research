"""
Public-facing event URLs mounted at the root for clean guest links.
e.g. events.biremecapital.com/<token>/
"""
from django.urls import path
from . import views

urlpatterns = [
    path('', views.RsvpPublicView.as_view(), name='rsvp_public_short'),
]
